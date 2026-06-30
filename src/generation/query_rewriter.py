from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from groq import Groq
from langsmith import traceable

from src.common.env_loader import load_project_env
from src.generation.context_resolver import (
    ContextResolution,
    clean_history,
    resolve_query_context,
)


DEFAULT_REWRITER_MODEL = "llama-3.1-8b-instant"
DEFAULT_REWRITER_API_KEY_ENV = "QUERY_REWRITER_API_KEY"
FALLBACK_REWRITER_API_KEY_ENV = "GROQ_API_KEY"


@dataclass(frozen=True)
class QueryRewriteResult:
    original_query: str
    effective_query: str
    rewritten_query: str | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None
    confidence: str = "none"
    reason: str = "disabled"
    llm_called: bool = False
    error_type: str | None = None
    error_message: str | None = None
    context_resolution: dict[str, Any] | None = None

    @property
    def changed(self) -> bool:
        return self.effective_query.strip() != self.original_query.strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_query": self.original_query,
            "effective_query": self.effective_query,
            "rewritten_query": self.rewritten_query,
            "changed": self.changed,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "confidence": self.confidence,
            "reason": self.reason,
            "llm_called": self.llm_called,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "context_resolution": self.context_resolution,
        }


class QueryRewriter:
    """Lớp LLM tùy chọn để chuẩn hóa câu hỏi nhiễu trước khi truy xuất."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        model_name: str = DEFAULT_REWRITER_MODEL,
        api_key_env_var: str = DEFAULT_REWRITER_API_KEY_ENV,
        temperature: float = 0.0,
        max_output_tokens: int = 256,
        request_timeout_seconds: float = 3,
        max_retries: int = 1,
        trigger_on_accentless: bool = True,
        trigger_on_short_query: bool = True,
        trigger_on_typo_signals: bool = True,
        client: Any | None = None,
    ) -> None:
        load_project_env(override=not _env_bool("STUDENT_RAG_OFFLINE_EVAL"))
        self.enabled = enabled
        self.model_name = model_name
        self.api_key_env_var = api_key_env_var
        self.temperature = float(temperature)
        self.max_output_tokens = int(max_output_tokens)
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.max_retries = int(max_retries)
        self.trigger_on_accentless = bool(trigger_on_accentless)
        self.trigger_on_short_query = bool(trigger_on_short_query)
        self.trigger_on_typo_signals = bool(trigger_on_typo_signals)
        self._client = client

        # Load dynamic keys
        keys_str = os.environ.get(
            self.api_key_env_var, 
            os.environ.get("GROQ_API_KEYS", os.environ.get("GROQ_API_KEY", ""))
        )
        self.available_keys = [k.strip() for k in keys_str.split(",") if k.strip()]

        # Build fallback matrix (Model x Key)
        fallback_models = [
            model_name,
            "qwen/qwen3.6-27b",
        ]
        self.models = []
        for m in fallback_models:
            if m not in self.models:
                self.models.append(m)

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> QueryRewriter:
        config = config or {}
        env_enabled = _env_bool("QUERY_REWRITER_ENABLED")
        enabled = bool(config.get("enabled", False) or env_enabled)
        api_key_env_var = str(
            config.get("api_key_env_var") or DEFAULT_REWRITER_API_KEY_ENV
        )

        return cls(
            enabled=enabled,
            model_name=str(config.get("model_name") or DEFAULT_REWRITER_MODEL),
            api_key_env_var=api_key_env_var,
            temperature=float(config.get("temperature", 0.0)),
            max_output_tokens=int(config.get("max_output_tokens", 256)),
            request_timeout_seconds=float(config.get("request_timeout_seconds", 3)),
            max_retries=int(config.get("max_retries", 1)),
            trigger_on_accentless=bool(config.get("trigger_on_accentless", True)),
            trigger_on_short_query=bool(config.get("trigger_on_short_query", True)),
            trigger_on_typo_signals=bool(config.get("trigger_on_typo_signals", True)),
        )

    @traceable(name="Query Rewriter", run_type="chain")
    def rewrite(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None = None,
    ) -> QueryRewriteResult:
        cleaned_query = query.strip()
        if not cleaned_query:
            return QueryRewriteResult(
                original_query=query,
                effective_query=cleaned_query,
                reason="empty_query",
            )

        if not self.enabled:
            return QueryRewriteResult(
                original_query=query,
                effective_query=cleaned_query,
                reason="disabled",
            )

        if not self.available_keys:
            return QueryRewriteResult(
                original_query=query,
                effective_query=cleaned_query,
                reason=f"missing_{self.api_key_env_var}",
            )

        context_resolution = resolve_query_context(cleaned_query, chat_history)
        if clean_history(chat_history):
            try:
                raw_context = self._call_context_llm(cleaned_query, chat_history)
                context_payload = _extract_json_object(raw_context)
                context_resolution = resolve_query_context(
                    cleaned_query,
                    chat_history,
                    llm_payload=context_payload,
                )
            except Exception as exc:
                context_resolution = ContextResolution(
                    history_used=False,
                    relevant_history=[],
                    reason="context_resolver_error",
                    decision="ambiguous",
                    confidence="low",
                    llm_called=True,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )

        if context_resolution.needs_clarification:
            return QueryRewriteResult(
                original_query=query,
                effective_query=cleaned_query,
                needs_clarification=True,
                clarification_question=context_resolution.clarification_question,
                confidence=context_resolution.confidence,
                reason=context_resolution.reason,
                llm_called=context_resolution.llm_called,
                context_resolution=context_resolution.to_dict(),
            )

        if context_resolution.history_used and context_resolution.standalone_query:
            history_text = _history_text(context_resolution.relevant_history)
            if _is_safe_rewrite(
                cleaned_query,
                context_resolution.standalone_query,
                has_history=True,
                history_text=history_text,
            ):
                return QueryRewriteResult(
                    original_query=query,
                    effective_query=context_resolution.standalone_query,
                    rewritten_query=context_resolution.standalone_query,
                    confidence=context_resolution.confidence,
                    reason=context_resolution.reason,
                    llm_called=True,
                    context_resolution=context_resolution.to_dict(),
                )

            return QueryRewriteResult(
                original_query=query,
                effective_query=cleaned_query,
                rewritten_query=context_resolution.standalone_query,
                needs_clarification=True,
                clarification_question=(
                    "Mình chưa chắc câu hỏi này đang nối tiếp phần nào trong lịch sử chat. "
                    "Bạn có thể viết rõ lại câu hỏi đầy đủ được không?"
                ),
                confidence=context_resolution.confidence,
                reason="unsafe_context_rewrite",
                llm_called=True,
                context_resolution=context_resolution.to_dict(),
            )

        rewrite_needed = (
            self._should_rewrite(cleaned_query) or context_resolution.history_used
        )
        if not rewrite_needed:
            return QueryRewriteResult(
                original_query=query,
                effective_query=cleaned_query,
                reason="not_triggered",
                llm_called=context_resolution.llm_called,
                context_resolution=context_resolution.to_dict(),
            )

        # Chỉ truyền history khi resolver xác nhận câu hiện tại là follow-up.
        prompt_history = (
            context_resolution.relevant_history
            if context_resolution.history_used
            else None
        )
        history_text = _history_text(prompt_history)

        try:
            raw_text = self._call_llm(cleaned_query, chat_history=prompt_history)
        except Exception as exc:
            return QueryRewriteResult(
                original_query=query,
                effective_query=cleaned_query,
                reason="llm_error",
                llm_called=True,
                error_type=type(exc).__name__,
                error_message=str(exc),
                context_resolution=context_resolution.to_dict(),
            )

        return self._parse_llm_result(
            cleaned_query,
            raw_text,
            has_history=context_resolution.history_used,
            history_text=history_text,
            context_resolution=context_resolution,
        )

    def _should_rewrite(self, query: str) -> bool:
        # Luôn luôn kích hoạt LLM để dịch ngôn ngữ người dùng (bao gồm từ lóng)
        # sang ngôn ngữ học thuật của Sổ tay sinh viên.
        return True

    def _call_llm(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None,
    ) -> str:
        from groq import (
            RateLimitError,
            APITimeoutError,
            InternalServerError,
            APIConnectionError,
        )

        last_error: Exception | None = None
        import random

        keys = list(self.available_keys)
        random.shuffle(keys)
        providers = [{"model": m, "api_key": k} for m in self.models for k in keys]

        for provider in providers:
            try:
                client = self._client or Groq(api_key=provider["api_key"], timeout=5.0, max_retries=0)
                kwargs: dict[str, Any] = {
                    "model": provider["model"],
                    "messages": [
                        {
                            "role": "user",
                            "content": _build_rewrite_prompt(
                                query,
                                chat_history=chat_history,
                            ),
                        }
                    ],
                    "temperature": self.temperature,
                    "max_tokens": self.max_output_tokens,
                    "response_format": {"type": "json_object"},
                }

                llm_result = client.chat.completions.create(**kwargs)
                raw_text = llm_result.choices[0].message.content
                if not raw_text:
                    raise ValueError("Empty response from Groq")
                print(f"[QueryRewriter] phase=rewrite model_used={provider['model']}")
                return raw_text
            except (
                RateLimitError,
                APITimeoutError,
                InternalServerError,
                APIConnectionError,
                ValueError,
            ) as exc:
                last_error = exc
                print(
                    f"[Fallback] QueryRewriter (Rewrite) failed with model {provider['model']}. Trying next... Error: {str(exc)}"
                )
                continue

        raise RuntimeError(
            f"Query rewriter all fallback providers failed. Last error: {str(last_error)}"
        )

    def _call_context_llm(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None,
    ) -> str:
        from groq import (
            RateLimitError,
            APITimeoutError,
            InternalServerError,
            APIConnectionError,
        )

        import random
        last_error: Exception | None = None

        keys = list(self.available_keys)
        random.shuffle(keys)
        providers = [{"model": m, "api_key": k} for m in self.models for k in keys]

        for provider in providers:
            try:
                client = self._client or Groq(api_key=provider["api_key"], timeout=5.0, max_retries=0)
                kwargs: dict[str, Any] = {
                    "model": provider["model"],
                    "messages": [
                        {
                            "role": "user",
                            "content": _build_context_resolution_prompt(
                                query,
                                chat_history=chat_history,
                            ),
                        }
                    ],
                    "temperature": self.temperature,
                    "max_tokens": self.max_output_tokens,
                    "response_format": {"type": "json_object"},
                }

                llm_result = client.chat.completions.create(**kwargs)
                raw_text = llm_result.choices[0].message.content
                if not raw_text:
                    raise ValueError("Empty response from Groq")
                print(f"[QueryRewriter] phase=context model_used={provider['model']}")
                return raw_text
            except (
                RateLimitError,
                APITimeoutError,
                InternalServerError,
                APIConnectionError,
                ValueError,
            ) as exc:
                last_error = exc
                print(
                    f"[Fallback] QueryRewriter (Context) failed with model {provider['model']}. Trying next... Error: {str(exc)}"
                )
                continue

        raise RuntimeError(
            f"Context resolver all fallback providers failed. Last error: {str(last_error)}"
        )

    def _parse_llm_result(
        self,
        query: str,
        raw_text: str,
        has_history: bool = False,
        history_text: str = "",
        context_resolution: ContextResolution | None = None,
    ) -> QueryRewriteResult:
        context_payload = context_resolution.to_dict() if context_resolution else None
        try:
            payload = _extract_json_object(raw_text)
        except ValueError as exc:
            return QueryRewriteResult(
                original_query=query,
                effective_query=query,
                reason="invalid_llm_json",
                llm_called=True,
                error_type="parse_error",
                error_message=str(exc),
                context_resolution=context_payload,
            )

        confidence = str(payload.get("confidence") or "low").lower().strip()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"

        clarification_question = _clean_optional_string(
            payload.get("clarification_question")
        )
        needs_clarification = bool(payload.get("needs_clarification", False))
        if needs_clarification and clarification_question:
            rewritten_query = _clean_optional_string(payload.get("normalized_query"))
            # Nếu resolver đã xác nhận đây là follow-up, ưu tiên câu rewrite an toàn.
            if has_history:
                # Neu LLM bao mo ho nhung van dua duoc cau rewrite an toan tu history,
                # dung rewrite do thay vi hoi lai nguoi dung.
                if rewritten_query and _is_safe_rewrite(
                    query,
                    rewritten_query,
                    has_history,
                    history_text,
                ):
                    return QueryRewriteResult(
                        original_query=query,
                        effective_query=rewritten_query,
                        rewritten_query=rewritten_query,
                        confidence=confidence,
                        reason="history_override_used_rewrite",
                        llm_called=True,
                        context_resolution=context_payload,
                    )
                return QueryRewriteResult(
                    original_query=query,
                    effective_query=query,
                    confidence=confidence,
                    reason="history_override_fallback",
                    llm_called=True,
                    context_resolution=context_payload,
                )

            return QueryRewriteResult(
                original_query=query,
                effective_query=query,
                needs_clarification=True,
                clarification_question=clarification_question,
                confidence=confidence,
                reason=str(payload.get("reason") or "llm_needs_clarification"),
                llm_called=True,
                context_resolution=context_payload,
            )

        rewritten_query = _clean_optional_string(payload.get("normalized_query"))
        if rewritten_query and confidence in {"high", "medium"}:
            # Guard cuoi cung: LLM co the them entity/noi dung moi, nen bat buoc so token.
            if not _is_safe_rewrite(query, rewritten_query, has_history, history_text):
                return QueryRewriteResult(
                    original_query=query,
                    effective_query=query,
                    rewritten_query=rewritten_query,
                    confidence=confidence,
                    reason="unsafe_rewrite_semantic_drift",
                    llm_called=True,
                    context_resolution=context_payload,
                )
            return QueryRewriteResult(
                original_query=query,
                effective_query=rewritten_query,
                rewritten_query=rewritten_query,
                confidence=confidence,
                reason=str(payload.get("reason") or "llm_rewritten"),
                llm_called=True,
                context_resolution=context_payload,
            )

        return QueryRewriteResult(
            original_query=query,
            effective_query=query,
            rewritten_query=rewritten_query,
            confidence=confidence,
            reason=str(payload.get("reason") or "low_confidence"),
            llm_called=True,
            context_resolution=context_payload,
        )


def _build_rewrite_prompt(
    query: str,
    chat_history: list[dict[str, str]] | None = None,
) -> str:
    history_block = ""
    if chat_history:
        lines = []
        for msg in chat_history[-6:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"User: {content}")
            else:
                lines.append(f"Assistant: {content[:800]}")
        history_block = f"""

Conversation history (use this only to resolve pronouns and follow-up references):
{chr(10).join(lines)}
"""

    return f"""
You are a query rewriting layer for a Vietnamese HCMUE student-handbook RAG chatbot.

Task:
- Restore Vietnamese accents when the user omits them.
- Fix light typos and chat shorthand.
- Expand common abbreviations only when clear: KTX, CNTT, CTCT-HSSV, GPA.
- Preserve the user's original meaning unless conversation history is needed for a follow-up.
- Do not add new entities or nouns unless they are necessary to resolve references from the provided history.
- Do not answer the question.
- If the current query introduces a completely new topic, do not merge it with history.
- If history is provided, resolve pronouns and ellipsis only when the current query is clearly a follow-up.
- Only set needs_clarification=true when there is no safe standalone rewrite.
{history_block}
Return only valid JSON with this schema:
{{
  "normalized_query": "string or null",
  "needs_clarification": false,
  "clarification_question": null,
  "confidence": "high|medium|low",
  "reason": "short reason"
}}

Examples:
Input: "email phong dao tao la gi"
Output: {{"normalized_query":"Email Phòng Đào tạo là gì?","needs_clarification":false,"clarification_question":null,"confidence":"high","reason":"accent_restoration"}}

Input (with history: User asked "học bổng loại khá cần bao nhiêu điểm"): "còn loại giỏi thì sao?"
Output: {{"normalized_query":"Sinh viên được học bổng loại giỏi cần bao nhiêu điểm?","needs_clarification":false,"clarification_question":null,"confidence":"high","reason":"history_context_resolution"}}

Input (with history about scholarships): "Khoa CNTT ở đâu?"
Output: {{"normalized_query":"Khoa Công nghệ thông tin ở đâu?","needs_clarification":false,"clarification_question":null,"confidence":"high","reason":"new_topic_accent_restoration"}}

Input: "diem ren luyen 85 la loai j"
Output: {{"normalized_query":"Điểm rèn luyện 85 là loại gì?","needs_clarification":false,"clarification_question":null,"confidence":"high","reason":"typo_and_accent_restoration"}}

Input: "hoc bong hoi ai"
Output: {{"normalized_query":null,"needs_clarification":true,"clarification_question":"Bạn muốn hỏi điều kiện học bổng, hồ sơ/biểu mẫu học bổng hay đơn vị liên hệ?","confidence":"medium","reason":"ambiguous_scholarship_scope"}}

User query: {json.dumps(query, ensure_ascii=False)}
""".strip()


def _build_context_resolution_prompt(
    query: str,
    chat_history: list[dict[str, str]] | None = None,
) -> str:
    lines = []
    for index, msg in enumerate(clean_history(chat_history)[-6:]):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{index}: {label}: {content}")

    history_block = "\n".join(lines) or "(empty)"

    return f"""
You are the context resolver for a Vietnamese HCMUE student-handbook RAG chatbot.

Your only job is to decide whether the current user query depends on the recent
conversation history. Do not answer the question.

Decision labels:
- standalone_new_topic: the current query is understandable by itself or introduces a new topic.
- follow_up: the current query clearly depends on a previous turn.
- ambiguous: you cannot safely tell whether it is a follow-up or a new topic.

Rules:
- Use follow_up only when the current query would be incomplete without history.
- Use standalone_new_topic when the query has its own subject/intent, even if history exists.
- If decision is follow_up, write standalone_query as the full question to retrieve.
- If decision is ambiguous or confidence is not high, ask a concise clarification question.
- Do not add entities that are not present in the current query or the referenced history turns.

Conversation history:
{history_block}

Current user query:
{json.dumps(query, ensure_ascii=False)}

Return only valid JSON with this schema:
{{
  "decision": "standalone_new_topic|follow_up|ambiguous",
  "confidence": "high|medium|low",
  "referenced_turns": [0],
  "standalone_query": "string or null",
  "clarification_question": "string or null",
  "reason": "short reason"
}}
""".strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM response did not contain a JSON object.")

    parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON response must be an object.")
    return parsed


def _looks_accentless_vietnamese(query: str) -> bool:
    ascii_query = _ascii_text(query)
    if not ascii_query or _has_vietnamese_diacritic(query):
        return False

    domain_terms = [
        "diem",
        "ren luyen",
        "hoc bong",
        "hoc phi",
        "phong",
        "khoa",
        "dao tao",
        "mau don",
        "don xin",
        "tam nghi",
        "ky tuc xa",
        "ktx",
        "sinh vien",
        "tin chi",
        "tot nghiep",
        "lien he",
        "email",
        "gpa",
        "cntt",
    ]
    return any(term in ascii_query for term in domain_terms)


def _has_typo_signal(ascii_query: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", ascii_query))
    typo_tokens = {"j", "ko", "khongg", "hok", "hocj", "mun", "mún", "dc", "duocj"}
    return bool(tokens & typo_tokens)


def _is_safe_rewrite(
    original_query: str,
    rewritten_query: str,
    has_history: bool = False,
    history_text: str = "",
) -> bool:
    # Ham nay giu Query Rewriter dung vai tro "chuan hoa cau hoi", khong duoc sang tac noi dung.
    # Khi khong dung history, token noi dung moi gan nhu bi cam tru cac abbreviation hop le.
    original_tokens = _tokenize_ascii(original_query)
    rewritten_tokens = _tokenize_ascii(rewritten_query)
    if not original_tokens or not rewritten_tokens:
        return False

    allowed_tokens = set(original_tokens)
    allowed_tokens.update(_allowed_expansion_tokens(original_tokens))

    # Token moi co do dai >= 3 thuong la entity/chu de moi, nen can kiem soat rat chat.
    added_content_tokens = [
        token
        for token in rewritten_tokens
        if token not in allowed_tokens and len(token) >= 3
    ]
    if added_content_tokens and not has_history:
        return False

    original_content = _content_tokens(original_tokens)
    rewritten_content = _content_tokens(rewritten_tokens)
    if original_content:
        # Cau rewrite phai giu lai phan lon y nghia goc; neu mat qua nhieu token thi xem la drift.
        retained_count = len(original_content & rewritten_content)
        retained_count += _retained_expansion_count(original_content, rewritten_content)
        retained_ratio = retained_count / len(original_content)
        minimum_ratio = 0.35 if has_history else 0.7
        if retained_ratio < minimum_ratio:
            return False

    if not has_history:
        if len(rewritten_tokens) > max(
            len(original_tokens) + 4, int(len(original_tokens) * 1.5)
        ):
            return False
        return True

    # Khi dùng history, token mới phải đến từ history hoặc là từ nối tự nhiên.
    history_tokens = set(_tokenize_ascii(history_text))
    unsafe_added = [
        token
        for token in added_content_tokens
        if token not in history_tokens and token not in _history_filler_tokens()
    ]
    return len(unsafe_added) <= 2


def _content_tokens(tokens: list[str]) -> set[str]:
    stopwords = {
        "ben",
        "con",
        "vay",
        "thi",
        "sao",
        "the",
        "cai",
        "do",
        "kia",
        "nay",
        "ay",
        "la",
        "gi",
        "nao",
        "hoi",
        "tiep",
        "truong",
        "hop",
    }
    return {token for token in tokens if len(token) >= 3 and token not in stopwords}


def _retained_expansion_count(
    original_content: set[str],
    rewritten_content: set[str],
) -> int:
    # Cho phep "cntt" duoc tinh la da giu y neu rewrite thanh "cong nghe thong tin".
    expansion_map = {
        "cntt": {"cong", "nghe", "thong", "tin"},
        "ktx": {"ky", "ki", "tuc", "xa"},
        "gpa": {"diem", "trung", "binh"},
    }
    retained = 0
    for token, expansion in expansion_map.items():
        if token in original_content and expansion & rewritten_content:
            retained += 1
    return retained


def _history_filler_tokens() -> set[str]:
    return {
        "sinh",
        "vien",
        "duoc",
        "can",
        "bao",
        "nhieu",
        "diem",
        "loai",
        "cau",
        "hoi",
        "thong",
        "tin",
        "lien",
        "he",
        "xin",
        "thi",
    }


def _tokenize_ascii(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _ascii_text(text))


def _allowed_expansion_tokens(original_tokens: list[str]) -> set[str]:
    # Bang mo rong nay la whitelist: LLM chi duoc them cac token tu viet tat/typo da biet.
    tokens = set(original_tokens)
    allowed: set[str] = set()
    expansion_map = {
        "j": {"gi"},
        "ko": {"khong"},
        "khongg": {"khong"},
        "hok": {"khong", "hoc"},
        "mun": {"muon"},
        "dc": {"duoc"},
        "duocj": {"duoc"},
        "ktx": {"ky", "ki", "tuc", "xa"},
        "cntt": {"cong", "nghe", "thong", "tin"},
        "pdt": {"phong", "dao", "tao"},
        "gpa": {"diem", "trung", "binh", "tich", "luy"},
    }
    for token, expansion in expansion_map.items():
        if token in tokens:
            allowed.update(expansion)

    if "ctct" in tokens or "hssv" in tokens or "ctsv" in tokens:
        allowed.update(
            {
                "phong",
                "cong",
                "tac",
                "chinh",
                "tri",
                "hoc",
                "sinh",
                "vien",
            }
        )

    return allowed


def _has_vietnamese_diacritic(text: str) -> bool:
    return any(
        unicodedata.category(char) == "Mn"
        for char in unicodedata.normalize("NFD", text)
    ) or any(char in {"đ", "Đ"} for char in text)


def _ascii_text(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    stripped = re.sub(r"[^a-zA-Z0-9]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def _clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _history_text(chat_history: list[dict[str, str]] | None) -> str:
    if not chat_history:
        return ""
    return " ".join(str(message.get("content", "")) for message in chat_history)


def _env_bool(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}
