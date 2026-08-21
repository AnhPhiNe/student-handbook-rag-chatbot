"""Apply explicit human review decisions and optionally freeze regression v3."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.single_cohort_regression_v3 import (  # noqa: E402
    BUNDLE_DIR,
    FROZEN_DATASET_VERSION,
    SUITE_FILES,
    file_sha256,
    load_json,
    validate_bundle,
    write_json,
)


ALLOWED_DECISIONS = {"accept", "revise", "defer_multi_cohort", "retire_invalid_gold"}


def _commit(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def apply_reviews(
    *,
    bundle_dir: Path = BUNDLE_DIR,
    decisions_path: Path | None = None,
    freeze: bool = False,
    root: Path = ROOT,
) -> dict[str, Any]:
    decisions_path = decisions_path or bundle_dir / "review_queue.json"
    decisions = load_json(decisions_path)
    if not isinstance(decisions, list):
        raise ValueError("Review decisions must be an array.")
    by_id: dict[str, dict[str, Any]] = {}
    for row in decisions:
        case_id = str(row.get("case_id") or "")
        decision = row.get("review_decision")
        if not case_id or case_id in by_id:
            raise ValueError(f"Missing or duplicate review case id: {case_id!r}")
        if decision is not None and decision not in ALLOWED_DECISIONS:
            raise ValueError(f"{case_id}: invalid review decision {decision!r}")
        by_id[case_id] = row

    unresolved: list[str] = []
    applied = 0
    now = datetime.now(UTC).isoformat()
    updated_suites: dict[str, list[dict[str, Any]]] = {}
    for suite, filename in SUITE_FILES.items():
        path = bundle_dir / filename
        cases = load_json(path)
        for case in cases:
            row = by_id.get(str(case.get("id") or ""))
            if not row or not row.get("review_decision"):
                unresolved.append(str(case.get("id") or ""))
                continue
            reviewer = str(row.get("reviewer") or "").strip()
            reviewed_at = str(row.get("reviewed_at") or "").strip()
            if not reviewer or not reviewed_at:
                raise ValueError(f"{case['id']}: reviewer and reviewed_at are required")
            decision = row["review_decision"]
            if decision == "revise":
                replacement = row.get("replacement_contract")
                if not isinstance(replacement, dict):
                    raise ValueError(f"{case['id']}: revise requires replacement_contract")
                case["expected_contract"] = replacement
                if row.get("replacement_lifecycle"):
                    case["lifecycle"] = row["replacement_lifecycle"]
            elif decision == "defer_multi_cohort":
                case["lifecycle"] = "deferred_multi_cohort"
                case["expected_contract"] = {
                    "outcome": "clarify",
                    "effective_cohort": None,
                    "retrieval_policy": "forbidden",
                    "atomic_requests": [],
                }
            elif decision == "retire_invalid_gold":
                reason = str(row.get("review_notes") or "").strip()
                if not reason:
                    raise ValueError(f"{case['id']}: retirement requires review_notes")
                case["lifecycle"] = "retired_invalid_gold"
                case["retirement_reason"] = reason
                case["expected_contract"] = {
                    "outcome": "clarify",
                    "effective_cohort": case.get("selected_cohort"),
                    "retrieval_policy": "forbidden",
                    "atomic_requests": [],
                }
            case["annotation"] = {
                **case.get("annotation", {}),
                "state": "human_approved",
                "review_decision": decision,
                "reviewer": reviewer,
                "reviewed_at": reviewed_at,
                "review_notes": row.get("review_notes"),
            }
            applied += 1
        updated_suites[suite] = cases

    if freeze and unresolved:
        raise ValueError(
            f"Cannot freeze with {len(unresolved)} unresolved reviews; "
            f"first ids={unresolved[:10]}"
        )
    manifest_path = bundle_dir / "manifest.json"
    manifest = load_json(manifest_path)
    manifest["review_application"] = {
        "applied_at": now,
        "applied_commit": _commit(root),
        "decision_file": str(decisions_path),
        "applied": applied,
        "unresolved": len(unresolved),
    }
    if freeze:
        manifest["frozen"] = True
        manifest["dataset_version"] = FROZEN_DATASET_VERSION
        manifest["frozen_at"] = now
        manifest["frozen_commit"] = _commit(root)
    bundle_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="single-cohort-regression-v3-apply-",
        dir=bundle_dir.parent,
    ) as temp_value:
        temp_dir = Path(temp_value)
        for suite, filename in SUITE_FILES.items():
            write_json(temp_dir / filename, updated_suites[suite])
        manifest["dataset_hashes"] = {
            suite: file_sha256(temp_dir / filename)
            for suite, filename in SUITE_FILES.items()
        }
        write_json(temp_dir / "manifest.json", manifest)
        validation = validate_bundle(temp_dir, root=root, require_frozen=freeze)
        if not validation.valid:
            raise ValueError(
                "Applied bundle is invalid:\n" + "\n".join(validation.errors)
            )

    # The real bundle is only updated after the complete candidate validates.
    for suite, filename in SUITE_FILES.items():
        write_json(bundle_dir / filename, updated_suites[suite])
    write_json(manifest_path, manifest)
    return {
        "applied": applied,
        "unresolved": len(unresolved),
        "frozen": freeze,
        "valid": validation.valid,
        "release_ready": validation.release_ready,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=BUNDLE_DIR)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            apply_reviews(
                bundle_dir=args.bundle,
                decisions_path=args.decisions,
                freeze=args.freeze,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
