from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import src.common.cohort as cohort_module
from src.generation.answer_pipeline import AnswerPipeline
from src.generation.context_allocation import ContextAllocationConfig
from src.api.routes.chat import _to_chat_response
from src.retrieval.core.query_plan import (
    legacy_rag_plan,
    normalize_query_plan,
    query_plan_json_schema,
    query_plan_response_schema,
)
from src.retrieval.core.slang_normalizer import SlangNormalizer
from src.retrieval.core.structured_dispatcher import StructuredResolution
from src.retrieval.core.structured_routing import (
    router_json_schema,
    router_response_schema,
)


def _rag_task(index: int, question: str | None = None) -> dict[str, Any]:
    return {
        "id": f"t{index}",
        "question": question or f"Câu hỏi quy định {index}",
        "mode": "rag",
        "intent": "open_question",
        "lookup_type": None,
        "slots": {},
        "slot_spans": {},
        "cohorts": [],
        "clarification_question": None,
    }


def _plan(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "context_mode": "standalone",
        "normalized_query": "Câu hỏi tổng hợp",
        "standalone_query": None,
        "referenced_turns": [],
        "out_of_domain": False,
        "tasks": tasks,
    }


def test_query_plan_accepts_one_and_three_tasks() -> None:
    one, errors = normalize_query_plan(_plan([_rag_task(1)]), query="q", selected_cohort="K51")
    assert errors == []
    assert len(one["tasks"]) == 1
    assert one["tasks"][0]["cohorts"] == ["K51"]

    three, errors = normalize_query_plan(
        _plan([_rag_task(1), _rag_task(2), _rag_task(3)]),
        query="q",
    )
    assert errors == []
    assert [task["id"] for task in three["tasks"]] == ["t1", "t2", "t3"]


def test_native_plan_schema_keeps_structured_slots_as_optional_compatibility() -> None:
    task_schema = query_plan_response_schema()["properties"]["tasks"]["items"]

    assert "lookup_type" in task_schema["required"]
    assert "intent" not in task_schema["required"]
    assert "slots" not in task_schema["required"]
    assert "slot_spans" not in task_schema["required"]


def test_query_plan_turns_more_than_three_requests_into_clarification() -> None:
    plan, errors = normalize_query_plan(
        _plan([_rag_task(1), _rag_task(2), _rag_task(3), _rag_task(4)]),
        query="bốn yêu cầu",
        selected_cohort="K50",
    )
    assert errors == []
    assert len(plan["tasks"]) == 1
    assert plan["tasks"][0]["mode"] == "clarify"
    assert "tối đa ba" in plan["tasks"][0]["clarification_question"]


def test_invalid_lookup_is_clarified_but_reference_table_slots_are_optional() -> None:
    invalid = {
        **_rag_task(1),
        "mode": "structured",
        "lookup_type": "unknown_tool",
        "intent": "direct_value",
    }
    plan, errors = normalize_query_plan(_plan([invalid]), query="tra dữ liệu")
    assert plan["tasks"][0]["mode"] == "clarify"
    assert any("unknown_lookup_type" in error for error in errors)

    missing = {
        **_rag_task(1, "IELTS tương đương bậc mấy?"),
        "mode": "structured",
        "lookup_type": "foreign_language",
        "intent": "direct_value",
    }
    plan, errors = normalize_query_plan(
        _plan([missing]),
        query=missing["question"],
        selected_cohort="K51",
    )
    assert errors == []
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["lookup_type"] == "foreign_language"
    assert plan["tasks"][0]["slots"] == {"certificate_or_language": "IELTS"}


def test_explicit_multi_cohort_is_preserved_over_ui_cohort() -> None:
    task = {**_rag_task(1), "cohorts": ["K50", "K51"]}
    plan, _ = normalize_query_plan(_plan([task]), query="so sánh K50 K51", selected_cohort="K48-K49")
    assert plan["tasks"][0]["cohorts"] == ["K50", "K51"]


@pytest.mark.parametrize(
    ("lookup_type", "query", "slots", "slot_spans", "expected_intent"),
    [
        (
            "study_duration",
            "So sánh thời gian đào tạo hệ chính quy giữa K50 và K51.",
            {"training_mode": "chinh_quy", "program_type": "first_degree"},
            {
                "training_mode": "hệ chính quy",
                "program_type": "thời gian đào tạo",
            },
            "direct_value",
        ),
        (
            "foreign_language",
            "So sánh IELTS 6.0 giữa K50 và K51.",
            {"certificate_or_language": "IELTS", "score_or_level": "6.0"},
            {"certificate_or_language": "IELTS", "score_or_level": "6.0"},
            "direct_value",
        ),
        (
            "scholarship_classification",
            "So sánh học bổng loại Giỏi giữa K50 và K51.",
            {"score_or_label": "Giỏi"},
            {"score_or_label": "Giỏi"},
            "direct_value",
        ),
        (
            "scoring",
            "So sánh xếp loại điểm rèn luyện 85 giữa K50 và K51.",
            {"operation": "conduct_classification", "score_or_grade": 85},
            {"score_or_grade": "85"},
            "direct_value",
        ),
    ],
)
def test_structured_compare_uses_each_lookup_base_intent(
    lookup_type: str,
    query: str,
    slots: dict[str, Any],
    slot_spans: dict[str, Any],
    expected_intent: str,
) -> None:
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "compare",
        "lookup_type": lookup_type,
        "slots": slots,
        "slot_spans": slot_spans,
        "cohorts": ["K50", "K51"],
    }

    plan, errors = normalize_query_plan(
        _plan([task]),
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert len(plan["tasks"]) == 1
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["intent"] == expected_intent
    assert plan["tasks"][0]["cohorts"] == ["K50", "K51"]


def test_single_cohort_compare_is_also_presentation_only() -> None:
    query = "So sánh IELTS và TOEFL ở K51."
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "compare",
        "lookup_type": "foreign_language",
        "cohorts": ["K51"],
    }

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert errors == []
    assert plan["tasks"][0]["intent"] == "direct_value"
    assert plan["tasks"][0]["question"] == query
    assert plan["tasks"][0]["cohorts"] == ["K51"]


def test_two_regulation_topics_keep_two_tasks_with_the_same_cohorts() -> None:
    first = {**_rag_task(1, "Quy định đăng ký học phần là gì?"), "cohorts": ["K50", "K51"]}
    second = {**_rag_task(2, "Quy định hoãn thi là gì?"), "cohorts": ["K50", "K51"]}

    plan, errors = normalize_query_plan(
        _plan([first, second]),
        query="So sánh K50 và K51 về đăng ký học phần và hoãn thi.",
    )

    assert errors == []
    assert len(plan["tasks"]) == 2
    assert [task["cohorts"] for task in plan["tasks"]] == [
        ["K50", "K51"],
        ["K50", "K51"],
    ]
    assert all(task["intent"] == "open_question" for task in plan["tasks"])


def test_single_query_cohort_fills_every_task_without_scope() -> None:
    plan, errors = normalize_query_plan(
        _plan([_rag_task(1), _rag_task(2)]),
        query="K51 cho biết quy định thứ nhất. Quy định thứ hai là gì?",
    )

    assert errors == []
    assert [task["cohorts"] for task in plan["tasks"]] == [["K51"], ["K51"]]


def test_rag_intent_is_canonicalized_to_open_question() -> None:
    task = {**_rag_task(1), "intent": "invented_regulation_taxonomy"}

    plan, errors = normalize_query_plan(_plan([task]), query="quy định học vụ")

    assert errors == []
    assert plan["tasks"][0]["intent"] == "open_question"
    assert plan["tasks"][0]["lookup_type"] is None


def test_offset_slot_spans_are_normalized_to_grounded_literals() -> None:
    query = "K51 IELTS 6.0 tương đương bậc mấy?"
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": "foreign_language",
        "slots": {"certificate_or_language": "IELTS", "score_or_level": "6.0"},
        "slot_spans": {
            "certificate_or_language": [{"start": 4, "end": 9}],
            "score_or_level": [{"start": 10, "end": 13}],
        },
        "cohorts": ["K51"],
    }
    plan, errors = normalize_query_plan(_plan([task]), query=query)
    assert errors == []
    assert plan["tasks"][0]["slot_spans"] == {
        "certificate_or_language": ["IELTS"],
        "score_or_level": ["6.0"],
    }


def test_per_cohort_rag_copies_merge_into_one_logical_task() -> None:
    first = {**_rag_task(1, "Thời gian học tối đa của K50 là bao lâu?"), "cohorts": ["K50"]}
    second = {**_rag_task(2, "Thời gian học tối đa của K51 là bao lâu?"), "cohorts": ["K51"]}
    plan, errors = normalize_query_plan(_plan([first, second]), query="So sánh K50 và K51")
    assert errors == []
    assert len(plan["tasks"]) == 1
    assert plan["tasks"][0]["cohorts"] == ["K50", "K51"]


def test_extended_cohort_registry_drives_schema_normalization_and_merging(
    monkeypatch,
) -> None:
    monkeypatch.setitem(
        cohort_module.COHORT_REGISTRY,
        "K52",
        {
            "aliases": ("K52", "K52+"),
            "admission_years": (2026,),
        },
    )

    assert cohort_module.normalize_cohort("k52+") == "K52"
    assert cohort_module.admission_years_for_cohort("K52") == (2026,)
    assert "K52" in query_plan_json_schema()["tasks"][0]["cohorts"]
    assert "K52" in query_plan_response_schema()["properties"]["tasks"]["items"][
        "properties"
    ]["cohorts"]["items"]["enum"]
    assert "K52" in router_json_schema()["cohorts"]
    assert "K52" in router_response_schema()["properties"]["cohorts"]["items"][
        "enum"
    ]

    first = {
        **_rag_task(1, "Quy định đăng ký học phần của K51 là gì?"),
        "cohorts": ["K51"],
    }
    second = {
        **_rag_task(2, "Quy định đăng ký học phần của K52+ là gì?"),
        "cohorts": ["K52+"],
    }
    plan, errors = normalize_query_plan(
        _plan([first, second]),
        query="So sánh K51 và K52+ về quy định đăng ký học phần",
    )

    assert errors == []
    assert len(plan["tasks"]) == 1
    assert plan["tasks"][0]["cohorts"] == ["K51", "K52"]


def test_legacy_fallback_is_one_regulation_rag_task() -> None:
    plan = legacy_rag_plan("quy định học vụ", "K51", reason="legacy_rag")
    assert plan["planner_fallback"] == "legacy_rag"
    assert plan["tasks"] == [
        {
            "id": "t1",
            "question": "quy định học vụ",
            "mode": "rag",
            "intent": "open_question",
            "lookup_type": None,
            "slots": {},
            "slot_spans": {},
            "cohorts": ["K51"],
            "clarification_question": None,
            "validation_errors": [],
        }
    ]


def _pipeline(plan: dict[str, Any]) -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.router = type("Planner", (), {"plan": lambda self, *args, **kwargs: plan})()
    pipeline.slang_normalizer = SlangNormalizer()
    pipeline.config = {
        "planning": {"enabled": True, "max_citations": 10},
        "retrieval": {"batch_size": 8, "candidate_multiplier": 5, "min_candidates": 24},
        "embedding": {"normalize_embeddings": True},
    }
    pipeline.model = None
    pipeline.collection = None
    pipeline.scoring_tables = []
    pipeline.formula_rules = []
    pipeline.entity_registry = []
    pipeline.expansion_rules = []
    pipeline.student_office_profiles = []
    pipeline.student_service_directory = []
    pipeline.student_faculty_profiles = []
    pipeline.foreign_language_tables = []
    pipeline.structured_tables_registry = []
    pipeline.program_directory = []
    pipeline.parent_sources_by_id = {}
    return pipeline


def test_two_structured_domains_execute_without_cross_domain_probing(monkeypatch) -> None:
    tasks = [
        {
            **_rag_task(1, "IELTS 6.0 tương đương bậc mấy?"),
            "mode": "structured",
            "lookup_type": "foreign_language",
            "intent": "direct_value",
            "cohorts": ["K51"],
        },
        {
            **_rag_task(2, "Điểm học bổng loại giỏi là bao nhiêu?"),
            "mode": "structured",
            "lookup_type": "scholarship_classification",
            "intent": "direct_value",
            "cohorts": ["K51"],
        },
    ]
    calls: list[tuple[str, bool]] = []

    def fake_resolve(decision, **kwargs):
        calls.append((decision["lookup_type"], kwargs["probe_other_domains"]))
        lookup_type = decision["lookup_type"]
        return StructuredResolution(
            lookup_type=lookup_type,
            strategy=f"{lookup_type}_lookup",
            result_kind="lookup",
            result={
                "lookup_type": lookup_type,
                "result": [{"value": lookup_type}],
                "cohort": "K51",
                "document_id": f"doc-{lookup_type}",
                "source_parent_id": f"parent-{lookup_type}",
                "source_pages": [1],
                "table_name": lookup_type,
            },
            target_chunk_types=["structured_lookup"],
        )

    monkeypatch.setattr(
        "src.retrieval.core.structured_dispatcher.resolve_structured_decision",
        fake_resolve,
    )
    result = _pipeline(_plan(tasks))._run_query_plan(query="hai ý", cohort="K51", chat_history=[])
    assert calls == [("foreign_language", False), ("scholarship_classification", False)]
    assert result["coverage_by_task"] == {"t1": "covered", "t2": "covered"}
    assert len(result["citations"]) == 2


def test_one_study_duration_task_executes_each_cohort_from_full_tables() -> None:
    task = {
        **_rag_task(
            1,
            "So sánh thời gian đào tạo tối đa hệ chính quy giữa K50 và K51.",
        ),
        "mode": "structured",
        "lookup_type": "study_duration",
        "intent": "direct_value",
        "cohorts": ["K50", "K51"],
    }
    pipeline = _pipeline(_plan([task]))
    pipeline.structured_tables_registry = json.loads(
        Path("data/processed/tables/structured_tables_registry.json").read_text(
            encoding="utf-8"
        )
    )

    result = pipeline._run_query_plan(
        query=task["question"],
        cohort="K51",
        chat_history=[],
    )

    assert result["coverage_by_task"] == {"t1": "covered"}
    assert result["task_results"][0]["coverage_by_cohort"] == {
        "K50": "covered",
        "K51": "covered",
    }
    assert len(result["structured_result"]["sub_lookups"]) == 2
    assert {citation["cohort"] for citation in result["citations"]} == {
        "K50",
        "K51",
    }


def test_rag_tasks_keep_top_five_and_deduplicate_shared_source(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    def fake_retrieval(**kwargs):
        calls.append((kwargs["query"], kwargs["top_k"]))
        return {
            "retrieved_items": [
                {
                    "chunk_id": "shared-parent",
                    "content": f"Nguồn cho {kwargs['query']}",
                    "metadata": {"cohort": "K51", "chunk_type": "rule"},
                }
            ],
            "citations": [
                {
                    "chunk_id": "shared-parent",
                    "source_parent_id": "shared-parent",
                    "cohort": "K51",
                    "source_pages": [10],
                }
            ],
        }

    monkeypatch.setattr("src.generation.answer_pipeline.run_hybrid_retrieval_pipeline", fake_retrieval)
    result = _pipeline(_plan([_rag_task(1, "quy định một"), _rag_task(2, "quy định hai")]))._run_query_plan(
        query="hai quy định", cohort="K51", chat_history=[]
    )
    assert calls == [("quy định một", 5), ("quy định hai", 5)]
    assert len(result["retrieved_items"]) == 1
    assert len(result["citations"]) == 1
    assert result["citations"][0]["supports_task_ids"] == ["t1", "t2"]
    assert result["coverage_by_task"] == {"t1": "covered", "t2": "covered"}


def test_covered_and_uncovered_tasks_keep_partial_answer_path(monkeypatch) -> None:
    def fake_retrieval(**kwargs):
        if "đủ nguồn" not in kwargs["query"]:
            return {"retrieved_items": [], "citations": []}
        return {
            "retrieved_items": [{"chunk_id": "p1", "content": "Có nguồn", "metadata": {"cohort": "K51"}}],
            "citations": [{"chunk_id": "p1", "source_parent_id": "p1", "cohort": "K51"}],
        }

    monkeypatch.setattr("src.generation.answer_pipeline.run_hybrid_retrieval_pipeline", fake_retrieval)
    result = _pipeline(_plan([_rag_task(1, "ý đủ nguồn"), _rag_task(2, "ý thiếu")]))._run_query_plan(
        query="hai ý", cohort="K51", chat_history=[]
    )
    assert result["coverage_by_task"] == {"t1": "covered", "t2": "uncovered"}
    assert result["needs_llm_answer"] is True
    assert result["needs_clarification"] is False


def test_sync_and_stream_metadata_share_plan_coverage_and_fallback() -> None:
    pipeline = _pipeline(_plan([_rag_task(1)]))
    retrieval_result = {
        "query_plan": _plan([_rag_task(1)]),
        "task_results": [{"task_id": "t1", "coverage": "covered"}],
        "coverage_by_task": {"t1": "covered"},
        "planner_fallback": "legacy_rag",
        "supports_task_ids": {"p1": ["t1"]},
        "citations": [{"chunk_id": "p1", "supports_task_ids": ["t1"]}],
        "effective_query": "q",
        "selected_cohort": "K51",
    }
    output = pipeline._build_output(
        query="q",
        retrieval_result=retrieval_result,
        final_answer="a",
        context_used="",
        selected_citations=retrieval_result["citations"],
        status="answered",
        error_type=None,
        error_message=None,
        llm_called=True,
        used_cache=False,
    )
    metadata = pipeline._build_stream_metadata(
        retrieval_result,
        status="answered",
        effective_query="q",
        citations_used=retrieval_result["citations"],
        llm_called=True,
    )
    for key in (
        "query_plan",
        "task_results",
        "coverage_by_task",
        "planner_fallback",
        "supports_task_ids",
    ):
        assert output[key] == metadata[key]


def test_compound_plan_calls_answer_llm_once(monkeypatch) -> None:
    retrieval_result = {
        "query_plan": _plan([_rag_task(1), _rag_task(2)]),
        "task_results": [
            {"task_id": "t1", "coverage": "covered"},
            {"task_id": "t2", "coverage": "uncovered"},
        ],
        "coverage_by_task": {"t1": "covered", "t2": "uncovered"},
        "planner_fallback": None,
        "supports_task_ids": {"p1": ["t1"]},
        "query": "hai ý",
        "effective_query": "hai ý",
        "intent": "multi_task",
        "strategy": "query_plan_execution",
        "execution_mode": "rag",
        "selected_cohort": "K51",
        "retrieved_items": [
            {
                "chunk_id": "p1",
                "content": "Nguồn trực tiếp",
                "supports_task_ids": ["t1"],
                "metadata": {"cohort": "K51", "chunk_type": "rule", "supports_task_ids": ["t1"]},
            }
        ],
        "citations": [{"chunk_id": "p1", "source_parent_id": "p1", "cohort": "K51", "supports_task_ids": ["t1"]}],
        "structured_result": None,
        "needs_clarification": False,
        "out_of_domain": False,
    }
    pipeline = _pipeline(retrieval_result["query_plan"])
    pipeline.max_context_chars = 10000
    pipeline.context_allocation = ContextAllocationConfig.from_config({"strategy": "full_sources"})
    pipeline.llm_config = {"model_name": "fake"}
    pipeline.config.update({"citations": {"max_sources": 5}, "guardrails": {"skip_llm_on_low_confidence": True}})
    pipeline._run_retrieval = lambda *args, **kwargs: retrieval_result
    pipeline._throttle_llm_call = lambda: None

    class Cache:
        def make_cache_key(self, **kwargs):
            return "key"

        def get(self, key):
            return None

        def set(self, key, value):
            return None

    class LLM:
        calls = 0

        def generate(self, prompt):
            self.calls += 1
            assert "coverage" in prompt
            return {"ok": True, "text": "Trả lời phần đủ nguồn", "model_used": "fake", "usage": {}}

    llm = LLM()
    pipeline.response_cache = Cache()
    pipeline._get_llm_client = lambda: llm
    monkeypatch.setattr("src.generation.answer_pipeline.resolve_cohort_from_query", lambda query, cohort: cohort)

    output = pipeline.answer("hai ý", cohort="K51")
    assert output["status"] == "answered"
    assert output["llm_called"] is True
    assert llm.calls == 1


def test_query_plan_telemetry_is_hidden_without_api_debug() -> None:
    result = {
        "answer": "a",
        "status": "answered",
        "query_plan": _plan([_rag_task(1)]),
        "task_results": [{"task_id": "t1", "coverage": "covered"}],
        "coverage_by_task": {"t1": "covered"},
        "planner_fallback": None,
        "supports_task_ids": {"p1": ["t1"]},
        "citations_used": [{"chunk_id": "p1", "task_id": "t1", "supports_task_ids": ["t1"]}],
    }
    production = _to_chat_response(result, include_debug=False)
    debug = _to_chat_response(result, include_debug=True)
    assert production.debug is None
    assert "task_id" not in production.citations_used[0]
    assert debug.debug["query_plan"]["schema_version"] == "v1"
    assert debug.debug["coverage_by_task"] == {"t1": "covered"}
    assert debug.citations_used[0]["supports_task_ids"] == ["t1"]
