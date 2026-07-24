import json
import os
from pathlib import Path
from unittest.mock import patch

from src.retrieval.core.retrieval_pipeline import run_retrieval_pipeline


FORMULAS_PATH = Path("data/processed/tables/formula_rules.json")
SCORING_PATH = Path("data/processed/tables/scoring_tables.json")


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(query: str, **kwargs):
    with (
        patch.dict(os.environ, {"STUDENT_RAG_DISABLE_AI_ROUTER": "1"}),
        patch("src.retrieval.core.retrieval_pipeline.retrieve_with_plan", return_value=[]),
    ):
        return run_retrieval_pipeline(
            query=query,
            model=None,
            collection=None,
            scoring_tables=kwargs.get("scoring_tables", []),
            formula_rules=kwargs.get("formula_rules", []),
            entity_registry=[],
            expansion_rules=[],
            cohort=kwargs.get("cohort"),
        )


def test_document_requirement_query_uses_regulation_path() -> None:
    result = _run("Muon tam nghi hoc can mau don nao?")

    assert result["strategy"] == "semantic_filtered"
    assert result["needs_llm_answer"] is True
    assert result.get("structured_result") in (None, {})


def test_formula_lookup_is_direct_when_formula_matches() -> None:
    result = _run(
        "Cong thuc tinh diem GPA la gi?",
        formula_rules=_load(FORMULAS_PATH),
        cohort="K50",
    )

    assert result["strategy"] == "formula_lookup"
    assert result["needs_llm_answer"] is False
    assert result["retrieved_items"] == []
    assert result["formula_result"]["rule_id"] == "gpa_weighted_average"
    assert result["formula_result"]["lookup_type"] == "formula"
    assert result["formula_result"]["cohort"] == "K50"
    assert result["citations"][0]["cohort"] == "K50"


def test_numeric_calculation_request_never_uses_removed_tool() -> None:
    result = _run("Ap dung cho K50, tinh diem hoc bong neu GPA 3.2 va ren luyen 90")

    assert result["strategy"] != "calculator_tool"
    assert "tool_result" not in result


def test_structured_lookup_is_direct_when_table_matches() -> None:
    result = _run(
        "Diem ren luyen 85 la loai gi?",
        scoring_tables=_load(SCORING_PATH),
        cohort="K50",
    )

    assert result["strategy"] == "structured_lookup"
    assert result["needs_llm_answer"] is False
    assert result["retrieved_items"] == []
    assert result["structured_result"]["lookup_type"] == "conduct_classification"


def test_numeric_score_maps_to_letter_grade() -> None:
    result = _run(
        "Diem 8.5 tuong ung diem chu nao?",
        scoring_tables=_load(SCORING_PATH),
        cohort="K50",
    )

    assert result["strategy"] == "structured_lookup"
    assert result["needs_llm_answer"] is False
    structured = result["structured_result"]
    assert structured["lookup_type"] == "grade_10_to_letter"
    assert isinstance(structured["result"], list)
    assert structured["result"]
    first = structured["result"][0]
    assert first["row"]["letter_grade"] == "A"
