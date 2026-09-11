"""Offline tests for the held-out answer and retrieval builders. No model calls."""
from collections import Counter
from pathlib import Path

import pytest
import yaml

from scripts.build_holdout_suites import build
from scripts.build_official_deterministic import ROOT, build as build_deterministic
from src.evaluation.dataset import validate_deterministic_case

WARNING = "Điểm trung bình học kỳ đạt dưới 0,8"
FIRST_YEAR = "dưới 1,2 đối với sinh viên trình độ năm thứ nhất"


def write_bundle(tmp_path: Path, cases: list[dict], extras: list[dict] | None = None) -> Path:
    bundle = tmp_path / "official_v2"
    bundle.mkdir()
    authoring = {"settings": {"id_prefix": "official_v2_det", "independent_holdout": True,
                              "expected": {"cases": len(cases)}}, "cases": cases}
    (bundle / "deterministic_authoring.yaml").write_text(yaml.safe_dump(authoring, allow_unicode=True), encoding="utf-8")
    if extras is not None:
        (bundle / "retrieval_authoring.yaml").write_text(yaml.safe_dump({"cases": extras}, allow_unicode=True), encoding="utf-8")
    return bundle


def test_suites_share_the_deterministic_gold(tmp_path):
    history = [{"role": "user", "content": "Bị cảnh báo học tập khi nào?"},
               {"role": "assistant", "content": "Khi điểm trung bình học kỳ quá thấp."}]
    policy = {"policy": ["QuyCheDaoTao_Chuong3_Dieu12", WARNING], "fact": "Dưới 0,8 ở học kỳ đầu."}
    bundle = write_bundle(tmp_path, [
        {"query": "GPA 2,76 là loại gì?", "category": "scoring", "slice": "single.scoring",
         "selected_cohort": "K51", "table": ["academic_classification", 2, "academic_classification"],
         "input_slots": {"score_or_grade": 2.76}},
        {"query": "ĐTB học kỳ dưới bao nhiêu thì bị cảnh báo?", "category": "policy",
         "slice": "single.regulation", "selected_cohort": "K51", **policy},
        {"query": "Còn K50 thì sao?", "category": "memory", "slice": "memory.cohort_switch",
         "selected_cohort": "K51", "history": history, "cohort": "K50", **policy},
        {"query": "Năm nhất bị cảnh báo khi nào, K50 và K51?", "category": "compound",
         "slice": "multi_cohort.regulation", "selected_cohort": "K51", "tasks": [
             {"cohort": "K50", "policy": ["QuyCheDaoTao_Chuong3_Dieu12", FIRST_YEAR], "fact": "Dưới 1,2."},
             {"cohort": "K51", "policy": ["QuyCheDaoTao_Chuong3_Dieu12", FIRST_YEAR], "fact": "Dưới 1,2."}]},
        {"query": "Rèn luyện của em loại gì?", "category": "insufficient_input", "slice": "boundary.clarify",
         "selected_cohort": "K50", "clarify": "Thiếu điểm rèn luyện."},
        {"query": "Cách nấu phở?", "category": "out_of_domain", "slice": "boundary.out_of_domain",
         "selected_cohort": "K50", "out_of_domain": True},
    ], extras=[{"query": "Bị cảnh báo học tập khi nào?", "selected_cohort": "K48-K49",
                "policy": ["QuyCheDaoTao_Chuong3_Dieu12", WARNING]}])

    answers, retrieval = build(bundle)

    assert [a["id"] for a in answers] == [f"official_v2_ans_{i:03d}" for i in range(1, 7)]
    assert answers[0]["required_facts"] == ["[K51] Học tập: Xếp loại: Khá"]
    assert answers[1]["required_facts"] == ["[K51] Dưới 0,8 ở học kỳ đầu."]
    # A follow-up keeps its history and the cohort it asks about, not the UI cohort.
    assert answers[2]["history"] == history and answers[2]["requested_cohorts"] == ["K50"]
    assert answers[3]["cohort"] == "K51" and answers[3]["requested_cohorts"] == ["K50", "K51"]
    assert answers[4]["expected_path"] == "clarify" and answers[5]["answerability"] == "unanswerable"
    # Retrieval: policy questions without history, then the retrieval-only extras.
    assert [r["id"] for r in retrieval] == ["official_v2_ret_002", "official_v2_ret_004", "official_v2_ret_extra_001"]
    assert retrieval[1]["cohort"] == "general" and retrieval[1]["requested_cohorts"] == ["K50", "K51"]
    assert retrieval[2]["cohort"] == "K48-K49" and all(r["independent_holdout"] for r in retrieval)


def test_equivalent_sources_form_one_requirement(tmp_path):
    anchor = "thay thế cho điểm thi kết thúc học phần"
    bundle = write_bundle(tmp_path, [{
        "query": "Đề tài NCKH có thay điểm thi được không?", "category": "policy", "slice": "single.regulation",
        "selected_cohort": "K50", "policy": ["QuyDinhNghienCuuKhoaHocSinhVien_Chuong4_Dieu14", anchor],
        "fact": "Được, không quá 3 tín chỉ.", "equivalent": [["QuyCheDaoTao_Chuong3_Dieu10", anchor]]}])

    _, retrieval = build(bundle)

    assert retrieval[0]["equivalent_source_groups"] == [[
        "K50_QuyDinhNghienCuuKhoaHocSinhVien_Chuong4_Dieu14", "K50_QuyCheDaoTao_Chuong3_Dieu10"]]
    assert [j["grade"] for j in retrieval[0]["relevance_judgments"]] == [2, 2]


def test_policy_task_without_an_authored_fact_is_rejected(tmp_path):
    bundle = write_bundle(tmp_path, [{
        "query": "ĐTB học kỳ dưới bao nhiêu thì bị cảnh báo?", "category": "policy", "slice": "single.regulation",
        "selected_cohort": "K51", "policy": ["QuyCheDaoTao_Chuong3_Dieu12", WARNING]}])

    with pytest.raises(AssertionError, match="Missing authored policy fact"):
        build(bundle)


def test_official_v2_compiles_against_the_current_catalogs():
    bundle = ROOT / "data/eval/official_v2"
    cases = build_deterministic(bundle)
    errors = []
    for case in cases:
        validate_deterministic_case(case, errors)
    answers, retrieval = build(bundle)

    assert errors == []
    assert len(answers) == len(cases)
    assert max(Counter(c["cohort"] for c in cases).values()) - min(Counter(c["cohort"] for c in cases).values()) <= 2
    assert sum(bool(c["history"]) for c in cases) >= 20
    assert len(retrieval) >= 90
