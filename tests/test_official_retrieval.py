"""Offline integrity checks, not retrieval-quality measurements."""
import json
import copy
import pytest
from collections import Counter

from scripts.build_official_retrieval import BUNDLE, build, validate_relevance


def test_retrieval_draft_counts_and_compiled_artifact():
    cases = build()
    assert len(cases) == 155
    assert Counter(c.get("allocation_cohort", c["cohort"]) for c in cases) == {"K48-K49": 52, "K50": 52, "K51": 51}
    assert Counter(c["question_style"] for c in cases) == {"realistic": 124, "stress": 31}
    assert cases == json.loads((BUNDLE / "retrieval_cases.json").read_text(encoding="utf-8"))


def test_every_retrieval_draft_has_cohort_grounded_source_and_remains_unfrozen():
    for case in build():
        assert case["query"].strip()
        assert case["frozen"] is False
        assert case["independent_holdout"] is False
        for judgment, evidence in zip(case["relevance_judgments"], case["gold_evidence"]):
            assert judgment["cohort"] in case.get("requested_cohorts", [case["cohort"]])
            assert judgment["parent_section_id"] == evidence["source_id"]
            assert evidence["anchor"] in evidence["context"]
            assert len(evidence["content_sha256"]) == 64


def test_cohort_article_numbering_is_not_assumed_identical():
    cases = build()
    assert cases[87]["relevance_judgments"][0]["parent_section_id"].endswith("Chuong5_Dieu27")
    assert cases[131]["relevance_judgments"][0]["parent_section_id"].startswith("K51_QuyCheDanhGiaRenLuyen_")


def test_multi_source_recall_requires_both_cohorts():
    from src.evaluation.retrieval import _retrieval_metrics_for_execution_units

    case = build()[34]
    grades = {j["parent_section_id"]: j["grade"] for j in case["relevance_judgments"]}
    assert case["cohort"] == "general"
    metrics, scope = _retrieval_metrics_for_execution_units(
        case=case, ranked_ids=list(grades)[:1], grade_by_id=grades, scope="end_to_end")
    assert scope == "per_cohort_execution_unit"
    assert metrics["required_source_recall_at_5"] == 0.5
    assert metrics["hit_at_5"] == 0
    complete, _ = _retrieval_metrics_for_execution_units(
        case=case, ranked_ids=list(grades), grade_by_id=grades, scope="end_to_end")
    assert complete["required_source_recall_at_5"] == 1


def test_multi_article_questions_require_every_primary_source():
    from src.evaluation.retrieval import _retrieval_metrics_for_execution_units

    case = build()[4]
    grades = {j["parent_section_id"]: j["grade"] for j in case["relevance_judgments"]}
    assert len(grades) == 2
    metrics, _ = _retrieval_metrics_for_execution_units(
        case=case, ranked_ids=list(grades)[:1], grade_by_id=grades, scope="end_to_end")
    assert metrics["required_source_recall_at_5"] == 0.5


def test_sufficient_exclusion_source_does_not_require_background_article():
    from src.evaluation.retrieval import _retrieval_metrics_for_execution_units

    case = build()[89]
    grades = {j["parent_section_id"]: j["grade"] for j in case["relevance_judgments"]}
    primary = [key for key, grade in grades.items() if grade == 2]
    assert len(primary) == 1 and sorted(grades.values()) == [1, 2]
    metrics, _ = _retrieval_metrics_for_execution_units(
        case=case, ranked_ids=primary, grade_by_id=grades, scope="end_to_end")
    assert metrics["required_source_recall_at_5"] == 1


def test_registration_comparison_requires_permissions_not_warning_background():
    from src.evaluation.retrieval import _retrieval_metrics_for_execution_units

    case = build()[44]
    grades = {j["parent_section_id"]: j["grade"] for j in case["relevance_judgments"]}
    primary = [key for key, grade in grades.items() if grade == 2]
    assert len(primary) == 2
    assert grades["K51_QuyCheDaoTao_Chuong3_Dieu12"] == 1
    complete, _ = _retrieval_metrics_for_execution_units(
        case=case, ranked_ids=primary, grade_by_id=grades, scope="end_to_end")
    assert complete["required_source_recall_at_5"] == 1
    incomplete, _ = _retrieval_metrics_for_execution_units(
        case=case, ranked_ids=primary[:1], grade_by_id=grades, scope="end_to_end")
    assert incomplete["required_source_recall_at_5"] == 0.5


def test_equivalent_source_either_suffices_without_double_credit():
    from src.evaluation.retrieval import _retrieval_metrics_for_execution_units

    for index in (106, 112, 149):
        case = build()[index]
        grades = {j["parent_section_id"]: j["grade"] for j in case["relevance_judgments"]}
        for ids in ([list(grades)[0]], [list(grades)[1]], list(grades)):
            metrics, _ = _retrieval_metrics_for_execution_units(
                case=case, ranked_ids=ids, grade_by_id=grades, scope="end_to_end")
            assert metrics["required_source_recall_at_5"] == 1
            assert metrics["ndcg_at_5"] == 1


def test_equivalent_duplicates_do_not_pull_rank_six_into_top_five():
    from src.evaluation.retrieval import _retrieval_metrics_for_execution_units

    case = {"cohort": "K50", "equivalent_source_groups": [["a", "b"]]}
    metrics, _ = _retrieval_metrics_for_execution_units(
        case=case, ranked_ids=["a", "b", "x", "y", "z", "c"],
        grade_by_id={"a": 2, "b": 2, "c": 2}, scope="end_to_end")
    assert metrics["required_source_recall_at_5"] == 0.5


@pytest.mark.parametrize("mutation", ["missing_source", "cross_cohort", "background", "overlap"])
def test_invalid_equivalence_gold_rejected(mutation):
    case = copy.deepcopy(build()[106])
    if mutation == "missing_source":
        case["equivalent_source_groups"][0].append("not-in-gold")
    elif mutation == "cross_cohort":
        case["requested_cohorts"] = ["K50", "K51"]
        case["relevance_judgments"][1]["cohort"] = "K51"
    elif mutation == "background":
        case["relevance_judgments"][1]["grade"] = 1
    else:
        case["equivalent_source_groups"].append(case["equivalent_source_groups"][0][:])
    with pytest.raises(AssertionError):
        validate_relevance(case)
