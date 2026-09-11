from __future__ import annotations

from functools import partial
from typing import Any

from src.common.cohort import is_cohort_applicable, normalize_cohort
from src.common.text import fold_text
from src.common.text import slot_values as _slot_values


def formula_lookup(
    query: str,
    formula_rules: list[dict[str, Any]],
    cohort: str | None = None,
    *,
    slots: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve formula rules from validated structured slots."""

    cohort = normalize_cohort(cohort)
    if cohort:
        formula_rules = [r for r in formula_rules if is_cohort_applicable(r, cohort)]

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


_ascii_text = partial(fold_text, keep="")
