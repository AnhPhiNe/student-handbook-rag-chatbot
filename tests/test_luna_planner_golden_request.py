"""Pin the v57 candidate's revised service scope offline, not its model quality.

The measured v56/v57 fixtures remain preserved separately. Only the service
tool-use text changes in this new fixture; schema, transport and system prompt
remain fixed. This records request identity, not live model accuracy.
"""
import json
from pathlib import Path

from src.retrieval.core.ai_router import AIRouter
from tests.luna_request_capture import capture_requests, compact

FIXTURE = Path(__file__).parent / "fixtures" / "luna_planner_request_v57_service_scope.json"


def test_candidate_config_sends_the_frozen_luna_requests(monkeypatch):
    for name in [name for name in __import__("os").environ if name.startswith("STUDENT_RAG_ROUTER")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("STUDENT_RAG_DISABLE_ROUTER_CACHE", "1")
    actual = compact(capture_requests(lambda: AIRouter.from_config("configs/ai_router.yaml"), monkeypatch))
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert actual["system_prompt"] == expected["system_prompt"]
    assert actual["text_format"] == expected["text_format"]
    assert actual["scenarios"] == expected["scenarios"]
