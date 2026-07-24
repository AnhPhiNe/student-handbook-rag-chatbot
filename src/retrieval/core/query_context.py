from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


QUERY_HANDLING_MODES = {"raw", "router_generated", "context_only"}
CONTEXT_MODES = {"standalone", "follow_up", "ambiguous"}
CONFIDENCE_LEVELS = {"high", "medium", "low", "none"}
MAX_QUERY_CHARS = 600
MAX_HISTORY_MESSAGES = 4

_CONTENT_STOPWORDS = {
    "ai",
    "bao",
    "ben",
    "cai",
    "can",
    "co",
    "con",
    "cua",
    "do",
    "duoc",
    "gi",
    "hoi",
    "khong",
    "la",
    "may",
    "minh",
    "muon",
    "nao",
    "nay",
    "nhu",
    "o",
    "sao",
    "thi",
    "the",
    "tui",
    "vay",
    "ve",
}


@dataclass(frozen=True)
class QueryHandlingResult:
    raw_query: str
    effective_query: str
    mode: str
    context_mode: str
    source: str
    normalized_query: str | None = None
    standalone_query: str | None = None
    referenced_turns: tuple[int, ...] = ()
    normalization_confidence: str = "none"
    context_confidence: str = "none"
    validation_errors: tuple[str, ...] = ()
    needs_clarification: bool = False
    clarification_question: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "effective_query": self.effective_query,
            "mode": self.mode,
            "context_mode": self.context_mode,
            "source": self.source,
            "normalized_query": self.normalized_query,
            "standalone_query": self.standalone_query,
            "referenced_turns": list(self.referenced_turns),
            "normalization_confidence": self.normalization_confidence,
            "context_confidence": self.context_confidence,
            "validation_errors": list(self.validation_errors),
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
        }


def query_handling_mode(value: str | None = None) -> str:
    candidate = (
        str(
            value or os.environ.get("STUDENT_RAG_QUERY_HANDLING_MODE") or "context_only"
        )
        .strip()
        .lower()
    )
    return candidate if candidate in QUERY_HANDLING_MODES else "context_only"


def select_effective_query(
    raw_query: str,
    router_decision: dict[str, Any],
    *,
    chat_history: list[dict[str, str]] | None = None,
    selected_cohort: str | None = None,
    mode: str | None = None,
) -> QueryHandlingResult:
    raw_query = str(raw_query or "").strip()
    selected_mode = query_handling_mode(mode)
    context_mode = (
        str(router_decision.get("context_mode") or "standalone").strip().lower()
    )
    if context_mode not in CONTEXT_MODES:
        context_mode = "ambiguous"

    normalized_query = _clean_query(router_decision.get("normalized_query"))
    standalone_query = _clean_query(router_decision.get("standalone_query"))
    normalization_confidence = _confidence(
        router_decision.get("normalization_confidence")
    )
    context_confidence = _confidence(router_decision.get("context_confidence"))
    referenced_turns = _referenced_turns(router_decision.get("referenced_turns"))
    clarification = _clean_query(router_decision.get("clarification_question"))

    if selected_mode == "raw":
        return QueryHandlingResult(
            raw_query=raw_query,
            effective_query=raw_query,
            mode=selected_mode,
            context_mode=context_mode,
            source="raw_query",
            normalized_query=normalized_query,
            standalone_query=standalone_query,
            referenced_turns=referenced_turns,
            normalization_confidence=normalization_confidence,
            context_confidence=context_confidence,
        )

    if selected_mode == "router_generated":
        proposed = _clean_query(router_decision.get("retrieval_query")) or raw_query
        return QueryHandlingResult(
            raw_query=raw_query,
            effective_query=proposed,
            mode=selected_mode,
            context_mode=context_mode,
            source="router_retrieval_query" if proposed != raw_query else "raw_query",
            normalized_query=normalized_query,
            standalone_query=standalone_query,
            referenced_turns=referenced_turns,
            normalization_confidence=normalization_confidence,
            context_confidence=context_confidence,
        )

    if context_mode == "ambiguous":
        return _clarification_result(
            raw_query,
            selected_mode,
            context_mode,
            normalized_query,
            standalone_query,
            referenced_turns,
            normalization_confidence,
            context_confidence,
            ("ambiguous_context",),
            clarification,
        )

    if context_mode == "follow_up":
        history = _history_window(chat_history)
        errors = validate_follow_up_query(
            raw_query,
            standalone_query,
            referenced_turns=referenced_turns,
            chat_history=history,
            confidence=context_confidence,
            selected_cohort=selected_cohort,
        )
        if errors:
            return _clarification_result(
                raw_query,
                selected_mode,
                context_mode,
                normalized_query,
                standalone_query,
                referenced_turns,
                normalization_confidence,
                context_confidence,
                tuple(errors),
                clarification,
            )
        return QueryHandlingResult(
            raw_query=raw_query,
            effective_query=standalone_query or raw_query,
            mode=selected_mode,
            context_mode=context_mode,
            source="grounded_follow_up",
            normalized_query=normalized_query,
            standalone_query=standalone_query,
            referenced_turns=referenced_turns,
            normalization_confidence=normalization_confidence,
            context_confidence=context_confidence,
        )

    normalization_errors = validate_normalized_query(
        raw_query,
        normalized_query,
        corrections=router_decision.get("corrections"),
        confidence=normalization_confidence,
    )
    if normalized_query and not normalization_errors:
        return QueryHandlingResult(
            raw_query=raw_query,
            effective_query=normalized_query,
            mode=selected_mode,
            context_mode=context_mode,
            source="validated_normalization",
            normalized_query=normalized_query,
            standalone_query=standalone_query,
            referenced_turns=referenced_turns,
            normalization_confidence=normalization_confidence,
            context_confidence=context_confidence,
        )

    return QueryHandlingResult(
        raw_query=raw_query,
        effective_query=raw_query,
        mode=selected_mode,
        context_mode=context_mode,
        source="raw_query_fallback",
        normalized_query=normalized_query,
        standalone_query=standalone_query,
        referenced_turns=referenced_turns,
        normalization_confidence=normalization_confidence,
        context_confidence=context_confidence,
        validation_errors=tuple(normalization_errors),
    )


def validate_normalized_query(
    raw_query: str,
    normalized_query: str | None,
    *,
    corrections: Any = None,
    confidence: str = "none",
) -> list[str]:
    if not normalized_query:
        return ["missing_normalized_query"]
    if len(normalized_query) > MAX_QUERY_CHARS:
        return ["normalized_query_too_long"]
    if _extract_cohorts(raw_query) != _extract_cohorts(normalized_query):
        return ["normalization_changed_cohort"]
    if _extract_numbers(raw_query) != _extract_numbers(normalized_query):
        return ["normalization_changed_number"]

    raw_ascii = _ascii_text(raw_query)
    normalized_ascii = _ascii_text(normalized_query)
    if raw_ascii == normalized_ascii:
        return []
    if _confidence(confidence) != "high":
        return ["normalization_not_high_confidence"]

    correction_items = _corrections(corrections)
    if not correction_items:
        return ["normalization_missing_corrections"]

    corrected = raw_ascii
    for original_span, normalized_span in correction_items:
        original_ascii = _ascii_text(original_span)
        normalized_span_ascii = _ascii_text(normalized_span)
        if not original_ascii or original_ascii not in corrected:
            return ["normalization_correction_not_grounded"]
        if not normalized_span_ascii:
            return ["normalization_empty_replacement"]
        similarity = SequenceMatcher(
            None, original_ascii, normalized_span_ascii
        ).ratio()
        if similarity < 0.50:
            return ["normalization_correction_changes_meaning"]
        corrected = corrected.replace(original_ascii, normalized_span_ascii, 1)

    if SequenceMatcher(None, corrected, normalized_ascii).ratio() < 0.92:
        return ["normalization_contains_undeclared_changes"]
    return []


def validate_follow_up_query(
    raw_query: str,
    standalone_query: str | None,
    *,
    referenced_turns: tuple[int, ...],
    chat_history: list[dict[str, str]],
    confidence: str,
    selected_cohort: str | None,
) -> list[str]:
    errors: list[str] = []
    if _confidence(confidence) != "high":
        errors.append("follow_up_not_high_confidence")
    if not standalone_query:
        errors.append("missing_standalone_query")
        return errors
    if len(standalone_query) > MAX_QUERY_CHARS:
        errors.append("standalone_query_too_long")
    if not chat_history or not referenced_turns:
        errors.append("follow_up_missing_referenced_history")
        return errors
    if any(index < 0 or index >= len(chat_history) for index in referenced_turns):
        errors.append("follow_up_invalid_referenced_turn")
        return errors

    referenced_text = " ".join(
        str(chat_history[index].get("content") or "") for index in referenced_turns
    )
    grounded_text = f"{raw_query} {referenced_text}".strip()

    raw_cohorts = _extract_cohorts(raw_query)
    standalone_cohorts = _extract_cohorts(standalone_query)
    grounded_cohorts = _extract_cohorts(grounded_text)
    selected = _extract_cohorts(selected_cohort or "")
    if raw_cohorts and standalone_cohorts != raw_cohorts:
        errors.append("follow_up_changed_current_cohort")
    elif not standalone_cohorts.issubset(grounded_cohorts | selected):
        errors.append("follow_up_added_ungrounded_cohort")

    raw_numbers = _extract_numbers(raw_query)
    standalone_numbers = _extract_numbers(standalone_query)
    grounded_numbers = _extract_numbers(grounded_text)
    if not raw_numbers.issubset(standalone_numbers):
        errors.append("follow_up_dropped_current_number")
    if not standalone_numbers.issubset(grounded_numbers):
        errors.append("follow_up_added_ungrounded_number")

    raw_content = _content_tokens(raw_query)
    standalone_content = _content_tokens(standalone_query)
    grounded_content = _content_tokens(grounded_text)
    if raw_content:
        retained_ratio = len(raw_content & standalone_content) / len(raw_content)
        if retained_ratio < 0.65:
            errors.append("follow_up_dropped_current_topic")
    if len(standalone_content - grounded_content) > 2:
        errors.append("follow_up_added_ungrounded_content")
    return errors


def _clarification_result(
    raw_query: str,
    mode: str,
    context_mode: str,
    normalized_query: str | None,
    standalone_query: str | None,
    referenced_turns: tuple[int, ...],
    normalization_confidence: str,
    context_confidence: str,
    errors: tuple[str, ...],
    clarification_question: str | None,
) -> QueryHandlingResult:
    return QueryHandlingResult(
        raw_query=raw_query,
        effective_query=raw_query,
        mode=mode,
        context_mode=context_mode,
        source="clarification",
        normalized_query=normalized_query,
        standalone_query=standalone_query,
        referenced_turns=referenced_turns,
        normalization_confidence=normalization_confidence,
        context_confidence=context_confidence,
        validation_errors=errors,
        needs_clarification=True,
        clarification_question=clarification_question
        or (
            "Bạn muốn hỏi tiếp nội dung trước đó hay đang chuyển sang một chủ đề "
            "mới? Bạn có thể viết rõ câu hỏi đầy đủ hơn giúp mình nhé."
        ),
    )


def _history_window(
    chat_history: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for item in (chat_history or [])[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if content:
            output.append(
                {
                    "role": str(item.get("role") or "user"),
                    "content": content,
                }
            )
    return output


def _clean_query(value: Any) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned or len(cleaned) > MAX_QUERY_CHARS:
        return None
    return cleaned


def _confidence(value: Any) -> str:
    cleaned = str(value or "none").strip().lower()
    return cleaned if cleaned in CONFIDENCE_LEVELS else "none"


def _referenced_turns(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    output: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if index >= 0 and index not in output:
            output.append(index)
    return tuple(output)


def _corrections(value: Any) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        return []
    output: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        original = str(item.get("original_span") or "").strip()
        normalized = str(item.get("normalized_span") or "").strip()
        if original and normalized:
            output.append((original, normalized))
    return output


def _ascii_text(value: Any) -> str:
    text = str(value or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^a-z0-9%+.,-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _ascii_text(value)))


def _content_tokens(value: Any) -> set[str]:
    return {
        token
        for token in _tokens(value)
        if len(token) >= 2 and token not in _CONTENT_STOPWORDS
    }


def _extract_numbers(value: Any) -> set[str]:
    normalized = _ascii_text(value).replace(",", ".")
    return set(re.findall(r"(?<![a-z])\d+(?:\.\d+)?%?", normalized))


def _extract_cohorts(value: Any) -> set[str]:
    normalized = _ascii_text(value).replace(" ", "")
    output: set[str] = set()
    if re.search(r"k48(?:-k?49)?", normalized) or "k49" in normalized:
        output.add("K48-K49")
    if "k50" in normalized:
        output.add("K50")
    if "k51" in normalized:
        output.add("K51")
    return output
