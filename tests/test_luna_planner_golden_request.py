"""Pin the planner request v63 sends to OpenAI, not the live model's routing quality.

v63 adds the social field to the strict schema and one rule to the system
prompt, so the whole request is frozen again. The v56–v62 snapshots stay as
historical records.
"""
import json
from pathlib import Path

from src.retrieval.core.ai_router import AIRouter
from tests.luna_request_capture import capture_requests, compact

FIXTURE = Path(__file__).parent / "fixtures" / "luna_planner_request_v63.json"


def test_candidate_config_sends_the_frozen_luna_requests(monkeypatch):
    for name in [name for name in __import__("os").environ if name.startswith("STUDENT_RAG_ROUTER")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("STUDENT_RAG_DISABLE_ROUTER_CACHE", "1")
    actual = compact(capture_requests(lambda: AIRouter.from_config("configs/ai_router.yaml"), monkeypatch))
    assert actual == json.loads(FIXTURE.read_text(encoding="utf-8"))
