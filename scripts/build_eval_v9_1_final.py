"""Build the V9.1.1 holdout with routing and retrieval evaluated separately."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_eval_v9_final import current_git_commit  # noqa: E402
from src.evaluation.dataset import (  # noqa: E402
    DATASET_FILES,
    file_hash,
    stable_json_hash,
    validate_bundle,
    write_json,
)


SOURCE_BUNDLE = ROOT / "data" / "eval" / "v9_1_final_holdout"
DEFAULT_OUTPUT = ROOT / "data" / "eval" / "v9_1_1_final_holdout"
DOCSTORE_PATH = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"


DETERMINISTIC_ANNOTATION_REVISIONS = {
    "v9_det_035": {
        "expected_item_count": 3,
        "annotation_status": "applicability_aware_v9_1_1_reviewed",
        "annotation_revision": "k51_multiple_grading_applicabilities",
    },
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _revise_deterministic_cases(cases: list[dict[str, Any]]) -> int:
    """Apply reviewed corrections without changing the evaluated query."""
    changed = 0
    seen_ids: set[str] = set()
    for case in cases:
        case_id = str(case.get("id") or "")
        revision = DETERMINISTIC_ANNOTATION_REVISIONS.get(case_id)
        if revision is None:
            continue
        seen_ids.add(case_id)
        case.update(revision)
        changed += 1

    missing = sorted(set(DETERMINISTIC_ANNOTATION_REVISIONS) - seen_ids)
    if missing:
        raise RuntimeError(
            f"Missing deterministic cases for V9.1.1 revisions: {missing}"
        )
    return changed


def _write_readme(output_dir: Path) -> None:
    (output_dir / "README.md").write_text(
        "\n".join(
            [
                "# V9.1.1 Final Holdout",
                "",
                "V9.1.1 keeps V9.1 intact and adds a reviewed applicability-aware "
                "annotation correction for K51 grading.",
                "",
                "- Pure retrieval is the headline retrieval scope.",
                "- End-to-end routing is reported separately.",
                "- Regulation questions remain source-anchored.",
                "- Structured/directory routing remains covered by the "
                "deterministic and production suites.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def build_bundle(output_dir: Path) -> dict[str, Any]:
    source_manifest = _load_json(SOURCE_BUNDLE / "manifest.json")
    datasets = {
        suite: copy.deepcopy(_load_json(SOURCE_BUNDLE / filename))
        for suite, filename in DATASET_FILES.items()
    }
    deterministic_revision_count = _revise_deterministic_cases(
        datasets["deterministic"]
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for suite, cases in datasets.items():
        write_json(output_dir / DATASET_FILES[suite], cases)

    audit_template = copy.deepcopy(
        _load_json(SOURCE_BUNDLE / "human_audit_template.json")
    )
    write_json(output_dir / "human_audit_template.json", audit_template)

    manifest = {
        **source_manifest,
        "version": "v9.1.1-final-routing-retrieval-split",
        "frozen": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "description": (
            "V9.1.1 final holdout with source-complete student questions, "
            "applicability-aware K51 grading annotation, and separate "
            "pure-retrieval versus end-to-end routing reports."
        ),
        "counts": {
            suite: len(cases) for suite, cases in datasets.items()
        },
        "dataset_hashes": {
            suite: stable_json_hash(cases)
            for suite, cases in datasets.items()
        },
        "auxiliary_hashes": {
            "human_audit_template": stable_json_hash(audit_template)
        },
        "git_commit": current_git_commit(),
        "docstore_hash": file_hash(DOCSTORE_PATH),
        "predecessor_bundle": "v9_1_final_holdout",
        "retrieval_evaluation": {
            "headline_scope": "pure",
            "secondary_scope": "end_to_end",
            "pure_scope_policy": (
                "Evaluate only regulation ranking after routing and query "
                "normalization; router decisions are scored separately."
            ),
        },
        "annotation_revision_count": deterministic_revision_count,
        "inherited_annotation_revision_count": int(
            source_manifest.get("annotation_revision_count") or 0
        ),
        "deterministic_annotation_revision_count": (
            deterministic_revision_count
        ),
        "structured_source_revision_count": 0,
        "inherited_structured_source_revision_count": int(
            source_manifest.get("structured_source_revision_count") or 0
        ),
        "annotation_revision_policy": (
            "The K51 grading item-count expectation was aligned with the approved "
            "applicability-specific tables; no query or source annotation inherited "
            "from V9.1 was changed."
        ),
        "holdout_policy": "single_run_no_post_tuning",
    }
    write_json(output_dir / "manifest.json", manifest)
    _write_readme(output_dir)

    validation = validate_bundle(output_dir, DOCSTORE_PATH, require_frozen=True)
    write_json(output_dir / "validation_report.json", validation)
    if not validation["valid"]:
        raise RuntimeError(
            "V9.1.1 bundle validation failed:\n"
            + "\n".join(validation.get("errors") or [])
        )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build_bundle(args.output.resolve())
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "version": manifest["version"],
                "counts": manifest["counts"],
                "annotation_revision_count": manifest[
                    "annotation_revision_count"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
