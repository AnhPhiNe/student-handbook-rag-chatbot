"""Validate regression-v3 provenance and produce a fail-closed run manifest.

Live quality evaluation is intentionally refused until every migration proposal
has been reviewed and the bundle is frozen.  This prevents unreviewed labels
from becoming release metrics merely because the current runtime agrees with
them.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.artifact_fingerprint import (  # noqa: E402
    release_artifact_fingerprint,
)
from src.evaluation.single_cohort_regression_v3 import (  # noqa: E402
    BUNDLE_DIR,
    SUITE_FILES,
    archive_integrity,
    load_json,
    metric_cases,
    validate_bundle,
)


def _commit(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def build_readiness_report(
    *,
    bundle_dir: Path = BUNDLE_DIR,
    root: Path = ROOT,
    require_frozen: bool,
) -> dict[str, Any]:
    validation = validate_bundle(
        bundle_dir,
        root=root,
        require_frozen=require_frozen,
    )
    archive = archive_integrity(root)
    suite_rows: dict[str, Any] = {}
    total_metric_cases = 0
    for suite, filename in SUITE_FILES.items():
        values = load_json(bundle_dir / filename) if (bundle_dir / filename).exists() else []
        active = metric_cases(values)
        total_metric_cases += len(active)
        outcomes = Counter(
            str((case.get("expected_contract") or {}).get("outcome"))
            for case in values
        )
        statuses = Counter(
            str(request.get("expected_status"))
            for case in active
            for request in (case.get("expected_contract") or {}).get("atomic_requests") or []
        )
        suite_rows[suite] = {
            "total": len(values),
            "active_metric_cases": len(active),
            "deferred": sum(
                case.get("lifecycle") == "deferred_multi_cohort" for case in values
            ),
            "retired": sum(
                case.get("lifecycle") == "retired_invalid_gold" for case in values
            ),
            "outcomes": dict(outcomes),
            "request_statuses": dict(statuses),
        }
    release_blockers = list(validation.errors)
    unresolved = validation.annotation_counts.get("review_required", 0)
    if unresolved:
        release_blockers.append(f"{unresolved} review proposals remain unresolved")
    if not validation.release_ready:
        release_blockers.append("bundle is not frozen release gold")
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": _commit(root),
        "artifact_fingerprint": release_artifact_fingerprint(root),
        "mode": "release" if require_frozen else "review_readiness",
        "archive": archive,
        "bundle_validation": {
            "valid": validation.valid,
            "errors": list(validation.errors),
            "release_ready": validation.release_ready,
            "counts": validation.counts,
            "lifecycle_counts": validation.lifecycle_counts,
            "annotation_counts": validation.annotation_counts,
        },
        "suite_plan": suite_rows,
        "metric_policy": {
            "active_only": True,
            "deferred_multi_cohort": "clarify_no_retrieval_not_quality_metric",
            "retired_invalid_gold": "reported_separately_never_counted_as_pass",
            "historical_exact_match": "diagnostic_only",
            "runtime_output_used_as_gold": False,
        },
        "active_metric_case_count": total_metric_cases,
        "release_blockers": list(dict.fromkeys(release_blockers)),
        "passed": validation.release_ready if require_frozen else validation.valid,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=BUNDLE_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--review-readiness",
        action="store_true",
        help="Validate proposal structure without pretending it is release gold.",
    )
    args = parser.parse_args()
    report = build_readiness_report(
        bundle_dir=args.bundle,
        require_frozen=not args.review_readiness,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "mode": report["mode"],
                "passed": report["passed"],
                "release_blockers": report["release_blockers"],
            },
            ensure_ascii=False,
        )
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
