from __future__ import annotations

from src.generation.answer_pipeline import AnswerPipeline


def _pipeline() -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.llm_config = {"model_name": "deterministic"}
    pipeline._finalize_evaluation_telemetry = lambda **_kwargs: None
    return pipeline


def _retrieval_result() -> dict:
    return {
        "router_decision": {
            "plan_version": "single-cohort-v2",
            "cohort": "K51",
            "execution_mode": "mixed",
        },
        "selected_cohort": "K51",
        "effective_query": "K51 query",
        "retrieval_executed": True,
        "request_results": [
            {"request_id": "r1", "status": "ok"},
            {"request_id": "r2", "status": "no_match"},
        ],
        "request_execution_contexts": [
            {
                "request_id": "r1",
                "query_span": "first",
                "retrieval_query": "first K51",
            },
            {
                "request_id": "r2",
                "query_span": "second",
                "retrieval_query": "second K51",
            },
        ],
        "citations": [],
    }


def test_sync_stream_and_cached_debug_metadata_have_contract_parity() -> None:
    pipeline = _pipeline()
    retrieval = _retrieval_result()
    base_kwargs = {
        "query": "query",
        "retrieval_result": retrieval,
        "final_answer": "answer",
        "context_used": "context",
        "selected_citations": [],
        "status": "answered",
        "error_type": None,
        "error_message": None,
        "llm_called": False,
    }
    sync = pipeline._build_output(**base_kwargs, used_cache=False)
    cached = pipeline._build_output(**base_kwargs, used_cache=True)
    stream = pipeline._build_stream_metadata(
        retrieval,
        status="answered",
        effective_query="K51 query",
    )

    expected_debug = {
        "plan_version": "single-cohort-v2",
        "effective_cohort": "K51",
        "retrieval_executed": True,
        "partial_status": "partial",
        "request_results": retrieval["request_results"],
        "request_execution_contexts": retrieval["request_execution_contexts"],
    }
    assert sync["debug"] == expected_debug
    assert cached["debug"] == expected_debug
    assert stream["debug"] == expected_debug
    assert sync["retrieval_query"] is None
    assert cached["retrieval_query"] is None
    assert sync["used_cache"] is False
    assert cached["used_cache"] is True
