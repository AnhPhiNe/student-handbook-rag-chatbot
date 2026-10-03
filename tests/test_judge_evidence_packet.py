"""Source preservation and compaction contracts, without a model or new gold."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.evaluation.answers import judge_answers
from src.evaluation.judge import (
    JUDGE_METRICS,
    JUDGE_PACKET_VERSION,
    _authorized_packet_evidence_units,
    _numbered_source_clauses,
    build_judge_prompt,
    compact_judge_packet,
)


def case(query="Điều kiện áp dụng là gì?", required=None):
    return {"id": "packet-test", "query": query, "cohort": "K50", "required_facts": required or []}


def record(answer, sources, **extra):
    return {"id": "packet-test", "answer": answer, "status": "answered",
            "context_used": json.dumps({"units": [{"task_id": "t1", "cohort": "K50",
                "primary_evidence": sources, "applicable_amendments": []}]}, ensure_ascii=False), **extra}


def source(**extra):
    return {"source_ref": "S1", "source_id": "parent-k50", "source_cohort": "K50",
            "article_label": "Điều 8", "title": "Phạm vi áp dụng", **extra}


def test_source_context_reaches_judge_with_original_qualifiers_and_table_layout():
    policy = "Chỉ áp dụng cho chương trình thứ nhất.\nKhông áp dụng khi đã quá thời gian chuẩn.\n| Loại | Hệ số |\n| Giỏi | 1,25 |"
    answer = record("Không áp dụng khi đã quá thời gian chuẩn.", [source(content="Hệ số: 1,25", source_context=policy)])
    packet = compact_judge_packet(case(), answer)
    assert "Task: t1 | Cohort: K50 | Source: S1" in packet["retrieved_context"]
    assert "Article: Điều 8" in packet["retrieved_context"]
    assert "Source context: " + policy in packet["retrieved_context"]
    assert packet["packet_version"] == JUDGE_PACKET_VERSION


def test_extra_answer_conditions_are_kept_even_when_gold_only_checks_the_main_fact():
    main = "Sinh viên được đăng ký chuyển ngành khi đủ điều kiện."
    conditions = "Phải đạt điều kiện trúng tuyển và được Trưởng khoa cùng Hiệu trưởng đồng ý."
    noise = "Hướng dẫn chuyển ngành cho sinh viên khi đủ điều kiện tại từng khóa.\n" * 150
    answer = record(main + "\n" + conditions, [source(content=main + "\n" + noise + conditions)])
    packet = compact_judge_packet(case("Chuyển ngành được không?", [main]), answer, max_input_tokens=700)
    assert main in packet["retrieved_context"] and conditions in packet["retrieved_context"]


def test_currency_note_is_retained_under_pressure_from_query_relevant_noise():
    note = "Quy chế này đã được thay thế bởi Quyết định 2000/QĐ-ĐHSP ngày 15/7/2024."
    answer = record("Kết quả là 0 điểm.\n" + note, [source(
        content="Kết quả là 0 điểm.\n" + "Sinh viên xem kết quả rèn luyện theo từng kỳ.\n" * 100,
        printed_in="Sổ tay sinh viên K50", currency_note=note,
    )])
    packet = compact_judge_packet(case("Kết quả rèn luyện thế nào?", ["Kết quả là 0 điểm."]), answer, max_input_tokens=700)
    assert "Currency note: " + note in packet["retrieved_context"]


def test_short_condition_is_anchored_even_when_answer_paraphrases_it_with_citation():
    condition = "Nghỉ do bệnh dài ngày cần chứng nhận của cơ sở khám chữa bệnh có thẩm quyền."
    answer = record(
        "Theo Sổ tay khóa K50 tại Điều 8, người học bị ốm điều trị thời gian dài cần có chứng nhận của cơ sở khám bệnh, chữa bệnh có thẩm quyền.",
        [source(content=condition + "\n" + "Theo quy định sinh viên nghỉ học hoặc tiếp tục học trong chương trình, khóa và thời gian học được xác định cho người học.\n" * 100)],
    )
    packet = compact_judge_packet(case("Nghỉ học cần hồ sơ gì?"), answer, max_input_tokens=700)
    assert condition in packet["retrieved_context"]


def test_atomic_source_context_does_not_lose_a_later_exception():
    policy = "Sinh viên đủ điểm được xem xét.\nNgoại lệ: sinh viên bị kỷ luật không được xét."
    units = _authorized_packet_evidence_units(record("q", [source(content="Đủ điểm.", source_context=policy)])["context_used"])
    contexts = [unit for unit in units if "Source context:" in unit]
    assert len(contexts) == 1 and contexts[0].endswith(policy)


def test_numbered_provision_keeps_all_subconditions_table_and_exception():
    first = "Điều 8. Áp dụng\n\n1. Các điều kiện:\na) Có minh chứng;\nb) Đúng phạm vi.\n\n| Loại | Điểm |\n| A | 3.6 |\n\nNgoại lệ: thiếu hồ sơ thì không áp dụng."
    second = "2. Nghĩa vụ báo cáo."
    clauses = _numbered_source_clauses(first + "\n\n" + second)
    assert clauses == [first, "Điều 8. Áp dụng\n\n" + second]
    assert "| Loại | Điểm |\n| A | 3.6 |" in clauses[0]
    assert "Ngoại lệ: thiếu hồ sơ thì không áp dụng." in clauses[0]


def test_source_intro_scope_follows_a_later_selected_clause():
    intro = "Chỉ áp dụng cho học phần nền tảng, không áp dụng cho các học phần khác."
    clauses = _numbered_source_clauses(intro + "\n\n1. Hồ sơ đăng ký.\n\n2. Điều kiện đạt là đủ điểm và đủ minh chứng.")
    assert len(clauses) == 2
    assert all(clause.startswith(intro + "\n\n") for clause in clauses)
    assert "2. Điều kiện đạt là đủ điểm và đủ minh chứng." in clauses[1]


def test_decimal_values_and_table_rows_do_not_create_clause_boundaries():
    text = "Điểm trung bình tối thiểu:\n3.6 hoặc cao hơn.\n| 1. Loại A | 3.6 |\nĐiều kiện kèm theo: đủ hồ sơ."
    assert _numbered_source_clauses(text) == [text]


def test_long_article_can_keep_short_relevant_provision_without_truncation():
    relevant = "2. Sinh viên chưa có minh chứng không được xét kết quả; không tự suy từ điểm số."
    article = "1. Trách nhiệm báo cáo. " + "Các đơn vị phải báo cáo theo học kỳ. " * 140 + "\n\n" + relevant
    answer = record("Sinh viên chưa có minh chứng không được xét kết quả.", [source(content="Điểm 8.", source_context=article)])
    packet = compact_judge_packet(case("Có được xét kết quả không?"), answer, max_input_tokens=700)
    assert "Source context: " + relevant in packet["retrieved_context"]
    assert packet["evidence_compaction"]["partial_units"] == 0
    assert "1. Trách nhiệm báo cáo." not in packet["retrieved_context"]


@pytest.mark.parametrize("case_id,markers", [
    ("official_ans_033", ["Được điều động vào lực lượng vũ trang", "Vì lý do cá nhân khác",
                          "không thuộc các trường hợp bị xem xét buộc thôi học", "Hai tuần trước khi hết thời gian tạm dừng"]),
    ("official_ans_129", ["Những điểm chữ không được quy định", "Những học phần không nằm trong yêu cầu",
                          "chương trình thứ nhất", "06 năm học", "7,5 năm học"]),
])
def test_saved_output_keeps_omitted_conditions_in_real_default_packet(case_id, markers):
    fixture_path = Path(__file__).parent / "fixtures/judge_compaction_saved_outputs.json"
    fixture = next(row for row in json.loads(fixture_path.read_text(encoding="utf-8")) if row["case"]["id"] == case_id)
    before = copy.deepcopy(fixture)
    packet = compact_judge_packet(fixture["case"], fixture["answer_record"])
    compact = " ".join(packet["retrieved_context"].split()).casefold()
    original = " ".join(fixture["answer_record"]["context_used"].split()).casefold()
    for marker in markers:
        assert marker.casefold() in original
        assert marker.casefold() in compact
    assert fixture == before
    assert packet["evidence_compaction"]["partial_units"] == 0
    assert packet["answer"] == fixture["answer_record"]["answer"]


def test_structured_json_is_not_split_inside_an_address_or_reordered():
    rows = [{"unit_name": "Đơn vị A", "emails": ["a@example.edu"], "office": "TP. HCM."},
            {"unit_name": "Đơn vị B", "emails": ["b@example.edu"], "office": "Nhà B."}]
    body = json.dumps(rows, ensure_ascii=False)
    units = _authorized_packet_evidence_units(record("q", [source(content=body)])["context_used"])
    assert len(units) == 1
    assert json.loads(units[0].split(" | ")[-1]) == rows


def test_resolved_result_stays_valid_json_before_whole_unit_compaction():
    resolved = {"unit_name": "Đơn vị A", "qualification": "Điều kiện có thật. " * 150}
    units = _authorized_packet_evidence_units(record("q", [source(content="q", resolved_result=resolved)])["context_used"])
    value = next(unit for unit in units if "Resolved result:" in unit)
    assert json.loads(value.split("Resolved result: ", 1)[1]) == resolved
    assert "[truncated]" not in value


def test_unapproved_execution_json_citations_or_gold_cannot_become_evidence():
    secret = "special-contact@example.edu"
    answer = record(secret, [source(content="Nguồn chỉ nêu địa chỉ văn phòng.")],
                    structured_result={"emails": [secret]}, citations=[{"content": secret}])
    packet = compact_judge_packet({**case(), "ground_truth": secret, "required_facts": [secret]}, answer)
    assert secret in packet["ground_truth"] and secret in packet["answer"]
    assert secret not in packet["retrieved_context"]
    assert packet["required_facts_present_in_packet"] == []


@pytest.mark.parametrize("units", [[], [{"task_id": "t1", "cohort": "K50", "primary_evidence": []}]])
def test_an_empty_authorized_packet_does_not_resurrect_public_citations(units):
    answer = {"answer": "Dữ liệu không đủ.", "context_used": json.dumps({"units": units}),
              "citations": [{"content": "Nguồn ngoài packet."}], "structured_result": {"result": "Ngoài packet"}}
    packet = compact_judge_packet(case(), answer)
    assert packet["retrieved_context"] == ""
    assert packet["evidence_compaction"]["candidate_units"] == 0


def test_related_references_and_unapproved_source_context_are_not_primary_evidence():
    context = {"units": [{"task_id": "t1", "cohort": "K50", "primary_evidence": [source(content="Nguồn chính.")],
                "related_references": [source(content="Nguồn phụ chưa được phép.", source_context="Điều kiện ngoài packet.")]}],
               "source_context": "Ngữ cảnh toàn cục không được cấp cho task."}
    packet = compact_judge_packet(case(), {"answer": "Nguồn chính.", "context_used": json.dumps(context)})
    assert "Nguồn chính." in packet["retrieved_context"]
    assert "Nguồn phụ" not in packet["retrieved_context"]
    assert "ngoài packet" not in packet["retrieved_context"]
    assert "Ngữ cảnh toàn cục" not in packet["retrieved_context"]


def test_multi_task_cohort_and_amendment_provenance_stays_separate():
    context = {"units": [
        {"task_id": "t1", "cohort": "K50", "primary_evidence": [source(content="Hệ số 1,0.", source_context="Chỉ áp dụng hệ số 1,0 cho K50.")]},
        {"task_id": "t2", "cohort": "K51", "primary_evidence": [source(content="Hệ số 1,25.", source_context="Chỉ áp dụng hệ số 1,25 cho K51.", source_cohort="K51")],
         "applicable_amendments": [{"amendment_source": "Quyết định K51", "effective_rule": "Áp dụng riêng K51.", "replacement_text": "Hệ số mới 1,25."}]},
    ]}
    packet = compact_judge_packet(case(), {"answer": "K50 1,0; K51 1,25.", "context_used": json.dumps(context)})
    assert "Task: t1 | Cohort: K50" in packet["retrieved_context"]
    assert "Task: t2 | Cohort: K51" in packet["retrieved_context"]
    assert "Chỉ áp dụng hệ số 1,0 cho K50." in packet["retrieved_context"]
    assert "Chỉ áp dụng hệ số 1,25 cho K51." in packet["retrieved_context"]
    assert "Task: t2 | Cohort: K51 | Amendment: Quyết định K51" in packet["retrieved_context"]


def test_compaction_omits_an_oversized_unit_without_cutting_its_condition():
    long_clause = "Chỉ được áp dụng khi " + "điều kiện rất dài " * 120 + "và không bị kỷ luật."
    packet = compact_judge_packet(case(), record("q", [source(content=long_clause)]), max_input_tokens=200)
    assert long_clause not in packet["retrieved_context"]
    assert "Chỉ được áp dụng khi" not in packet["retrieved_context"]
    assert packet["evidence_compaction"] == {"candidate_units": 1, "retained_units": 0, "omitted_units": 1, "partial_units": 0}


def test_wrong_number_is_not_replaced_with_gold_or_classified_as_supported_by_compactor():
    answer = record("Hệ số là 1,5.", [source(content="Hệ số là 1,0.")])
    packet = compact_judge_packet(case(required=["Hệ số là 1,5."]), answer)
    assert "Hệ số là 1,0." in packet["retrieved_context"]
    assert "Hệ số là 1,5." not in packet["retrieved_context"]
    assert packet["required_facts_present_in_packet"] == []
    assert "1,5" in packet["answer"]  # Judge must see the error, not a corrected answer.


def test_packet_building_is_deterministic_and_does_not_mutate_inputs_or_rubric():
    gold = case(required=["Kết quả có điều kiện."])
    answer = record("Kết quả có điều kiện.", [source(content="Kết quả có điều kiện.", source_context="Không áp dụng khi thiếu minh chứng.")])
    original = copy.deepcopy((gold, answer))
    first = compact_judge_packet(gold, answer)
    assert first == compact_judge_packet(gold, answer) and (gold, answer) == original
    prompt = build_judge_prompt(first)
    assert "Do not reward fluent wording over factual correctness" in prompt
    assert "Set unsupported_claim true only when" in prompt
    assert "looks acceptable but contains a dangerous/decisive wrong claim" in prompt


def test_packet_version_is_bound_to_checkpoint_and_report(tmp_path):
    class Judge:
        def judge(self, packet):
            assert packet["packet_version"] == JUDGE_PACKET_VERSION
            return {"ok": True, "scores": {**{metric: 1.0 for metric in JUDGE_METRICS},
                                           "unsupported_claim": False, "critical_false_pass": False}}

    path = tmp_path / "judge.json"
    report = judge_answers([case()], [record("q", [source(content="q")])],
                           checkpoint_path=path, resume=False, judge_client=Judge())
    identity = json.loads(path.with_suffix(".json.identity.json").read_text(encoding="utf-8"))
    assert identity["context"]["judge_packet_version"] == JUDGE_PACKET_VERSION
    assert report["summary"]["judge_packet_version"] == JUDGE_PACKET_VERSION
    assert report["cases"][0]["judge_packet_version"] == JUDGE_PACKET_VERSION
    assert report["cases"][0]["packet_evidence_compaction"]["partial_units"] == 0


def test_changed_packet_version_rejects_resume_without_touching_old_scores(tmp_path, monkeypatch):
    class Judge:
        def judge(self, packet):
            return {"ok": True, "scores": {**{metric: 1.0 for metric in JUDGE_METRICS},
                                           "unsupported_claim": False, "critical_false_pass": False}}

    path = tmp_path / "judge.json"
    args = ([case()], [record("q", [source(content="q")])])
    judge_answers(*args, checkpoint_path=path, resume=False, judge_client=Judge())
    original = path.read_bytes()
    monkeypatch.setattr("src.evaluation.answers.JUDGE_PACKET_VERSION", "another-contract")
    with pytest.raises(ValueError, match="identity mismatch"):
        judge_answers(*args, checkpoint_path=path, resume=True, judge_client=Judge())
    assert path.read_bytes() == original
