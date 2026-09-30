from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import metrics


class FakeCollection:
    """The two pymongo calls the counter makes, over one in-memory document."""

    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    def find_one_and_update(self, query, update, upsert, return_document):
        document = self.documents.setdefault(query["_id"], {"_id": query["_id"], "count": 0})
        document["count"] += update["$inc"]["count"]
        return dict(document)

    def find_one(self, query):
        return self.documents.get(query["_id"])


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(metrics.router)
    return TestClient(app)


def test_visits_counter_increments_in_mongodb(monkeypatch) -> None:
    monkeypatch.setattr(metrics, "_collection", FakeCollection())
    monkeypatch.setenv("STUDENT_RAG_VISIT_COUNT_OFFSET", "200")

    client = make_client()

    first = client.get("/api/metrics/visits?increment=true")
    second = client.get("/api/metrics/visits?increment=true")
    read_only = client.get("/api/metrics/visits")

    assert first.status_code == 200
    assert first.json() == {"count": 201, "raw_count": 1, "status": "ok"}
    assert second.json() == {"count": 202, "raw_count": 2, "status": "ok"}
    assert read_only.json() == {"count": 202, "raw_count": 2, "status": "ok"}


def test_a_developer_machine_does_not_touch_the_shared_counter(monkeypatch) -> None:
    monkeypatch.setattr(metrics, "_collection", None)
    monkeypatch.setenv("MONGODB_URL", "mongodb+srv://shared.example")
    monkeypatch.setenv("STUDENT_RAG_VISIT_COUNTER", "false")
    assert metrics.get_metrics_collection() is False


def test_visits_counter_returns_null_without_a_database(monkeypatch) -> None:
    monkeypatch.setattr(metrics, "_collection", False)

    client = make_client()
    response = client.get("/api/metrics/visits?increment=true")

    assert response.status_code == 200
    assert response.json() == {"count": None, "status": "unavailable"}
