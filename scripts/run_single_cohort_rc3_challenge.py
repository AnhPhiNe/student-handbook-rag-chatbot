"""Run the bounded RC3 Planner challenge before a development evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_single_cohort_v2 import run_live_planner  # noqa: E402
from src.common.cohort import (  # noqa: E402
    cohort_registry_digest,
    cohort_registry_version,
)
from src.generation.answer_pipeline import AnswerPipeline  # noqa: E402
from src.retrieval.core.ai_router import (  # noqa: E402
    ROUTER_CONTRACT_VERSION,
    ROUTER_PROMPT_VERSION,
    ROUTER_VALIDATOR_VERSION,
)
from src.retrieval.core.structured_routing import (  # noqa: E402
    load_lookup_registry,
    registry_digest,
)


CHALLENGE_PATH = ROOT / "data" / "eval" / "single_cohort_v2" / "rc3_challenge.json"
EXPECTED_COUNTS = {
    "follow_up_cohort_provenance": 8,
    "metadata_vs_information_need": 6,
    "registry_capability": 6,
    "two_regulations_source_binding": 4,
}


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "single-cohort-rc3-challenge-v1":
        raise ValueError("Unsupported RC3 challenge schema.")
    if payload.get("max_remediation_rounds") != 2:
        raise ValueError("RC3 challenge must remain capped at two remediation rounds.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("RC3 challenge must contain exactly 24 cases.")
    if Counter(case.get("category") for case in cases) != EXPECTED_COUNTS:
        raise ValueError("RC3 challenge category coverage is invalid.")
    return cases


def _planner_case(case: dict[str, Any]) -> dict[str, Any]:
    """Fill evaluator-neutral defaults without changing the annotated semantics."""

    expected = dict(case["expected"])
    expected.setdefault("query_mode", "validated")
    requests: list[dict[str, Any]] = []
    for index, raw_request in enumerate(expected.get("atomic_requests") or [], start=1):
        request = dict(raw_request)
        request.setdefault("request_id", f"r{index}")
        request.setdefault("slots", {})
        request.setdefault("slot_spans", {})
        request.setdefault("expected_status", "ok")
        requests.append(request)
    expected["atomic_requests"] = requests
    return {**case, "expected": expected}


def _citation_value(citation: dict[str, Any], field: str) -> Any:
    metadata = citation.get("metadata")
    return citation.get(field) or (
        metadata.get(field) if isinstance(metadata, dict) else None
    )


def _source_contract_bound(
    citations: list[dict[str, Any]],
    request: dict[str, Any],
) -> bool:
    scoped = [
        citation
        for citation in citations
        if citation.get("request_id") == request["request_id"]
    ]
    if not scoped:
        return False
    required = {"document_id", "parent_section_id", "source_pages"}
    if request["request_kind"] == "rag":
        required.add("chunk_id")
    return all(
        all(_citation_value(citation, field) for field in required)
        for citation in scoped
    )


def _run_execution(
    cases: list[dict[str, Any]],
    planner_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pipeline = AnswerPipeline()
    planner_by_id = {str(row["id"]): row for row in planner_rows}
    rows: list[dict[str, Any]] = []
    for case in cases:
        expected = case["expected"]
        planner_row = planner_by_id[case["id"]]
        if expected["outcome"] != "execute":
            passed = bool(planner_row.get("execution_eligible"))
            rows.append(
                {
                    "id": case["id"],
                    "passed": passed,
                    "retrieval_executed": False,
                    "source_contract_binding": True,
                }
            )
            continue
        if not planner_row.get("execution_eligible"):
            rows.append(
                {
                    "id": case["id"],
                    "passed": False,
                    "failure_type": "planner_not_execution_eligible",
                }
            )
            continue
        decision = planner_row["validated_decision"]
        effective_query = str(decision.get("effective_query") or case["query"])
        retrieval_query = pipeline.slang_normalizer.normalize_for_retrieval(
            effective_query
        )
        try:
            result = pipeline._execute_single_cohort_retrieval(
                query=case["query"],
                effective_query=effective_query,
                retrieval_query=retrieval_query,
                cohort=decision.get("cohort"),
                router_decision=dict(decision),
                query_handling=dict(decision.get("query_handling") or {}),
                chat_history=case.get("chat_history") or [],
            )
            actual_statuses = {
                str(item.get("request_id")): item.get("status")
                for item in result.get("request_results") or []
            }
            expected_requests = expected.get("atomic_requests") or []
            citations = result.get("citations") or []
            request_ids = {request["request_id"] for request in expected_requests}
            status_binding = all(
                actual_statuses.get(request["request_id"])
                == request["expected_status"]
                for request in expected_requests
            )
            source_binding = all(
                _source_contract_bound(citations, request)
                for request in expected_requests
                if request["expected_status"] == "ok"
            )
            isolation = all(
                citation.get("request_id") in request_ids for citation in citations
            )
            passed = status_binding and source_binding and isolation
            rows.append(
                {
                    "id": case["id"],
                    "passed": passed,
                    "status_binding": status_binding,
                    "source_contract_binding": source_binding,
                    "citation_isolation": isolation,
                    "retrieval_executed": bool(result.get("retrieval_executed")),
                    "request_statuses": actual_statuses,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "id": case["id"],
                    "passed": False,
                    "failure_type": "execution_error",
                    "error_type": type(exc).__name__,
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=CHALLENGE_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call the pinned Planner; omit for deterministic bundle validation only.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run adapter/retrieval source contracts after a live Planner pass.",
    )
    args = parser.parse_args()
    cases = _load_cases(args.input)
    working_tree_diff = subprocess.check_output(
        ["git", "diff", "--binary"], cwd=ROOT
    )
    working_tree_status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT
    )
    report: dict[str, Any] = {
        "schema_version": "single-cohort-rc3-challenge-report-v1",
        "input": str(args.input),
        "case_count": len(cases),
        "category_counts": dict(Counter(case["category"] for case in cases)),
        "live": args.live,
        "execute": args.execute,
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "working_tree_dirty": bool(working_tree_status),
        "working_tree_state_sha256": hashlib.sha256(
            working_tree_diff + working_tree_status + args.input.read_bytes()
        ).hexdigest(),
        "planner_versions": {
            "contract": ROUTER_CONTRACT_VERSION,
            "prompt": ROUTER_PROMPT_VERSION,
            "validator": ROUTER_VALIDATOR_VERSION,
        },
        "tool_registry_sha256": hashlib.sha256(
            registry_digest(load_lookup_registry()).encode("utf-8")
        ).hexdigest(),
        "cohort_registry_version": cohort_registry_version(),
        "cohort_registry_digest": cohort_registry_digest(),
        "passed": True,
    }
    if args.execute and not args.live:
        parser.error("--execute requires --live.")
    if args.live:
        planner_cases = [_planner_case(case) for case in cases]
        rows = run_live_planner(planner_cases)
        report["rows"] = rows
        report["provider_failures"] = sum(
            bool(row.get("provider_failure")) for row in rows
        )
        report["execution_eligible_rate"] = sum(
            bool(row.get("execution_eligible")) for row in rows
        ) / len(rows)
        report["passed"] = (
            report["provider_failures"] == 0
            and report["execution_eligible_rate"] == 1.0
        )
        if args.execute and report["passed"]:
            execution_rows = _run_execution(planner_cases, rows)
            report["execution_rows"] = execution_rows
            report["passed"] = all(row["passed"] for row in execution_rows)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
