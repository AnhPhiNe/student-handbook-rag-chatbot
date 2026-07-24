from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.retrieval.core.ai_router import AIRouter
from src.retrieval.core.query_context import select_effective_query


CASES: list[dict[str, Any]] = [
    {
        "id": "accentless_regulation",
        "query": "K50 dieu kien bao luu ket qua hoc tap la gi?",
        "cohort": "K50",
        "expected_route": "rag",
        "expected_context": "standalone",
    },
    {
        "id": "typo_regulation",
        "query": "K51 dieu kien xet hoc bong khuyen khich hc tap?",
        "cohort": "K51",
        "expected_route": "rag",
        "expected_context": "standalone",
    },
    {
        "id": "office_abbreviation",
        "query": "email pdt o dau?",
        "expected_route": "structured",
        "expected_context": "standalone",
    },
    {
        "id": "faculty_abbreviation",
        "query": "phong cntt o dau?",
        "expected_route": "structured",
        "expected_context": "standalone",
    },
    {
        "id": "service_natural",
        "query": "tui cần in bảng điểm thì đến phòng nào?",
        "expected_route": "structured",
        "expected_context": "standalone",
    },
    {
        "id": "program_cohort",
        "query": "K51 Khoa CNTT có những ngành nào?",
        "cohort": "K51",
        "expected_route": "structured",
        "expected_context": "standalone",
    },
    {
        "id": "foreign_language_table",
        "query": "K50 IELTS 5.5 tương đương bậc mấy?",
        "cohort": "K50",
        "expected_route": "structured",
        "expected_context": "standalone",
    },
    {
        "id": "foreign_language_policy",
        "query": "K50 chưa có IELTS thì có được xét tốt nghiệp không?",
        "cohort": "K50",
        "expected_route": "rag",
        "expected_context": "standalone",
    },
    {
        "id": "numeric_preservation",
        "query": "K51 điểm rèn luyện 80 được xếp loại gì?",
        "cohort": "K51",
        "expected_route": "structured",
        "expected_context": "standalone",
    },
    {
        "id": "mixed_policy_table",
        "query": "K50 IELTS 5.5 đã đủ chuẩn để xét tốt nghiệp chưa?",
        "cohort": "K50",
        "expected_route": "rag",
        "expected_execution_mode": "mixed",
        "expected_context": "standalone",
    },
    {
        "id": "new_topic_after_history",
        "query": "Email Phòng Đào tạo là gì?",
        "history": [
            {"role": "user", "content": "K50 được bảo lưu tối đa bao lâu?"},
            {"role": "assistant", "content": "Quy định bảo lưu của K50..."},
        ],
        "expected_route": "structured",
        "expected_context": "standalone",
    },
    {
        "id": "follow_up_cohort",
        "query": "Còn K51 thì sao?",
        "history": [
            {
                "role": "user",
                "content": "K50 thời gian học tối đa của hệ chính quy là bao lâu?",
            },
            {
                "role": "assistant",
                "content": "K50 có thời gian học tối đa theo quy định của sổ tay.",
            },
        ],
        "expected_route": "structured",
        "expected_context": "follow_up",
    },
    {
        "id": "follow_up_entity",
        "query": "Còn số điện thoại?",
        "history": [
            {"role": "user", "content": "Email Phòng Đào tạo là gì?"},
            {"role": "assistant", "content": "Email của Phòng Đào tạo là..."},
        ],
        "expected_route": "structured",
        "expected_context": "follow_up",
    },
    {
        "id": "ambiguous_follow_up",
        "query": "Còn trường hợp đó thì sao?",
        "history": [
            {"role": "user", "content": "K50 được bảo lưu không?"},
            {"role": "user", "content": "K51 được xét học bổng không?"},
        ],
        "expected_route": "clarify",
        "expected_context": "ambiguous",
    },
    {
        "id": "missing_office_entity",
        "query": "Cho mình xin địa chỉ với?",
        "expected_route": "clarify",
        "expected_context": "ambiguous",
    },
    {
        "id": "out_of_domain",
        "query": "Thời tiết Thành phố Hồ Chí Minh hôm nay thế nào?",
        "expected_route": "out_of_domain",
        "expected_context": "standalone",
    },
    {
        "id": "formula",
        "query": "K50 công thức tính điểm trung bình học kỳ là gì?",
        "cohort": "K50",
        "expected_route": "structured",
        "expected_context": "standalone",
    },
    {
        "id": "regulation_short",
        "query": "K50 rớt môn thì sao?",
        "cohort": "K50",
        "expected_route": "rag",
        "expected_context": "standalone",
    },
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/eval/reports/query_handling_smoke.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    router = AIRouter.from_config()
    rows: list[dict[str, Any]] = []
    for case in CASES:
        started = time.perf_counter()
        try:
            decision = router.route(
                case["query"],
                cohort=case.get("cohort"),
                chat_history=case.get("history"),
            )
            handling = select_effective_query(
                case["query"],
                decision,
                selected_cohort=case.get("cohort"),
                chat_history=case.get("history"),
                mode="context_only",
            )
            context_ok = decision.get("context_mode") == case["expected_context"]
            route_ok = decision.get("route") == case["expected_route"]
            execution_ok = (
                not case.get("expected_execution_mode")
                or decision.get("execution_mode") == case["expected_execution_mode"]
            )
            handling_ok = (
                handling.needs_clarification
                if case["expected_route"] == "clarify"
                else not handling.needs_clarification
            )
            row = {
                **case,
                "route": decision.get("route"),
                "execution_mode": decision.get("execution_mode"),
                "context_mode": decision.get("context_mode"),
                "normalized_query": decision.get("normalized_query"),
                "standalone_query": decision.get("standalone_query"),
                "effective_query": handling.effective_query,
                "query_source": handling.source,
                "validation_errors": list(handling.validation_errors),
                "router_cache_hit": bool(decision.get("router_cache_hit")),
                "route_ok": route_ok,
                "execution_ok": execution_ok,
                "context_ok": context_ok,
                "handling_ok": handling_ok,
                "passed": route_ok and execution_ok and context_ok and handling_ok,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        except Exception as exc:
            row = {
                **case,
                "passed": False,
                "error": str(exc),
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        rows.append(row)
        print(
            f"[{len(rows):02d}/{len(CASES)}] {case['id']}: "
            f"{'PASS' if row['passed'] else 'FAIL'}"
        )

    passed = sum(bool(row["passed"]) for row in rows)
    report = {
        "summary": {
            "n": len(rows),
            "passed": passed,
            "pass_rate": passed / len(rows),
            "mean_latency_ms": sum(row["latency_ms"] for row in rows) / len(rows),
        },
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
