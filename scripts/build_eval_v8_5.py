"""Build the V8.5 answer-evaluation bundle without mutating frozen V8.4.

V8.5 carries the validated deterministic/retrieval/production suites forward
and corrects four answer annotations found during the V8.4 human audit. The
corrections change labels or question scope only; they do not encode expected
runtime answers in production code.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.dataset import stable_json_hash  # noqa: E402


SOURCE_DIR = ROOT / "data" / "eval" / "v8_4_holdout"
DEFAULT_OUTPUT = ROOT / "data" / "eval" / "v8_5_answer_holdout"
DATASET_FILES = {
    "deterministic": "deterministic_tool_cases.json",
    "retrieval": "retrieval_cases.json",
    "answers": "generated_answer_cases.json",
    "production": "production_cases.json",
}

ANSWER_CORRECTIONS: dict[str, dict[str, Any]] = {
    "v84_ans_009": {
        "query": (
            "Em thuộc K48-K49, quy định khen thưởng và kỷ luật đối với "
            "cố vấn học tập (CVHT) gồm những nội dung gì?"
        ),
        "annotation_status": "v8_5_corrected_subject_scope_cvht",
        "annotation_note": "Disambiguated student policy from CVHT policy.",
    },
    "v84_ans_021": {
        "query": (
            "Đối với K50, cố vấn học tập (CVHT) được khen thưởng hoặc xử lý "
            "khi không hoàn thành nhiệm vụ như thế nào?"
        ),
        "annotation_status": "v8_5_corrected_subject_scope_cvht",
        "annotation_note": "Disambiguated student policy from CVHT policy.",
    },
    "v84_ans_050": {
        "query": (
            "Quy định giao tiếp qua điện thoại và thư điện tử công vụ áp dụng "
            "cho viên chức như thế nào?"
        ),
        "annotation_status": "v8_5_corrected_subject_scope_staff",
        "annotation_note": "Aligned the question subject with the cited staff rule.",
    },
    "v84_ans_096": {
        "cohort": "K50",
        "annotation_status": "v8_5_corrected_cohort",
        "annotation_note": "Aligned cohort metadata with the explicit K50 query.",
    },
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def apply_answer_corrections(
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    corrected: list[dict[str, Any]] = []
    seen_corrections: set[str] = set()
    for source_case in cases:
        case = dict(source_case)
        source_id = str(case.get("id") or "")
        if source_id in ANSWER_CORRECTIONS:
            case.update(ANSWER_CORRECTIONS[source_id])
            seen_corrections.add(source_id)

        case["predecessor_case_id"] = source_id
        if source_id.startswith("v84_ans_"):
            case["id"] = source_id.replace("v84_ans_", "v85_ans_", 1)
        corrected.append(case)

    missing = set(ANSWER_CORRECTIONS) - seen_corrections
    if missing:
        raise RuntimeError(f"Missing V8.4 cases required for correction: {sorted(missing)}")
    return corrected


def build_bundle(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_manifest = load_json(SOURCE_DIR / "manifest.json")

    for suite, filename in DATASET_FILES.items():
        source_path = SOURCE_DIR / filename
        output_path = output_dir / filename
        if suite == "answers":
            answer_cases = apply_answer_corrections(load_json(source_path))
            write_json(output_path, answer_cases)
        else:
            shutil.copy2(source_path, output_path)

    audit_template_path = SOURCE_DIR / "human_audit_template.json"
    audit_rows: list[dict[str, Any]] = []
    if audit_template_path.exists():
        audit_rows = load_json(audit_template_path)
        for row in audit_rows:
            case_id = str(row.get("case_id") or row.get("id") or "")
            if case_id.startswith("v84_ans_"):
                replacement = case_id.replace("v84_ans_", "v85_ans_", 1)
                if "case_id" in row:
                    row["case_id"] = replacement
                if row.get("id") == case_id:
                    row["id"] = replacement
        write_json(output_dir / "human_audit_template.json", audit_rows)

    dataset_hashes = {
        suite: stable_json_hash(load_json(output_dir / filename))
        for suite, filename in DATASET_FILES.items()
    }
    manifest = dict(source_manifest)
    manifest.update(
        {
            "version": "v8.5-answer-annotation-corrected",
            "frozen": True,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "description": (
                "V8.5 answer holdout derived from frozen V8.4 with four "
                "human-audited annotation corrections; runtime fixes are generic."
            ),
            "git_commit": _git_commit(),
            "dataset_hashes": dataset_hashes,
            "auxiliary_hashes": {
                "human_audit_template": stable_json_hash(audit_rows)
            },
            "predecessor_bundle": "v8_4_holdout",
            "annotation_corrections": [
                {
                    "predecessor_case_id": case_id,
                    "case_id": case_id.replace("v84_ans_", "v85_ans_", 1),
                    "status": values["annotation_status"],
                    "note": values["annotation_note"],
                }
                for case_id, values in ANSWER_CORRECTIONS.items()
            ],
            "holdout_policy": (
                "V8.5 corrects known V8.4 labels and is suitable for regression. "
                "A fresh-query holdout is still required for final post-fix claims."
            ),
        }
    )
    write_json(output_dir / "manifest.json", manifest)
    (output_dir / "README.md").write_text(
        "# V8.5 Answer Evaluation\n\n"
        "This bundle preserves the frozen V8.4 retrieval, deterministic, and "
        "production suites. It corrects four answer annotations identified by "
        "human audit and assigns new `v85_ans_*` IDs. Use it for regression; use "
        "fresh queries for the final post-fix headline audit.\n",
        encoding="utf-8",
    )
    return manifest


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


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
                "corrections": len(manifest["annotation_corrections"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
