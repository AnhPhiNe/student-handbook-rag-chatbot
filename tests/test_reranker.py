"""Voyage and DeepInfra reranking, with the HTTP call replaced by a fake."""
from unittest.mock import Mock

import pytest
import requests

from src.retrieval.core.reranker import Reranker, RerankerConfig

DEEPINFRA = RerankerConfig(
    provider="deepinfra",
    model="Qwen/Qwen3-Reranker-8B",
    api_url="https://api.deepinfra.com/v1/inference",
    api_key_env_var="DEEPINFRA_API_KEY",
)


def _candidates(count: int = 4) -> list[tuple[float, dict[str, object]]]:
    return [(1.0 - i / 100, {"chunk_id": f"c{i}", "content": f"doc {i}"}) for i in range(count)]


def _response(status: int = 200, body: object = None) -> Mock:
    response = Mock()
    response.status_code = status
    response.json.return_value = body
    return response


def _voyage_body(scores: list[float], **extra: object) -> dict[str, object]:
    return {"data": [{"index": i, "relevance_score": s} for i, s in enumerate(scores)], **extra}


def test_voyage_reranks_every_candidate_by_score_and_reports_it() -> None:
    post = Mock(return_value=_response(body=_voyage_body([0.1, 0.9, 0.5, 0.9])))

    ranked, telemetry = Reranker(RerankerConfig(), api_key="k", post=post).rerank("câu hỏi", _candidates())

    # c1 and c3 tie at 0.9; the tie keeps the RRF order.
    assert [chunk["chunk_id"] for _, chunk in ranked] == ["c1", "c3", "c2", "c0"]
    assert telemetry["ranking_method"] == "voyage_reranker"
    assert telemetry["reranker_applied"] is True
    assert post.call_args.args[0] == "https://ai.mongodb.com/v1/rerank"
    payload = post.call_args.kwargs["json"]
    assert payload["query"] == "câu hỏi"
    assert payload["documents"] == ["doc 0", "doc 1", "doc 2", "doc 3"]
    assert payload["model"] == "rerank-3"
    assert post.call_args.kwargs["timeout"] == 10.0


def test_voyage_scores_follow_the_index_each_document_carries() -> None:
    """Voyage may answer in score order, so a document keeps its own index."""

    body = {"data": [{"index": 2, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.7},
                     {"index": 3, "relevance_score": 0.5}, {"index": 1, "relevance_score": 0.1}]}
    ranked, _ = Reranker(RerankerConfig(), api_key="k",
                         post=Mock(return_value=_response(body=body))).rerank("q", _candidates())

    assert [chunk["chunk_id"] for _, chunk in ranked] == ["c2", "c0", "c3", "c1"]


def test_voyage_token_usage_is_kept_and_no_price_is_claimed() -> None:
    body = _voyage_body([0.1, 0.9, 0.5, 0.2], usage={"total_tokens": 4321})
    _, telemetry = Reranker(RerankerConfig(), api_key="k",
                            post=Mock(return_value=_response(body=body))).rerank("q", _candidates())

    assert telemetry["reranker_input_tokens"] == 4321
    assert telemetry["reranker_cost"] is None


def test_deepinfra_keeps_its_own_request_shape_tokens_and_price() -> None:
    body = {"scores": [0.1, 0.9, 0.5, 0.2], "input_tokens": 168,
            "inference_status": {"runtime_ms": 67, "cost": 8.4e-06, "tokens_input": 168}}
    post = Mock(return_value=_response(body=body))

    ranked, telemetry = Reranker(DEEPINFRA, api_key="k", post=post).rerank("câu hỏi", _candidates())

    assert [chunk["chunk_id"] for _, chunk in ranked] == ["c1", "c2", "c3", "c0"]
    assert telemetry["ranking_method"] == "qwen3_reranker"
    assert post.call_args.args[0] == "https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-8B"
    assert post.call_args.kwargs["json"]["queries"] == ["câu hỏi"]
    assert telemetry["reranker_input_tokens"] == 168
    assert telemetry["reranker_cost"] == pytest.approx(8.4e-06)


@pytest.mark.parametrize(
    ("config", "post", "reason"),
    [
        (RerankerConfig(), Mock(side_effect=requests.Timeout("slow")), "request_error:Timeout"),
        (RerankerConfig(), Mock(return_value=_response(503, {})), "http_503"),
        (RerankerConfig(), Mock(return_value=_response(body=_voyage_body([0.5]))), "invalid_response"),
        (RerankerConfig(), Mock(return_value=_response(
            body=_voyage_body([0.5, float("nan"), 0.1, 0.2]))), "invalid_response"),
        (RerankerConfig(), Mock(return_value=_response(body={"other": 1})), "invalid_response"),
        (RerankerConfig(), Mock(return_value=_response(
            body={"data": [{"index": 9, "relevance_score": 0.5}] * 4})), "invalid_response"),
        (DEEPINFRA, Mock(return_value=_response(body={"scores": [0.5]})), "invalid_response"),
        (DEEPINFRA, Mock(return_value=_response(body={"other": 1})), "invalid_response"),
    ],
)
def test_failures_keep_the_rrf_order(config: RerankerConfig, post: Mock, reason: str) -> None:
    candidates = _candidates()
    ranked, telemetry = Reranker(config, api_key="k", post=post).rerank("q", candidates)

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


def test_the_configured_provider_is_used_and_an_unknown_one_is_refused() -> None:
    config = RerankerConfig.from_config({"provider": "DeepInfra", "model": "m", "api_url": "https://x"})
    assert (config.provider, config.model) == ("deepinfra", "m")
    assert RerankerConfig.from_config({}).provider == "voyage"
    with pytest.raises(ValueError, match="Unknown reranker provider"):
        RerankerConfig.from_config({"provider": "cohere"})


def test_the_deployed_config_selects_voyage_rerank_3() -> None:
    from src.retrieval.runtime_config import load_retrieval_runtime_config

    config = RerankerConfig.from_config(load_retrieval_runtime_config().get("reranker"))
    assert (config.provider, config.model) == ("voyage", "rerank-3")
    assert config.api_key_env_var == "VOYAGE_API_KEY"
