"""Audit/freeze workflow for the single-cohort-v2 gold bundle."""

from __future__ import annotations

import argparse
import hashlib
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

from src.evaluation.single_cohort_gold import (  # noqa: E402
    BUNDLE_DIR,
    CANDIDATE_DATASET_VERSION,
    FROZEN_DATASET_VERSION,
    FROZEN_GOLD_SCHEMA_VERSION,
    GOLD_SCHEMA_VERSION,
    apply_hidden_review,
    apply_approved_rag_source_expansions,
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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _apply_dev_source_expansion(bundle: Path, approval_path: Path) -> None:
    approval = _load(approval_path)
    manifest_path = bundle / "manifest.json"
    dev_path = bundle / "dev.json"
    hidden_path = bundle / "hidden.json"
    manifest = _load(manifest_path)
    if not (
        manifest.get("hidden_frozen")
        and manifest.get("hidden_human_review_complete")
    ):
        raise SystemExit("Dev source expansion requires the hidden suite to remain frozen")

    current_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if approval.get("approval_base_commit") != current_commit:
        raise SystemExit("Source expansion approval does not match current HEAD")
    source_hashes = approval.get("source_hashes") or {}
    actual_source_hashes = {
        "dev.json": _sha(dev_path),
        "hidden.json": _sha(hidden_path),
    }
    if source_hashes != actual_source_hashes:
        raise SystemExit("Source expansion approval input hashes do not match")

    dev_before = _load(dev_path)
    old_parents: dict[tuple[str, str], list[str]] = {}
    for case in dev_before:
        for request in case.get("expected", {}).get("atomic_requests") or []:
            old_parents[(case["id"], request["request_id"])] = list(
                (request.get("expected_evidence") or {}).get(
                    "parent_section_ids", []
                )
            )
    corpus_chunks = _load(
        ROOT / "data/processed/chunks/child_parent_chunks.json"
    )
    dev = apply_approved_rag_source_expansions(
        dev_before, approval, corpus_chunks
    )
    dev_hash = _write(dev_path, dev)
    hidden_hash = _sha(hidden_path)

    corrections = []
    for row in approval.get("expansions") or []:
        case_id = str(row["case_id"])
        request_id = str(row["request_id"])
        additions = sorted(
            {str(value) for value in row.get("add_parent_section_ids") or []}
        )
        corrections.append(
            {
                "case_id": case_id,
                "request_id": request_id,
                "approved_by": approval["approved_by"],
                "approved_at": approval["approved_at"],
                "approval_base_commit": approval["approval_base_commit"],
                "approval_sha256": _sha(approval_path),
                "reason": "human_approved_alternative_rag_source_expansion",
                "old_parent_section_ids": old_parents[(case_id, request_id)],
                "added_parent_section_ids": additions,
                "new_parent_section_ids": sorted(
                    set(old_parents[(case_id, request_id)]) | set(additions)
                ),
                "hidden_changed": False,
            }
        )

    manifest["files"] = {"dev.json": dev_hash, "hidden.json": hidden_hash}
    manifest_gold = dict(manifest.get("gold_audit") or {})
    manifest_gold["approved_corrections"] = list(
        manifest_gold.get("approved_corrections") or []
    ) + corrections
    manifest_gold["last_correction_at"] = approval["approved_at"]
    manifest["gold_audit"] = manifest_gold
    _write(manifest_path, manifest)

    gold_report_path = bundle / "gold_audit_report.json"
    gold_report = _load(gold_report_path)
    gold_report["approved_corrections"] = list(
        gold_report.get("approved_corrections") or []
    ) + corrections
    gold_report["last_correction_at"] = approval["approved_at"]
    _write(gold_report_path, gold_report)

    from src.evaluation.single_cohort_v2 import validate_bundle

    validation = validate_bundle(bundle, require_gold_complete=True)
    validation_report = {
        "valid": validation.valid,
        "errors": validation.errors,
        "generated_at": datetime.now(UTC).isoformat(),
        "schema_version": manifest["schema_version"],
        "counts": validation.counts,
        "hashes": manifest["files"],
        "coverage": validation.coverage,
        "hidden_frozen": manifest["hidden_frozen"],
    }
    _write(bundle / "validation_report.json", validation_report)
    print(json.dumps(validation_report, ensure_ascii=False, indent=2))
    if not validation.valid:
        raise SystemExit(1)


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
        "baseline_commit": "839c27ba",
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
    parser.add_argument(
        "--apply-dev-source-expansion",
        type=Path,
        help="Apply a reviewed additive RAG source expansion without opening hidden.",
    )
    parser.add_argument("--bundle", type=Path, default=BUNDLE_DIR)
    args = parser.parse_args()
    review_actions = sum(
        value is not None
        for value in (
            args.apply_dev_review,
            args.apply_hidden_review,
            args.apply_dev_source_expansion,
        )
    )
    if args.write_candidates and review_actions:
        parser.error("--write-candidates cannot be combined with review application")
    if review_actions > 1:
        parser.error("Review application actions are mutually exclusive")
    if args.apply_dev_source_expansion is not None:
        _apply_dev_source_expansion(args.bundle, args.apply_dev_source_expansion)
        return

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
