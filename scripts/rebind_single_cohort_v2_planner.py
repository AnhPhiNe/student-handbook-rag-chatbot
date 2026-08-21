"""Rebind frozen dev Planner outputs after an isolated retrieval-only change.

This command never calls a provider. It accepts only the pinned BM25 runtime
and index changes plus evaluation/test changes; prompt, registry, dataset and
all other runtime artifact hashes must remain identical to the source report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import evaluate_single_cohort_v2 as evaluator  # noqa: E402
from scripts import replay_single_cohort_v2_dev as replay  # noqa: E402
from src.evaluation.single_cohort_v2 import validate_bundle  # noqa: E402


RETRIEVAL_ONLY_PATHS = {
    "src/retrieval/core/bm25_retriever.py",
    "data/processed/retrieval/bm25_index.json",
    "data/processed/retrieval/bm25_index_v28_candidate.json",
    "data/processed/retrieval/bm25_title_index_v28_3.json",
    "data/processed/retrieval/bm25_title_index_v29_0.json",
}
EVALUATION_ONLY_PATHS = {
    "scripts/evaluate_single_cohort_v2.py",
    "scripts/replay_single_cohort_v2_dev.py",
    "scripts/rebind_single_cohort_v2_planner.py",
    "scripts/selective_single_cohort_answer_reuse.py",
    "src/evaluation/single_cohort_v2.py",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def _path_is_allowed(path: str) -> bool:
    return bool(
        path in RETRIEVAL_ONLY_PATHS
        or path in EVALUATION_ONLY_PATHS
        or path.startswith("tests/")
    )


def validate_rebind_source(
    source: Mapping[str, Any],
    *,
    current_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    source_commit = str(source.get("commit") or "").strip()
    if not source_commit:
        raise ValueError("Planner rebind source has no commit")
    subprocess.check_call(
        ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"],
        cwd=ROOT,
    )
    changed_paths = [
        value
        for value in _git("diff", "--name-only", f"{source_commit}..HEAD").splitlines()
        if value
    ]
    unsafe = [path for path in changed_paths if not _path_is_allowed(path)]
    if unsafe:
        raise ValueError(f"Planner rebind crosses non-retrieval runtime changes: {unsafe}")
    if not any(path in RETRIEVAL_ONLY_PATHS for path in changed_paths):
        raise ValueError("Planner rebind requires a declared retrieval-only change")

    current_fingerprint = evaluator._artifact_fingerprint()
    source_fingerprint = source.get("artifact_fingerprint") or {}
    allowed_mismatches = {"bm25_index", "implementation_tree"}
    mismatched = {
        key
        for key, value in current_fingerprint.items()
        if source_fingerprint.get(key) != value
    }
    unexpected = sorted(mismatched - allowed_mismatches)
    if unexpected:
        raise ValueError(f"Planner runtime artifact mismatch: {unexpected}")
    if "bm25_index" not in mismatched:
        raise ValueError("Expected BM25 artifact hash to change")

    old_cases = json.loads(
        _git("show", f"{source_commit}:data/eval/single_cohort_v2/dev.json")
    )
    if [replay._runtime_case_projection(case) for case in old_cases] != [
        replay._runtime_case_projection(case) for case in current_cases
    ]:
        raise ValueError("Planner-visible dev inputs changed")
    if (source.get("models") or {}).get("planner") != evaluator.PLANNER_MODEL:
        raise ValueError("Planner model changed")
    if source.get("prompt_version") != evaluator.ROUTER_PROMPT_VERSION:
        raise ValueError("Planner prompt changed")
    manifest = _load(evaluator.BUNDLE_DIR / "manifest.json")
    if source.get("dataset_prompt_version") != manifest.get("prompt_version"):
        raise ValueError("Dataset prompt version changed")
    if source.get("registry_version") != manifest.get("registry_version"):
        raise ValueError("Registry version changed")
    return {
        "source_commit": source_commit,
        "source_report_sha256": None,
        "changed_paths": changed_paths,
        "allowed_runtime_changes": sorted(
            path for path in changed_paths if path in RETRIEVAL_ONLY_PATHS
        ),
        "unchanged_artifact_keys": sorted(
            set(current_fingerprint) - allowed_mismatches
        ),
        "provider_calls": 0,
    }


def rebind_planner_report(source_path: Path) -> dict[str, Any]:
    if _git("status", "--porcelain"):
        raise ValueError("Planner rebind requires a clean worktree")
    source = _load(source_path)
    validation = validate_bundle(require_gold_complete=True)
    if not validation.valid:
        raise ValueError("Current single-cohort bundle is invalid")
    current_cases = _load(evaluator.BUNDLE_DIR / "dev.json")
    provenance = validate_rebind_source(source, current_cases=current_cases)
    provenance["source_report_sha256"] = _sha(source_path)
    case_by_id = {str(case["id"]): case for case in current_cases}
    planner_rows = replay._refresh_planner_rows(source, case_by_id)
    manifest = _load(evaluator.BUNDLE_DIR / "manifest.json")
    report = evaluator._planner_checkpoint_report(
        planner_rows,
        manifest=manifest,
        validation=validation,
    )
    report["rebind_provenance"] = {
        **provenance,
        "source_report": str(source_path.resolve()),
        "rebound_at": datetime.now(UTC).isoformat(),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = rebind_planner_report(args.source_report)
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    evaluator._write_json_atomic(args.output, report)
    rows = (report.get("planner") or {}).get("dev", {}).get("rows", [])
    print(
        json.dumps(
            {
                "commit": report["commit"],
                "source_commit": report["rebind_provenance"]["source_commit"],
                "planner_rows": len(rows),
                "provider_calls": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
