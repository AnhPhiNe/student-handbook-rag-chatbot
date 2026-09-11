"""Offline authoring checks, not chatbot quality metrics."""
import json
from collections import Counter

from scripts.build_official_answers import BUNDLE, build


def test_answer_policy_drafts_are_source_backed_and_unfrozen():
    cases = build()
    assert len(cases) == 150
    assert Counter(c.get("allocation_cohort", c["cohort"]) for c in cases) == {"K48-K49": 50, "K50": 50, "K51": 50}
    assert Counter(c["question_style"] for c in cases) == {"realistic": 120, "stress": 30}
    assert cases == json.loads((BUNDLE / "generated_answer_cases.json").read_text(encoding="utf-8"))
    for case in cases:
        assert case["frozen"] is False
        assert case["independent_holdout"] is False
        assert case["ground_truth"] and case["required_facts"]
    for case in cases[:60]:
        evidence = case["gold_evidence"][0]
        assert evidence["cohort"] == case["cohort"]
        assert evidence["anchor"] in " ".join(evidence["content"].split())
        assert evidence["source_id"] == case["expected_citations"][0]["parent_section_id"]
        assert len(evidence["content_sha256"]) == 64


def test_answer_gold_uses_complete_parent_not_retrieval_preview():
    case = build()[29]
    assert "03 năm" in case["gold_evidence"][0]["content"]
    assert "Nội dung:" in case["gold_evidence"][0]["content"]
    assert "pending" in case["review_status"]


def test_compound_gold_preserves_requested_parts_and_cohorts():
    cases = build()
    assert len(cases[126]["answer_units"]) == 3
    assert {u["cohort"] for u in cases[123]["answer_units"]} == {"K50", "K51"}
    assert "cao nhất" in cases[123]["required_facts"][1]
    assert "lần học cuối" in cases[123]["required_facts"][0]
    assert {u["mode"] for u in cases[125]["answer_units"]} == {"rag", "structured"}
    partial = cases[129]
    assert partial["expected_path"] == "clarify"
    assert partial["expected_structured_sources"]
    assert len(partial["required_facts"]) == 2


def test_missing_and_live_data_cases_do_not_have_invented_values():
    cases = build()
    for case in cases[144:]:
        assert not case["gold_evidence"]
        assert case["required_facts"]
    assert cases[145]["expected_answer_behavior"] == "clarify_or_scope"
    assert cases[146]["answerability"] == "unanswerable"


def test_structured_sources_are_recognized_by_existing_evaluator():
    from scripts.build_official_answers import ROOT
    from src.evaluation.dataset import _structured_source_index, _structured_record_matches_cohort

    index = _structured_source_index(ROOT)
    for case in build():
        for source in case.get("expected_structured_sources", []):
            assert (source["catalog"], source["source_id"]) in index, (case["id"], source)
            assert _structured_record_matches_cohort(index[(source["catalog"], source["source_id"])], source["cohort"])


def test_official_semantic_gold_does_not_become_a_lexical_failure():
    from src.evaluation.answers import _answer_checks
    case = build()[60]
    checks = _answer_checks(case, {"status": "answered", "answer": "GPA của em xếp loại xuất sắc."})
    assert checks["required_fact_hit"] is None
    assert checks["question_handling_correctness"] is None
    assert checks["answer_success"] is True
    legacy = {**case, "lexical_fact_check_applicable": True}
    assert isinstance(_answer_checks(legacy, {"status": "answered", "answer": "Xuất sắc"})["required_fact_hit"], bool)


def test_judge_packet_receives_guidance_but_not_gold_as_retrieved_evidence():
    from src.evaluation.judge import compact_judge_packet
    case = build()[129]
    packet = compact_judge_packet(case, {"status": "needs_clarification", "answer": "Em có GPA bao nhiêu?"})
    assert packet["evaluation_notes"] == case["evaluation_notes"]
    assert len(packet["required_facts"]) == 2
    assert "trungtamnn@hcmue.edu.vn" in packet["ground_truth"]
    assert "trungtamnn@hcmue.edu.vn" not in packet["retrieved_context"]


def test_all_answers_satisfy_common_evaluator_fields():
    from src.evaluation.dataset import _validate_common
    errors = []
    for case in build():
        _validate_common(case, "answers", errors)
        assert len(case["ground_truth"]) < 4000
    assert not errors


def test_structured_gold_is_scoped_to_requested_answer():
    cases = build()
    assert "Thang điểm 4" not in cases[60]["ground_truth"]
    assert "input_requirements" not in cases[104]["ground_truth"]
    assert "Công thức" not in cases[104]["ground_truth"]
    assert "gpa_weighted_average" not in cases[105]["ground_truth"]
    assert "B1 Preliminary" not in cases[90]["ground_truth"]
    assert "Xuất sắc" in cases[101]["ground_truth"] and "Giỏi" in cases[101]["ground_truth"]
    assert "Học tập" in cases[121]["required_facts"][0]
    assert "Rèn luyện" in cases[121]["required_facts"][1]


def test_official_run_snapshot_records_the_planner_identity(monkeypatch):
    """The snapshot is built before any model call; it must not touch removed router fields."""
    from scripts.run_official_answers import _snapshot
    from src.common.key_pool import KeyPoolConfig

    monkeypatch.setenv("GROQ_ROUTER_API_KEYS", "test-key")
    # Keep the throwaway key out of the local key-state file.
    monkeypatch.setattr("src.retrieval.core.ai_router.router_key_pool_config",
                        lambda _config: KeyPoolConfig(name="ai_router", rpm_limit_per_key=1))
    snapshot = _snapshot("retrieval", BUNDLE / "retrieval_cases.json")

    assert snapshot["planner"]["provider"] == "groq"
    assert snapshot["planner"]["model"]
    assert snapshot["dataset"] == "data/eval/official_v1/retrieval_cases.json"
