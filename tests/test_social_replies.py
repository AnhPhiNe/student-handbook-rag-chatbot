"""A greeting, thanks or question about the assistant gets a fixed reply.

The planner sets QueryPlan.social only for a whole social query; the normalizer
keeps it only when no task was planned, and the pipeline answers from
configs/social_replies.yaml without the composer or citations.
"""
import random

import pytest

from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
from src.generation.social_replies import COHORT_MARK, load_replies, reply_for
from src.retrieval.core.query_plan import normalize_query_plan
from tests.test_release_backend_regressions import _pipeline


def _payload(*, social, tasks=(), out_of_domain=False, query="Xin chào"):
    return {
        "schema_version": "v1", "context_mode": "standalone",
        "normalized_query": query, "standalone_query": None,
        "referenced_turns": [], "out_of_domain": out_of_domain,
        "social": social, "tasks": list(tasks),
    }


def _rag_task(question):
    return {"id": "t1", "question": question, "mode": "rag", "intent": "open_question",
            "lookup_type": None, "slots": {}, "slot_spans": {}, "cohorts": ["K51"],
            "clarification_question": None}


@pytest.mark.parametrize("kind", ["greeting", "thanks", "about_bot"])
def test_a_whole_social_query_has_no_tasks_and_is_not_out_of_domain(kind):
    plan, errors = normalize_query_plan(
        _payload(social=kind, out_of_domain=True), query="Xin chào", selected_cohort="K51",
    )
    assert errors == []
    assert plan["social"] == kind
    assert plan["tasks"] == [] and plan["out_of_domain"] is False


def test_any_planned_task_cancels_the_social_reply():
    query = "Chào bạn, cho em hỏi học bổng KKHT xét thế nào?"
    plan, _ = normalize_query_plan(
        _payload(social="greeting", tasks=[_rag_task(query)], query=query),
        query=query, selected_cohort="K51",
    )
    assert plan.get("social") in (None, "none")
    assert [task["mode"] for task in plan["tasks"]] == ["rag"]


def test_an_unknown_social_value_is_ignored():
    plan, _ = normalize_query_plan(
        _payload(social="smalltalk", out_of_domain=True), query="Xin chào", selected_cohort="K51",
    )
    assert plan.get("social") in (None, "none")
    assert plan["out_of_domain"] is True


def test_every_kind_has_a_reply_without_a_cohort_and_fills_the_cohort_mark():
    replies = load_replies()
    assert set(replies) == {"greeting", "thanks", "about_bot", "out_of_domain"}
    for kind in replies:
        for seed in range(20):
            text = reply_for(kind, None, rng=random.Random(seed))
            assert COHORT_MARK not in text and text
    marked = [text for text in replies["greeting"] if COHORT_MARK in text]
    assert marked
    seen = {reply_for("greeting", "K50", rng=random.Random(seed)) for seed in range(50)}
    assert any("khóa K50" in text for text in seen)
    assert len(seen) == len(replies["greeting"])


@pytest.mark.parametrize(("kind", "status"), [("greeting", "social"), (None, "out_of_domain")])
def test_social_and_out_of_domain_answers_never_call_the_composer(kind, status):
    plan, _ = normalize_query_plan(
        _payload(social=kind or "none", out_of_domain=kind is None),
        query="Xin chào", selected_cohort="K51",
    )
    pipeline = _pipeline(plan)
    # The real executor, with the planner stubbed to return this plan.
    pipeline._plan_executor = PlanExecutor(
        router=pipeline.router, slang_normalizer=pipeline.slang_normalizer,
        catalogs=StructuredCatalogs([], [], [], [], [], []),
        parent_sources_by_id={}, top_k=5, public_source_limit=5,
    )
    pipeline._get_llm_client = lambda: (_ for _ in ()).throw(
        AssertionError("a fixed reply must not initialize the composer")
    )
    result = pipeline.answer("Xin chào", cohort="K51")
    assert result["status"] == status
    assert result["llm_called"] is False
    assert not result.get("citations_used")
    expected = load_replies()["greeting" if kind else "out_of_domain"]
    assert result["answer"] in [text.replace(COHORT_MARK, "K51") for text in expected]
