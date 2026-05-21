from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from src.common.env_loader import load_project_env

from .gemini_client import GeminiClient


DEFAULT_REWRITER_MODEL = "gemini-2.5-flash-lite"
DEFAULT_REWRITER_API_KEY_ENV = "QUERY_REWRITER_API_KEY"


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
        }


class QueryRewriter:
    """Optional LLM layer that normalizes noisy user questions before retrieval."""

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
        client: GeminiClient | None = None,
    ) -> None:
        load_project_env()
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

    def rewrite(self, query: str) -> QueryRewriteResult:
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

        if not os.environ.get(self.api_key_env_var):
            return QueryRewriteResult(
                original_query=query,
                effective_query=cleaned_query,
                reason=f"missing_{self.api_key_env_var}",
            )

        if not self._should_rewrite(cleaned_query):
            return QueryRewriteResult(
                original_query=query,
                effective_query=cleaned_query,
                reason="not_triggered",
            )

        llm_result = self._get_client().generate(_build_rewrite_prompt(cleaned_query))
        if not llm_result.get("ok"):
            return QueryRewriteResult(
                original_query=query,
                effective_query=cleaned_query,
                reason="llm_error",
                llm_called=True,
                error_type=llm_result.get("error_type"),
                error_message=llm_result.get("error_message"),
            )

        return self._parse_llm_result(cleaned_query, str(llm_result.get("text") or ""))

    def _should_rewrite(self, query: str) -> bool:
        normalized = _ascii_text(query)
        token_count = len(re.findall(r"[a-z0-9]+", normalized))

        if self.trigger_on_accentless and _looks_accentless_vietnamese(query):
            return True

        if self.trigger_on_typo_signals and _has_typo_signal(normalized):
            return True

        if self.trigger_on_short_query and token_count <= 4:
            return True

        return False

    def _get_client(self) -> GeminiClient:
        if self._client is None:
            self._client = GeminiClient(
                model_name=self.model_name,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                max_retries=self.max_retries,
                request_timeout_seconds=self.request_timeout_seconds,
                api_key_env_var=self.api_key_env_var,
            )
        return self._client

    def _parse_llm_result(self, query: str, raw_text: str) -> QueryRewriteResult:
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
            )

        confidence = str(payload.get("confidence") or "low").lower().strip()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"

        clarification_question = _clean_optional_string(
            payload.get("clarification_question")
        )
        needs_clarification = bool(payload.get("needs_clarification", False))
        if needs_clarification and clarification_question:
            return QueryRewriteResult(
                original_query=query,
                effective_query=query,
                needs_clarification=True,
                clarification_question=clarification_question,
                confidence=confidence,
                reason=str(payload.get("reason") or "llm_needs_clarification"),
                llm_called=True,
            )

        rewritten_query = _clean_optional_string(payload.get("normalized_query"))
        if rewritten_query and confidence in {"high", "medium"}:
            if not _is_safe_rewrite(query, rewritten_query):
                return QueryRewriteResult(
                    original_query=query,
                    effective_query=query,
                    rewritten_query=rewritten_query,
                    confidence=confidence,
                    reason="unsafe_rewrite_semantic_drift",
                    llm_called=True,
                )
            return QueryRewriteResult(
                original_query=query,
                effective_query=rewritten_query,
                rewritten_query=rewritten_query,
                confidence=confidence,
                reason=str(payload.get("reason") or "llm_rewritten"),
                llm_called=True,
            )

        return QueryRewriteResult(
            original_query=query,
            effective_query=query,
            rewritten_query=rewritten_query,
            confidence=confidence,
            reason=str(payload.get("reason") or "low_confidence"),
            llm_called=True,
        )


def _build_rewrite_prompt(query: str) -> str:
    return f"""
You are a query rewriting layer for a Vietnamese HCMUE student-handbook RAG chatbot.

Task:
- Restore Vietnamese accents when the user omits them.
- Fix light typos and chat shorthand.
- Expand common abbreviations only when clear: KTX, CNTT, CTCT-HSSV, GPA.
- Preserve the user's original meaning, wording, entities, and sentence structure as much as possible.
- Do not reinterpret the query, do not infer a different subject, and do not add new entities or nouns.
- Do not answer the question.
- If a token can be read in more than one way, choose the reading that changes the fewest words.
- Do not expand "cau" into "câu lạc bộ" unless the user explicitly writes "clb" or "câu lạc bộ".
- If you cannot normalize safely, return the original query with restored punctuation only, or ask for clarification.
- If the query is ambiguous, ask one short Vietnamese clarification question.

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

Input: "diem ren luyen 85 la loai j"
Output: {{"normalized_query":"Điểm rèn luyện 85 là loại gì?","needs_clarification":false,"clarification_question":null,"confidence":"high","reason":"typo_and_accent_restoration"}}

Input: "cau biet khoa tieng Trung o dau khong"
Output: {{"normalized_query":"Cậu biết Khoa Tiếng Trung ở đâu không?","needs_clarification":false,"clarification_question":null,"confidence":"high","reason":"accent_restoration"}}

Input: "hoc bong hoi ai"
Output: {{"normalized_query":null,"needs_clarification":true,"clarification_question":"Bạn muốn hỏi điều kiện học bổng, hồ sơ/biểu mẫu học bổng hay đơn vị liên hệ?","confidence":"medium","reason":"ambiguous_scholarship_scope"}}

User query: {json.dumps(query, ensure_ascii=False)}
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


def _is_safe_rewrite(original_query: str, rewritten_query: str) -> bool:
    original_tokens = _tokenize_ascii(original_query)
    rewritten_tokens = _tokenize_ascii(rewritten_query)
    if not original_tokens or not rewritten_tokens:
        return False

    allowed_tokens = set(original_tokens)
    allowed_tokens.update(_allowed_expansion_tokens(original_tokens))

    added_content_tokens = [
        token
        for token in rewritten_tokens
        if token not in allowed_tokens and len(token) >= 3
    ]
    if added_content_tokens:
        return False

    original_content = {token for token in original_tokens if len(token) >= 3}
    rewritten_content = {token for token in rewritten_tokens if len(token) >= 3}
    if original_content:
        retained_ratio = len(original_content & rewritten_content) / len(original_content)
        if retained_ratio < 0.7:
            return False

    if len(rewritten_tokens) > max(len(original_tokens) + 4, int(len(original_tokens) * 1.5)):
        return False

    return True


def _tokenize_ascii(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _ascii_text(text))


def _allowed_expansion_tokens(original_tokens: list[str]) -> set[str]:
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
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    stripped = re.sub(r"[^a-zA-Z0-9]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def _clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _env_bool(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}
