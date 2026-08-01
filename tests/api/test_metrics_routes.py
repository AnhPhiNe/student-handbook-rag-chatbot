from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import metrics


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def get(self, key: str) -> int | None:
        return self.values.get(key)


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(metrics.router)
    return TestClient(app)


def test_visits_counter_increments_in_redis(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(metrics, "_redis_client", fake_redis)
    monkeypatch.setenv("STUDENT_RAG_VISIT_COUNT_OFFSET", "200")

    client = make_client()

    first = client.get("/api/metrics/visits?increment=true")
    second = client.get("/api/metrics/visits?increment=true")
    read_only = client.get("/api/metrics/visits")

    assert first.status_code == 200
    assert first.json() == {"count": 201, "raw_count": 1, "status": "ok"}
    assert second.json() == {"count": 202, "raw_count": 2, "status": "ok"}
    assert read_only.json() == {"count": 202, "raw_count": 2, "status": "ok"}


def test_visits_counter_returns_null_without_redis(monkeypatch) -> None:
    monkeypatch.setattr(metrics, "_redis_client", False)

    client = make_client()
    response = client.get("/api/metrics/visits?increment=true")

    assert response.status_code == 200
    assert response.json() == {"count": None, "status": "redis_unavailable"}
