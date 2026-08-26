from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_product_regression import _automatic_checks, load_cases, validate_cases


DATASET = Path("data/eval/product_regression/cases.json")


def test_product_regression_dataset_is_valid_and_balanced() -> None:
    payload, cases = load_cases(DATASET)

    assert payload["schema_version"] == "product-regression-v1"
    assert len(cases) == 30
    categories = {case["category"] for case in cases}
    assert {
        "structured_single",
        "structured_structured",
        "regulation_single",
        "regulation_regulation",
        "structured_regulation",
        "multi_cohort",
        "clarification",
        "partial_answer",
        "out_of_domain",
        "follow_up",
    } <= categories


def test_product_regression_rejects_duplicate_case_ids() -> None:
    _, cases = load_cases(DATASET)
    duplicate = json.loads(json.dumps(cases, ensure_ascii=False))
    duplicate[1]["id"] = duplicate[0]["id"]

    with pytest.raises(ValueError, match="Duplicate case id"):
        validate_cases(duplicate)


def test_automatic_checks_require_citation_for_each_covered_task() -> None:
    case = {
        "expected_outcome": "answered",
    }
    result = {
        "status": "answered",
        "coverage_by_task": {"t1": "covered", "t2": "covered"},
        "citations_used": [
            {"source_ref": "S1", "supports_task_ids": ["t1"]},
        ],
    }

    checks = _automatic_checks(case, result)

    assert checks["no_runtime_error"] is True
    assert checks["expected_outcome_shape"] is True
    assert checks["covered_tasks_have_citations"] is False


def test_automatic_checks_accept_out_of_domain_without_llm() -> None:
    case = {"expected_outcome": "out_of_domain"}
    result = {
        "status": "out_of_domain",
        "llm_called": False,
        "coverage_by_task": {},
        "citations_used": [],
    }

    assert all(_automatic_checks(case, result).values())

