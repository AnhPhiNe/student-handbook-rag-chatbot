import json
from pathlib import Path

from src.generation.answer_guardrails import (
    build_deterministic_answer,
    can_answer_deterministically,
)
from src.retrieval.core.foreign_language_lookup import foreign_language_lookup
from src.retrieval.core.retrieval_pipeline import run_retrieval_pipeline


TABLE_PATH = Path("data/processed/tables/foreign_language_equivalency_table.json")


def load_tables() -> list[dict]:
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


def test_ielts_55_maps_to_level_4_for_k50() -> None:
    result = foreign_language_lookup("K50 IELTS 5.5 tương đương bậc mấy?", load_tables())

    assert result is not None
    assert result["lookup_type"] == "foreign_language_equivalency"
    assert result["cohort"] == "K50"
    assert result["result"]["certificate"] == "IELTS"
    assert result["result"]["matched_level"] == "bac_4"


def test_ielts_50_maps_to_level_3_for_k50() -> None:
    result = foreign_language_lookup("K50 IELTS 5.0 đạt bậc mấy?", load_tables())

    assert result is not None
    assert result["result"]["matched_level"] == "bac_3"


def test_hsk_bac_4_uses_k51_table() -> None:
    result = foreign_language_lookup("K51 HSK bậc 4 tương đương gì?", load_tables())

    assert result is not None
    assert result["cohort"] == "K51"
    assert result["result"]["certificate"] == "Hanyu Shuiping Kaoshi (HSK)"
    assert result["result"]["matched_level"] == "bac_4"


def test_jlpt_n3_maps_to_level_4() -> None:
    result = foreign_language_lookup("JLPT N3 chuẩn đầu ra ngoại ngữ K48", load_tables())

    assert result is not None
    assert result["cohort"] == "K48-K49"
    assert result["result"]["matched_level"] == "bac_4"


def test_policy_question_falls_back_to_rag() -> None:
    result = foreign_language_lookup(
        "Quy trình công nhận ngoại ngữ để xét tốt nghiệp như thế nào?",
        load_tables(),
        cohort="K50",
    )

    assert result is None


def test_pipeline_returns_deterministic_foreign_language_lookup(monkeypatch) -> None:
    monkeypatch.setenv("STUDENT_RAG_DISABLE_AI_ROUTER", "1")
    result = run_retrieval_pipeline(
        query="K50 IELTS 5.5 tương đương bậc mấy?",
        model=None,
        collection=None,
        scoring_tables=[],
        formula_rules=[],
        entity_registry=[],
        expansion_rules=[],
        foreign_language_tables=load_tables(),
        cohort="K50",
    )

    assert result["strategy"] == "foreign_language_lookup"
    assert result["needs_llm_answer"] is False
    assert can_answer_deterministically(result) is True
    answer = build_deterministic_answer(result["query"], result)
    assert "IELTS" in answer
    assert "bậc 4" in answer
