"""Audit/freeze workflow for the single-cohort-v2 gold bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.single_cohort_gold import (  # noqa: E402
    BUNDLE_DIR,
    CANDIDATE_DATASET_VERSION,
    FROZEN_DATASET_VERSION,
    FROZEN_GOLD_SCHEMA_VERSION,
    GOLD_SCHEMA_VERSION,
    apply_hidden_review,
    apply_review,
    audit_bundle,
    legacy_compatibility_report,
)


def _write(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest(
    bundle_dir: Path,
    *,
    dev_hash: str,
    hidden_hash: str,
    hidden_frozen: bool,
    gold_report: dict[str, Any],
) -> dict[str, Any]:
    current = _load(bundle_dir / "manifest.json")
    return {
        **current,
        "schema_version": (
            FROZEN_GOLD_SCHEMA_VERSION if hidden_frozen else GOLD_SCHEMA_VERSION
        ),
        "dataset_version": (
            FROZEN_DATASET_VERSION
            if hidden_frozen
            else CANDIDATE_DATASET_VERSION
        ),
        "baseline_commit": "15f971d5",
        "files": {"dev.json": dev_hash, "hidden.json": hidden_hash},
        "hidden_frozen": hidden_frozen,
        "hidden_human_review_required": True,
        "hidden_human_review_complete": hidden_frozen,
        "gold_audit": {
            "commit": gold_report["commit"],
            "generated_at": gold_report["generated_at"],
            "data_versions": gold_report["data_versions"],
            "gold_ready": gold_report["gold_ready"] and hidden_frozen,
        },
        "frozen_at": datetime.now(UTC).isoformat() if hidden_frozen else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-candidates",
        action="store_true",
        help="Write audited dev/hidden candidates and a 60-case human review queue.",
    )
    parser.add_argument(
        "--apply-dev-review",
        type=Path,
        help="Apply the completed review queue for non-auto-verified dev cases.",
    )
    parser.add_argument(
        "--apply-hidden-review",
        type=Path,
        help="Apply a completed human review queue and freeze hidden hashes.",
    )
    parser.add_argument("--bundle", type=Path, default=BUNDLE_DIR)
    args = parser.parse_args()
    if args.write_candidates and (
        args.apply_dev_review is not None or args.apply_hidden_review is not None
    ):
        parser.error("--write-candidates cannot be combined with review application")

    result = audit_bundle(args.bundle, root=ROOT)
    if (
        not args.write_candidates
        and args.apply_dev_review is None
        and args.apply_hidden_review is None
    ):
        print(json.dumps(result.report, ensure_ascii=False, indent=2))
        return

    current_manifest = _load(args.bundle / "manifest.json")
    dev = result.dev
    hidden = result.hidden
    hidden_frozen = False
    if args.apply_hidden_review is not None and args.apply_dev_review is None:
        prior_audit = current_manifest.get("gold_audit") or {}
        if prior_audit.get("data_versions") != result.report["data_versions"]:
            raise SystemExit(
                "Code or source data changed after dev review; regenerate and review gold again"
            )
        dev = _load(args.bundle / "dev.json")
        if any(
            case.get("annotation", {}).get("state") == "review_required"
            for case in dev
        ):
            raise SystemExit("Dev gold audit is incomplete; hidden cannot be frozen")
    if args.apply_dev_review is not None:
        dev = apply_review(
            dev,
            _load(args.apply_dev_review),
            require_every_case=False,
        )
    if args.apply_hidden_review is not None:
        hidden = apply_hidden_review(hidden, _load(args.apply_hidden_review))
        hidden_frozen = all(
            case.get("annotation", {}).get("state") == "human_approved"
            for case in hidden
        )
        result.report["gold_ready"] = all(
            case.get("annotation", {}).get("state") != "review_required"
            for case in dev + hidden
        )
        if not result.report["gold_ready"]:
            raise SystemExit("Dev gold audit is incomplete; hidden cannot be frozen")

    all_cases = dev + hidden
    result.report["case_annotation_states"] = dict(
        Counter(case.get("annotation", {}).get("state") for case in all_cases)
    )
    result.report["request_annotation_states"] = dict(
        Counter(
            (request.get("gold_audit") or {}).get("annotation_state")
            for case in all_cases
            for request in case.get("expected", {}).get("atomic_requests") or []
        )
    )
    result.report["dev_review_required"] = sum(
        case.get("annotation", {}).get("state") == "review_required" for case in dev
    )
    result.report["hidden_review_required"] = sum(
        case.get("annotation", {}).get("state") == "review_required"
        for case in hidden
    )
    result.report["gold_ready"] = bool(
        hidden_frozen
        and all(
            case.get("annotation", {}).get("state") != "review_required"
            for case in all_cases
        )
    )

    dev_hash = _write(args.bundle / "dev.json", dev)
    hidden_hash = _write(args.bundle / "hidden.json", hidden)
    manifest = _manifest(
        args.bundle,
        dev_hash=dev_hash,
        hidden_hash=hidden_hash,
        hidden_frozen=hidden_frozen,
        gold_report=result.report,
    )
    _write(args.bundle / "manifest.json", manifest)
    _write(args.bundle / "gold_audit_report.json", result.report)
    _write(args.bundle / "legacy_compatibility.json", legacy_compatibility_report(ROOT))
    if args.write_candidates:
        _write(args.bundle / "dev_review_queue.json", result.dev_review_queue)
        _write(args.bundle / "hidden_review_queue.json", result.review_queue)
    elif args.apply_dev_review is not None and not hidden_frozen:
        _write(args.bundle / "hidden_review_queue.json", result.review_queue)

    from src.evaluation.single_cohort_v2 import validate_bundle

    validation = validate_bundle(args.bundle)
    validation_report = {
        "valid": validation.valid,
        "errors": validation.errors,
        "generated_at": datetime.now(UTC).isoformat(),
        "schema_version": manifest["schema_version"],
        "counts": validation.counts,
        "hashes": manifest["files"],
        "coverage": validation.coverage,
        "hidden_frozen": hidden_frozen,
    }
    _write(args.bundle / "validation_report.json", validation_report)
    print(json.dumps(validation_report, ensure_ascii=False, indent=2))
    if not validation.valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
