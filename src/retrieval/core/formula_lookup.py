from __future__ import annotations

import re
import unicodedata
from typing import Any


def formula_lookup(
    query: str, formula_rules: list[dict[str, Any]], cohort: str | None = None
) -> dict[str, Any] | None:
    ascii_query = _ascii_text(query)
    if not _asks_for_formula(ascii_query):
        return None

    if cohort:
        formula_rules = [r for r in formula_rules if r.get("cohort") == cohort]

    preferred_rule_id = _preferred_rule_id(ascii_query)
    if preferred_rule_id:
        return _find_formula(formula_rules, preferred_rule_id)

    return None


def _find_formula(
    formula_rules: list[dict[str, Any]],
    rule_id: str,
) -> dict[str, Any] | None:
    for rule in formula_rules:
        if rule.get("rule_id") == rule_id:
            return {
                "formula_type": str(rule.get("calculation_type") or ""),
                "rule_id": rule.get("rule_id"),
                "rule_name": rule.get("rule_name"),
                "formula_text": rule.get("formula_text"),
                "variables": rule.get("variables") or {},
                "calculator_function": rule.get("calculator_function"),
                "source_article": rule.get("source_article"),
                "source_pages": rule.get("source_pages") or [],
            }
    return None


def _preferred_rule_id(ascii_query: str) -> str | None:
    if "hoc bong" in ascii_query:
        return "scholarship_score"

    if (
        "gpa" in ascii_query
        or "diem trung binh" in ascii_query
        or "diem tbc" in ascii_query
        or re.search(r"\btbc\b", ascii_query)
        or re.search(r"\btb\b", ascii_query)
    ):
        return "gpa_weighted_average"

    return None


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


def _ascii_text(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    stripped = re.sub(r"[^a-zA-Z0-9]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped.lower()).strip()
