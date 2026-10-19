"""Catalog referral for parts without evidence (composer v3.44, official_v4 SPEC run S)."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.generation.answer_pipeline import AnswerPipeline, StreamAnswerCleaner
from src.generation.catalog_referral import (
    collect_referrals,
    referable_tasks,
    render_referrals,
    split_unsupported_marker,
)
from src.generation.prompt_builder import render_answer_prompt
from src.retrieval.core.directory_selector import DirectorySelector

CATALOG = [
    {"service_id": "K51_tram_y_te_service_4", "cohort": "K51", "unit_name": "Trạm Y tế",
     "service": "Làm thẻ và phát thẻ bảo hiểm y tế", "phones": ["(028) 38352020"],
     "internal_numbers": ["152"], "emails": ["tramyte@hcmue.edu.vn"], "websites": [],
     "office": "Nhà A, tầng trệt, P.011"},
    {"service_id": "K51_phong_ke_hoach_tai_chinh_service_2", "cohort": "K51",
     "unit_name": "Phòng Kế hoạch – Tài chính",
     "service": "Thực hiện việc cấp HBKKHT và chi trả các chế độ, chính sách hỗ trợ cho sinh viên",
     "phones": ["(028) 38352020"], "internal_numbers": ["136", "137"],
     "emails": ["phongkhtc@hcmue.edu.vn"], "websites": ["phongkhtc.hcmue.edu.vn"],
     "office": "Nhà A, tầng 2, P.205"},
]
ANSWER = "Theo Sổ tay sinh viên khóa K51, điều kiện xét học bổng là Khá trở lên.\n\nVề thời điểm chuyển tiền: sổ tay chưa quy định."


def _selector(reply):
    client = Mock()
    client.generate.return_value = {"ok": True, "text": json.dumps(reply)}
    thinking = Mock()
    thinking.generate.side_effect = AssertionError("the referral path never asks the thinking retry")
    return DirectorySelector(client, thinking), client


def _pipeline(chunks, reply):
    tasks = [{"id": "t1", "mode": "rag", "question": "Điều kiện xét học bổng?", "cohorts": ["K51"]},
             {"id": "t2", "mode": "rag", "question": "Khi nào tiền học bổng được chuyển?", "cohorts": ["K51"]}]
    citation = {"chunk_id": "p1", "cohort": "K51", "content": "Điều 27. Kết quả học tập từ loại Khá trở lên.",
                "supports_task_ids": ["t1", "t2"]}
    result = {
        "query_plan": {"tasks": tasks},
        "task_results": [{"task_id": t["id"], "question": t["question"], "mode": "rag", "cohorts": ["K51"],
                          "coverage": "covered", "execution_mode_by_cohort": {"K51": "rag"}} for t in tasks],
        "coverage_by_task": {"t1": "covered", "t2": "covered"},
        "citations": [citation], "evidence_citations": [citation],
        "retrieved_items": [{"chunk_id": "p1", "content": citation["content"]}],
    }
    pipeline = object.__new__(AnswerPipeline)
    pipeline.config = {"guardrails": {"skip_llm_on_low_confidence": True}}
    pipeline.llm_config = {"model_name": "offline-fake"}
    pipeline.model_name = "offline-fake"
    pipeline.max_context_chars = 10000
    pipeline._run_retrieval = lambda *args, **kwargs: result
    selector, selector_client = _selector(reply)
    pipeline._plan_executor = SimpleNamespace(
        directory_selector=selector, catalogs=SimpleNamespace(student_service_directory=CATALOG))
    llm = Mock()
    llm.generate.return_value = {"ok": True, "text": "".join(chunks), "usage": {}}
    llm.generate_stream.side_effect = lambda prompt: iter(chunks)
    pipeline._get_llm_client = lambda: llm
    return pipeline, selector_client


def _answer(pipeline, transport):
    if transport == "sync":
        result = pipeline.answer("Điều kiện học bổng và khi nào chuyển tiền?", cohort="K51")
        return result["answer"], result["catalog_referrals"]
    events = list(pipeline.answer_stream("Điều kiện học bổng và khi nào chuyển tiền?", cohort="K51"))
    return "".join(e["text"] for e in events if e["type"] == "token"), None


def test_the_marker_is_split_off_with_its_task_ids():
    assert split_unsupported_marker(ANSWER + "\n[[CHUA_CAN_CU: t2, t3]]") == (ANSWER, ["t2", "t3"])
    assert split_unsupported_marker(ANSWER) == (ANSWER, [])
    # A marker the composer did not finish is removed too, and lists nothing.
    assert split_unsupported_marker(ANSWER + "\n[[CHUA_CAN") == (ANSWER, [])


@pytest.mark.parametrize("transport", ["sync", "stream"])
def test_a_marked_part_gets_the_catalog_unit_with_the_catalog_contacts(transport):
    chunks = [ANSWER[:40], ANSWER[40:], "\n[[CHUA_CA", "N_CU: t2]]"]
    pipeline, selector_client = _pipeline(chunks, {"decision": "match", "ids": ["S02"]})
    answer, decisions = _answer(pipeline, transport)
    assert "[[" not in answer and "CHUA_CAN_CU" not in answer
    assert answer.startswith(ANSWER)
    assert "Sổ tay không quy định về ý này" in answer and "**Phòng Kế hoạch – Tài chính**" in answer
    # Contacts come from the catalog record, untouched by the identifier corrector.
    assert "phongkhtc@hcmue.edu.vn" in answer and "số máy nội bộ 136, 137" in answer
    # One selector call per referable task, each asked with the task question and the query.
    assert selector_client.generate.call_count == 2
    prompts = [call.args[0] for call in selector_client.generate.call_args_list]
    assert any("Khi nào tiền học bổng được chuyển?" in prompt and "câu hỏi gốc" in prompt for prompt in prompts)
    if decisions is not None:
        assert decisions == [{"task_id": "t2", "status": "match",
                              "service_id": "K51_phong_ke_hoach_tai_chinh_service_2",
                              "unit_name": "Phòng Kế hoạch – Tài chính",
                              "reply": json.dumps({"decision": "match", "ids": ["S02"]}), "cohort": "K51"}]


@pytest.mark.parametrize("reply", [{"decision": "none", "ids": []},
                                   {"decision": "ambiguous", "ids": ["S01", "S02"]},
                                   {"not": "json the selector accepts"}])
@pytest.mark.parametrize("transport", ["sync", "stream"])
def test_no_referral_and_no_question_when_the_selector_does_not_match(transport, reply):
    pipeline, _ = _pipeline([ANSWER + "\n[[CHUA_CAN_CU: t2]]"], reply)
    answer, decisions = _answer(pipeline, transport)
    assert answer == ANSWER
    if decisions is not None:
        assert len(decisions) == 1 and decisions[0]["task_id"] == "t2" and decisions[0]["status"] != "match"


@pytest.mark.parametrize("transport", ["sync", "stream"])
def test_an_answer_without_the_marker_gets_no_referral(transport):
    pipeline, _ = _pipeline([ANSWER], {"decision": "match", "ids": ["S02"]})
    answer, decisions = _answer(pipeline, transport)
    assert answer == ANSWER
    assert decisions in (None, [])


def test_the_stream_still_reads_a_marker_after_a_dropped_source_footer():
    cleaner = StreamAnswerCleaner()
    for chunk in [ANSWER + "\n\nNguồn:\n- Điều 27", "\n[[CHUA_CAN_CU: t2]]"]:
        cleaner.feed(chunk)
    cleaner.finish()
    assert "Nguồn" not in cleaner.text and "[[" not in cleaner.text
    assert cleaner.unsupported == ["t2"]


def test_only_tasks_read_from_regulation_text_are_referable():
    result = {"task_results": [
        {"task_id": "t1", "question": "Số điện thoại Phòng Đào tạo?", "mode": "structured",
         "execution_mode_by_cohort": {"K51": "structured"}},
        {"task_id": "t2", "question": "Khi nào có lịch thi?", "mode": "structured",
         "execution_mode_by_cohort": {"K51": "rag"}},
    ]}
    assert referable_tasks(result) == [{"task_id": "t2", "question": "Khi nào có lịch thi?", "cohort": "K51"}]
    assert collect_referrals({}, ["t1"]) == [{"task_id": "t1", "status": "not_referable"}]


def test_one_block_per_unit():
    decision = {"status": "match", "unit_name": "Trạm Y tế", "record": CATALOG[0]}
    text = render_referrals([{"task_id": "t1", **decision}, {"task_id": "t2", **decision}])
    assert text.count("Trạm Y tế") == 1 and "số máy nội bộ 152" in text


def test_the_prompt_asks_for_the_marker_and_keeps_grounded_units():
    prompt, _ = render_answer_prompt("Hỏi?", {"units": []})
    assert "[[CHUA_CAN_CU: task_id]]" in prompt
    assert "Được nêu một đơn vị và thông tin liên hệ của đơn vị đó khi evidence cho biết đơn vị đó làm đúng việc được hỏi" in prompt
    assert "không nêu đơn vị, số điện thoại hay email lấy từ đoạn khác" in prompt


def test_the_referral_wording_leaves_the_directory_lookup_prompts_unchanged():
    """The referral asks which unit is in charge; the lookups keep their exact wording (2026-10-19)."""
    import hashlib

    from src.retrieval.core.directory_selector import render_prompt

    records = [{"unit_name": "Trạm Y tế", "service": "Làm thẻ và phát thẻ bảo hiểm y tế", "aliases": []},
               {"unit_name": "Phòng Đào tạo", "service": "Tổ chức đăng ký học phần", "aliases": ["PĐT"]}]
    expected = {
        "student_service": "9de226a5b65d3204685cef3c001646082d06f4e0250617ac6ff7fe00f517c047",
        "office": "4d2a957e1c6d6d37c75d27e2165a64ff3274cbc70b0ad4841aba6fe3bf51ecac",
        "faculty": "197187befd278710d4cf78ce167ff83769ad2f584715a492c7548cb9e6afa831",
    }
    for lookup_type, digest in expected.items():
        prompt, _ = render_prompt(lookup_type, "thẻ bảo hiểm y tế", records,
                                  question="Em mất thẻ BHYT thì làm lại ở đâu?", requested_field="phone")
        assert hashlib.sha256(prompt.encode()).hexdigest() == digest, lookup_type
    referral, _ = render_prompt("service_referral", "Căn tin mở cửa mấy giờ?", records, question="Căn tin?")
    assert "đơn vị phụ trách đúng việc đó" in referral and "thông tin riêng của một người" in referral


# The template (owner, 2026-10-19): when every composed task is marked and matched, the body is
# replaced, because retrieved passages that do not answer still carried other units' contacts into it.

@pytest.mark.parametrize("transport", ["sync", "stream"])
def test_the_template_replaces_the_body_when_every_composed_task_is_unsupported(transport):
    from src.generation.prompt_builder import handbook_label

    body = "Phòng CTCT&HSSV, email nghidinh116@hcmue.edu.vn, nhánh 127. " * 12  # a long body the stream would release
    pipeline, _ = _pipeline([body[:300], body[300:], "\n[[CHUA_CAN_CU: t1, t2]]"],
                            {"decision": "match", "ids": ["S02"]})
    if transport == "stream":
        events = list(pipeline.answer_stream("Điều kiện học bổng và khi nào chuyển tiền?", cohort="K51"))
        tokens = [e["text"] for e in events if e["type"] == "token"]
        assert not any("nghidinh116" in token or "CTCT" in token for token in tokens)  # no body text shown
        answer = "".join(tokens)
        assert events[-1]["citations_used"] == []
    else:
        result = pipeline.answer("Điều kiện học bổng và khi nào chuyển tiền?", cohort="K51")
        answer = result["answer"]
        assert result["referral_template"] is True and result["citations_used"] == []
    record = CATALOG[1]
    assert answer.startswith(f"{handbook_label('K51')} không quy định về việc này.")
    assert f"Bạn có thể liên hệ **{record['unit_name']}** (phụ trách: {record['service']}):" in answer
    # The contacts are the catalog record's, field for field; one block for the one unit.
    assert "- Điện thoại: (028) 38352020, số máy nội bộ 136, 137" in answer
    assert "- Email: phongkhtc@hcmue.edu.vn" in answer and "- Website: phongkhtc.hcmue.edu.vn" in answer
    assert "- Văn phòng: Nhà A, tầng 2, P.205" in answer
    assert answer.count("Bạn có thể liên hệ") == 1 and "nghidinh116" not in answer


@pytest.mark.parametrize("transport", ["sync", "stream"])
def test_a_mixed_question_keeps_the_body_and_adds_the_referral(transport):
    pipeline, _ = _pipeline([ANSWER, "\n[[CHUA_CAN_CU: t2]]"], {"decision": "match", "ids": ["S02"]})
    answer, _ = _answer(pipeline, transport)
    assert answer.startswith(ANSWER) and "Gợi ý nơi liên hệ" in answer and "không quy định về việc này." not in answer


@pytest.mark.parametrize("transport", ["sync", "stream"])
def test_all_unsupported_without_a_match_keeps_the_body(transport):
    pipeline, _ = _pipeline([ANSWER, "\n[[CHUA_CAN_CU: t1, t2]]"], {"decision": "none", "ids": []})
    answer, _ = _answer(pipeline, transport)
    assert answer == ANSWER


def test_the_template_needs_every_composed_task_marked_and_matched():
    from src.generation.catalog_referral import template_applies

    match = lambda task_id: {"task_id": task_id, "status": "match", "record": CATALOG[0]}  # noqa: E731
    assert template_applies(["t1", "t2"], ["t1", "t2"], [match("t1"), match("t2")])
    assert not template_applies(["t1", "t2"], ["t2"], [match("t2")])  # t1 has evidence
    assert not template_applies(["t1", "t2"], ["t1", "t2"], [match("t1"), {"task_id": "t2", "status": "none"}])
    assert not template_applies([], ["t1"], [match("t1")])
