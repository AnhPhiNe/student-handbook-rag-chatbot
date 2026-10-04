"""Pin v58 answer-kind guidance offline, not the live model's routing quality.

Keep the v56/v57 snapshots intact. Schema, transport, task semantics and model
configuration must still match v57; only system/tool-use instructions change.
"""
import json
from pathlib import Path

from src.retrieval.core.ai_router import AIRouter
from tests.luna_request_capture import capture_requests, compact

FIXTURE = Path(__file__).parent / "fixtures" / "luna_planner_request_v58_answer_kind.json"
BASELINE = Path(__file__).parent / "fixtures" / "luna_planner_request_v57_service_scope.json"


def test_candidate_config_sends_the_frozen_luna_requests(monkeypatch):
    for name in [name for name in __import__("os").environ if name.startswith("STUDENT_RAG_ROUTER")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("STUDENT_RAG_DISABLE_ROUTER_CACHE", "1")
    actual = compact(capture_requests(lambda: AIRouter.from_config("configs/ai_router.yaml"), monkeypatch))
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    instructions = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected["system_prompt"] = instructions["system_prompt"]
    # Reuse the historical request; change exactly the approved service line.
    # Schema, other tools, input scenarios and provider settings stay pinned.
    for scenario in expected["scenarios"]:
        for call in scenario["calls"]:
            user = call["request"]["input"][1]
            user["content"] = "\n".join(
                instructions["service_line"] if line.startswith("student_service|") else line
                for line in user["content"].splitlines()
            )
    assert actual["system_prompt"] == expected["system_prompt"]
    assert actual["text_format"] == expected["text_format"]
    assert actual["scenarios"] == expected["scenarios"]


def test_v58_instruction_snapshot_is_a_small_explicit_delta_not_a_rewritten_baseline():
    previous = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(current) == {"system_prompt", "service_line"}
    assert current["system_prompt"] != previous["system_prompt"]
    assert current["service_line"].startswith("student_service|")
