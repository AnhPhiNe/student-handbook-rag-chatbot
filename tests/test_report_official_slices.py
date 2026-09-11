import pytest

from scripts.report_official_slices import breakdown, reweighted
from src.evaluation.metrics import wilson_interval


def test_wilson_interval_matches_known_values():
    ci = wilson_interval(9, 10)
    assert ci["low"] == pytest.approx(0.596, abs=1e-3)
    assert ci["high"] == pytest.approx(0.982, abs=1e-3)
    assert wilson_interval(0, 0) == {"low": None, "high": None}


def test_breakdown_groups_by_slice_family_cohort_and_history():
    cases = {
        "a": {"slice": "single.structured", "cohort": "K51", "question_style": "realistic", "history": []},
        "b": {"slice": "single.regulation", "cohort": "K50", "question_style": "stress", "history": []},
        "c": {"slice": "memory.cohort_switch", "cohort": "K50", "question_style": "realistic",
              "history": [{"role": "user", "content": "x"}]},
    }
    report = {"suite": "deterministic", "cases": [
        {"id": "a", "passed": True}, {"id": "b", "passed": False}, {"id": "c", "passed": True}]}

    result = breakdown(report, cases, metric="answer_correctness")

    assert result["overall"]["all"]["n"] == 3
    assert result["family"]["single"]["mean"] == pytest.approx(0.5)
    assert result["family"]["memory"]["mean"] == 1.0
    assert result["slice"]["single.regulation"]["mean"] == 0.0
    assert result["history"]["with history"]["n"] == 1
    # Reweighting to 80% single questions and 20% follow-ups.
    assert reweighted(result["family"], {"single": 0.8, "memory": 0.2}) == pytest.approx(0.6)


def test_judge_reports_average_the_chosen_score():
    cases = {"a": {"category": "policy"}, "b": {"category": "policy"}}
    report = {"suite": "judge", "cases": [
        {"id": "a", "judge": {"scores": {"answer_correctness": 1.0}}},
        {"id": "b", "judge": {"scores": {"answer_correctness": 0.5}}}]}

    result = breakdown(report, cases, metric="answer_correctness")

    assert result["slice"]["policy"]["mean"] == pytest.approx(0.75)


def test_retrieval_reports_average_a_ranking_metric_with_a_wilson_interval_when_binary():
    cases = {"a": {"slice": "single.regulation"}, "b": {"slice": "single.regulation"}}
    report = {"suite": "retrieval", "cases": [{"id": "a", "hit_at_5": 1.0, "mrr": 0.5},
                                              {"id": "b", "hit_at_5": 0.0, "mrr": 0.25}]}

    hits = breakdown(report, cases, metric="hit_at_5")["overall"]["all"]
    mrr = breakdown(report, cases, metric="mrr")["overall"]["all"]

    assert hits["mean"] == 0.5
    assert hits["low"] == pytest.approx(wilson_interval(1, 2)["low"])
    assert mrr["mean"] == pytest.approx(0.375)
