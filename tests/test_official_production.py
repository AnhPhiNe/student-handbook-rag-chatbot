import json
from collections import Counter

from scripts.build_official_production import BUNDLE, build


def test_production_counts_artifact_and_pairs():
    cases = build()
    assert cases == json.loads((BUNDLE / "production_cases.json").read_text(encoding="utf-8"))
    assert Counter(c["scenario"] for c in cases) == {
        "cold_rag": 20, "deterministic": 10, "warm_cache": 10, "streaming": 10, "burst": 10}
    by_id = {c["id"]: c for c in cases}
    assert len(by_id) == 60
    for case in cases:
        assert not case["frozen"]
        assert case["stream"] == (case["scenario"] == "streaming")
        target = case["repeat_of"] or case["paired_sync_id"]
        if target:
            source = by_id[target]
            assert source["id"] < case["id"]
            assert (source["query"], source["cohort"], source["history"]) == (
                case["query"], case["cohort"], case["history"])
    assert Counter(c["concurrency"] for c in cases if c["scenario"] == "burst") == {3: 5, 5: 5}


def test_production_common_contract():
    from src.evaluation.dataset import _validate_common
    errors = []
    for case in build():
        _validate_common(case, "production", errors)
    assert not errors


def test_all_sixty_requests_use_existing_runner_with_fake_http(monkeypatch):
    from io import BytesIO
    from threading import Lock
    import src.evaluation.suites as suites

    observed = []
    seen = set()
    lock = Lock()

    class Response(BytesIO):
        status = 200

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data)
        key = (payload["query"], payload["cohort"])
        with lock:
            used_cache = key in seen
            seen.add(key)
            observed.append((request.full_url, key))
        body = {"answer": "Câu trả lời fixture, không phải kết quả model.", "status": "answered",
                "used_cache": used_cache, "citations": []}
        if request.full_url.endswith("/stream"):
            chunks = [f"event: {event}\ndata: {json.dumps(data)}\n\n" for event, data in (
                ("metadata", body), ("token", {"text": body["answer"]}), ("done", {"status": "answered"}))]
            return Response("".join(chunks).encode())
        return Response(json.dumps(body).encode())

    monkeypatch.setattr(suites.urllib_request, "urlopen", fake_urlopen)
    result = suites.evaluate_production(build(), base_url="https://fixture.invalid")
    assert len(observed) == 60
    assert sum(url.endswith("/stream") for url, _ in observed) == 10
    assert result["summary"]["cache_protocol_valid"]
    assert all(row["success"] for row in result["cases"])
    assert len({row["id"] for row in result["cases"]}) == 60


def test_runner_records_http_and_stream_errors_without_live_calls(monkeypatch):
    from io import BytesIO
    import src.evaluation.suites as suites

    def http_failure(request, timeout):
        raise suites.urllib_error.HTTPError(request.full_url, 429, "fixture capacity", {}, BytesIO(b"fixture"))

    monkeypatch.setattr(suites.urllib_request, "urlopen", http_failure)
    result = suites.evaluate_production(build()[:1], base_url="https://fixture.invalid")
    assert not result["cases"][0]["success"]
    assert result["cases"][0]["status_code"] == 429

    class Response(BytesIO):
        status = 200

    monkeypatch.setattr(suites.urllib_request, "urlopen", lambda *a, **k: Response(
        b'event: error\ndata: {"error_type":"fixture_timeout"}\n\nevent: done\ndata: {"status":"api_error"}\n\n'))
    result = suites.evaluate_production([build()[40]], base_url="https://fixture.invalid")
    assert result["cases"][0]["stream_error"]
    assert not result["cases"][0]["success"]


def test_official_runner_production_suite_attaches_release_gates(tmp_path, monkeypatch):
    import sys

    import scripts.run_official_answers as runner
    import src.evaluation.suites as suites

    calls = {}

    def fake_evaluate_production(cases, *, base_url, limit, checkpoint_path, resume, checkpoint_context):
        calls.update(base_url=base_url, limit=limit, n=len(cases))
        return {"summary": {"success_rate": 1.0, "http_429_rate": 0.0}}

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "_snapshot", lambda suite, case_path: {"suite": suite})
    monkeypatch.setattr(suites, "evaluate_production", fake_evaluate_production)
    monkeypatch.setattr(sys, "argv", ["run_official_answers", "--suite", "production",
                                      "--limit", "2", "--base-url", "http://example.test"])
    runner.main()

    (report_path,) = (tmp_path / "data/eval/reports").glob("official_v1_production_smoke2_*/production.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert calls == {"base_url": "http://example.test", "limit": 2, "n": 60}
    assert report["gates"]["passed"] is True
    assert report["gates"]["checks"]["success_rate"]["passed"] is True
    assert report["run_snapshot"]["base_url"] == "http://example.test"
