"""Exercise planner-owned inputs through validation, execution and evidence merge."""

import json
from pathlib import Path

from src.generation.answer_pipeline import AnswerPipeline
from src.generation.prompt_builder import build_authorized_evidence_packet
from src.retrieval.core.citation_builder import build_citation_from_lookup
from src.retrieval.core.query_plan import normalize_query_plan
from src.retrieval.core.structured_dispatcher import resolve_structured_decision


def _task(question, lookup_type, slots, spans, cohorts):
    return {
        "question": question,
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": lookup_type,
        "slots": slots,
        "slot_spans": spans,
        "cohorts": cohorts,
    }


def _resolve(task, cohort):
    tables = json.loads(
        Path("data/processed/tables/structured_tables_registry.json").read_text(
            encoding="utf-8"
        )
    )
    return resolve_structured_decision(
        task, query=task["question"], cohort=cohort,
        scoring_tables=[], formula_rules=[], office_directory=[],
        student_service_directory=[], student_faculty_profiles=[],
        foreign_language_tables=[], structured_tables_registry=tables,
        program_directory=[],
    )


def test_validated_inputs_keep_task_and_cohort_identity_through_packet():
    questions = [
        "K50 và K51: 7,6 điểm môn đại cương ra chữ gì?",
        "K51: 6,1 điểm môn còn lại ra chữ gì?",
        "K50: hệ chính quy học bằng đại học đầu tiên tối đa bao lâu?",
    ]
    raw_tasks = [
        _task(questions[0], "scoring", {
            "operation": "grade_10_to_letter", "score_or_grade": "7,6",
            "course_scope": "foundation",
        }, {"score_or_grade": "7,6", "course_scope": "môn đại cương"}, ["K50", "K51"]),
        _task(questions[1], "scoring", {
            "operation": "grade_10_to_letter", "score_or_grade": "6,1",
            "course_scope": "remaining",
        }, {"score_or_grade": "6,1", "course_scope": "môn còn lại"}, ["K51"]),
        _task(questions[2], "study_duration", {
            "training_mode": "chinh_quy", "program_type": "first_degree",
        }, {"training_mode": "chính quy", "program_type": "bằng đại học đầu tiên"}, ["K50"]),
    ]
    query = " ".join(questions)
    plan, errors = normalize_query_plan(
        {"context_mode": "standalone", "tasks": raw_tasks}, query=query,
        selected_cohort="K51",
    )
    assert errors == []
    assert len(plan["tasks"]) == 3
    citations, expected = [], {}
    for task in plan["tasks"]:
        assert task["mode"] == "structured"
        for cohort in task["cohorts"]:
            resolution = _resolve(task, cohort)
            assert resolution is not None
            lock = resolution.result["resolved_result"]
            assert lock["cohort"] == cohort
            expected[(task["id"], cohort)] = lock
            citations.extend(
                {**citation, "supports_task_ids": [task["id"]]}
                for citation in build_citation_from_lookup(resolution.result)
            )
    packet = build_authorized_evidence_packet(
        query=query,
        retrieval_result={
            "query_plan": plan,
            "coverage_by_task": {task["id"]: "covered" for task in plan["tasks"]},
        },
        selected_citations=AnswerPipeline._merge_task_citations(citations),
        fallback_cohort="K51", max_context_chars=30000,
    )
    seen = set()
    for unit in packet["units"]:
        for evidence in unit["primary_evidence"]:
            lock = evidence.get("resolved_result")
            if lock:
                key = (unit["task_id"], lock["cohort"])
                # Packet compaction removes UI-only rows, not the locked
                # value or its source/task/cohort identity.
                for field in ("result", "cohort", "table_id", "source_parent_id"):
                    assert lock[field] == expected[key][field]
                seen.add(key)
    assert seen == set(expected)


def test_missing_duration_selector_stays_evidence_only_after_normalization():
    query = "K50 chính quy, bằng thứ nhất học tối đa bao lâu?"
    task = _task(query, "study_duration", {"training_mode": "chinh_quy"},
                 {"training_mode": "chính quy"}, ["K50"])
    plan, errors = normalize_query_plan(
        {"context_mode": "standalone", "tasks": [task]}, query=query,
        selected_cohort="K50",
    )
    assert errors == []
    normalized = plan["tasks"][0]
    assert "program_type" not in normalized["slots"]
    resolution = _resolve(normalized, "K50")
    assert resolution is not None
    assert resolution.resolution_status == "evidence_only"
    assert len(resolution.result["items"]) == 4
