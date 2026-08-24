from __future__ import annotations

import json
import os
import sys
import time
import argparse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.generation.answer_pipeline import AnswerPipeline
from src.retrieval.core.ai_router import AIRouter


CASES: list[dict[str, Any]] = [
    {
        "id": "two_structured_domains",
        "query": "K51 IELTS 6.0 tương đương bậc mấy và điểm học bổng loại giỏi là bao nhiêu?",
        "min_tasks": 2,
        "required_modes": {"structured"},
        "expected_task_cohorts": {"K51"},
    },
    {
        "id": "structured_plus_regulation",
        "query": "K51 điểm học bổng loại giỏi là bao nhiêu và thủ tục xin xác nhận sinh viên thực hiện thế nào?",
        "min_tasks": 2,
        "required_modes": {"structured", "rag"},
        "expected_task_cohorts": {"K51"},
    },
    {
        "id": "two_regulation_topics",
        "query": "K51 quy định về cảnh báo học tập là gì và khi nào sinh viên bị buộc thôi học?",
        "min_tasks": 2,
        "required_modes": {"rag"},
        "expected_task_cohorts": {"K51"},
    },
    {
        "id": "multi_cohort_multi_intent",
        "query": "So sánh K48-K49 và K51 về thời gian học tối đa và chuẩn đầu ra ngoại ngữ.",
        "min_tasks": 2,
        "required_modes": {"rag"},
        "expected_task_cohorts": {"K48-K49", "K51"},
    },
    {
        "id": "two_sentences_one_message",
        "query": "K51 thời gian học tối đa là bao lâu? Điểm học bổng loại xuất sắc là bao nhiêu?",
        "min_tasks": 2,
        "required_modes": {"structured", "clarify"},
        "expected_task_cohorts": {"K51"},
    },
    {
        "id": "same_tool_two_entities",
        "query": "K51 IELTS 6.0 và TOEFL iBT 60 lần lượt tương đương bậc mấy?",
        "min_tasks": 1,
        "max_tasks": 1,
        "required_modes": {"structured"},
        "expected_task_cohorts": {"K51"},
    },
    {
        "id": "partial_answer",
        "query": "K51 điều kiện nhận học bổng là gì và quy định về dịch chuyển tức thời giữa các cơ sở như thế nào?",
        "min_tasks": 2,
        "required_modes": {"rag"},
        "expected_task_cohorts": {"K51"},
        "expected_noncovered_task_position": 1,
    },
    {
        "id": "more_than_three_requests",
        "query": (
            "K51 cho mình biết điểm học bổng loại giỏi, thời gian học tối đa, "
            "IELTS 6.0 tương đương bậc mấy và thủ tục xin xác nhận sinh viên."
        ),
        "min_tasks": 1,
        "max_tasks": 1,
        "required_modes": {"clarify"},
        "expected_task_cohorts": {"K51"},
    },
]


def _case_checks(case: dict[str, Any], result: dict[str, Any]) -> list[str]:
    plan = result.get("query_plan") or {}
    failures = _plan_checks(case, plan)

    coverage = result.get("coverage_by_task") or {}
    for task_id, status in coverage.items():
        if status == "covered" and not any(
            task_id in (citation.get("supports_task_ids") or [])
            for citation in (result.get("citations_used") or [])
        ):
            failures.append(f"covered_without_citation={task_id}")
    if len(result.get("citations_used") or []) > 10:
        failures.append("citations>10")
    if result.get("planner_fallback") and result.get("planner_fallback") != "legacy_rag":
        failures.append("invalid_planner_fallback")
    return failures


def _plan_checks(case: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    tasks = plan.get("tasks") or []
    modes = {str(task.get("mode")) for task in tasks}
    failures: list[str] = []
    if len(tasks) < int(case.get("min_tasks", 1)):
        failures.append(f"task_count<{case['min_tasks']}")
    max_tasks = case.get("max_tasks", 3)
    if len(tasks) > int(max_tasks):
        failures.append(f"task_count>{max_tasks}")
    missing_modes = set(case.get("required_modes") or set()) - modes
    if missing_modes:
        failures.append(f"missing_modes={sorted(missing_modes)}")
    expected_cohorts = set(case.get("expected_task_cohorts") or set())
    if expected_cohorts:
        for task in tasks:
            actual_cohorts = set(task.get("cohorts") or [])
            if actual_cohorts != expected_cohorts:
                failures.append(
                    f"cohort_scope:{task.get('id')}={sorted(actual_cohorts)}"
                    f" expected={sorted(expected_cohorts)}"
                )
    return failures


def _case_warnings(case: dict[str, Any], result: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    position = case.get("expected_noncovered_task_position")
    if isinstance(position, int):
        tasks = (result.get("query_plan") or {}).get("tasks") or []
        if 0 <= position < len(tasks):
            task_id = tasks[position].get("id")
            coverage = (result.get("coverage_by_task") or {}).get(task_id)
            if coverage == "covered":
                warnings.append(
                    f"expected_noncovered_but_rule_coverage_is_covered={task_id}; defer relevance threshold to P1"
                )
    return warnings


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--case", action="append", dest="case_ids")
    args = parser.parse_args()
    selected_cases = [
        case for case in CASES if not args.case_ids or case["id"] in set(args.case_ids)
    ]

    os.environ.setdefault("STUDENT_RAG_DISABLE_ROUTER_CACHE", "1")
    os.environ.setdefault("STUDENT_RAG_QUERY_PLAN_ENABLED", "1")

    if args.plan_only:
        router = AIRouter.from_config()
        failed = 0
        for case in selected_cases:
            plan = router.plan(case["query"], cohort=None, chat_history=[])
            failures = _plan_checks(case, plan)
            if plan.get("planner_fallback"):
                failures.append(f"planner_fallback={plan['planner_fallback']}")
            row = {
                "id": case["id"],
                "passed": not failures,
                "failures": failures,
                "planner_fallback": plan.get("planner_fallback"),
                "planner_validation_errors": plan.get("planner_validation_errors") or [],
                "tasks": plan.get("tasks") or [],
                "planner_error_type": plan.get("planner_error_type"),
                "planner_error": plan.get("planner_error"),
            }
            if failures:
                failed += 1
            print(json.dumps(row, ensure_ascii=False), flush=True)
        return 1 if failed else 0

    pipeline = AnswerPipeline()
    if hasattr(pipeline.response_cache, "enabled"):
        pipeline.response_cache.enabled = False

    rows: list[dict[str, Any]] = []
    for case in selected_cases:
        started = time.perf_counter()
        try:
            result = pipeline.answer(case["query"], cohort=None)
            failures = _case_checks(case, result)
            warnings = _case_warnings(case, result)
            row = {
                "id": case["id"],
                "passed": not failures,
                "failures": failures,
                "warnings": warnings,
                "latency_seconds": round(time.perf_counter() - started, 2),
                "status": result.get("status"),
                "llm_called": result.get("llm_called"),
                "planner_fallback": result.get("planner_fallback"),
                "tasks": (result.get("query_plan") or {}).get("tasks") or [],
                "coverage_by_task": result.get("coverage_by_task") or {},
                "citation_count": len(result.get("citations_used") or []),
                "answer_preview": str(result.get("answer") or "")[:1000],
            }
        except Exception as exc:
            row = {
                "id": case["id"],
                "passed": False,
                "failures": [f"{type(exc).__name__}: {exc}"],
                "latency_seconds": round(time.perf_counter() - started, 2),
            }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    summary = {
        "total": len(rows),
        "passed": sum(bool(row["passed"]) for row in rows),
        "failed": sum(not bool(row["passed"]) for row in rows),
        "failed_ids": [row["id"] for row in rows if not row["passed"]],
        "warnings": sum(len(row.get("warnings") or []) for row in rows),
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False), flush=True)
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
