"""Safely reuse dev answers whose deterministic composer inputs did not change.

This release helper is intentionally conservative.  It ignores retrieval telemetry,
but requires the effective query, validated request contract, structured payload and
the exact bounded evidence context to remain identical before an old answer can be
reused.  Changed cases are regenerated and judged normally.
"""

from __future__ import annotations

import argparse
import copy
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

from src.evaluation.artifact_fingerprint import release_artifact_fingerprint  # noqa: E402
from src.evaluation.single_cohort_v2 import validate_bundle  # noqa: E402
from src.generation.citation_formatter import select_relevant_citations  # noqa: E402
from src.generation.context_allocation import (  # noqa: E402
    ContextAllocationConfig,
    build_context_for_prompt,
)
from src.generation.io_utils import load_yaml  # noqa: E402


ANSWER_CONFIG = ROOT / "configs" / "answer_generation.yaml"
TELEMETRY_FIELDS = frozenset(
    {
        "score",
        "semantic_score",
        "distance",
        "rerank",
        "selection_method",
        "retrieval_rank",
        "request_retrieval_rank",
        "latency_ms",
        "duration_ms",
        "usage",
        "provider",
        "key_fingerprint",
        "attempts",
    }
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _current_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _stable(value: Any) -> Any:
    """Remove operational telemetry without erasing answer-bearing data."""

    if isinstance(value, Mapping):
        return {
            str(key): _stable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in TELEMETRY_FIELDS
        }
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(
        _stable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _request_contract(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        provenance = row.get("provenance")
        provenance = provenance if isinstance(provenance, Mapping) else {}
        output.append(
            {
                "request_id": row.get("request_id"),
                "request_index": row.get("request_index"),
                "request_kind": row.get("request_kind"),
                "lookup_type": row.get("lookup_type"),
                "intent": row.get("intent"),
                "query_span": row.get("query_span"),
                "cohort": row.get("cohort"),
                "status": row.get("status"),
                "reason": row.get("reason"),
                "source_bound": provenance.get("source_bound"),
                "qualified": provenance.get("qualified"),
            }
        )
    return output


def _decision_contract(decision: Any) -> dict[str, Any]:
    if not isinstance(decision, Mapping):
        return {}
    handling = decision.get("query_handling")
    handling = handling if isinstance(handling, Mapping) else {}
    requests = decision.get("lookup_requests") or decision.get("atomic_requests") or []
    normalized_requests: list[dict[str, Any]] = []
    for index, request in enumerate(requests):
        if not isinstance(request, Mapping):
            continue
        normalized_requests.append(
            {
                "request_id": request.get("request_id") or f"r{index + 1}",
                "request_kind": request.get("request_kind"),
                "tool_name": request.get("tool_name") or request.get("lookup_type"),
                "intent": request.get("intent"),
                "query_span": request.get("query_span"),
                "slots": request.get("slots") or {},
                "cohort_refs": request.get("cohort_refs") or [],
            }
        )
    return {
        "outcome": decision.get("outcome"),
        "cohort": decision.get("cohort"),
        "effective_cohort_source": decision.get("effective_cohort_source"),
        "effective_query": decision.get("effective_query")
        or handling.get("effective_query"),
        "query_mode": handling.get("mode") or decision.get("query_mode"),
        "context_mode": handling.get("context_mode")
        or decision.get("context_mode"),
        "requests": normalized_requests,
    }


def build_current_snapshot(
    result: Mapping[str, Any], *, config: Mapping[str, Any]
) -> dict[str, Any]:
    citations_config = config.get("citations") or {}
    llm_config = config.get("llm") or {}
    allocation = ContextAllocationConfig.from_config(config.get("context_allocation"))
    selected = select_relevant_citations(
        list(result.get("citations") or []),
        intent=result.get("intent"),
        retrieval_result=dict(result),
        max_sources=int(citations_config.get("max_sources", 2)),
    )
    effective_query = str(result.get("effective_query") or "").strip()
    context = build_context_for_prompt(
        dict(result),
        query=effective_query,
        selected_citations=selected,
        max_context_chars=int(llm_config.get("max_context_chars", 160000)),
        allocation_config=allocation,
    )
    return {
        "effective_query": effective_query,
        "decision": _decision_contract(result.get("router_decision")),
        "requests": _request_contract(result.get("request_results")),
        "structured_result": _stable(result.get("structured_result")),
        "formula_result": _stable(result.get("formula_result")),
        "context_used": context,
    }


def build_source_snapshot(answer: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "effective_query": str(answer.get("effective_query") or "").strip(),
        "decision": _decision_contract(answer.get("router_decision")),
        "requests": _request_contract(answer.get("request_results")),
        "structured_result": _stable(answer.get("structured_result")),
        "formula_result": _stable(answer.get("formula_result")),
        "context_used": str(answer.get("context_used") or ""),
    }


def compare_snapshots(
    source: Mapping[str, Any], current: Mapping[str, Any]
) -> tuple[bool, list[str]]:
    changed = [
        field
        for field in (
            "effective_query",
            "decision",
            "requests",
            "structured_result",
            "formula_result",
            "context_used",
        )
        if _stable(source.get(field)) != _stable(current.get(field))
    ]
    return not changed, changed


def _validate_current_artifact(payload: Mapping[str, Any]) -> None:
    validation = validate_bundle(require_gold_complete=True)
    if not validation.valid:
        raise ValueError("Single-cohort gold bundle is invalid")
    if payload.get("commit") != _current_commit():
        raise ValueError("Execution artifact is not bound to current HEAD")
    if payload.get("dataset_hashes") != validation.hashes:
        raise ValueError("Execution artifact dataset hashes do not match")
    if payload.get("artifact_fingerprint") != release_artifact_fingerprint(ROOT):
        raise ValueError("Execution artifact fingerprint does not match current inputs")


def prepare(args: argparse.Namespace) -> None:
    source = _load(args.source_report)
    execution = _load(args.execution_results)
    planner = _load(args.planner_report)
    _validate_current_artifact(execution)
    if execution.get("planner_report_sha256") != _sha256(args.planner_report):
        raise ValueError("Execution artifact is not bound to the supplied Planner report")
    if planner.get("commit") != _current_commit():
        raise ValueError("Planner report is not rebound to current HEAD")
    if len((planner.get("planner") or {}).get("dev", {}).get("rows") or []) != 150:
        raise ValueError("Planner report must cover all 150 development cases")

    answers = source.get("answers")
    results = execution.get("results")
    if not isinstance(answers, list) or not isinstance(results, Mapping):
        raise ValueError("Source answers or current execution results are missing")
    config = load_yaml(ANSWER_CONFIG)
    comparisons: list[dict[str, Any]] = []
    for answer in answers:
        case_id = str(answer.get("id") or "")
        current_result = results.get(case_id)
        if not case_id or not isinstance(current_result, Mapping):
            raise ValueError(f"Missing current execution result for {case_id!r}")
        source_snapshot = build_source_snapshot(answer)
        current_snapshot = build_current_snapshot(current_result, config=config)
        reusable, changed_fields = compare_snapshots(source_snapshot, current_snapshot)
        comparisons.append(
            {
                "id": case_id,
                "reusable": reusable,
                "changed_fields": changed_fields,
                "source_composer_input_sha256": _digest(source_snapshot),
                "current_composer_input_sha256": _digest(current_snapshot),
            }
        )

    changed_ids = [row["id"] for row in comparisons if not row["reusable"]]
    reusable_ids = [row["id"] for row in comparisons if row["reusable"]]
    report = {
        "report_type": "single_cohort_v2_selective_answer_reuse",
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": _current_commit(),
        "source_commit": source.get("commit"),
        "source_report": str(args.source_report.resolve()),
        "source_report_sha256": _sha256(args.source_report),
        "planner_report_sha256": _sha256(args.planner_report),
        "execution_results_sha256": _sha256(args.execution_results),
        "dataset_hashes": execution.get("dataset_hashes"),
        "artifact_fingerprint": execution.get("artifact_fingerprint"),
        "policy": {
            "telemetry_fields_ignored": sorted(TELEMETRY_FIELDS),
            "required_equal_fields": [
                "effective_query",
                "decision",
                "requests",
                "structured_result",
                "formula_result",
                "context_used",
            ],
        },
        "counts": {
            "source_answers": len(answers),
            "reusable": len(reusable_ids),
            "changed": len(changed_ids),
        },
        "reusable_case_ids": reusable_ids,
        "changed_case_ids": changed_ids,
        "comparisons": comparisons,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.case_ids_output.write_text(
        json.dumps(changed_ids, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["counts"], ensure_ascii=False))


def merge_answers(args: argparse.Namespace) -> None:
    reuse = _load(args.reuse_report)
    source = _load(args.source_report)
    executor = _load(args.executor_report)
    changed = _load(args.changed_answers_report)
    if reuse.get("commit") != _current_commit():
        raise ValueError("Reuse report does not match current HEAD")
    _validate_current_artifact(executor)
    _validate_current_artifact(changed)
    if reuse.get("source_report_sha256") != _sha256(args.source_report):
        raise ValueError("Reuse report does not match source report")
    reusable_ids = set(reuse.get("reusable_case_ids") or [])
    changed_ids = set(reuse.get("changed_case_ids") or [])
    source_answers = {str(row["id"]): row for row in source.get("answers") or []}
    changed_answers = {str(row["id"]): row for row in changed.get("answers") or []}
    if set(changed_answers) != changed_ids:
        raise ValueError("Changed answer report does not cover exactly the changed cases")
    if set(source_answers) != reusable_ids | changed_ids:
        raise ValueError("Reuse partition does not cover the source answers exactly")

    comparison_by_id = {
        str(row["id"]): row for row in reuse.get("comparisons") or []
    }
    merged: list[dict[str, Any]] = []
    for case_id in source_answers:
        if case_id in changed_ids:
            row = copy.deepcopy(changed_answers[case_id])
            row["answer_reuse_provenance"] = {"reused": False}
        else:
            row = copy.deepcopy(source_answers[case_id])
            comparison = comparison_by_id[case_id]
            row["answer_reuse_provenance"] = {
                "reused": True,
                "source_commit": source.get("commit"),
                "source_report_sha256": reuse.get("source_report_sha256"),
                "composer_input_sha256": comparison.get(
                    "current_composer_input_sha256"
                ),
            }
        merged.append(row)

    report = copy.deepcopy(dict(executor))
    report.update(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "commit": _current_commit(),
            "artifact_fingerprint": release_artifact_fingerprint(ROOT),
            "answers": merged,
            "answers_report_hash": None,
            "answer_judgments": [],
            "selective_answer_reuse": {
                "report_sha256": _sha256(args.reuse_report),
                "source_commit": source.get("commit"),
                "reused": len(reusable_ids),
                "regenerated": len(changed_ids),
            },
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["selective_answer_reuse"], ensure_ascii=False))


def prepare_judgments(args: argparse.Namespace) -> None:
    reuse = _load(args.reuse_report)
    source = _load(args.source_report)
    answers_hash = _sha256(args.answers_report)
    reusable_ids = set(reuse.get("reusable_case_ids") or [])
    rows: list[dict[str, Any]] = []
    for source_row in source.get("answer_judgments") or []:
        case_id = str(source_row.get("id") or "")
        if case_id not in reusable_ids:
            continue
        row = copy.deepcopy(source_row)
        row["answers_report_hash"] = answers_hash
        row["judgment_reuse_provenance"] = {
            "source_commit": source.get("commit"),
            "source_report_sha256": reuse.get("source_report_sha256"),
            "identical_composer_input": True,
        }
        rows.append(row)
    if len(rows) != len(reusable_ids):
        raise ValueError("Source judgments do not cover every reusable answer")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"reused_judgments": len(rows)}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--source-report", type=Path, required=True)
    prepare_parser.add_argument("--execution-results", type=Path, required=True)
    prepare_parser.add_argument("--planner-report", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--case-ids-output", type=Path, required=True)
    prepare_parser.set_defaults(handler=prepare)

    merge_parser = subparsers.add_parser("merge-answers")
    merge_parser.add_argument("--reuse-report", type=Path, required=True)
    merge_parser.add_argument("--source-report", type=Path, required=True)
    merge_parser.add_argument("--executor-report", type=Path, required=True)
    merge_parser.add_argument("--changed-answers-report", type=Path, required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    merge_parser.set_defaults(handler=merge_answers)

    judgment_parser = subparsers.add_parser("prepare-judgments")
    judgment_parser.add_argument("--reuse-report", type=Path, required=True)
    judgment_parser.add_argument("--source-report", type=Path, required=True)
    judgment_parser.add_argument("--answers-report", type=Path, required=True)
    judgment_parser.add_argument("--output", type=Path, required=True)
    judgment_parser.set_defaults(handler=prepare_judgments)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
