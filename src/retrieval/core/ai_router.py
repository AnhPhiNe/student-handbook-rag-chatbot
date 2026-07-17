from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from groq import Groq
import yaml

from src.common.env_loader import load_project_env

from .structured_routing import (
    compact_registry_for_prompt,
    load_lookup_registry,
    normalize_router_decision,
    registry_digest,
    router_json_schema,
)


DEFAULT_ROUTER_MODEL = "qwen/qwen3.6-27b"
ROUTER_PROMPT_VERSION = "structured-regulation-v12-vi"

ROUTER_SYSTEM_PROMPT = """
Bạn là AI Query Router của hệ thống Sổ tay Sinh viên HCMUE.

Chỉ phân loại và trích xuất slot. Không trả lời câu hỏi. Chỉ xuất một JSON đúng
JSON SCHEMA, không Markdown hoặc giải thích. Chỉ dùng lookup_type, intent và field
được khai báo trong TOOLS; không tự tạo tên mới.

ROUTE VÀ EXECUTION MODE
- structured / structured: câu hỏi có thể trả lời từ một bảng hoặc catalog JSON
  (số liệu, danh sách, liên hệ, ngành, biểu mẫu, công thức). Hệ thống phía sau sẽ
  lấy dữ liệu có thẩm quyền rồi để Answer LLM diễn giải; router không tính đáp án.
- rag / regulation: phải đọc Điều/khoản để trả lời quy định, điều kiện, thủ tục,
  ngoại lệ, hậu quả, quyền/nghĩa vụ, thời hạn hoặc trường hợp áp dụng.
- rag / mixed: cần cả dữ liệu structured và quy định. lookup_type chọn đúng một
  nguồn structured chính; target_chunk_types=["regulation"].
- clarify: thiếu cohort hoặc thiếu entity khiến không thể chọn dữ liệu an toàn.
- out_of_domain: ngoài phạm vi Sổ tay Sinh viên HCMUE.

Với route=structured:
- execution_mode="structured";
- lookup_type là đúng một tool trong TOOLS;
- intent thuộc tool đó;
- target_chunk_types=[];
- slots chỉ mô tả yêu cầu và đối tượng, không chứa câu trả lời suy đoán.

Với route=rag, execution_mode=regulation:
- lookup_type=null;
- intent="regulation";
- target_chunk_types=["regulation"].
Hệ thống không có procedure chunk type; mọi thủ tục/quy trình vẫn là regulation.

NGUYÊN TẮC PHÂN LOẠI
- Từ "bao nhiêu", "tối đa", "điểm", "IELTS" không tự quyết định route.
- Chọn structured nếu bảng/catalog có thể cung cấp dữ liệu cần thiết.
- Chọn regulation nếu phải suy ra điều kiện áp dụng, ngoại lệ hoặc cách xử lý.
- Chọn mixed khi câu hỏi thực sự cần cả giá trị bảng và quy định liên quan.
- Hỏi nơi tải một biểu mẫu là structured/form; hỏi thủ tục hoặc hồ sơ là regulation.
- Hỏi đích danh đơn vị là office/faculty; mô tả dịch vụ và hỏi nơi phụ trách là
  student_service; hỏi ngành hoặc ngành thuộc khoa nào là program.
- formula chỉ cung cấp công thức/hướng dẫn áp dụng, không thực hiện calculator.

COHORT VÀ ENTITY
- Giữ cohort K48-K49, K50 hoặc K51 nếu có. Không tự chọn cohort.
- Nếu dữ liệu phụ thuộc cohort mà QUERY/HISTORY/UI không có cohort, dùng clarify.
- Giữ nguyên entity người dùng nhập, kể cả viết tắt hoặc không dấu. Resolver sẽ
  đối chiếu entity với catalog; router không tự mở rộng hoặc sửa sang entity khác.

SLOT VÀ SLOT_SPANS
- Tuân thủ slot_schema trong TOOLS.
- slot_spans phải là đoạn xuất hiện nguyên văn trong QUERY hoặc CHAT HISTORY.
- Các field chuẩn hóa như requested_field/operation có thể nằm trong slots, nhưng
  span của chúng vẫn phải là cụm từ nguyên văn thể hiện yêu cầu của người dùng.
- Không bịa slot chỉ để thỏa schema. Nếu thiếu slot nhận diện entity/cohort quan
  trọng thì dùng clarify; slot chi tiết của bảng có thể để trống vì Answer LLM sẽ
  đọc toàn bộ bảng đã chọn cùng câu hỏi gốc.

RETRIEVAL_QUERY
- Viết lại thành câu độc lập, dễ tìm kiếm; giữ cohort, số liệu, phủ định và mọi
  yêu cầu độc lập. Chỉ sửa chính tả nhẹ, không thêm thông tin mới.

Trước khi xuất JSON, kiểm tra route/mode khớp nhau, lookup_type và intent có trong
TOOLS, slot đúng schema, span có thật trong nguồn vào, và không có "procedure"
trong target_chunk_types. Chỉ xuất JSON.
"""


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
                for index, key in enumerate(self.keys):
                    key_id = self.fingerprint(key)
                    state = self._key_state(key_id)
                    requests_today = int(state.get("requests_today", 0))
                    tokens_today = int(state.get("tokens_today", 0))
                    if (
                        requests_today < self.config.rpd_limit_per_key
                        and tokens_today + estimated_tokens <= self.config.tpd_limit_per_key
                    ):
                        daily_available = True
                    else:
                        continue

                    cooldown_until = float(state.get("cooldown_until", 0.0))
                    if cooldown_until > now:
                        wait_until.append(cooldown_until)
                        continue

                    events = list(state.get("minute_events", []))
                    minute_tokens = sum(int(event.get("tokens", 0)) for event in events)
                    if len(events) >= self.config.rpm_limit_per_key:
                        wait_until.append(float(events[0]["at"]) + 60.0)
                        continue
                    if minute_tokens + estimated_tokens > self.config.tpm_limit_per_key:
                        wait_until.append(float(events[0]["at"]) + 60.0 if events else now + 1.0)
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
                    raise RuntimeError("all_qwen_router_keys_daily_quota_exhausted")

                next_time = min(wait_until) if wait_until else now + 1.0
                wait_seconds = max(0.1, min(60.0, next_time - now))

            if not self.config.wait_when_limited:
                raise RuntimeError(
                    f"all_qwen_router_keys_temporarily_limited_retry_after_{wait_seconds:.1f}s"
                )
            time.sleep(wait_seconds)

    def record_success(self, key_id: str, *, actual_tokens: int, reserved_tokens: int) -> None:
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

    def record_rate_limit(self, key_id: str) -> None:
        with self._lock:
            state = self._key_state(key_id)
            state["cooldown_until"] = time.time() + self.config.cooldown_seconds
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
            }
        return states[state_key]

    def _record_attempt(
        self, key_id: str, now: float, today: str, estimated_tokens: int
    ) -> None:
        state = self._key_state(key_id)
        state["minute_events"].append({"at": now, "tokens": estimated_tokens})
        state["requests_today"] = int(state.get("requests_today", 0)) + 1
        state["tokens_today"] = int(state.get("tokens_today", 0)) + estimated_tokens
        state["daily_reset_date"] = today
        state["last_used_at"] = now
        self._save_state()

    def _reset_daily(self, today: str) -> None:
        for state in self._state.get("keys", {}).values():
            if state.get("daily_reset_date") != today:
                state["daily_reset_date"] = today
                state["requests_today"] = 0
                state["tokens_today"] = 0

    def _prune_windows(self, now: float) -> None:
        for state in self._state.get("keys", {}).values():
            state["minute_events"] = [
                event
                for event in state.get("minute_events", [])
                if now - float(event.get("at", 0.0)) < 60.0
            ]

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
    """Primary Qwen query-understanding router with a strict JSON contract."""

    def __init__(
        self,
        model_name: str = DEFAULT_ROUTER_MODEL,
        temperature: float = 0.0,
        max_output_tokens: int = 256,
        request_timeout_seconds: float = 5.0,
        max_retries: int = 1,
        key_pool_config: GroqRouterPoolConfig | dict[str, Any] | None = None,
        cache_path: str = "data/cache/qwen_router_cache.json",
        cache_enabled: bool = True,
    ) -> None:
        load_project_env()
        keys_value = (
            os.environ.get("GROQ_ROUTER_API_KEYS")
            or os.environ.get("GROQ_API_KEYS")
            or os.environ.get("GROQ_API_KEY")
            or ""
        )
        self.available_keys = [key.strip() for key in keys_value.split(",") if key.strip()]
        if not self.available_keys:
            raise RuntimeError(
                "Missing GROQ_ROUTER_API_KEYS, GROQ_API_KEYS, or GROQ_API_KEY."
            )
        self.model_name = model_name
        self.temperature = float(temperature)
        self.max_output_tokens = max(64, int(max_output_tokens))
        self.request_timeout_seconds = max(1.0, float(request_timeout_seconds))
        self.max_retries = max(0, int(max_retries))
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
        return cls(
            model_name=str(config.get("model_name", DEFAULT_ROUTER_MODEL)),
            temperature=float(config.get("temperature", 0.0)),
            max_output_tokens=int(config.get("max_output_tokens", 256)),
            request_timeout_seconds=float(config.get("request_timeout_seconds", 5.0)),
            max_retries=int(config.get("max_retries", 1)),
            key_pool_config=key_pool_config,
            cache_path=str(config.get("cache_path", "data/cache/qwen_router_cache.json")),
            cache_enabled=bool(config.get("cache_enabled", True))
            and not cache_disabled,
        )

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
            }

        estimated_tokens = max(
            128,
            (
                len(ROUTER_SYSTEM_PROMPT)
                + len(dynamic_prompt)
                + self.max_output_tokens * 4
            )
            // 4,
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
                    reasoning_effort="none",
                    response_format={"type": "json_object"},
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
                if self.cache:
                    self.cache.set(cache_key, decision)
                return {
                    **decision,
                    "model_used": self.model_name,
                    "usage": usage,
                    "key_fingerprint": key_id,
                    "router_cache_hit": False,
                    "attempts": attempts,
                }
            except Exception as exc:
                last_error = exc
                error_type = self._classify_error(exc)
                if error_type == "rate_limit":
                    self.key_pool.record_rate_limit(key_id)
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

        raise RuntimeError(f"qwen_router_failed: {last_error}")

    def _build_prompt(
        self,
        query: str,
        *,
        cohort: str | None,
        chat_history: list[dict[str, str]] | None,
        routing_hint: dict[str, Any] | None = None,
    ) -> str:
        history_lines = []
        for item in (chat_history or [])[-2:]:
            role = str(item.get("role") or "user")
            content = str(item.get("content") or "")[:300]
            if content:
                history_lines.append(f"{role}:{content}")
        history = "\n".join(history_lines) or "none"
        schema = json.dumps(router_json_schema(), ensure_ascii=False, separators=(",", ":"))
        hint = json.dumps(routing_hint, ensure_ascii=False, separators=(",", ":"))
        hint_instruction = (
            "CATALOG_HINT is an exact span grounded in production data. Use its lookup_type "
            "and entity_text to emit a structured decision, then infer only intent and "
            "requested_field from QUERY. Do not copy unit contact facts into the answer. "
            if routing_hint
            else ""
        )
        return (
            f"{hint_instruction}"
            f"TOOLS (type | intents | required slots | purpose):\n"
            f"{compact_registry_for_prompt(self.registry)}\n\n"
            f"JSON SCHEMA:\n"
            f"{schema}\n\n"
            f"CATALOG_HINT:\n"
            f"{hint if routing_hint else 'none'}\n\n"
            f"COHORT:\n"
            f"{cohort or 'unknown'}\n\n"
            f"CHAT HISTORY:\n"
            f"{history}\n\n"
            f"QUERY:\n"
            f"{query}"
        )

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
            "history": (chat_history or [])[-2:],
            "routing_hint": routing_hint,
            "model": self.model_name,
            "prompt_version": ROUTER_PROMPT_VERSION,
            "registry": registry_digest(self.registry),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        stripped = text.strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Qwen router response did not contain JSON.")
        value = json.loads(stripped[start : end + 1])
        if not isinstance(value, dict):
            raise ValueError("Qwen router JSON must be an object.")
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
        if any(token in text for token in ("groq", "api", "connection")):
            return "api_error"
        return "invalid_response"
