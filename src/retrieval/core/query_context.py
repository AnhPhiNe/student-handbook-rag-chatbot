from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any
import warnings


QUERY_HANDLING_MODES = {"raw", "validated"}
LEGACY_QUERY_HANDLING_MODES = {"router_generated", "context_only"}
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
class ReferencedEvidenceSpan:
    turn_id: int
    evidence_span: str

    def to_dict(self) -> dict[str, Any]:
        return {"turn_id": self.turn_id, "evidence_span": self.evidence_span}


@dataclass(frozen=True)
class QueryContextResult:
    raw_query: str
    effective_query: str
    mode: str
    context_mode: str
    effective_query_source: str
    normalized_query: str | None = None
    standalone_query: str | None = None
    referenced_turn_ids: tuple[int, ...] = ()
    referenced_evidence: tuple[ReferencedEvidenceSpan, ...] = ()
    normalization_confidence: str = "none"
    context_confidence: str = "none"
    validation_errors: tuple[str, ...] = ()
    needs_clarification: bool = False
    clarification_question: str | None = None

    @property
    def source(self) -> str:
        """Compatibility alias for older response consumers."""
        return self.effective_query_source

    @property
    def referenced_turns(self) -> tuple[int, ...]:
        """Compatibility alias for the pre-v2 field name."""
        return self.referenced_turn_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "effective_query": self.effective_query,
            "mode": self.mode,
            "context_mode": self.context_mode,
            "source": self.effective_query_source,
            "effective_query_source": self.effective_query_source,
            "normalized_query": self.normalized_query,
            "standalone_query": self.standalone_query,
            "referenced_turn_ids": list(self.referenced_turn_ids),
            "referenced_turns": list(self.referenced_turn_ids),
            "referenced_evidence": [
                item.to_dict() for item in self.referenced_evidence
            ],
            "normalization_confidence": self.normalization_confidence,
            "context_confidence": self.context_confidence,
            "validation_errors": list(self.validation_errors),
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
        }


# Kept as an import-compatible alias while callers migrate to QueryContextResult.
QueryHandlingResult = QueryContextResult


def query_handling_mode(value: str | None = None) -> str:
    candidate = (
        str(
            value or os.environ.get("STUDENT_RAG_QUERY_HANDLING_MODE") or "validated"
        )
        .strip()
        .lower()
    )
    if candidate in LEGACY_QUERY_HANDLING_MODES:
        warnings.warn(
            f"Query handling mode '{candidate}' is deprecated; using 'validated'.",
            DeprecationWarning,
            stacklevel=2,
        )
        return "validated"
    return candidate if candidate in QUERY_HANDLING_MODES else "validated"


def select_effective_query(
    raw_query: str,
    router_decision: dict[str, Any],
    *,
    chat_history: list[dict[str, str]] | None = None,
    selected_cohort: str | None = None,
    mode: str | None = None,
) -> QueryContextResult:
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
    referenced_turns = _referenced_turns(
        router_decision.get("referenced_turn_ids")
        or router_decision.get("referenced_turns")
    )
    referenced_evidence = _referenced_evidence(
        router_decision.get("referenced_evidence")
    )
    clarification = _clean_query(router_decision.get("clarification_question"))

    if selected_mode == "raw":
        return QueryContextResult(
            raw_query=raw_query,
            effective_query=raw_query,
            mode=selected_mode,
            context_mode=context_mode,
            effective_query_source="raw_query",
            normalized_query=normalized_query,
            standalone_query=standalone_query,
            referenced_turn_ids=referenced_turns,
            referenced_evidence=referenced_evidence,
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
            referenced_evidence,
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
            referenced_evidence=referenced_evidence,
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
                referenced_evidence,
                normalization_confidence,
                context_confidence,
                tuple(errors),
                clarification,
            )
        return QueryContextResult(
            raw_query=raw_query,
            effective_query=standalone_query or raw_query,
            mode=selected_mode,
            context_mode=context_mode,
            effective_query_source="grounded_follow_up",
            normalized_query=normalized_query,
            standalone_query=standalone_query,
            referenced_turn_ids=referenced_turns,
            referenced_evidence=referenced_evidence,
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
        return QueryContextResult(
            raw_query=raw_query,
            effective_query=normalized_query,
            mode=selected_mode,
            context_mode=context_mode,
            effective_query_source="validated_normalization",
            normalized_query=normalized_query,
            standalone_query=standalone_query,
            referenced_turn_ids=referenced_turns,
            referenced_evidence=referenced_evidence,
            normalization_confidence=normalization_confidence,
            context_confidence=context_confidence,
        )

    return QueryContextResult(
        raw_query=raw_query,
        effective_query=raw_query,
        mode=selected_mode,
        context_mode=context_mode,
        effective_query_source="raw_query_fallback",
        normalized_query=normalized_query,
        standalone_query=standalone_query,
        referenced_turn_ids=referenced_turns,
        referenced_evidence=referenced_evidence,
        normalization_confidence=normalization_confidence,
        context_confidence=context_confidence,
        validation_errors=tuple(normalization_errors),
    )


def validated_correction_provenance(
    router_decision: dict[str, Any],
    query_context: QueryContextResult,
) -> list[dict[str, str]]:
    """Return corrections only after the normalized query passed provenance checks."""

    if (
        query_context.effective_query_source != "validated_normalization"
        or query_context.validation_errors
    ):
        return []
    if _canonical_query(query_context.raw_query) == _canonical_query(
        query_context.normalized_query or ""
    ):
        # No correction was needed to produce the accepted normalization.
        # Ignore any model-declared corrections instead of treating unused
        # declarations as provenance for canonical structured slots.
        return []
    errors = validate_normalized_query(
        query_context.raw_query,
        query_context.normalized_query,
        corrections=router_decision.get("corrections"),
        confidence=query_context.normalization_confidence,
    )
    if errors:
        return []
    return [
        {"original_span": original, "normalized_span": normalized}
        for original, normalized in _corrections(router_decision.get("corrections"))
    ]


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

    if _canonical_query(raw_query) == _canonical_query(normalized_query):
        return []
    if _confidence(confidence) != "high":
        return ["normalization_not_high_confidence"]

    correction_items = _corrections(corrections)
    if not correction_items:
        return ["normalization_missing_corrections"]

    corrected = raw_query
    for original_span, normalized_span in correction_items:
        if not original_span or original_span not in corrected:
            return ["normalization_correction_not_grounded"]
        if not normalized_span:
            return ["normalization_empty_replacement"]
        if not _is_allowed_normalization(original_span, normalized_span):
            return ["normalization_correction_substitutes_content"]
        corrected = corrected.replace(original_span, normalized_span, 1)

    if _canonical_query(corrected) != _canonical_query(normalized_query):
        return ["normalization_contains_undeclared_changes"]
    return []


def validate_follow_up_query(
    raw_query: str,
    standalone_query: str | None,
    *,
    referenced_turns: tuple[int, ...],
    referenced_evidence: tuple[ReferencedEvidenceSpan, ...] = (),
    chat_history: list[dict[str, str]],
    confidence: str,
    selected_cohort: str | None,
) -> list[str]:
    errors: list[str] = []
    if _confidence(confidence) not in {"high", "medium"}:
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

    if not referenced_evidence:
        errors.append("follow_up_missing_evidence_spans")
        return errors

    referenced_text_parts: list[str] = []
    for evidence in referenced_evidence:
        if evidence.turn_id not in referenced_turns:
            errors.append("follow_up_evidence_turn_not_declared")
            continue
        if evidence.turn_id < 0 or evidence.turn_id >= len(chat_history):
            errors.append("follow_up_invalid_evidence_turn")
            continue
        turn_content = str(chat_history[evidence.turn_id].get("content") or "")
        if not evidence.evidence_span or evidence.evidence_span not in turn_content:
            errors.append("follow_up_evidence_span_not_grounded")
            continue
        referenced_text_parts.append(evidence.evidence_span)
    if errors:
        return errors

    referenced_text = " ".join(referenced_text_parts)
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

    standalone_content = _content_tokens(standalone_query)
    grounded_content = _content_tokens(grounded_text)
    # Additions must be fully attributable to the current query or declared
    # history evidence. We intentionally do not use token-coverage thresholds:
    # anaphora replacement may remove surface words while preserving all critical
    # cohort, number and negation invariants checked above.
    if not standalone_content.issubset(grounded_content):
        errors.append("follow_up_added_ungrounded_content")
    if _negation_markers(raw_query) != _negation_markers(standalone_query):
        errors.append("follow_up_changed_negation")
    return errors


def _clarification_result(
    raw_query: str,
    mode: str,
    context_mode: str,
    normalized_query: str | None,
    standalone_query: str | None,
    referenced_turns: tuple[int, ...],
    referenced_evidence: tuple[ReferencedEvidenceSpan, ...],
    normalization_confidence: str,
    context_confidence: str,
    errors: tuple[str, ...],
    clarification_question: str | None,
) -> QueryContextResult:
    return QueryContextResult(
        raw_query=raw_query,
        effective_query=raw_query,
        mode=mode,
        context_mode=context_mode,
        effective_query_source="clarification",
        normalized_query=normalized_query,
        standalone_query=standalone_query,
        referenced_turn_ids=referenced_turns,
        referenced_evidence=referenced_evidence,
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


def _referenced_evidence(value: Any) -> tuple[ReferencedEvidenceSpan, ...]:
    if not isinstance(value, list):
        return ()
    output: list[ReferencedEvidenceSpan] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        turn_id = item.get("turn_id")
        if isinstance(turn_id, bool) or not isinstance(turn_id, int) or turn_id < 0:
            continue
        evidence_span = str(item.get("evidence_span") or "").strip()
        if not evidence_span:
            continue
        evidence = ReferencedEvidenceSpan(turn_id, evidence_span)
        if evidence not in output:
            output.append(evidence)
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


def _canonical_query(value: Any) -> str:
    """Compare reconstructed text without applying semantic normalization."""
    return unicodedata.normalize("NFC", str(value or "")).strip()


def _is_allowed_normalization(original: str, replacement: str) -> bool:
    """Allow only accent/Unicode changes or a single local typo correction.

    The caller already proves the full proposal can be reconstructed from these
    edits, so this predicate deliberately avoids fuzzy whole-query similarity.
    """
    original_folded = _ascii_text(original)
    replacement_folded = _ascii_text(replacement)
    if not original_folded or not replacement_folded:
        return False
    if original_folded == replacement_folded:
        return True
    original_tokens = re.findall(r"[a-z0-9]+", original_folded)
    replacement_tokens = re.findall(r"[a-z0-9]+", replacement_folded)
    return (
        len(original_tokens) == len(replacement_tokens) == 1
        and min(len(original_tokens[0]), len(replacement_tokens[0])) >= 2
        and _is_single_typo(original_tokens[0], replacement_tokens[0])
    )


def _tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _ascii_text(value)))


def _is_safe_typo_correction(original_ascii: str, normalized_ascii: str) -> bool:
    original_tokens = re.findall(r"[a-z0-9]+", original_ascii)
    normalized_tokens = re.findall(r"[a-z0-9]+", normalized_ascii)
    if len(original_tokens) != len(normalized_tokens):
        return False
    if not original_tokens:
        return False
    return all(
        _is_single_typo(original, normalized)
        for original, normalized in zip(original_tokens, normalized_tokens)
    )


def _is_single_typo(original: str, normalized: str) -> bool:
    if original == normalized:
        return True
    if abs(len(original) - len(normalized)) > 1:
        return False
    if len(original) == len(normalized):
        differences = [
            index
            for index, (left, right) in enumerate(zip(original, normalized))
            if left != right
        ]
        if len(differences) == 1:
            return True
        if len(differences) == 2:
            first, second = differences
            return (
                second == first + 1
                and original[first] == normalized[second]
                and original[second] == normalized[first]
            )
        return False

    shorter, longer = (
        (original, normalized)
        if len(original) < len(normalized)
        else (normalized, original)
    )
    for index in range(len(longer)):
        if shorter == longer[:index] + longer[index + 1 :]:
            return True
    return False


def _content_tokens(value: Any) -> set[str]:
    return {
        token
        for token in _tokens(value)
        if len(token) >= 2 and token not in _CONTENT_STOPWORDS
    }


def _negation_markers(value: Any) -> set[str]:
    normalized = _ascii_text(value)
    markers: set[str] = set()
    if re.search(r"\bkhong\b", normalized):
        markers.add("khong")
    if re.search(r"\bchua\b", normalized):
        markers.add("chua")
    if re.search(r"\bnot\b", normalized):
        markers.add("not")
    return markers


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
