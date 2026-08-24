from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from groq import Groq
import yaml

from src.common.env_loader import load_project_env

from .structured_routing import (
    compact_registry_for_prompt,
    fallback_to_rag,
    load_lookup_registry,
    normalize_router_decision,
    registry_digest,
    router_json_schema,
    router_response_schema,
    validate_router_decision,
)
from .query_plan import (
    legacy_rag_plan,
    normalize_query_plan,
    query_plan_json_schema,
    query_plan_response_schema,
)


DEFAULT_ROUTER_MODEL = "qwen/qwen3.6-27b"
ROUTER_PROMPT_VERSION = "structured-regulation-v26-query-plan-contract"
_DURATION_TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|[hms])", re.IGNORECASE)
_RETRY_TEXT_RE = re.compile(
    r"(?:try again in|retry after)\s+"
    r"((?:\d+(?:\.\d+)?\s*(?:ms|[hms])\s*)+)",
    re.IGNORECASE,
)

ROUTER_SYSTEM_PROMPT = """
Bạn là AI Router của hệ thống Sổ tay Sinh viên HCMUE.
Chỉ phân loại và trích xuất dữ liệu; không trả lời câu hỏi. Chỉ xuất một JSON
đúng OUTPUT CONTRACT, không Markdown hay giải thích.

NGỮ CẢNH VÀ CHUẨN HÓA
- standalone: QUERY tự đủ nghĩa; không lấy thông tin từ CHAT HISTORY.
- follow_up: QUERY thật sự nối tiếp lịch sử (context_confidence=high hoặc medium);
  standalone_query chỉ ghép thông tin có trong QUERY và referenced_turns.
- ambiguous: không xác định chắc ngữ cảnh; route=clarify và hỏi lại ngắn gọn.
- normalized_query chỉ sửa dấu, lỗi chính tả nhẹ hoặc viết tắt phổ biến.
  Không đổi cohort, số liệu, phủ định, thực thể hay chủ đề.
- Không thay một từ đã hợp lệ bằng từ gần âm hoặc khái niệm khác. Nếu không chắc,
  giữ nguyên từ người dùng đã viết.
- Nếu có sửa, corrections phải chứa original_span nguyên văn và normalized_span.

PHÂN LUỒNG
- structured/structured: tra trực tiếp bảng hoặc catalog JSON trong TOOLS.
- rag/regulation: cần đọc Điều/khoản về quy định, điều kiện, thủ tục, ngoại lệ,
  hậu quả, quyền, nghĩa vụ hoặc trường hợp áp dụng.
- rag/mixed: câu hỏi phức hợp cần tra cứu một nguồn structured chính trong TOOLS và đồng thời cần đối chiếu quy định/điều kiện.
- clarify: thiếu entity/cohort cốt lõi khiến tra cứu không xác định được.
  Không clarify câu hỏi quy chế chung chỉ vì thiếu tên môn hoặc ngành.
- out_of_domain: ngoài phạm vi sổ tay sinh viên HCMUE.

RÀNG BUỘC
- Chỉ dùng lookup_type và intent khai báo trong TOOLS.
- structured dùng đúng một tool; regulation có lookup_type=null,
  intent=regulation; mixed chọn đúng một tool chính.
- Giá trị, danh sách và thông tin catalog dùng structured. Điều kiện áp dụng,
  ngoại lệ hoặc hệ quả dùng regulation; cần cả hai thì dùng mixed.
- Khi câu hỏi chứa từ 2 ý định trở lên (chứa cả ý tra cứu bảng dữ liệu trong TOOLS và ý quy định/điều kiện), hãy chọn route=rag, execution_mode=mixed và đặt lookup_type là tool tương ứng với bảng dữ liệu đó.
- Hỏi đích danh đơn vị dùng office/faculty; mô tả dịch vụ cần làm dùng
  student_service; ngành, chương trình, đầu ra nghề nghiệp dùng program.
- Không có form/procedure tool. Hồ sơ, biểu mẫu và quy trình là regulation.
- formula chỉ tra công thức, không tính toán.
- Giữ cohort nếu có; không tự đoán cohort hoặc entity.
- cohort và cohorts: Nếu QUERY chỉ nêu 1 khóa duy nhất, đặt cohort và cohorts=[cohort], is_multi_cohort=false. Nếu QUERY đề cập hoặc so sánh từ 2 khóa trở lên, hãy trích xuất tất cả các khóa vào mảng cohorts, đặt is_multi_cohort=true và cohort là khóa đầu tiên.
- slots tuân thủ TOOLS. slot_spans phải xuất hiện nguyên văn trong QUERY hoặc
  CHAT HISTORY. Không bịa slot để thỏa contract.
- Không tự tạo dữ liệu, tool, intent hoặc chủ đề mới.

Tự kiểm tra route/mode, tool/intent, slot/span và cohort trước khi xuất JSON.
"""

PLANNER_SYSTEM_PROMPT = """
Bạn là Query Planner của hệ thống Sổ tay Sinh viên HCMUE. Không trả lời câu hỏi.
Chỉ xuất đúng một JSON theo OUTPUT CONTRACT, không Markdown hay giải thích.

1. NGỮ CẢNH
- standalone: QUERY tự đủ nghĩa; không lấy dữ liệu từ CHAT HISTORY.
- follow_up: QUERY cần lịch sử; standalone_query chỉ ghép dữ liệu có thật trong
  QUERY và referenced_turns đã dùng.
- Chỉ đặt context_mode=ambiguous khi toàn bộ QUERY không thể được lập kế hoạch
  chắc chắn. Nếu chỉ một yêu cầu mơ hồ, giữ context phù hợp và tạo clarify cho
  riêng task đó.
- normalized_query chỉ sửa dấu, chính tả nhẹ hoặc viết tắt phổ biến; không đổi
  entity, cohort, số liệu, phủ định, chủ đề hoặc ý định.

2. LOGICAL TASKS
- Một task là một yêu cầu thực thi độc lập bằng một mode/tool/intent. Chỉ gộp
  nhiều entity của cùng một phép tra structured với cùng lookup_type và intent.
- Với RAG, mỗi mệnh đề hỏi có answer target riêng là một task, dù cùng domain
  hoặc nguồn; không ghép chúng thành một retrieval query tổng hợp.
- TASK IDENTITY không phụ thuộc cohort: M yêu cầu áp dụng N cohort tạo M logical
  tasks, không tạo M×N tasks. Mỗi task giữ toàn bộ phạm vi trong `cohorts`.
- Plan có 1-3 tasks. Nếu có hơn 3 yêu cầu độc lập, tạo đúng một clarify task yêu
  cầu chọn tối đa 3; không bỏ hoặc nhét chung yêu cầu.

3. COHORT
- Ưu tiên cohort trong QUERY của task, rồi referenced history. COHORT từ UI chỉ
  điền cho task vẫn chưa có cohort; không ghi đè và không nhân bản task theo cohort.

4. MODE
- structured: tra giá trị trực tiếp từ đúng một bảng trong TOOLS. Entity/value
  slots phải được grounding trong QUERY/HISTORY. Control slots như operation,
  requested_field, scope, formula_type được phép chuẩn hóa từ yêu cầu rõ ràng;
  không được tạo entity, giá trị hay yêu cầu mới.
- rag: cần đọc quy định, thủ tục, điều kiện, ngoại lệ, hậu quả hoặc một chuẩn/
  chính sách áp dụng nói chung. Không chọn structured chỉ vì trùng từ chủ đề.
- clarify: yêu cầu tra giá trị trực tiếp thiếu required slot làm đổi kết quả,
  hoặc tham chiếu thật sự mơ hồ. Không clarify chính sách chung để đủ slot cho
  tool. Chỉ clarify task bị thiếu thông tin.
- Mọi RAG task dùng intent=open_question và lookup_type=null. Clarify task cũng
  có lookup_type=null. Nếu toàn bộ QUERY ngoài sổ tay, đặt out_of_domain=true.

5. TỰ KIỂM TRA
- Giữ mọi task độc lập còn lại khi một task cần clarify, thiếu slot hoặc ngữ cảnh.
- task.question tự đủ nghĩa; không thêm entity, số liệu, phủ định, cohort, chủ đề.
- slot_spans là chuỗi nguyên văn hoặc danh sách chuỗi; không xuất `{start,end}`.
- Chỉ dùng lookup_type, intent, slots và required slots khai báo trong TOOLS.

- TOOLS và OUTPUT CONTRACT là contract bắt buộc.
- CATALOG_HINT là metadata đã được grounding; chỉ dùng lookup_type/entity_text
  cho task liên quan; không dùng hint để tạo yêu cầu, intent hay slot mới.
"""


def _parse_duration_seconds(value: str | None) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass

    total = 0.0
    matched = False
    for amount_text, unit in _DURATION_TOKEN_RE.findall(text):
        matched = True
        amount = float(amount_text)
        normalized_unit = unit.lower()
        if normalized_unit == "h":
            total += amount * 3600.0
        elif normalized_unit == "m":
            total += amount * 60.0
        elif normalized_unit == "ms":
            total += amount / 1000.0
        else:
            total += amount
    return total if matched else None


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    for header_name in (
        "retry-after",
        "x-ratelimit-reset-tokens",
        "x-ratelimit-reset-requests",
    ):
        header_value = headers.get(header_name)
        if header_value is None:
            header_value = headers.get(header_name.title())
        parsed = _parse_duration_seconds(header_value)
        if parsed is not None:
            return parsed
        if header_name == "retry-after" and header_value:
            try:
                retry_at = parsedate_to_datetime(str(header_value))
                return max(
                    0.0,
                    retry_at.timestamp() - datetime.now().astimezone().timestamp(),
                )
            except (TypeError, ValueError, OverflowError):
                pass

    match = _RETRY_TEXT_RE.search(str(exc))
    return _parse_duration_seconds(match.group(1)) if match else None


def _next_local_midnight_timestamp() -> float:
    local_now = datetime.now().astimezone()
    return (
        (local_now + timedelta(days=1))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
    )


@dataclass(frozen=True)
class GroqRouterPoolConfig:
    rpm_limit_per_key: int = 30
    rpd_limit_per_key: int = 1000
    tpm_limit_per_key: int = 8000
    tpd_limit_per_key: int = 200000
    cooldown_seconds: float = 65.0
    state_path: str = "data/cache/qwen_router_key_state.json"
    wait_when_limited: bool = False

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "GroqRouterPoolConfig":
        config = config or {}
        return cls(
            rpm_limit_per_key=max(1, int(config.get("rpm_limit_per_key", 30))),
            rpd_limit_per_key=max(1, int(config.get("rpd_limit_per_key", 1000))),
            tpm_limit_per_key=max(1, int(config.get("tpm_limit_per_key", 8000))),
            tpd_limit_per_key=max(1, int(config.get("tpd_limit_per_key", 200000))),
            cooldown_seconds=max(1.0, float(config.get("cooldown_seconds", 65.0))),
            state_path=str(
                config.get("state_path", "data/cache/qwen_router_key_state.json")
            ),
            wait_when_limited=bool(config.get("wait_when_limited", False)),
        )


class GroqRouterKeyPool:
    """Quota-aware LRU key pool that tracks requests and reserved tokens."""

    def __init__(
        self,
        keys: list[str],
        *,
        model_name: str,
        config: GroqRouterPoolConfig | dict[str, Any] | None = None,
    ) -> None:
        self.keys = [key for key in keys if key]
        if not self.keys:
            raise RuntimeError("No Groq router API keys available.")
        self.model_name = model_name
        self.config = (
            config
            if isinstance(config, GroqRouterPoolConfig)
            else GroqRouterPoolConfig.from_config(config)
        )
        self._lock = threading.Lock()
        self._state_path = Path(self.config.state_path)
        self._state: dict[str, Any] = {"keys": {}}
        self._load_state()
        for key in self.keys:
            self._key_state(self.fingerprint(key))
        self._save_state()

    @staticmethod
    def fingerprint(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def acquire_key(self, estimated_tokens: int) -> tuple[str, str, int]:
        estimated_tokens = max(1, int(estimated_tokens))
        while True:
            with self._lock:
                now = time.time()
                today = date.today().isoformat()
                self._reset_daily(today)
                self._prune_windows(now)

                candidates: list[tuple[int, int, float, int, str]] = []
                wait_until: list[float] = []
                daily_available = False
                daily_reasons: set[str] = set()
                state_changed = False
                for index, key in enumerate(self.keys):
                    key_id = self.fingerprint(key)
                    state = self._key_state(key_id)
                    requests_today = int(state.get("requests_today", 0))
                    tokens_today = int(state.get("tokens_today", 0))
                    if requests_today >= self.config.rpd_limit_per_key:
                        daily_reasons.add("daily_request_quota")
                        state_changed |= self._mark_unavailable(
                            state,
                            reason="daily_request_quota",
                            available_at=_next_local_midnight_timestamp(),
                        )
                        continue
                    if (
                        tokens_today + estimated_tokens
                        > self.config.tpd_limit_per_key
                    ):
                        daily_reasons.add("daily_token_quota")
                        state_changed |= self._mark_unavailable(
                            state,
                            reason="daily_token_quota",
                            available_at=_next_local_midnight_timestamp(),
                        )
                        continue
                    daily_available = True

                    cooldown_until = float(state.get("cooldown_until", 0.0))
                    if cooldown_until > now:
                        wait_until.append(cooldown_until)
                        state_changed |= self._mark_unavailable(
                            state,
                            reason=str(
                                state.get("unavailable_reason") or "api_rate_limit"
                            ),
                            available_at=cooldown_until,
                        )
                        continue

                    events = list(state.get("minute_events", []))
                    minute_tokens = sum(int(event.get("tokens", 0)) for event in events)
                    if len(events) >= self.config.rpm_limit_per_key:
                        available_at = float(events[0]["at"]) + 60.0
                        wait_until.append(available_at)
                        state_changed |= self._mark_unavailable(
                            state,
                            reason="rpm_limit",
                            available_at=available_at,
                        )
                        continue
                    if minute_tokens + estimated_tokens > self.config.tpm_limit_per_key:
                        available_at = (
                            float(events[0]["at"]) + 60.0 if events else now + 1.0
                        )
                        wait_until.append(available_at)
                        state_changed |= self._mark_unavailable(
                            state,
                            reason="tpm_limit",
                            available_at=available_at,
                        )
                        continue

                    candidates.append(
                        (
                            len(events),
                            minute_tokens,
                            float(state.get("last_used_at", 0.0)),
                            index,
                            key_id,
                        )
                    )

                if candidates:
                    _, _, _, index, key_id = min(candidates)
                    self._record_attempt(key_id, now, today, estimated_tokens)
                    return self.keys[index], key_id, index

                if not daily_available:
                    available_at = _next_local_midnight_timestamp()
                    if state_changed:
                        self._save_state()
                    reason = (
                        next(iter(daily_reasons))
                        if len(daily_reasons) == 1
                        else "daily_quota"
                    )
                    wait_seconds = max(0.0, available_at - now)
                    raise RuntimeError(
                        f"all_ai_router_keys_{reason}_exhausted_"
                        f"retry_after_{wait_seconds:.1f}s"
                    )

                next_time = min(wait_until) if wait_until else now + 1.0
                wait_seconds = max(0.1, min(60.0, next_time - now))
                if state_changed:
                    self._save_state()

            if not self.config.wait_when_limited:
                raise RuntimeError(
                    f"all_ai_router_keys_temporarily_limited_retry_after_{wait_seconds:.1f}s"
                )
            time.sleep(wait_seconds)

    def record_success(
        self, key_id: str, *, actual_tokens: int, reserved_tokens: int
    ) -> None:
        with self._lock:
            state = self._key_state(key_id)
            extra = max(0, int(actual_tokens) - int(reserved_tokens))
            if extra:
                state["tokens_today"] = int(state.get("tokens_today", 0)) + extra
                events = state.get("minute_events") or []
                if events:
                    events[-1]["tokens"] = int(events[-1].get("tokens", 0)) + extra
            state["failure_count"] = 0
            state["last_error_type"] = None
            self._save_state()

    def record_failure(self, key_id: str, error_type: str) -> None:
        with self._lock:
            state = self._key_state(key_id)
            state["failure_count"] = int(state.get("failure_count", 0)) + 1
            state["last_error_type"] = error_type
            self._save_state()

    def record_rate_limit(
        self,
        key_id: str,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        with self._lock:
            state = self._key_state(key_id)
            retry_seconds = (
                max(0.1, float(retry_after_seconds))
                if retry_after_seconds is not None
                else self.config.cooldown_seconds
            )
            available_at = time.time() + retry_seconds
            state["cooldown_until"] = available_at
            self._mark_unavailable(
                state,
                reason="api_rate_limit",
                available_at=available_at,
            )
            state["failure_count"] = int(state.get("failure_count", 0)) + 1
            state["last_error_type"] = "rate_limit"
            self._save_state()

    def _state_key(self, key_id: str) -> str:
        return f"{self.model_name}:{key_id}"

    def _key_state(self, key_id: str) -> dict[str, Any]:
        states = self._state.setdefault("keys", {})
        state_key = self._state_key(key_id)
        if state_key not in states:
            states[state_key] = {
                "minute_events": [],
                "requests_today": 0,
                "tokens_today": 0,
                "daily_reset_date": date.today().isoformat(),
                "cooldown_until": 0.0,
                "last_used_at": 0.0,
                "failure_count": 0,
                "last_error_type": None,
                "unavailable_reason": None,
                "available_at": 0.0,
            }
        return states[state_key]

    @staticmethod
    def _mark_unavailable(
        state: dict[str, Any],
        *,
        reason: str,
        available_at: float,
    ) -> bool:
        changed = (
            state.get("unavailable_reason") != reason
            or float(state.get("available_at", 0.0)) != float(available_at)
        )
        state["unavailable_reason"] = reason
        state["available_at"] = float(available_at)
        return changed

    def _record_attempt(
        self, key_id: str, now: float, today: str, estimated_tokens: int
    ) -> None:
        state = self._key_state(key_id)
        state["minute_events"].append({"at": now, "tokens": estimated_tokens})
        state["requests_today"] = int(state.get("requests_today", 0)) + 1
        state["tokens_today"] = int(state.get("tokens_today", 0)) + estimated_tokens
        state["daily_reset_date"] = today
        state["last_used_at"] = now
        state["unavailable_reason"] = None
        state["available_at"] = 0.0
        self._save_state()

    def _reset_daily(self, today: str) -> None:
        for state in self._state.get("keys", {}).values():
            if state.get("daily_reset_date") != today:
                state["daily_reset_date"] = today
                state["requests_today"] = 0
                state["tokens_today"] = 0
                if str(state.get("unavailable_reason") or "").startswith("daily_"):
                    state["unavailable_reason"] = None
                    state["available_at"] = 0.0

    def _prune_windows(self, now: float) -> None:
        for state in self._state.get("keys", {}).values():
            state["minute_events"] = [
                event
                for event in state.get("minute_events", [])
                if now - float(event.get("at", 0.0)) < 60.0
            ]
            if (
                state.get("unavailable_reason") in {"rpm_limit", "tpm_limit"}
                and float(state.get("available_at", 0.0)) <= now
            ):
                state["unavailable_reason"] = None
                state["available_at"] = 0.0

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            value = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(value, dict) and isinstance(value.get("keys"), dict):
            self._state = {"keys": value["keys"]}

    def _save_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps(self._state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return


class RouterDecisionCache:
    def __init__(self, path: str, max_entries: int = 2000) -> None:
        self.path = Path(path)
        self.max_entries = max(1, int(max_entries))
        self._lock = threading.Lock()
        self._items: dict[str, Any] = {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                self._items = value
        except (OSError, json.JSONDecodeError):
            pass

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._items.get(key)
            return dict(value) if isinstance(value, dict) else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._items[key] = dict(value)
            if len(self._items) > self.max_entries:
                oldest = next(iter(self._items))
                self._items.pop(oldest, None)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(
                    json.dumps(self._items, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError:
                return


class AIRouter:
    """Groq-backed query-understanding router with a strict JSON contract."""

    def __init__(
        self,
        model_name: str = DEFAULT_ROUTER_MODEL,
        temperature: float = 0.0,
        max_output_tokens: int = 256,
        request_timeout_seconds: float = 5.0,
        max_retries: int = 1,
        reasoning_effort: str = "auto",
        response_format: str = "auto",
        key_pool_config: GroqRouterPoolConfig | dict[str, Any] | None = None,
        cache_path: str = "data/cache/qwen_router_cache.json",
        cache_enabled: bool = True,
    ) -> None:
        load_project_env()
        keys_value = (
            os.environ.get("GROQ_ROUTER_API_KEYS")
            or os.environ.get("GROQ_API_KEYS")
            or ""
        )
        self.available_keys = [
            key.strip() for key in keys_value.split(",") if key.strip()
        ]
        if not self.available_keys:
            raise RuntimeError(
                "Missing GROQ_ROUTER_API_KEYS or GROQ_API_KEYS."
            )
        self.model_name = model_name
        self.temperature = float(temperature)
        self.max_output_tokens = max(64, int(max_output_tokens))
        self.request_timeout_seconds = max(1.0, float(request_timeout_seconds))
        self.max_retries = max(0, int(max_retries))
        self.reasoning_effort = str(reasoning_effort or "auto").strip().lower()
        self.response_format = str(response_format or "auto").strip().lower()
        self.registry = load_lookup_registry()
        self.key_pool = GroqRouterKeyPool(
            self.available_keys,
            model_name=self.model_name,
            config=key_pool_config,
        )
        self.cache = RouterDecisionCache(cache_path) if cache_enabled else None

    @classmethod
    def from_config(cls, path: str | Path = "configs/ai_router.yaml") -> "AIRouter":
        try:
            config = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        except OSError:
            config = {}
        cache_disabled = str(
            os.environ.get("STUDENT_RAG_DISABLE_ROUTER_CACHE") or ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        key_pool_config = dict(config.get("key_pool") or {})
        wait_override = os.environ.get("STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED")
        if wait_override is not None:
            key_pool_config["wait_when_limited"] = wait_override.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        model_name = str(
            os.environ.get("STUDENT_RAG_ROUTER_MODEL")
            or config.get("model_name")
            or DEFAULT_ROUTER_MODEL
        )
        max_output_tokens = int(
            os.environ.get("STUDENT_RAG_ROUTER_MAX_OUTPUT_TOKENS")
            or config.get("max_output_tokens")
            or 256
        )
        return cls(
            model_name=model_name,
            temperature=float(config.get("temperature", 0.0)),
            max_output_tokens=max_output_tokens,
            request_timeout_seconds=float(config.get("request_timeout_seconds", 5.0)),
            max_retries=int(config.get("max_retries", 1)),
            reasoning_effort=str(
                os.environ.get("STUDENT_RAG_ROUTER_REASONING_EFFORT")
                or config.get("reasoning_effort")
                or "auto"
            ),
            response_format=str(
                os.environ.get("STUDENT_RAG_ROUTER_RESPONSE_FORMAT")
                or config.get("response_format")
                or "auto"
            ),
            key_pool_config=key_pool_config,
            cache_path=str(
                config.get("cache_path", "data/cache/qwen_router_cache.json")
            ),
            cache_enabled=bool(config.get("cache_enabled", True))
            and not cache_disabled,
        )

    def plan(
        self,
        query: str,
        *,
        cohort: str | None = None,
        chat_history: list[dict[str, str]] | None = None,
        routing_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a bounded, validated QueryPlan for one user message."""
        dynamic_prompt = self._build_plan_prompt(
            query,
            cohort=cohort,
            chat_history=chat_history,
            routing_hint=routing_hint,
        )
        response_format = self._plan_response_format_payload()
        prompt_stats = self._prompt_stats_for_system(
            PLANNER_SYSTEM_PROMPT, dynamic_prompt, response_format
        )
        cache_key = "plan:" + self._cache_key(
            query,
            cohort=cohort,
            chat_history=chat_history,
            routing_hint=routing_hint,
        )
        if self.cache and (cached := self.cache.get(cache_key)):
            return {
                **cached,
                "model_used": self.model_name,
                "usage": None,
                "router_cache_hit": True,
                "prompt_stats": prompt_stats,
            }

        max_output_tokens = max(
            self.max_output_tokens,
            int(os.environ.get("STUDENT_RAG_PLANNER_MAX_OUTPUT_TOKENS", "768")),
        )
        estimated_tokens = max(
            128,
            int(prompt_stats["estimated_input_tokens"]) + max_output_tokens,
        )
        attempts = 0
        transient_failures = 0
        max_attempts = len(self.available_keys)
        last_error: Exception | None = None
        while attempts < max_attempts:
            key, key_id, key_index = self.key_pool.acquire_key(estimated_tokens)
            attempts += 1
            try:
                client = Groq(
                    api_key=key,
                    timeout=self.request_timeout_seconds,
                    max_retries=0,
                )
                response = client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": PLANNER_SYSTEM_PROMPT.strip()},
                        {"role": "user", "content": dynamic_prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=max_output_tokens,
                    reasoning_effort=self._resolved_reasoning_effort(),
                    response_format=response_format,
                )
                raw = response.choices[0].message.content or ""
                parsed = self._extract_json_object(raw)
                usage = self._usage(response)
                actual_tokens = int(usage.get("total", estimated_tokens))
                self.key_pool.record_success(
                    key_id,
                    actual_tokens=actual_tokens,
                    reserved_tokens=estimated_tokens,
                )
                grounding_context = "\n".join(
                    str(item.get("content") or "")
                    for item in (chat_history or [])[-4:]
                    if isinstance(item, dict)
                )
                plan, validation_errors = normalize_query_plan(
                    parsed,
                    query=query,
                    selected_cohort=cohort,
                    grounding_context=grounding_context,
                    registry=self.registry,
                )
                fatal_validation = any(
                    any(
                        marker in error
                        for marker in (
                            "invalid_object",
                            "invalid_mode",
                            "rag_must_not_select_lookup",
                            "unknown_lookup_type",
                        )
                    )
                    for error in validation_errors
                ) or any(
                    task.get("mode") == "structured" and task.get("validation_errors")
                    for task in (plan.get("tasks") or [])
                )
                if fatal_validation:
                    plan = legacy_rag_plan(query, cohort, reason="legacy_rag")
                    plan["planner_validation_errors"] = validation_errors
                if self.cache:
                    self.cache.set(cache_key, plan)
                return {
                    **plan,
                    "model_used": self.model_name,
                    "usage": usage,
                    "key_fingerprint": key_id,
                    "router_cache_hit": False,
                    "attempts": attempts,
                    "prompt_stats": prompt_stats,
                }
            except Exception as exc:
                last_error = exc
                error_type = self._classify_error(exc)
                if error_type == "rate_limit":
                    self.key_pool.record_rate_limit(
                        key_id,
                        retry_after_seconds=_retry_after_seconds(exc),
                    )
                    continue
                self.key_pool.record_failure(key_id, error_type)
                if error_type not in {"timeout", "api_error", "transient_error"}:
                    break
                transient_failures += 1
                if transient_failures > self.max_retries:
                    break
                print(
                    f"[AIRouter] Retrying planner {self.model_name} after {error_type} "
                    f"on key {key_index}:{key_id}."
                )

        if last_error is not None:
            fallback = legacy_rag_plan(query, cohort, reason="legacy_rag")
            return {
                **fallback,
                "model_used": self.model_name,
                "usage": None,
                "key_fingerprint": None,
                "router_cache_hit": False,
                "attempts": attempts,
                "prompt_stats": prompt_stats,
                "planner_error_type": self._classify_error(last_error),
                "planner_error": str(last_error),
            }
        raise RuntimeError("ai_planner_failed: no_attempts")

    def route(
        self,
        query: str,
        *,
        cohort: str | None = None,
        chat_history: list[dict[str, str]] | None = None,
        routing_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dynamic_prompt = self._build_prompt(
            query,
            cohort=cohort,
            chat_history=chat_history,
            routing_hint=routing_hint,
        )
        response_format = self._response_format_payload()
        prompt_stats = self._prompt_stats(dynamic_prompt, response_format)
        cache_key = self._cache_key(
            query,
            cohort=cohort,
            chat_history=chat_history,
            routing_hint=routing_hint,
        )
        if self.cache and (cached := self.cache.get(cache_key)):
            return {
                **cached,
                "model_used": self.model_name,
                "usage": None,
                "router_cache_hit": True,
                "prompt_stats": prompt_stats,
            }

        estimated_tokens = max(
            128,
            int(prompt_stats["estimated_input_tokens"]) + self.max_output_tokens,
        )
        attempts = 0
        transient_failures = 0
        max_attempts = len(self.available_keys)
        last_error: Exception | None = None
        while attempts < max_attempts:
            key, key_id, key_index = self.key_pool.acquire_key(estimated_tokens)
            attempts += 1
            try:
                client = Groq(
                    api_key=key,
                    timeout=self.request_timeout_seconds,
                    max_retries=0,
                )
                response = client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": ROUTER_SYSTEM_PROMPT.strip(),
                        },
                        {
                            "role": "user",
                            "content": dynamic_prompt,
                        },
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_output_tokens,
                    reasoning_effort=self._resolved_reasoning_effort(),
                    response_format=response_format,
                )
                raw = response.choices[0].message.content or ""
                parsed = self._extract_json_object(raw)
                usage = self._usage(response)
                actual_tokens = int(usage.get("total", estimated_tokens))
                self.key_pool.record_success(
                    key_id,
                    actual_tokens=actual_tokens,
                    reserved_tokens=estimated_tokens,
                )
                decision = normalize_router_decision(
                    parsed,
                    query=query,
                    selected_cohort=cohort,
                )
                grounding_context = "\n".join(
                    str(item.get("content") or "")
                    for item in (chat_history or [])[-4:]
                    if isinstance(item, dict)
                )
                validation_errors = validate_router_decision(
                    decision,
                    query=query,
                    selected_cohort=cohort,
                    grounding_context=grounding_context,
                    registry=self.registry,
                )
                if validation_errors:
                    decision = fallback_to_rag(
                        decision,
                        validation_errors,
                        query=query,
                    )
                decision["router_validation_errors"] = validation_errors
                if self.cache:
                    self.cache.set(cache_key, decision)
                return {
                    **decision,
                    "model_used": self.model_name,
                    "usage": usage,
                    "key_fingerprint": key_id,
                    "router_cache_hit": False,
                    "attempts": attempts,
                    "prompt_stats": prompt_stats,
                }
            except Exception as exc:
                last_error = exc
                error_type = self._classify_error(exc)
                if error_type == "rate_limit":
                    self.key_pool.record_rate_limit(
                        key_id,
                        retry_after_seconds=_retry_after_seconds(exc),
                    )
                    continue
                self.key_pool.record_failure(key_id, error_type)
                if error_type not in {"timeout", "api_error", "transient_error"}:
                    break
                transient_failures += 1
                if transient_failures > self.max_retries:
                    break
                print(
                    f"[AIRouter] Retrying {self.model_name} after {error_type} "
                    f"on key {key_index}:{key_id}."
                )

        if last_error is not None:
            return self._fallback_after_router_error(
                query,
                cohort=cohort,
                attempts=attempts,
                prompt_stats=prompt_stats,
                error=last_error,
            )
        raise RuntimeError("ai_router_failed: no_attempts")

    def _fallback_after_router_error(
        self,
        query: str,
        *,
        cohort: str | None,
        attempts: int,
        prompt_stats: dict[str, Any],
        error: Exception,
    ) -> dict[str, Any]:
        error_type = self._classify_error(error)
        decision = normalize_router_decision(
            {
                "context_mode": "standalone",
                "context_confidence": "none",
                "normalized_query": query,
                "normalization_confidence": "none",
                "corrections": [],
                "standalone_query": None,
                "referenced_turns": [],
                "route": "rag",
                "execution_mode": "regulation",
                "intent": "open_question",
                "lookup_type": None,
                "cohort": cohort,
                "slots": {},
                "slot_spans": {},
                "target_chunk_types": ["regulation"],
                "retrieval_query": query,
                "clarification_question": None,
            },
            query=query,
            selected_cohort=cohort,
        )
        return {
            **decision,
            "model_used": self.model_name,
            "usage": None,
            "key_fingerprint": None,
            "router_cache_hit": False,
            "attempts": attempts,
            "prompt_stats": prompt_stats,
            "router_validation_errors": [],
            "router_error_type": error_type,
            "router_error": str(error),
            "router_fallback": "router_error_to_rag",
        }

    def _build_prompt(
        self,
        query: str,
        *,
        cohort: str | None,
        chat_history: list[dict[str, str]] | None,
        routing_hint: dict[str, Any] | None = None,
    ) -> str:
        history_lines = []
        history_window = (chat_history or [])[-4:]
        for local_index, item in enumerate(history_window):
            role = str(item.get("role") or "user")
            content = str(item.get("content") or "")[:300]
            if content:
                history_lines.append(f"[{local_index}] {role}:{content}")
        history = "\n".join(history_lines) or "none"
        schema = json.dumps(
            router_json_schema(), ensure_ascii=False, separators=(",", ":")
        )
        hint = json.dumps(routing_hint, ensure_ascii=False, separators=(",", ":"))
        hint_instruction = (
            "CATALOG_HINT is grounded production metadata. Use its lookup_type and "
            "entity_text; infer only intent/requested_field from QUERY.\n"
            if routing_hint
            else ""
        )
        return (
            f"{hint_instruction}"
            "TOOLS:\n"
            f"{compact_registry_for_prompt(self.registry)}\n\n"
            f"OUTPUT CONTRACT:\n"
            f"{schema}\n\n"
            f"CATALOG_HINT: {hint if routing_hint else 'none'}\n"
            f"COHORT: {cohort or 'unknown'}\n"
            f"CHAT HISTORY:\n{history}\n"
            f"QUERY: {query}"
        )

    def _build_plan_prompt(
        self,
        query: str,
        *,
        cohort: str | None,
        chat_history: list[dict[str, str]] | None,
        routing_hint: dict[str, Any] | None = None,
    ) -> str:
        history_lines = []
        for local_index, item in enumerate((chat_history or [])[-4:]):
            role = str(item.get("role") or "user")
            content = str(item.get("content") or "")[:300]
            if content:
                history_lines.append(f"[{local_index}] {role}:{content}")
        history = "\n".join(history_lines) or "none"
        schema = json.dumps(
            query_plan_json_schema(), ensure_ascii=False, separators=(",", ":")
        )
        hint = json.dumps(routing_hint, ensure_ascii=False, separators=(",", ":"))
        return (
            "TOOLS:\n"
            f"{compact_registry_for_prompt(self.registry)}\n\n"
            f"OUTPUT CONTRACT:\n{schema}\n\n"
            f"CATALOG_HINT: {hint if routing_hint else 'none'}\n"
            f"COHORT: {cohort or 'unknown'}\n"
            f"CHAT HISTORY:\n{history}\n"
            f"QUERY: {query}"
        )

    def _resolved_reasoning_effort(self) -> str:
        if self.reasoning_effort != "auto":
            return self.reasoning_effort
        return "low" if "gpt-oss" in self.model_name.lower() else "none"

    def _resolved_response_format(self) -> str:
        if self.response_format != "auto":
            return self.response_format
        return "json_schema" if "gpt-oss" in self.model_name.lower() else "json_object"

    def _response_format_payload(self) -> dict[str, Any]:
        if self._resolved_response_format() == "json_schema":
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "router_decision",
                    "strict": False,
                    "schema": router_response_schema(),
                },
            }
        return {"type": "json_object"}

    def _plan_response_format_payload(self) -> dict[str, Any]:
        if self._resolved_response_format() == "json_schema":
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "query_plan",
                    "strict": False,
                    "schema": query_plan_response_schema(),
                },
            }
        return {"type": "json_object"}

    @staticmethod
    def _prompt_stats(
        dynamic_prompt: str,
        response_format: dict[str, Any],
    ) -> dict[str, int]:
        return AIRouter._prompt_stats_for_system(
            ROUTER_SYSTEM_PROMPT, dynamic_prompt, response_format
        )

    @staticmethod
    def _prompt_stats_for_system(
        system_prompt: str,
        dynamic_prompt: str,
        response_format: dict[str, Any],
    ) -> dict[str, int]:
        system_chars = len(system_prompt.strip())
        dynamic_chars = len(dynamic_prompt)
        schema_chars = len(
            json.dumps(response_format, ensure_ascii=False, separators=(",", ":"))
        )
        total_chars = system_chars + dynamic_chars + schema_chars
        return {
            "system_chars": system_chars,
            "dynamic_chars": dynamic_chars,
            "response_format_chars": schema_chars,
            "total_chars": total_chars,
            "estimated_input_tokens": max(1, total_chars // 4),
        }

    def _cache_key(
        self,
        query: str,
        *,
        cohort: str | None,
        chat_history: list[dict[str, str]] | None,
        routing_hint: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "query": query.strip(),
            "cohort": cohort,
            "history": (chat_history or [])[-4:],
            "routing_hint": routing_hint,
            "model": self.model_name,
            "prompt_version": ROUTER_PROMPT_VERSION,
            "registry": registry_digest(self.registry),
        }
        raw = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        stripped = text.strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise ValueError("AI router response did not contain JSON.")
        value = json.loads(stripped[start : end + 1])
        if not isinstance(value, dict):
            raise ValueError("AI router JSON must be an object.")
        return value

    @staticmethod
    def _usage(response: Any) -> dict[str, int]:
        usage = getattr(response, "usage", None)
        return {
            "input": int(getattr(usage, "prompt_tokens", 0) or 0),
            "output": int(getattr(usage, "completion_tokens", 0) or 0),
            "total": int(getattr(usage, "total_tokens", 0) or 0),
        }

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "timeout"
        text = f"{type(exc).__name__}: {exc}".lower()
        if any(token in text for token in ("429", "rate limit", "ratelimit", "quota")):
            return "rate_limit"
        if any(token in text for token in ("timeout", "timed out", "deadline")):
            return "timeout"
        if any(token in text for token in ("503", "unavailable", "temporarily")):
            return "transient_error"
        if any(
            token in text
            for token in (
                "json_validate_failed",
                "failed to generate json",
                "failed_generation",
            )
        ):
            return "transient_error"
        if any(
            token in text
            for token in (
                "disconnected",
                "connecterror",
                "connection reset",
                "network",
                "remoteprotocolerror",
            )
        ):
            return "transient_error"
        if any(token in text for token in ("groq", "api", "connection")):
            return "api_error"
        return "invalid_response"
