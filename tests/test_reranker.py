"""Qwen3-Reranker on DeepInfra, with the HTTP call replaced by a fake."""
from unittest.mock import Mock

import pytest
import requests

from src.retrieval.core.reranker import Reranker, RerankerConfig


def _candidates(count: int = 4) -> list[tuple[float, dict[str, object]]]:
    return [(1.0 - i / 100, {"chunk_id": f"c{i}", "content": f"doc {i}"}) for i in range(count)]


def _response(status: int = 200, body: object = None) -> Mock:
    response = Mock()
    response.status_code = status
    response.json.return_value = body
    return response


def test_reranks_every_candidate_by_score_and_reports_it() -> None:
    post = Mock(return_value=_response(body={"scores": [0.1, 0.9, 0.5, 0.9]}))
    reranker = Reranker(RerankerConfig(), api_key="k", post=post)

    ranked, telemetry = reranker.rerank("câu hỏi", _candidates())

    # c1 and c3 tie at 0.9; the tie keeps the RRF order.
    assert [chunk["chunk_id"] for _, chunk in ranked] == ["c1", "c3", "c2", "c0"]
    assert telemetry["ranking_method"] == "qwen3_reranker"
    assert telemetry["reranker_applied"] is True
    kwargs = post.call_args.kwargs
    assert post.call_args.args[0] == "https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-8B"
    assert kwargs["json"]["queries"] == ["câu hỏi"]
    assert kwargs["json"]["documents"] == ["doc 0", "doc 1", "doc 2", "doc 3"]
    assert kwargs["timeout"] == 10.0


@pytest.mark.parametrize(
    ("post", "reason"),
    [
        (Mock(side_effect=requests.Timeout("slow")), "request_error:Timeout"),
        (Mock(return_value=_response(503, {})), "http_503"),
        (Mock(return_value=_response(body={"scores": [0.5]})), "invalid_response"),
        (Mock(return_value=_response(body={"scores": [0.5, float("nan"), 0.1, 0.2]})), "invalid_response"),
        (Mock(return_value=_response(body={"other": 1})), "invalid_response"),
    ],
)
def test_failures_keep_the_rrf_order(post: Mock, reason: str) -> None:
    candidates = _candidates()
    ranked, telemetry = Reranker(RerankerConfig(), api_key="k", post=post).rerank("q", candidates)

    assert ranked == candidates
    assert telemetry["ranking_method"] == "rrf"
    assert telemetry["reranker_fallback_reason"] == reason


def test_missing_key_or_disabled_reranker_makes_no_call() -> None:
    post = Mock()
    candidates = _candidates()
    for reranker, reason in ((Reranker(RerankerConfig(), api_key="", post=post), "missing_api_key"),
                             (Reranker(RerankerConfig(enabled=False), api_key="k", post=post), "disabled")):
        ranked, telemetry = reranker.rerank("q", candidates)
        assert ranked == candidates
        assert telemetry["reranker_fallback_reason"] == reason
    post.assert_not_called()
