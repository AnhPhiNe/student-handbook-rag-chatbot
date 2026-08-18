from __future__ import annotations

from typing import Any

from src.generation.answer_pipeline import AnswerPipeline
from src.generation.context_allocation import build_context_for_prompt


def _pipeline() -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.config = {
        "retrieval": {
            "default_top_k": 5,
            "candidate_multiplier": 5,
            "min_candidates": 25,
        },
        "embedding": {"normalize_embeddings": True},
    }
    pipeline.model = object()
    pipeline.collection = object()
    pipeline.scoring_tables = []
    pipeline.formula_rules = []
    pipeline.entity_registry = []
    pipeline.expansion_rules = {}
    pipeline.student_office_profiles = []
    pipeline.student_service_directory = []
    pipeline.student_faculty_profiles = []
    pipeline.foreign_language_tables = []
    pipeline.structured_tables_registry = []
    pipeline.program_directory = []
    pipeline.parent_sources_by_id = {}

    class Normalizer:
        def replace_for_router(self, value: str) -> str:
            return f"router::{value}"

        def normalize_for_retrieval(self, value: str) -> str:
            return f"slang::{value}"

    pipeline.slang_normalizer = Normalizer()
    return pipeline


def _request(
    *,
    request_kind: str,
    intent: str,
    query_span: str,
    lookup_type: str | None = None,
    slots: dict[str, Any] | None = None,
    cohort_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "request_kind": request_kind,
        "lookup_type": lookup_type,
        "intent": intent,
        "query_span": query_span,
        "slots": slots or {},
        "slot_spans": {},
        "cohort_refs": cohort_refs or [],
    }


def _decision(
    query: str,
    requests: list[dict[str, Any]],
    *,
    cohorts: list[str] | None = None,
) -> dict[str, Any]:
    cohorts = cohorts or ["K51"]
    return {
        "context_mode": "standalone",
        "context_confidence": "high",
        "normalized_query": query,
        "normalization_confidence": "high",
        "corrections": [],
        "standalone_query": None,
        "referenced_turns": [],
        "route": "rag" if len(requests) > 1 else (
            "structured" if requests[0]["request_kind"] == "structured" else "rag"
        ),
        "execution_mode": "mixed" if len(requests) > 1 else (
            "structured" if requests[0]["request_kind"] == "structured" else "regulation"
        ),
        "intent": "multi_request" if len(requests) > 1 else requests[0]["intent"],
        "lookup_type": next(
            (
                request.get("lookup_type")
                for request in requests
                if request.get("lookup_type")
            ),
            None,
        ),
        "cohort": cohorts[0] if cohorts else None,
        "cohorts": cohorts,
        "is_multi_cohort": len(cohorts) > 1,
        "lookup_requests": requests,
    }


class Router:
    def __init__(self, decision: dict[str, Any]) -> None:
        self.decision = decision

    def route(self, query, chat_history=None, cohort=None):
        return self.decision


def _scoring_table() -> dict[str, Any]:
    return {
        "table_id": "academic_classification",
        "table_name": "Xếp loại học lực",
        "cohort": "K51",
        "document_id": "handbook-k51",
        "source_section_id": "K51_Dieu11",
        "source_pages": [22],
        "rows": [
            {"range": "3.20-3.59", "label": "Giỏi"},
            {"range": "2.50-3.19", "label": "Khá"},
        ],
    }


def _foreign_language_table() -> dict[str, Any]:
    return {
        "table_id": "foreign_language_equivalency_table",
        "table_name": "Quy đổi chứng chỉ ngoại ngữ",
        "cohort": "K51",
        "document_id": "handbook-k51",
        "source_section_id": "K51_Dieu8",
        "source_pages": [14],
        "applicable_cohorts": ["K51"],
        "rows": [
            {
                "language": "Tiếng Anh",
                "certificate": "IELTS",
                "level_or_scale": "IELTS",
                "equivalent_level_3": "4.0 - 5.0",
                "equivalent_level_4": "5.5 - 6.5",
            }
        ],
    }


def test_two_structured_requests_keep_numeric_slots_isolated() -> None:
    pipeline = _pipeline()
    pipeline.scoring_tables = [_scoring_table()]
    pipeline.foreign_language_tables = [_foreign_language_table()]
    query = "IELTS 6.0 tương đương bậc mấy và GPA 3.4 xếp loại gì?"
    requests = [
        _request(
            request_kind="structured",
            lookup_type="foreign_language",
            intent="direct_value",
            query_span="IELTS 6.0 tương đương bậc mấy",
            slots={
                "certificate_or_language": "IELTS",
                "score_or_level": "6.0",
            },
            cohort_refs=["K51"],
        ),
        _request(
            request_kind="structured",
            lookup_type="scoring",
            intent="direct_value",
            query_span="GPA 3.4 xếp loại gì",
            slots={
                "operation": "academic_classification",
                "score_or_grade": 3.4,
            },
            cohort_refs=["K51"],
        ),
    ]
    pipeline.router = Router(_decision(query, requests))

    result = pipeline._run_retrieval(query, cohort="K51")

    assert result["structured_result"]["lookup_type"] == "multi_request"
    children = result["structured_result"]["sub_results"]
    assert children[0]["result"]["result"]["matched_value"] == 6.0
    assert children[1]["result"]["input_value"] == 3.4
    assert children[1]["result"]["result"]["label"] == "Giỏi"
    assert [citation["request_index"] for citation in result["citations"]] == [0, 1]
    assert result["needs_llm_answer"] is True


def test_structured_and_rag_requests_execute_independently(monkeypatch) -> None:
    pipeline = _pipeline()
    pipeline.program_directory = [
        {
            "program_name": "Công nghệ Thông tin",
            "faculty_name": "Khoa Công nghệ Thông tin",
            "cohort": "K51",
            "document_id": "program-catalog-k51",
            "source_record_id": "program-cntt",
        }
    ]
    query = "Ngành Công nghệ Thông tin thuộc khoa nào và điều kiện tốt nghiệp là gì?"
    requests = [
        _request(
            request_kind="structured",
            lookup_type="program",
            intent="direct_value",
            query_span="Ngành Công nghệ Thông tin thuộc khoa nào",
            slots={
                "program_or_faculty": "Công nghệ Thông tin",
                "requested_field": "faculty",
            },
            cohort_refs=["K51"],
        ),
        _request(
            request_kind="rag",
            intent="policy",
            query_span="điều kiện tốt nghiệp là gì",
            cohort_refs=["K51"],
        ),
    ]
    pipeline.router = Router(_decision(query, requests))
    calls = []

    def fake_hybrid(**kwargs):
        calls.append(kwargs)
        return {
            "retrieved_items": [
                {
                    "chunk_id": "graduation-rule",
                    "content": "Điều kiện tốt nghiệp.",
                    "metadata": {
                        "title": "Điều kiện tốt nghiệp",
                        "chunk_type": "regulation",
                        "document_id": "handbook-k51",
                        "cohort": kwargs["cohort"],
                    },
                }
            ],
            "citations": [
                {
                    "chunk_id": "graduation-rule",
                    "title": "Điều kiện tốt nghiệp",
                    "document_id": "handbook-k51",
                    "cohort": kwargs["cohort"],
                }
            ],
            "related_items": [],
            "related_references": [],
        }

    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        fake_hybrid,
    )

    result = pipeline._run_retrieval(query, cohort="K51")

    assert [call["query"] for call in calls] == ["điều kiện tốt nghiệp là gì"]
    assert calls[0]["retrieval_query"] == "slang::điều kiện tốt nghiệp là gì"
    assert result["structured_result"]["lookup_type"] == "program_directory"
    assert result["retrieved_items"][0]["request_index"] == 1
    assert {citation["request_index"] for citation in result["citations"]} == {0, 1}


def test_unresolved_structured_request_falls_back_only_its_clause(monkeypatch) -> None:
    pipeline = _pipeline()
    query = "IELTS 9.0 tương đương bậc mấy và thủ tục bảo lưu thế nào?"
    requests = [
        _request(
            request_kind="structured",
            lookup_type="foreign_language",
            intent="direct_value",
            query_span="IELTS 9.0 tương đương bậc mấy",
            slots={
                "certificate_or_language": "IELTS",
                "score_or_level": "9.0",
            },
            cohort_refs=["K51"],
        ),
        _request(
            request_kind="rag",
            intent="procedure",
            query_span="thủ tục bảo lưu thế nào",
            cohort_refs=["K51"],
        ),
    ]
    pipeline.router = Router(_decision(query, requests))
    calls = []

    def fake_hybrid(**kwargs):
        calls.append(kwargs["query"])
        return {
            "retrieved_items": [],
            "citations": [],
            "related_items": [],
            "related_references": [],
        }

    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        fake_hybrid,
    )

    result = pipeline._run_retrieval(query, cohort="K51")

    assert calls == [
        "IELTS 9.0 tương đương bậc mấy",
        "thủ tục bảo lưu thế nào",
    ]
    assert result["unresolved_lookup_requests"][0]["request_index"] == 0
    assert result["unresolved_lookup_requests"][0]["query_span"] == (
        "IELTS 9.0 tương đương bậc mấy"
    )


def test_same_structured_tool_can_execute_twice() -> None:
    pipeline = _pipeline()
    pipeline.scoring_tables = [_scoring_table()]
    query = "GPA 3.4 xếp loại gì, còn GPA 2.7 xếp loại gì?"
    requests = [
        _request(
            request_kind="structured",
            lookup_type="scoring",
            intent="direct_value",
            query_span="GPA 3.4 xếp loại gì",
            slots={
                "operation": "academic_classification",
                "score_or_grade": 3.4,
            },
            cohort_refs=["K51"],
        ),
        _request(
            request_kind="structured",
            lookup_type="scoring",
            intent="direct_value",
            query_span="GPA 2.7 xếp loại gì",
            slots={
                "operation": "academic_classification",
                "score_or_grade": 2.7,
            },
            cohort_refs=["K51"],
        ),
    ]
    pipeline.router = Router(_decision(query, requests))

    result = pipeline._run_retrieval(query, cohort="K51")

    children = result["structured_result"]["sub_results"]
    assert [child["result"]["result"]["label"] for child in children] == [
        "Giỏi",
        "Khá",
    ]
    assert [citation["request_index"] for citation in result["citations"]] == [0, 1]


def test_request_specific_cohorts_execute_as_request_by_cohort(monkeypatch) -> None:
    pipeline = _pipeline()
    query = "K50 hỏi cảnh báo học vụ, K51 hỏi thủ tục bảo lưu."
    requests = [
        _request(
            request_kind="rag",
            intent="policy",
            query_span="K50 hỏi cảnh báo học vụ",
            cohort_refs=["K50"],
        ),
        _request(
            request_kind="rag",
            intent="procedure",
            query_span="K51 hỏi thủ tục bảo lưu",
            cohort_refs=["K51"],
        ),
    ]
    pipeline.router = Router(_decision(query, requests, cohorts=["K50", "K51"]))
    calls = []

    def fake_hybrid(**kwargs):
        calls.append((kwargs["query"], kwargs["cohort"]))
        chunk_id = f"{kwargs['cohort']}:{kwargs['query']}"
        return {
            "retrieved_items": [
                {
                    "chunk_id": chunk_id,
                    "content": kwargs["query"],
                    "metadata": {
                        "title": kwargs["query"],
                        "chunk_type": "regulation",
                        "document_id": f"handbook-{kwargs['cohort']}",
                        "cohort": kwargs["cohort"],
                    },
                }
            ],
            "citations": [
                {
                    "chunk_id": chunk_id,
                    "title": kwargs["query"],
                    "document_id": f"handbook-{kwargs['cohort']}",
                    "cohort": kwargs["cohort"],
                }
            ],
            "related_items": [],
            "related_references": [],
        }

    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        fake_hybrid,
    )

    result = pipeline._run_retrieval(query)

    assert calls == [
        ("K50 hỏi cảnh báo học vụ", "K50"),
        ("K51 hỏi thủ tục bảo lưu", "K51"),
    ]
    assert [item["request_index"] for item in result["retrieved_items"]] == [0, 1]
    assert [citation["request_index"] for citation in result["citations"]] == [0, 1]
    assert [item["cohort"] for item in result["request_results"]] == ["K50", "K51"]


def test_single_request_uses_router_cohort_when_caller_omits_it(monkeypatch) -> None:
    pipeline = _pipeline()
    query = "K51 thủ tục bảo lưu thế nào?"
    request = _request(
        request_kind="rag",
        intent="procedure",
        query_span=query,
        cohort_refs=["K51"],
    )
    pipeline.router = Router(_decision(query, [request]))
    cohorts = []

    def fake_hybrid(**kwargs):
        cohorts.append(kwargs["cohort"])
        return {
            "retrieved_items": [],
            "citations": [],
            "related_items": [],
            "related_references": [],
        }

    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        fake_hybrid,
    )

    pipeline._run_retrieval(query)

    assert cohorts == ["K51"]


def test_context_headers_expose_request_ownership() -> None:
    context = build_context_for_prompt(
        {
            "query": "Hai ý hỏi",
            "retrieved_items": [
                {
                    "chunk_id": "rule-1",
                    "content": "Nội dung quy định.",
                    "request_index": 2,
                    "query_span": "thủ tục xin bảo lưu",
                    "metadata": {
                        "title": "Bảo lưu",
                        "chunk_type": "regulation",
                        "cohort": "K51",
                    },
                }
            ],
        },
        max_context_chars=2000,
    )

    assert "Request: 2" in context
    assert "Query span: thủ tục xin bảo lưu" in context
