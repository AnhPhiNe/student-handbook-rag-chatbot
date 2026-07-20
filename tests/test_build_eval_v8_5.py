from __future__ import annotations

from scripts.build_eval_v8_5 import ANSWER_CORRECTIONS, apply_answer_corrections


def test_v85_corrections_do_not_mutate_source_cases() -> None:
    source = [
        {"id": case_id, "query": "old", "cohort": "K51"}
        for case_id in ANSWER_CORRECTIONS
    ]

    corrected = apply_answer_corrections(source)

    assert all(case["query"] == "old" for case in source)
    assert {case["predecessor_case_id"] for case in corrected} == set(
        ANSWER_CORRECTIONS
    )
    assert all(case["id"].startswith("v85_ans_") for case in corrected)


def test_v85_corrections_disambiguate_subject_and_cohort() -> None:
    source = [
        {"id": case_id, "query": "old", "cohort": "K51"}
        for case_id in ANSWER_CORRECTIONS
    ]

    by_id = {case["id"]: case for case in apply_answer_corrections(source)}

    assert "cố vấn học tập" in by_id["v85_ans_009"]["query"]
    assert "cố vấn học tập" in by_id["v85_ans_021"]["query"]
    assert "viên chức" in by_id["v85_ans_050"]["query"]
    assert by_id["v85_ans_096"]["cohort"] == "K50"
