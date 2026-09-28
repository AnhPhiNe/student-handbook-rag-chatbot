"""Capture what the planner sends to OpenAI, offline, for the golden request test.

The fixture tests/fixtures/luna_planner_request_v53.json records the requests of
the measured Luna v53 configuration (official_v1 133/135, official_v3 run 1).
Refactors must leave these requests byte-identical.
"""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

import openai

from src.retrieval.core import ai_router as module

SCENARIOS = [
    {"name": "standalone", "query": "Email Phòng Đào tạo là gì?", "cohort": "K51", "history": []},
    {"name": "follow_up", "query": "Vậy K50 thì sao?", "cohort": "K51",
     "history": [{"role": "user", "content": "Điểm 7,3 là điểm chữ gì?"},
                 {"role": "assistant", "content": "Theo sổ tay K51, 7,3 điểm là B."}]},
    # One task for three numbered requests triggers the single count repair.
    {"name": "numbered_repair", "cohort": "K50",
     "query": "Thứ nhất: Điều 1 nói gì? Thứ hai: Điều 2 nói gì? Thứ ba: Điều 3 nói gì?",
     "history": []},
]


def _plan_text(task_count: int) -> str:
    tasks = [{"id": f"t{i}", "question": "Quy định học vụ?", "mode": "rag", "intent": "open_question",
              "lookup_type": None, "slots": {}, "slot_spans": {}, "cohorts": ["K51"],
              "clarification_question": None} for i in range(1, task_count + 1)]
    return json.dumps({"schema_version": "v1", "context_mode": "standalone",
                       "normalized_query": "Quy định học vụ?", "standalone_query": None,
                       "referenced_turns": [], "out_of_domain": False, "tasks": tasks},
                      ensure_ascii=False)


def _response(task_count: int):
    return NS(status="completed", incomplete_details=None, output_text=_plan_text(task_count),
              output=[], usage=NS(input_tokens=1, output_tokens=1, total_tokens=2,
                                  input_tokens_details=None, output_tokens_details=None))


def capture_requests(build_router, monkeypatch) -> list[dict]:
    """Run every scenario through a router and return the requests it sent."""
    sent: list[dict] = []

    class Client:
        def __init__(self, **options):
            self.options = {k: v for k, v in options.items() if k != "api_key"}
            self.responses = NS(create=self.create)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create(self, **request):
            sent.append({"client": self.options, "request": request})
            numbered = "Thứ ba" in json.dumps(request["input"], ensure_ascii=False)
            first_try = not any(m.get("role") == "assistant" for m in request["input"])
            return _response(1 if numbered and first_try else 3 if numbered else 1)

    monkeypatch.setattr(openai, "OpenAI", Client)
    monkeypatch.setattr(module, "load_project_env", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-openai-key")
    router = build_router()
    captured = []
    for scenario in SCENARIOS:
        start = len(sent)
        router.plan(scenario["query"], cohort=scenario["cohort"], chat_history=scenario["history"])
        captured.append({"scenario": scenario["name"], "calls": sent[start:]})
    return captured


def compact(captured: list[dict]) -> dict:
    """Store the shared system prompt and text format once, then each call."""
    first = captured[0]["calls"][0]["request"]
    system, text_format = first["input"][0]["content"], first["text"]
    scenarios = []
    for scenario in captured:
        calls = []
        for call in scenario["calls"]:
            request = dict(call["request"])
            assert request["input"][0] == {"role": "system", "content": system}
            assert request["text"] == text_format
            request["input"] = ["<system_prompt>", *request["input"][1:]]
            request["text"] = "<text_format>"
            calls.append({"client": call["client"], "request": request})
        scenarios.append({"scenario": scenario["scenario"], "calls": calls})
    return {"system_prompt": system, "text_format": text_format, "scenarios": scenarios}
