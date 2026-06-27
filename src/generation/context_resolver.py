from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MAX_HISTORY_MESSAGES = 6
VALID_CONTEXT_DECISIONS = {"standalone_new_topic", "follow_up", "ambiguous"}
VALID_CONFIDENCE_LEVELS = {"high", "medium", "low"}


@dataclass(frozen=True)
class ContextResolution:
    """Kết quả quyết định có nên dùng lịch sử chat cho câu hỏi hiện tại."""

    history_used: bool
    relevant_history: list[dict[str, str]]
    reason: str
    decision: str = "standalone_new_topic"
    confidence: str = "none"
    standalone_query: str | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None
    referenced_turns: list[int] | None = None
    llm_called: bool = False
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "history_used": self.history_used,
            "history_message_count": len(self.relevant_history),
            "reason": self.reason,
            "decision": self.decision,
            "confidence": self.confidence,
            "standalone_query": self.standalone_query,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "referenced_turns": self.referenced_turns or [],
            "llm_called": self.llm_called,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


def resolve_query_context(
    query: str,
    chat_history: list[dict[str, str]] | None,
    llm_payload: dict[str, Any] | None = None,
) -> ContextResolution:
    """Đọc quyết định context từ LLM thay vì tự đoán bằng danh sách từ khóa.

    Hàm này không còn hardcode cụm follow-up như "còn", "vậy", "thì sao".
    Nếu có history, LLM Context Resolver phải trả JSON để phân loại câu hiện tại.
    Code chỉ giữ vai trò kiểm tra confidence và chặn các quyết định không chắc.
    """
    cleaned_history = clean_history(chat_history)
    if not cleaned_history:
        return ContextResolution(False, [], "no_history")

    if llm_payload is None:
        return ContextResolution(
            history_used=False,
            relevant_history=[],
            reason="awaiting_llm_context_resolution",
            decision="ambiguous",
            confidence="none",
            needs_clarification=True,
            clarification_question=(
                "Bạn muốn hỏi tiếp nội dung trước đó hay đang chuyển sang một chủ đề mới?"
            ),
        )

    decision = _clean_decision(llm_payload.get("decision"))
    confidence = _clean_confidence(llm_payload.get("confidence"))
    standalone_query = _clean_optional_string(llm_payload.get("standalone_query"))
    clarification_question = _clean_optional_string(
        llm_payload.get("clarification_question")
    )
    referenced_turns = _clean_referenced_turns(llm_payload.get("referenced_turns"))
    reason = (
        _clean_optional_string(llm_payload.get("reason")) or "llm_context_resolution"
    )

    if decision == "follow_up" and confidence == "high" and standalone_query:
        return ContextResolution(
            history_used=True,
            relevant_history=cleaned_history[-MAX_HISTORY_MESSAGES:],
            reason=reason,
            decision=decision,
            confidence=confidence,
            standalone_query=standalone_query,
            referenced_turns=referenced_turns,
            llm_called=True,
        )

    if decision == "standalone_new_topic" and confidence in {"high", "medium"}:
        return ContextResolution(
            history_used=False,
            relevant_history=[],
            reason=reason,
            decision=decision,
            confidence=confidence,
            standalone_query=standalone_query,
            referenced_turns=referenced_turns,
            llm_called=True,
        )

    return ContextResolution(
        history_used=False,
        relevant_history=[],
        reason=reason,
        decision=decision,
        confidence=confidence,
        standalone_query=standalone_query,
        needs_clarification=True,
        clarification_question=clarification_question
        or "Bạn muốn hỏi tiếp nội dung trước đó hay đang chuyển sang một chủ đề mới?",
        referenced_turns=referenced_turns,
        llm_called=True,
    )


def clean_history(chat_history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if not chat_history:
        return []

    cleaned = []
    for message in chat_history:
        # Chỉ giữ role/content để prompt context không bị nhiễm metadata lạ từ frontend.
        role = str(message.get("role", "user")).strip().lower()
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        cleaned.append({"role": role, "content": content})
    return cleaned


def _clean_decision(value: Any) -> str:
    decision = str(value or "").strip().lower()
    if decision not in VALID_CONTEXT_DECISIONS:
        return "ambiguous"
    return decision


def _clean_confidence(value: Any) -> str:
    confidence = str(value or "").strip().lower()
    if confidence not in VALID_CONFIDENCE_LEVELS:
        return "low"
    return confidence


def _clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _clean_referenced_turns(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []

    turns: list[int] = []
    for item in value:
        try:
            turn = int(item)
        except (TypeError, ValueError):
            continue
        if turn >= 0:
            turns.append(turn)
    return turns
