from __future__ import annotations

from email.utils import formatdate
from unittest.mock import Mock, patch

import pytest
import requests

from src.common.key_pool import KeyPool, NoAvailableKey, retry_after_seconds
from src.retrieval.core.cohere_reranker import (
    CohereReranker,
    CohereRerankerConfig,
)


def _candidates(count: int = 24) -> list[tuple[float, dict[str, object]]]:
    return [
        (1.0 - index / 100, {"chunk_id": f"c{index}", "content": f"doc {index}"})
        for index in range(count)
    ]


def _config(**overrides: object) -> CohereRerankerConfig:
    values: dict[str, object] = {
        "enabled": True,
        "candidate_count": 16,
        "rpm_limit_per_key": 10,
        "cooldown_seconds": 65.0,
    }
    values.update(overrides)
    return CohereRerankerConfig(**values)


def _response(
    status_code: int,
    *,
    results: list[dict[str, object]] | None = None,
    headers: dict[str, str] | None = None,
) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = {"results": results or []}
    return response


def test_disabled_reranker_returns_full_rrf_without_http() -> None:
    post = Mock()
    original = _candidates()
    reranker = CohereReranker(_config(enabled=False), keys=["key-a"], post=post)

    ranked, telemetry = reranker.rerank("query", original)

    assert ranked == original
    assert telemetry["ranking_method"] == "rrf"
    assert telemetry["cohere_fallback_reason"] == "disabled"
    post.assert_not_called()


def test_success_reranks_only_configured_rrf_prefix() -> None:
    results = [
        {"index": index, "relevance_score": 1.0 - rank / 100}
        for rank, index in enumerate(reversed(range(16)))
    ]
    post = Mock(return_value=_response(200, results=results))
    reranker = CohereReranker(_config(), keys=["key-a"], post=post)

    ranked, telemetry = reranker.rerank("query", _candidates())

    assert len(ranked) == 16
    assert [chunk["chunk_id"] for _, chunk in ranked] == [
        f"c{index}" for index in reversed(range(16))
    ]
    assert telemetry["ranking_method"] == "cohere_rerank_v4_fast"
    assert telemetry["cohere_reranker_applied"] is True
    assert telemetry["cohere_key_index"] == 0
    assert "cohere_key_fingerprint" not in telemetry
    request_json = post.call_args.kwargs["json"]
    assert request_json["documents"] == [f"doc {index}" for index in range(16)]


def test_rate_limit_rotates_to_next_key_without_waiting() -> None:
    success = [
        {"index": index, "relevance_score": 1.0 - index / 100}
        for index in range(16)
    ]
    post = Mock(
        side_effect=[
            _response(429, headers={"Retry-After": "30"}),
            _response(200, results=success),
        ]
    )
    reranker = CohereReranker(_config(), keys=["key-a", "key-b"], post=post)

    ranked, telemetry = reranker.rerank("query", _candidates())

    assert len(ranked) == 16
    assert telemetry["cohere_reranker_applied"] is True
    assert telemetry["cohere_attempts"] == 2
    assert [
        call.kwargs["headers"]["Authorization"] for call in post.call_args_list
    ] == ["Bearer key-a", "Bearer key-b"]


def test_retry_after_accepts_http_date() -> None:
    response = _response(429, headers={"Retry-After": formatdate(200.0, usegmt=True)})

    with patch("src.common.key_pool.time.time", return_value=100.0):
        seconds = retry_after_seconds(response)

    assert seconds == pytest.approx(100.0)


def test_key_pool_enforces_rolling_per_minute_limit() -> None:
    config = CohereRerankerConfig(rpm_limit_per_key=1, cooldown_seconds=65)
    pool = KeyPool(["key-a", "key-b"], config.key_pool_config())
    with patch("src.common.key_pool.time.time", return_value=100.0):
        assert pool.acquire()[2] == 0
        assert pool.acquire()[2] == 1
        with pytest.raises(NoAvailableKey):
            pool.acquire()

    with patch("src.common.key_pool.time.time", return_value=161.0):
        assert pool.acquire()[2] == 0


def test_all_rate_limited_keys_fail_open_to_full_rrf() -> None:
    post = Mock(
        side_effect=[
            _response(429, headers={"Retry-After": "5"}),
            _response(429, headers={"Retry-After": "5"}),
        ]
    )
    original = _candidates()
    reranker = CohereReranker(_config(), keys=["key-a", "key-b"], post=post)

    ranked, telemetry = reranker.rerank("query", original)

    assert ranked == original
    assert telemetry["ranking_method"] == "rrf"
    assert telemetry["cohere_fallback_reason"] == "all_keys_rate_limited"
    assert telemetry["cohere_attempts"] == 2


def test_request_timeout_fails_open_without_trying_every_key() -> None:
    post = Mock(side_effect=requests.Timeout("timed out"))
    original = _candidates()
    reranker = CohereReranker(_config(), keys=["key-a", "key-b"], post=post)

    ranked, telemetry = reranker.rerank("query", original)

    assert ranked == original
    assert telemetry["cohere_fallback_reason"] == "request_error"
    assert telemetry["cohere_attempts"] == 1
    post.assert_called_once()


def test_incomplete_response_fails_open_to_full_rrf() -> None:
    post = Mock(
        return_value=_response(
            200,
            results=[{"index": 0, "relevance_score": 1.0}],
        )
    )
    original = _candidates()
    reranker = CohereReranker(_config(), keys=["key-a"], post=post)

    ranked, telemetry = reranker.rerank("query", original)

    assert ranked == original
    assert telemetry["cohere_fallback_reason"] == "invalid_response"


def test_non_object_json_response_fails_open_to_full_rrf() -> None:
    response = _response(200)
    response.json.return_value = [
        {"index": 0, "relevance_score": 1.0},
    ]
    original = _candidates()
    reranker = CohereReranker(_config(), keys=["key-a"], post=Mock(return_value=response))

    ranked, telemetry = reranker.rerank("query", original)

    assert ranked == original
    assert telemetry["cohere_fallback_reason"] == "invalid_response"


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_relevance_score_fails_open_to_full_rrf(score: float) -> None:
    results = [
        {"index": index, "relevance_score": score if index == 0 else 0.5}
        for index in range(16)
    ]
    original = _candidates()
    reranker = CohereReranker(
        _config(), keys=["key-a"], post=Mock(return_value=_response(200, results=results))
    )

    ranked, telemetry = reranker.rerank("query", original)

    assert ranked == original
    assert telemetry["cohere_fallback_reason"] == "invalid_response"
