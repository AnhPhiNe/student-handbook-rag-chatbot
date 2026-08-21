"""Run the modern deterministic single-cohort production smoke matrix.

The matrix is intentionally independent from hidden data and retired legacy
bundles.  Each entry is an existing production-path integration contract; the
report records per-case duration as telemetry, while pass/fail remains strict.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.artifact_fingerprint import release_artifact_fingerprint  # noqa: E402


SMOKE_CASES = (
    (
        "structured_two_requests",
        "tests/test_semantic_request_executor.py::test_two_structured_requests_keep_numeric_slots_isolated",
    ),
    (
        "mixed_independent_execution",
        "tests/test_semantic_request_executor.py::test_structured_and_rag_requests_execute_independently",
    ),
    (
        "structured_same_tool_twice",
        "tests/test_semantic_request_executor.py::test_same_structured_tool_can_execute_twice",
    ),
    (
        "formula_sync_cache",
        "tests/test_structured_low_confidence_contract.py::test_source_bound_formula_bypasses_rag_low_confidence_in_sync_and_cache",
    ),
    (
        "formula_stream_cache",
        "tests/test_structured_low_confidence_contract.py::test_source_bound_formula_bypasses_rag_low_confidence_in_stream_and_cache",
    ),
    (
        "rag_no_match",
        "tests/test_semantic_request_executor.py::test_rag_without_source_bound_evidence_is_no_match_and_not_composed",
    ),
    (
        "rag_child_source_binding",
        "tests/test_semantic_request_executor.py::test_rag_evidence_requires_matching_child_chunk_within_parent_source",
    ),
    (
        "grounded_follow_up",
        "tests/test_semantic_request_executor.py::test_follow_up_rag_request_keeps_validated_grounding_in_retrieval_query",
    ),
    (
        "ungrounded_follow_up",
        "tests/test_query_context.py::test_no_history_unresolved_follow_up_still_clarifies",
    ),
    (
        "two_regulations",
        "tests/test_semantic_routing_contract.py::test_two_regulations_become_two_rag_requests",
    ),
    (
        "multi_cohort_rejection",
        "tests/test_single_cohort_contract.py::test_multi_cohort_is_rejected_before_execution",
    ),
    (
        "mixed_partial_success",
        "tests/test_semantic_request_executor.py::test_partial_success_preserves_error_for_composer",
    ),
    (
        "request_exception",
        "tests/test_semantic_request_executor.py::test_all_request_exceptions_are_infrastructure_error",
    ),
    (
        "structured_no_fallback",
        "tests/test_semantic_request_executor.py::test_unresolved_structured_request_never_falls_back_to_rag",
    ),
    (
        "sync_stream_cache_parity",
        "tests/test_request_scoped_pipeline.py::test_sync_then_stream_cache_have_composition_debug_parity",
    ),
    (
        "stream_authoritative_replacement",
        "tests/test_request_scoped_pipeline.py::test_uncached_stream_buffers_until_contract_validated_replacement",
    ),
    (
        "cache_fingerprint_isolation",
        "tests/test_response_cache.py::ResponseCacheTest::test_cache_key_changes_with_context_fingerprint",
    ),
    (
        "plan_tampering",
        "tests/test_single_cohort_contract.py::test_post_validation_plan_tampering_clarifies_without_retrieval_or_cache",
    ),
    (
        "router_provider_failure",
        "tests/test_single_cohort_contract.py::test_router_provider_failure_is_not_reported_as_clarification",
    ),
    (
        "cross_request_citation_rejection",
        "tests/test_request_answer_contract.py::test_rag_draft_rejects_cross_request_citation",
    ),
)


def _commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def run_case(case_id: str, node_id: str) -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", node_id],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return {
        "id": case_id,
        "node_id": node_id,
        "passed": result.returncode == 0,
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip():
        parser.error("Production smoke requires a clean worktree")

    rows = [run_case(case_id, node_id) for case_id, node_id in SMOKE_CASES]
    report = {
        "report_type": "single_cohort_production_smoke_v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": _commit(),
        "provider": "deterministic",
        "artifact_fingerprint": release_artifact_fingerprint(ROOT),
        "case_count": len(rows),
        "passed": all(row["passed"] for row in rows),
        "latency_blocking": False,
        "checks": {row["id"]: row["passed"] for row in rows},
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "commit": report["commit"],
                "passed": report["passed"],
                "case_count": report["case_count"],
                "failed": [row["id"] for row in rows if not row["passed"]],
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
