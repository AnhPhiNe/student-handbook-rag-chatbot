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
                              "reply": json.dumps({"decision": "match", "ids": ["S02"]})}]


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
