"""The production planner sends exactly the requests that were measured.

official_v1 (133/135) and the single clean official_v3 run (115/132) used
planner prompt v53 with Luna, a strict schema and medium reasoning; v56 adds one
rule (a given value checked against a condition is a lookup plus RAG) and was
re-measured on official_v1 before release. Any change
to what reaches OpenAI must be deliberate and re-measured, so this test fails
on the smallest difference in prompt, schema or request parameters.
"""
import json
from pathlib import Path

from src.retrieval.core.ai_router import AIRouter
from tests.luna_request_capture import capture_requests, compact

FIXTURE = Path(__file__).parent / "fixtures" / "luna_planner_request_v56.json"


def test_production_config_sends_the_measured_luna_requests(monkeypatch):
    for name in [name for name in __import__("os").environ if name.startswith("STUDENT_RAG_ROUTER")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("STUDENT_RAG_DISABLE_ROUTER_CACHE", "1")
    actual = compact(capture_requests(lambda: AIRouter.from_config("configs/ai_router.yaml"), monkeypatch))
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert actual["system_prompt"] == expected["system_prompt"]
    assert actual["text_format"] == expected["text_format"]
    assert actual["scenarios"] == expected["scenarios"]
