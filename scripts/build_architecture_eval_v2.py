from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import unicodedata
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.dataset import file_hash, load_json, stable_json_hash, write_json


DEFAULT_SOURCE = ROOT / "data" / "eval" / "final_holdout"
DEFAULT_TARGET = ROOT / "data" / "eval" / "architecture_v2"
DOCSTORE = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"
BUILD_MANIFEST = ROOT / "data" / "processed" / "metadata" / "build_manifest.json"
CONFIG_PATHS = {
    "answer_generation": ROOT / "configs" / "answer_generation.yaml",
    "retrieval": ROOT / "configs" / "retrieval.yaml",
    "ai_router": ROOT / "configs" / "ai_router.yaml",
    "structured_lookup_registry": ROOT / "configs" / "structured_lookup_registry.yaml",
}
LOOKUP_TYPE_BY_GROUP = {
    "conduct": "scoring",
    # The current table-first contract resolves program/faculty relationships
    # through the curated program directory. The separate faculty lookup is for
    # faculty contact/profile fields, not program membership.
    "faculty": "program",
    "foreign_language": "foreign_language",
    "formula": "formula",
    "office": "office",
    "program": "program",
    "scholarship": "scholarship_classification",
    "scoring": "scoring",
    "service": "student_service",
    "study_duration": "study_duration",
}

# Human-reviewed changes caused by the architecture contract, not by observed
# pass/fail output. They live only in the migration tool and never affect runtime.
REVIEWED_CASE_CONTRACTS: dict[str, dict[str, Any]] = {
    "v9_det_090": {"task_count": 2},
    # Table-first lookup intentionally returns the applicable duration tables so
    # the answer can state each modality when the user did not select one.
    "v9_det_105": {
        "evaluation_case_type": "positive",
        "lookup_group": "study_duration",
        "expected_llm_called": True,
    },
}


def _current_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _expected_plan(case: dict[str, Any]) -> dict[str, Any]:
    case_type = str(case.get("evaluation_case_type") or case.get("case_type") or "")
    cohort = str(case.get("cohort") or "")
    cohorts = [] if cohort in {"", "general", "all"} else [cohort]
    if case_type == "positive":
        lookup_group = str(case.get("lookup_group") or "")
        lookup_type = LOOKUP_TYPE_BY_GROUP[lookup_group]
        return {
            "task_count": int(case.get("reviewed_task_count") or 1),
            "allowed_modes": ["structured"],
            "lookup_types": [lookup_type],
            "cohorts": cohorts,
            "out_of_domain": False,
            "needs_clarification": False,
        }
    if case_type == "hard_negative":
        return {
            "task_count": int(case.get("reviewed_task_count") or 1),
            "allowed_modes": ["rag"],
            "lookup_types": [],
            "cohorts": cohorts,
            "out_of_domain": False,
            "needs_clarification": False,
        }
    if case_type == "ambiguous":
        return {
            "task_count": 1,
            "allowed_modes": ["clarify"],
            "lookup_types": [],
            "cohorts": [],
            "out_of_domain": False,
            "needs_clarification": True,
        }
    if case_type == "out_of_domain":
        return {
            "task_count": 0,
            "allowed_modes": [],
            "lookup_types": [],
            "cohorts": [],
            "out_of_domain": True,
            "needs_clarification": False,
        }
    raise ValueError(f"Unsupported deterministic case_type={case_type!r}")


def migrate_deterministic(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    migrated: list[dict[str, Any]] = []
    for source_case in cases:
        case = copy.deepcopy(source_case)
        reviewed = REVIEWED_CASE_CONTRACTS.get(str(case.get("id") or ""), {})
        if reviewed:
            case["legacy_case_type"] = case.get("case_type")
            case.update(
                {
                    key: value
                    for key, value in reviewed.items()
                    if key not in {"task_count"}
                }
            )
            if reviewed.get("task_count") is not None:
                case["reviewed_task_count"] = int(reviewed["task_count"])
        case["contract_version"] = "query-plan-table-first-v2"
        case["expected_plan"] = _expected_plan(case)
        evaluation_case_type = str(
            case.get("evaluation_case_type") or case.get("case_type") or ""
        )
        case["expected_llm_called"] = evaluation_case_type in {
            "positive",
            "hard_negative",
        }
        case.pop("expected_item_count", None)
        if evaluation_case_type == "positive":
            case["expected_group"] = "structured"
            case["expected_intents"] = []
            case["expected_strategies"] = ["query_plan_execution"]
            case["expected_lookup_type"] = case["expected_plan"]["lookup_types"][0]
        elif evaluation_case_type == "hard_negative":
            case["expected_group"] = "rag"
            case["expected_intents"] = ["open_question"]
            case["expected_strategies"] = ["query_plan_execution"]
        elif evaluation_case_type == "ambiguous":
            case["expected_group"] = "clarification"
            case["expected_intents"] = []
            case["expected_strategies"] = ["query_plan_execution"]
        else:
            case["expected_group"] = "guardrail"
            case["expected_intents"] = ["out_of_domain"]
            case["expected_strategies"] = ["query_plan"]
        migrated.append(case)
    return migrated


def _annotate_cases(
    cases: list[dict[str, Any]], *, contract_version: str
) -> list[dict[str, Any]]:
    annotated = copy.deepcopy(cases)
    for case in annotated:
        case["contract_version"] = contract_version
    return annotated


def _normalized_label(value: Any) -> str:
    return re.sub(
        r"\s+", " ", unicodedata.normalize("NFKC", str(value or "")).casefold()
    ).strip()


def expand_general_relevance(
    cases: list[dict[str, Any]], docstore: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Allow equivalent cohort editions for queries with no cohort constraint."""
    by_id = {str(item.get("_id") or ""): item for item in docstore}
    by_source_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in docstore:
        metadata = item.get("metadata") or {}
        key = (
            _normalized_label(metadata.get("document_title")),
            _normalized_label(metadata.get("title")),
        )
        if all(key):
            by_source_key.setdefault(key, []).append(item)

    expanded_cases = copy.deepcopy(cases)
    for case in expanded_cases:
        if str(case.get("cohort") or "") not in {"", "general", "all"}:
            case["relevance_scope"] = "requested_cohort"
            continue
        judgments = case.get("relevance_judgments") or []
        expanded = {str(item.get("parent_section_id") or ""): item for item in judgments}
        for judgment in judgments:
            source = by_id.get(str(judgment.get("parent_section_id") or "")) or {}
            metadata = source.get("metadata") or {}
            key = (
                _normalized_label(metadata.get("document_title")),
                _normalized_label(metadata.get("title")),
            )
            for equivalent in by_source_key.get(key, []):
                equivalent_metadata = equivalent.get("metadata") or {}
                parent_id = str(equivalent.get("_id") or "")
                if not parent_id or parent_id in expanded:
                    continue
                expanded[parent_id] = {
                    "parent_section_id": parent_id,
                    "grade": int(judgment.get("grade") or 0),
                    "cohort": equivalent_metadata.get("cohort")
                    or equivalent.get("cohort"),
                    "document_id": equivalent_metadata.get("document_id")
                    or equivalent.get("document_id"),
                    "content_type": equivalent_metadata.get("content_type"),
                    "source_section": equivalent_metadata.get("title"),
                    "source_pages": equivalent_metadata.get("source_pages") or [],
                    "anchor_source": "equivalent_cohort_edition",
                }
        case["relevance_judgments"] = sorted(
            expanded.values(), key=lambda item: str(item.get("parent_section_id") or "")
        )
        case["relevance_scope"] = "any_equivalent_cohort_edition"
    return expanded_cases


def build_bundle(source_dir: Path, target_dir: Path) -> dict[str, Any]:
    deterministic = migrate_deterministic(
        load_json(source_dir / "deterministic_tool_cases.json")
    )
    retrieval = _annotate_cases(
        expand_general_relevance(
            load_json(source_dir / "retrieval_cases.json"), load_json(DOCSTORE)
        ),
        contract_version="current-build-parent-anchor-v2",
    )
    answers = _annotate_cases(
        load_json(source_dir / "generated_answer_cases.json"),
        contract_version="final-answer-grounding-v2",
    )
    production = copy.deepcopy(load_json(source_dir / "production_cases.json"))
    human_audit = copy.deepcopy(load_json(source_dir / "human_audit_template.json"))

    target_dir.mkdir(parents=True, exist_ok=True)
    datasets = {
        "deterministic": deterministic,
        "retrieval": retrieval,
        "answers": answers,
        "production": production,
    }
    filenames = {
        "deterministic": "deterministic_tool_cases.json",
        "retrieval": "retrieval_cases.json",
        "answers": "generated_answer_cases.json",
        "production": "production_cases.json",
    }
    for suite, cases in datasets.items():
        write_json(target_dir / filenames[suite], cases)
    write_json(target_dir / "human_audit_template.json", human_audit)

    old_manifest = load_json(source_dir / "manifest.json")
    build_manifest = load_json(BUILD_MANIFEST)
    manifest = copy.deepcopy(old_manifest)
    manifest.update(
        {
            "version": "architecture-v2-query-plan-table-first",
            "frozen": True,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "description": (
                "Versioned regression bundle aligned with QueryPlan, table-first "
                "structured lookup, the current v31 parent/child build, and the "
                "current final-answer grounding contract."
            ),
            "git_commit": _current_commit(),
            "docstore_hash": file_hash(DOCSTORE),
            "config_hashes": {
                name: file_hash(path) for name, path in CONFIG_PATHS.items()
            },
            "dataset_hashes": {
                suite: stable_json_hash(cases) for suite, cases in datasets.items()
            },
            "auxiliary_hashes": {
                "human_audit_template": stable_json_hash(human_audit)
            },
            "evaluation_contract": "query-plan-table-first-v2",
            "deterministic_contract": "query-plan-table-first-v2",
            "retrieval_contract": "current-build-parent-anchor-v2",
            "answer_contract": "final-answer-grounding-v2",
            "judge_role": "diagnostic_only_human_confirmation_required",
            "holdout_policy": "versioned_regression_not_unseen_acceptance",
            "retrieval_evaluation": {
                "headline_scope": "end_to_end",
                "secondary_scope": "pure",
                "scope_policy": (
                    "The 180-case headline includes QueryPlan normalization because "
                    "that is the production retrieval path. Pure Qdrant/Mongo hybrid "
                    "retrieval is retained as a secondary diagnostic."
                ),
            },
            "predecessor_bundle": str(old_manifest.get("version") or "unknown"),
            "source_build_id": build_manifest.get("build_id"),
            "source_qdrant_collection": (
                build_manifest.get("storage_targets") or {}
            ).get("qdrant_collection"),
            "source_mongo_collection": (
                build_manifest.get("storage_targets") or {}
            ).get("mongo_parent_collection"),
        }
    )
    write_json(target_dir / "manifest.json", manifest)
    (target_dir / "README.md").write_text(
        "# Architecture Regression V2\n\n"
        "Versioned copy of the legacy 120/180/100 suites aligned with the "
        "current QueryPlan, table-first lookup, v31 data build, and answer "
        "grounding contracts. It is a regression/development bundle, not an "
        "unseen acceptance holdout. The legacy final_holdout remains immutable.\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build architecture evaluation v2")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    manifest = build_bundle(args.source, args.target)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
