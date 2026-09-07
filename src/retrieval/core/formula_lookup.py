from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.common.cohort import is_cohort_applicable, normalize_cohort


def formula_lookup(
    query: str,
    formula_rules: list[dict[str, Any]],
    cohort: str | None = None,
    slots: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve deterministic formula questions from extracted rules."""

    cohort = normalize_cohort(cohort)
    if cohort:
        formula_rules = [r for r in formula_rules if is_cohort_applicable(r, cohort)]

    # A supplied slot mapping is the planner/normalizer contract.  Even an
    # empty mapping is meaningful here: do not re-read the task question to
    # invent a formula family (or expand a single task into several formulas).
    if slots is not None:
        requested_types = _slot_values(slots.get("formula_type"))
        if not requested_types:
            return _all_formulas_result(query, formula_rules, cohort)

        matched: list[dict[str, Any]] = []
        for formula_type in requested_types:
            resolved = _find_formula_by_data(formula_rules, str(formula_type))
            if resolved is None:
                # A malformed/unknown requested choice must not silently turn
                # into a partial multi-formula answer.
                return None
            matched.append(resolved)
        matched = _dedupe_formula_results(matched)
        if not matched:
            return None
        if len(matched) == 1:
            return matched[0]
        return _multi_formula_result(query, matched, cohort)

    ascii_query = _ascii_text(query)
    explicit_rule_ids = _requested_rule_ids(ascii_query, formula_rules)
    if len(explicit_rule_ids) > 1 and _asks_for_multiple_formulas(ascii_query):
        matched = [
            result
            for rule_id in explicit_rule_ids
            if (result := _find_formula(formula_rules, rule_id)) is not None
        ]
        if len(matched) > 1:
            return {
                "lookup_type": "multi_formula",
                "formula_count": len(matched),
                "result": matched,
                "sub_lookups": matched,
                "cohort": cohort,
                "content_type": "multi_formula",
            }

    if not _asks_for_formula(ascii_query):
        return None

    preferred_rule_id = _preferred_rule_id(ascii_query)
    if preferred_rule_id:
        return _find_formula(formula_rules, preferred_rule_id)

    return None


def _slot_values(value: Any) -> list[Any]:
    """Return supplied slot choices without collapsing a list to one value."""

    if isinstance(value, list):
        return [item for item in value if item is not None and str(item).strip()]
    if value is None or not str(value).strip():
        return []
    return [value]


def _all_formulas_result(
    query: str,
    formula_rules: list[dict[str, Any]],
    cohort: str | None,
) -> dict[str, Any] | None:
    matched = [
        resolved
        for rule in formula_rules
        if (resolved := _find_formula(formula_rules, str(rule.get("rule_id") or "")))
        is not None
    ]
    matched = _dedupe_formula_results(matched)
    if not matched:
        return None
    return _multi_formula_result(query, matched, cohort)


def _dedupe_formula_results(
    matched: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in matched:
        key = str(item.get("rule_id") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(item)
    return deduped


def _multi_formula_result(
    query: str,
    matched: list[dict[str, Any]],
    cohort: str | None,
) -> dict[str, Any]:
    # Keep every requested formula as a separate leaf.  The dispatcher can
    # bind provenance for each leaf and, importantly, cannot treat this packet
    # as one uniquely resolved formula.
    return {
        "lookup_type": "multi_formula",
        "formula_count": len(matched),
        "result": matched,
        "sub_lookups": matched,
        "input_value": query,
        "cohort": cohort,
        "content_type": "multi_formula",
    }


def _find_formula_by_data(
    formula_rules: list[dict[str, Any]], formula_type: str
) -> dict[str, Any] | None:
    wanted = _ascii_text(formula_type)
    if not wanted:
        return None
    wanted_tokens = set(wanted.split())
    scored: list[tuple[int, dict[str, Any]]] = []
    for rule in formula_rules:
        searchable = _ascii_text(
            " ".join(
                str(rule.get(key) or "")
                for key in ("rule_id", "rule_name", "calculation_type")
            )
        )
        score = len(wanted_tokens & set(searchable.split()))
        if wanted == _ascii_text(rule.get("rule_id")):
            score += 20
        if wanted == _ascii_text(rule.get("calculation_type")):
            score += 15
        if wanted in searchable or searchable in wanted:
            score += 8
        if score > 0:
            scored.append((score, rule))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return _find_formula([scored[0][1]], str(scored[0][1].get("rule_id") or ""))


def _find_formula(
    formula_rules: list[dict[str, Any]],
    rule_id: str,
) -> dict[str, Any] | None:
    for rule in formula_rules:
        if rule.get("rule_id") == rule_id:
            return {
                "lookup_type": "formula",
                "formula_type": str(rule.get("calculation_type") or ""),
                "rule_id": rule.get("rule_id"),
                "rule_name": rule.get("rule_name"),
                "formula_text": rule.get("formula_text"),
                "variables": rule.get("variables") or {},
                "source_article": rule.get("source_article"),
                "source_pages": rule.get("source_pages") or [],
                "cohort": rule.get("cohort"),
                "document_id": rule.get("document_id"),
                "source_section": rule.get("source_section"),
                "source_parent_id": rule.get("source_parent_id"),
                "content_type": rule.get("content_type") or "formula_rule",
            }
    return None


def _preferred_rule_id(ascii_query: str) -> str | None:
    if (
        "gpa" in ascii_query
        or "diem trung binh" in ascii_query
        or "diem tbc" in ascii_query
        or re.search(r"\btbc\b", ascii_query)
        or re.search(r"\btb\b", ascii_query)
    ):
        return "gpa_weighted_average"

    if "hoc bong" in ascii_query:
        return "scholarship_score"

    return None


def _requested_rule_ids(
    ascii_query: str,
    formula_rules: list[dict[str, Any]],
) -> list[str]:
    """Return every formula family explicitly named by the user.

    The planner normally creates one task per formula. This deterministic
    completeness guard preserves multi-formula requests when a provider emits
    one combined structured task.
    """

    requested: list[str] = []
    for rule in formula_rules:
        rule_id = str(rule.get("rule_id") or "").strip()
        if not rule_id or rule_id in requested:
            continue
        folded_id = _ascii_text(rule_id.replace("_", " "))
        folded_name = _ascii_text(str(rule.get("rule_name") or ""))
        aliases = {folded_id, folded_name}
        if "gpa" in folded_id:
            aliases.update({"gpa", "diem trung binh", "diem tbc"})
        if "scholarship" in folded_id or "hoc bong" in folded_name:
            aliases.update({"hoc bong", "diem hoc bong"})
        if any(alias and alias in ascii_query for alias in aliases):
            requested.append(rule_id)
    return requested


def _asks_for_formula(ascii_query: str) -> bool:
    formula_terms = [
        "cong thuc",
        "cach tinh",
        "tinh kieu",
        "tinh kieu gi",
        "tinh nhu the nao",
        "tinh ra sao",
    ]
    return any(term in ascii_query for term in formula_terms)


def _asks_for_multiple_formulas(ascii_query: str) -> bool:
    return bool(
        re.search(r"\b(?:cac|nhung|hai)\s+cong thuc\b", ascii_query)
        or re.search(r"\bcong thuc\b.*\b(?:va|voi)\b", ascii_query)
    )


def _ascii_text(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    stripped = re.sub(r"[^a-zA-Z0-9]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped.lower()).strip()
