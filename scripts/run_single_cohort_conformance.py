"""Create commit-bound quality, parity and fault-conformance artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
NPM = shutil.which("npm") or shutil.which("npm.cmd") or "npm"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.artifact_fingerprint import (  # noqa: E402
    release_artifact_fingerprint,
)


def _commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _fingerprint() -> dict[str, str | None]:
    return release_artifact_fingerprint(ROOT)


def _run(command: list[str], *, cwd: Path = ROOT) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as exc:
        return {
            "passed": False,
            "returncode": None,
            "command": command,
            "output_tail": f"{type(exc).__name__}: {exc}",
        }
    output = completed.stdout or ""
    return {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "command": command,
        "output_tail": output[-8000:],
    }


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Diagnostic only; skipped frontend checks remain failed.",
    )
    args = parser.parse_args()

    temp_root = ROOT / ".tmp" / "single-cohort-conformance"
    def targeted(name: str, *nodes: str) -> dict[str, Any]:
        temp_root.mkdir(parents=True, exist_ok=True)
        return _run(
            [
                str(PYTHON), "-B", "-m", "pytest", *nodes,
                "-p", "no:cacheprovider", "--basetemp", str(temp_root / name),
            ]
        )

    parity_run = targeted(
        "parity",
        "tests/test_single_cohort_debug_parity.py::test_sync_stream_and_cached_debug_metadata_have_contract_parity",
    )
    status_run = targeted(
        "status-matrix",
        "tests/test_tool_registry.py::test_registry_status_matrix_is_fail_closed",
    )
    tampering_run = targeted(
        "tampering",
        "tests/test_single_cohort_contract.py::test_post_validation_plan_tampering_clarifies_without_retrieval_or_cache",
    )
    fallback_run = targeted(
        "fallback",
        "tests/test_single_cohort_contract.py::test_structured_no_match_never_falls_back_to_rag",
    )
    isolation_run = targeted(
        "citation-isolation",
        "tests/test_single_cohort_v2_evaluation.py::test_citation_isolation_rejects_unscoped_or_cross_request_evidence",
    )
    no_retrieval_run = targeted(
        "no-retrieval",
        "tests/test_single_cohort_contract.py::test_router_provider_failure_is_not_reported_as_clarification",
        "tests/test_single_cohort_contract.py::test_cohortless_rag_plan_is_rejected",
        "tests/test_single_cohort_contract.py::test_clarify_and_out_of_domain_never_call_retriever",
    )
    temp_root.mkdir(parents=True, exist_ok=True)
    pytest_run = _run(
        [
            str(PYTHON), "-B", "-m", "pytest", "tests",
            "-p", "no:cacheprovider", "--basetemp", str(temp_root / "full"),
        ]
    )
    ruff_run = _run(
        [str(PYTHON), "-B", "-m", "ruff", "check", "src", "tests", "scripts", "--no-cache"]
    )
    frontend_lint = {"passed": False, "reason": "skipped"}
    frontend_build = {"passed": False, "reason": "skipped"}
    if not args.skip_frontend:
        frontend_lint = _run([NPM, "run", "lint"], cwd=ROOT / "frontend")
        frontend_build = _run([NPM, "run", "build"], cwd=ROOT / "frontend")

    common = {
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": _commit(),
        "artifact_fingerprint": _fingerprint(),
    }
    quality = {
        **common,
        "checks": {
            "pytest": pytest_run["passed"],
            "ruff": ruff_run["passed"],
            "frontend_lint": frontend_lint["passed"],
            "frontend_build": frontend_build["passed"],
        },
        "runs": {
            "pytest": pytest_run,
            "ruff": ruff_run,
            "frontend_lint": frontend_lint,
            "frontend_build": frontend_build,
        },
    }
    parity = {
        **common,
        "provider": "deterministic",
        "checks": {
            "sync_stream": parity_run["passed"],
            "sync_cache": parity_run["passed"],
            "stream_cache": parity_run["passed"],
            "debug_metadata": parity_run["passed"],
        },
        "run": parity_run,
    }
    conformance = {
        **common,
        "provider": "deterministic",
        "checks": {
            "no_match": status_run["passed"],
            "invalid": status_run["passed"],
            "unresolved": status_run["passed"],
            "adapter_exception": status_run["passed"],
            "plan_tampering": tampering_run["passed"],
            "structured_to_rag_fallback_zero": fallback_run["passed"],
            "citation_isolation": isolation_run["passed"],
            "no_retrieval_on_non_execute": no_retrieval_run["passed"],
        },
        "runs": {
            "status_matrix": status_run,
            "plan_tampering": tampering_run,
            "structured_to_rag_fallback_zero": fallback_run,
            "citation_isolation": isolation_run,
            "no_retrieval_on_non_execute": no_retrieval_run,
        },
    }
    _write(args.output_dir / "quality_report.json", quality)
    _write(args.output_dir / "parity_report.json", parity)
    _write(args.output_dir / "conformance_report.json", conformance)
    print(
        json.dumps(
            {
                "quality_passed": all(quality["checks"].values()),
                "parity_passed": all(parity["checks"].values()),
                "conformance_passed": all(conformance["checks"].values()),
            },
            ensure_ascii=False,
        )
    )
    if (
        not all(quality["checks"].values())
        or not all(parity["checks"].values())
        or not all(conformance["checks"].values())
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
