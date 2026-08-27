from __future__ import annotations

from unittest.mock import patch

from src.api.langsmith_helper import (
    build_trace_metadata,
    get_langsmith_client,
    push_trace_to_langsmith,
)
from src.generation.answer_pipeline import PIPELINE_VERSION
from src.generation.prompt_builder import ANSWER_PROMPT_VERSION
from src.retrieval.core.ai_router import ROUTER_PROMPT_VERSION
from src.retrieval.core.query_plan import (
    QUERY_PLAN_NORMALIZER_VERSION,
    QUERY_PLAN_SCHEMA_VERSION,
)


def _query_plan_result() -> dict:
    return {
        "status": "partial",
        "effective_query": "So sánh K50 và K51 rồi giải thích thủ tục",
        "model_used": "gemini-3.1-flash-lite",
        "llm_called": True,
        "used_cache": False,
        "retrieved_chunks_count": 9,
        "query_plan": {
            "schema_version": "v1",
            "context_mode": "follow_up",
            "tasks": [
                {
                    "id": "t1",
                    "question": "So sánh thời gian K50 và K51",
                    "mode": "structured",
                    "lookup_type": "study_duration",
                    "intent": "direct_value",
                    "cohorts": ["K50", "K51"],
                    "clarification_question": None,
                },
                {
                    "id": "t2",
                    "question": "Thủ tục còn thiếu là gì?",
                    "mode": "rag",
                    "lookup_type": None,
                    "intent": "open_question",
                    "cohorts": ["K51"],
                    "clarification_question": None,
                },
            ],
        },
        "task_results": [
            {
                "task_id": "t1",
                "coverage": "covered",
                "coverage_by_cohort": {"K50": "covered", "K51": "covered"},
                "evidence": [{"large": "payload"}, {"large": "payload"}],
                "citation_count": 2,
            },
            {
                "task_id": "t2",
                "coverage": "uncovered",
                "coverage_by_cohort": {"K51": "uncovered"},
                "evidence": [],
                "citation_count": 0,
            },
        ],
        "coverage_by_task": {"t1": "covered", "t2": "uncovered"},
        "citations_used": [
            {
                "chunk_id": "K50_Dieu1",
                "parent_section_id": "K50_Dieu1",
                "title": "Điều 1",
                "cohort": "K50",
                "supports_task_ids": ["t1"],
                "content": "full source text must not be traced",
                "parent_content": "another full source copy",
                "dense_score": 0.91,
            }
        ],
        "related_references": [
            {
                "chunk_id": "K50_Dieu2",
                "title": "Điều 2",
                "cohort": "K50",
                "content": "related full text must not be traced",
            }
        ],
        "structured_results": [
            {
                "id": "study_duration:K50:0",
                "lookup_type": "study_duration",
                "title": "Thời gian đào tạo",
                "cohort": "K50",
                "rows": [{"mode": "regular"}, {"mode": "part-time"}],
                "provenance": {
                    "source_type": "structured_dataset",
                    "document_id": "handbook_k50",
                    "source_pages": [20],
                },
            }
        ],
    }


def test_build_trace_metadata_matches_query_plan_runtime_without_raw_payloads() -> None:
    with patch.dict(
        "os.environ",
        {
            "QDRANT_COLLECTION_NAME": "student_handbook_semantic_v31",
            "MONGODB_PARENT_COLLECTION": "parent_docs_v31",
        },
    ):
        metadata = build_trace_metadata(
            _query_plan_result(),
            query="Câu hỏi gốc",
            cohort="K51",
            chat_history=[{"role": "user", "content": "private history"}],
            latency_ms=1250,
            ttft_ms=410,
        )

    assert metadata["pipeline_version"] == PIPELINE_VERSION
    assert metadata["answer_prompt_version"] == ANSWER_PROMPT_VERSION
    assert metadata["router_prompt_version"] == ROUTER_PROMPT_VERSION
    assert metadata["query_plan_schema_version"] == QUERY_PLAN_SCHEMA_VERSION
    assert metadata["query_plan_normalizer_version"] == QUERY_PLAN_NORMALIZER_VERSION
    assert metadata["context_mode"] == "follow_up"
    assert metadata["task_count"] == 2
    assert metadata["task_modes"] == ["structured", "rag"]
    assert metadata["lookup_types"] == ["study_duration"]
    assert metadata["cohorts"] == ["K50", "K51"]
    assert metadata["is_multi_cohort"] is True
    assert metadata["covered_task_count"] == 1
    assert metadata["uncovered_task_count"] == 1
    assert metadata["task_summaries"][0]["evidence_count"] == 2
    assert "evidence" not in metadata["task_summaries"][0]
    assert metadata["citations_used"][0]["chunk_id"] == "K50_Dieu1"
    assert "content" not in metadata["citations_used"][0]
    assert "parent_content" not in metadata["citations_used"][0]
    assert "dense_score" not in metadata["citations_used"][0]
    assert "content" not in metadata["related_references"][0]
    assert metadata["structured_result_summaries"][0]["row_count"] == 2
    assert "rows" not in metadata["structured_result_summaries"][0]
    assert metadata["chat_history_turns"] == 1
    assert metadata["has_chat_history"] is True
    assert "chat_history" not in metadata
    assert "raw_query" not in metadata


class _FakeLangSmithClient:
    def __init__(self) -> None:
        self.runs: list[dict] = []

    def create_run(self, **kwargs) -> None:
        self.runs.append(kwargs)


def test_explicit_langsmith_switch_disables_client_creation() -> None:
    with (
        patch.dict(
            "os.environ",
            {
                "LANGSMITH_TRACING": "false",
                "LANGSMITH_API_KEY": "secret-key",
            },
            clear=True,
        ),
        patch("src.api.langsmith_helper.Client") as client_class,
    ):
        assert get_langsmith_client() is None

    client_class.assert_not_called()


def test_push_trace_uses_task_tags_and_compact_root_outputs() -> None:
    client = _FakeLangSmithClient()
    metadata = build_trace_metadata(
        _query_plan_result(),
        query="Câu hỏi gốc",
        cohort="K51",
    )
    original = dict(metadata)

    with patch(
        "src.api.langsmith_helper.get_langsmith_client",
        return_value=client,
    ):
        push_trace_to_langsmith(
            "trace-123",
            input_text="Câu hỏi gốc",
            output_text="Câu trả lời",
            metadata=metadata,
            tags=["stream"],
        )

    assert metadata == original
    assert len(client.runs) == 1
    root = client.runs[0]
    assert "multi_task:true" in root["tags"]
    assert "multi_cohort:true" in root["tags"]
    assert "task_mode:structured" in root["tags"]
    assert "task_mode:rag" in root["tags"]
    assert "coverage:covered" in root["tags"]
    assert "coverage:uncovered" in root["tags"]
    assert "comparison:true" not in root["tags"]
    assert root["outputs"]["task_count"] == 2
    assert root["outputs"]["citations"][0]["chunk_id"] == "K50_Dieu1"
    assert "content" not in root["outputs"]["citations"][0]
    assert root["outputs"]["structured_results"][0]["row_count"] == 2
