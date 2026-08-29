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
    cohort = normalize_cohort(cohort)
    if cohort:
        formula_rules = [r for r in formula_rules if is_cohort_applicable(r, cohort)]

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

    if slots:
        formula_type = str(slots.get("formula_type") or "").strip()
        return _find_formula_by_data(formula_rules, formula_type)

    if not _asks_for_formula(ascii_query):
        return None

    preferred_rule_id = _preferred_rule_id(ascii_query)
    if preferred_rule_id:
        return _find_formula(formula_rules, preferred_rule_id)

    return None


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
