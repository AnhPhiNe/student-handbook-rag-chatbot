import json
from pathlib import Path

from src.generation.answer_guardrails import (
    build_deterministic_answer,
    can_answer_deterministically,
)
from src.retrieval.core.retrieval_pipeline import run_retrieval_pipeline
from src.retrieval.core.scholarship_lookup import scholarship_classification_lookup
from src.retrieval.core.study_duration_lookup import study_duration_lookup


SCORING_TABLES = Path("data/processed/tables/scoring_tables.json")
STRUCTURED_TABLES = Path("data/processed/tables/structured_tables_registry.json")


def load_scoring_tables() -> list[dict]:
    return json.loads(SCORING_TABLES.read_text(encoding="utf-8"))


def load_structured_tables() -> list[dict]:
    return json.loads(STRUCTURED_TABLES.read_text(encoding="utf-8"))


def test_study_duration_lookup_filters_cohort_and_mode() -> None:
    result = study_duration_lookup(
        "K50 hệ chính quy cấp bằng thứ nhất học tối đa bao nhiêu năm?",
        load_structured_tables(),
    )

    assert result is not None
    assert result["lookup_type"] == "study_duration"
    assert result["cohort"] == "K50"
    assert result["items"][0]["training_mode"] == "chinh_quy"
    row = result["items"][0]["rows"][0]
    assert row["Thời gian học tập tối đa"] == "8 năm học"


def test_study_duration_lookup_vlvh() -> None:
    result = study_duration_lookup(
        "K51 vừa làm vừa học cấp bằng thứ nhất thời gian chuẩn là bao lâu?",
        load_structured_tables(),
    )

    assert result is not None
    assert result["cohort"] == "K51"
    assert result["items"][0]["training_mode"] == "vua_lam_vua_hoc"
    assert result["items"][0]["rows"][0]["Thời gian học tập chuẩn"] == "05 năm học"


def test_scholarship_lookup_by_label() -> None:
    result = scholarship_classification_lookup(
        "K50 học bổng loại giỏi cần bao nhiêu điểm?",
        load_scoring_tables(),
    )

    assert result is not None
    assert result["lookup_type"] == "scholarship_classification"
    assert result["cohort"] == "K50"
    assert result["result"]["label"] == "Giỏi"
    assert result["result"]["scholarship_score_range"] == "3.20-3.672"


def test_scholarship_lookup_by_score() -> None:
    result = scholarship_classification_lookup(
        "điểm học bổng 3.7 xếp loại gì K51?",
        load_scoring_tables(),
    )

    assert result is not None
    assert result["cohort"] == "K51"
    assert result["result"]["label"] == "Xuất sắc"


def test_scholarship_policy_question_falls_back_to_rag() -> None:
    result = scholarship_classification_lookup(
        "Điều kiện xét học bổng khuyến khích học tập là gì?",
        load_scoring_tables(),
        cohort="K50",
    )

    assert result is None


def test_pipeline_returns_deterministic_study_duration(monkeypatch) -> None:
    monkeypatch.setenv("STUDENT_RAG_DISABLE_AI_ROUTER", "1")
    result = run_retrieval_pipeline(
        query="K50 hệ chính quy cấp bằng thứ nhất học tối đa bao nhiêu năm?",
        model=None,
        collection=None,
        scoring_tables=[],
        formula_rules=[],
        entity_registry=[],
        expansion_rules=[],
        structured_tables_registry=load_structured_tables(),
        cohort="K50",
    )

    assert result["strategy"] == "study_duration_lookup"
    assert result["needs_llm_answer"] is False
    assert can_answer_deterministically(result) is True
    assert "8 năm học" in build_deterministic_answer(result["query"], result)


def test_pipeline_returns_deterministic_scholarship_classification(monkeypatch) -> None:
    monkeypatch.setenv("STUDENT_RAG_DISABLE_AI_ROUTER", "1")
    result = run_retrieval_pipeline(
        query="K50 học bổng loại giỏi cần bao nhiêu điểm?",
        model=None,
        collection=None,
        scoring_tables=load_scoring_tables(),
        formula_rules=[],
        entity_registry=[],
        expansion_rules=[],
        cohort="K50",
    )

    assert result["strategy"] == "scholarship_classification_lookup"
    assert result["needs_llm_answer"] is False
    assert can_answer_deterministically(result) is True
    assert "Giỏi" in build_deterministic_answer(result["query"], result)


def test_numeric_score_answer_mentions_letter_grade(monkeypatch) -> None:
    monkeypatch.setenv("STUDENT_RAG_DISABLE_AI_ROUTER", "1")
    result = run_retrieval_pipeline(
        query="Điểm 8.5 tương ứng điểm chữ nào?",
        model=None,
        collection=None,
        scoring_tables=load_scoring_tables(),
        formula_rules=[],
        entity_registry=[],
        expansion_rules=[],
        cohort="K50",
    )

    assert result["strategy"] == "structured_lookup"
    answer = build_deterministic_answer(result["query"], result)
    assert "điểm chữ A" in answer
