"""Composer replay reproduces the pipeline's prompt and post-composer steps offline."""
import json

import pytest

from src.evaluation.composer_replay import replay_answers, replay_record
from src.generation.prompt_builder import (
    ANSWER_PROMPT_VERSION,
    build_answer_prompt_bundle,
    render_answer_prompt,
)

RETRIEVAL = {
    "effective_query": "Điều kiện xét học bổng là gì?",
    "retrieved_items": [{"chunk_id": "p1", "content": "Có ba điều kiện xét học bổng.",
                         "metadata": {"title": "Điều 12", "cohort": "K51"}}],
}


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.result


def _source(**overrides):
    prompt, context_used = build_answer_prompt_bundle(
        query="Điều kiện xét học bổng là gì?", retrieval_result=RETRIEVAL,
        max_context_chars=10000, cohort="K51",
    )
    record = {"id": "c1", "query": "Điều kiện xét học bổng?", "effective_query": "Điều kiện xét học bổng là gì?",
              "llm_called": True, "context_used": context_used, "status": "answered",
              "answer": "Câu cũ.", "citations": [{"title": "Điều 5"}, {"title": "Điều 12"}],
              "evaluation_telemetry": {"total_ms": 1}}
    return {**record, **overrides}, prompt


def test_recorded_packet_renders_the_pipeline_prompt_exactly():
    source, pipeline_prompt = _source()
    replayed_prompt, context_used = render_answer_prompt(
        source["effective_query"], json.loads(source["context_used"]))
    assert replayed_prompt == pipeline_prompt
    assert context_used == source["context_used"]


def test_replay_composes_cleans_and_reorders_citations_by_the_new_answer():
    source, pipeline_prompt = _source()
    client = FakeClient({"ok": True, "text": "Theo **Điều 12**, có ba điều kiện.\n\nNguồn:\n- Điều 12",
                         "attempts": 2, "model_used": "deepseek-flash"})
    row = replay_record(source, client=client, public_max_sources=10)
    assert client.prompts == [pipeline_prompt]
    assert row["answer"] == "Theo **Điều 12**, có ba điều kiện."
    assert [c["title"] for c in row["citations"]] == ["Điều 12", "Điều 5"]
    assert (row["status"], row["error_type"], row["model_used"], row["replay"]) == (
        "answered", None, "deepseek-flash", "composer")
    assert row["evaluation_telemetry"]["retry_count"] == 1
    assert json.loads(row["context_used"])["answer_prompt_version"] == ANSWER_PROMPT_VERSION


def test_replay_copies_cases_without_a_composer_call_and_reports_failures():
    source, _ = _source(llm_called=False, status="needs_clarification")
    client = FakeClient({"ok": True, "text": "unused"})
    assert replay_record(source, client=client, public_max_sources=10)["replay"] == "copied"
    assert client.prompts == []
    source, _ = _source()
    failed = replay_record(source, client=FakeClient({"ok": False, "error_type": "timeout"}),
                           public_max_sources=10)
    assert (failed["status"], failed["error_type"], failed["answer"]) == ("api_error", "timeout", "")


def test_replay_answers_checkpoints_in_dataset_order(tmp_path):
    source, _ = _source()
    cases = [{"id": "c1", "query": "Điều kiện xét học bổng?"}]
    client = FakeClient({"ok": True, "text": "Có ba điều kiện.", "model_used": "m"})
    report = replay_answers(cases, [source], client=client, cache_path=tmp_path / "a.json",
                            resume=False, public_max_sources=10)
    assert report["summary"]["replayed_n"] == 1 and report["summary"]["success_rate"] == 1.0
    # A resumed run reuses the checkpoint instead of calling the composer again.
    replay_answers(cases, [source], client=client, cache_path=tmp_path / "a.json",
                   resume=True, public_max_sources=10)
    assert len(client.prompts) == 1
    with pytest.raises(ValueError, match="lacks cases"):
        replay_answers([{"id": "other", "query": "?"}], [source], client=client,
                       cache_path=tmp_path / "b.json", resume=False, public_max_sources=10)
