from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.env_loader import load_project_env
from src.evaluation.dataset import DATASET_FILES, load_json, validate_bundle
from src.evaluation.gates import evaluate_gates
from src.evaluation.human_audit import summarize_human_audit
from src.evaluation.reporting import write_report_bundle
from src.evaluation.suites import (
    evaluate_deterministic_v2,
    evaluate_graph_supplement,
    evaluate_production,
    evaluate_retrieval,
    generate_answers,
    judge_answers,
    load_answer_checkpoint,
)
from src.generation.answer_pipeline import PIPELINE_VERSION
from src.retrieval.core.retrieval_mode import DEFAULT_RETRIEVAL_MODE


DEFAULT_DATASET = ROOT / "data" / "eval" / "architecture_v3"
DEFAULT_OUTPUT = ROOT / "data" / "eval" / "reports" / "release_candidate"
DEFAULT_DOCSTORE = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"
AI_ROUTER_CONFIG = ROOT / "configs" / "ai_router.yaml"
LOOKUP_REGISTRY_CONFIG = ROOT / "configs" / "structured_lookup_registry.yaml"
RETRIEVAL_CONFIG = ROOT / "configs" / "retrieval.yaml"
ANSWER_GENERATION_CONFIG = ROOT / "configs" / "answer_generation.yaml"
SLANG_DICTIONARY_CONFIG = ROOT / "configs" / "hcmue_slang_dictionary.yaml"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _normalized_text_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _provenance(
    dataset_dir: Path,
    backend: str,
    *,
    allow_docstore_drift: bool = False,
) -> dict[str, Any]:
    manifest = load_json(dataset_dir / "manifest.json")
    router_config = yaml.safe_load(AI_ROUTER_CONFIG.read_text(encoding="utf-8")) or {}
    answer_config = (
        yaml.safe_load(ANSWER_GENERATION_CONFIG.read_text(encoding="utf-8")) or {}
    )
    llm_config = answer_config.get("llm") or {}
    cache_config = answer_config.get("cache") or {}
    expected_config_hashes = dict(manifest.get("config_hashes") or {})
    config_hash = (
        _normalized_text_hash
        if manifest.get("config_hash_method") == "sha256-lf-normalized-v1"
        else _file_hash
    )
    actual_config_hashes = {
        "ai_router": config_hash(AI_ROUTER_CONFIG),
        "structured_lookup_registry": config_hash(LOOKUP_REGISTRY_CONFIG),
        "retrieval": config_hash(RETRIEVAL_CONFIG),
        "answer_generation": config_hash(ANSWER_GENERATION_CONFIG),
        "slang_dictionary": config_hash(SLANG_DICTIONARY_CONFIG),
    }
    current_commit = _git_commit()
    evaluated_system_commit = str(manifest.get("evaluated_system_commit") or "")
    system_commit_matches_manifest = bool(evaluated_system_commit) and (
        current_commit == evaluated_system_commit
    )
    config_hashes_match_manifest = bool(expected_config_hashes) and all(
        actual_config_hashes.get(name) == expected_hash
        for name, expected_hash in expected_config_hashes.items()
    )
    benchmark_run_kind = (
        "frozen_holdout"
        if system_commit_matches_manifest and config_hashes_match_manifest
        else "post_fix_regression"
    )
    return {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": current_commit,
        "evaluated_system_commit": evaluated_system_commit or None,
        "evaluation_harness_commit": manifest.get("evaluation_harness_commit"),
        "system_commit_matches_manifest": system_commit_matches_manifest,
        "benchmark_run_kind": benchmark_run_kind,
        "dataset_version": manifest.get("version"),
        "dataset_frozen": bool(manifest.get("frozen")),
        "dataset_revision": manifest.get("revision"),
        "evaluation_contract": manifest.get("evaluation_contract"),
        "deterministic_contract": manifest.get("deterministic_contract"),
        "retrieval_contract": manifest.get("retrieval_contract"),
        "dataset_hashes": manifest.get("dataset_hashes"),
        "docstore_hash": manifest.get("docstore_hash"),
        "expected_docstore_hash": manifest.get("docstore_hash"),
        "actual_docstore_hash": _file_hash(DEFAULT_DOCSTORE),
        "compatibility_diagnostic": allow_docstore_drift,
        "config_hashes": actual_config_hashes,
        "expected_config_hashes": expected_config_hashes,
        "config_hashes_match_manifest": config_hashes_match_manifest,
        "generation_model": llm_config.get("model_name")
        or manifest.get("generation_model"),
        "dataset_generation_model": manifest.get("generation_model"),
        "answer_pipeline_version": PIPELINE_VERSION,
        "answer_generation_retrieval_mode": DEFAULT_RETRIEVAL_MODE,
        "phoranker_used_for_answer_generation": False,
        "response_cache_mode": "exact" if cache_config.get("enabled", True) else "off",
        "router_provider": router_config.get("provider", "groq"),
        "router_model": os.environ.get("STUDENT_RAG_ROUTER_MODEL")
        or router_config.get("model_name", "qwen/qwen3.8-27b"),
        "router_reasoning_effort": os.environ.get(
            "STUDENT_RAG_ROUTER_REASONING_EFFORT"
        )
        or router_config.get("reasoning_effort", "auto"),
        "router_max_output_tokens": int(
            os.environ.get("STUDENT_RAG_ROUTER_MAX_OUTPUT_TOKENS")
            or router_config.get("max_output_tokens", 256)
        ),
        "router_response_format": os.environ.get(
            "STUDENT_RAG_ROUTER_RESPONSE_FORMAT"
        )
        or router_config.get("response_format", "auto"),
        "judge_model": manifest.get("judge_model"),
        "backend": backend,
        "qdrant_collection": os.environ.get("STUDENT_RAG_HYBRID_COLLECTION")
        or os.environ.get("QDRANT_COLLECTION_NAME"),
        "mongodb_parent_collection": os.environ.get("MONGODB_PARENT_COLLECTION"),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def _file_hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_env(names: tuple[str, ...], message: str) -> None:
    if not any(os.environ.get(name) for name in names):
        raise SystemExit(message)


def _resolve_deterministic_contract(
    manifest: dict[str, Any], cases: list[dict[str, Any]]
) -> str:
    """Resolve the deterministic evaluator contract without a legacy fallback."""
    declared = str(manifest.get("deterministic_contract") or "").strip()
    case_contracts = {
        str(case.get("contract_version") or "").strip()
        for case in cases
        if str(case.get("contract_version") or "").strip()
    }
    if len(case_contracts) > 1:
        raise ValueError(
            "Deterministic cases declare conflicting contracts: "
            + ", ".join(sorted(case_contracts))
        )
    case_contract = next(iter(case_contracts), "")
    if declared and case_contract and declared != case_contract:
        raise ValueError(
            "Deterministic contract mismatch: "
            f"manifest={declared!r}, cases={case_contract!r}"
        )
    contract = declared or case_contract
    if not contract:
        raise ValueError(
            "Deterministic evaluation contract is missing; refusing to use the "
            "legacy evaluator implicitly"
        )
    if not contract.startswith("query-plan-"):
        raise ValueError(f"Unsupported deterministic evaluation contract: {contract!r}")
    return contract


def _runtime_storage_errors(
    manifest: dict[str, Any], provenance: dict[str, Any], backend: str
) -> list[str]:
    """Reject evaluation runs whose storage identity differs from the manifest."""
    if backend != "qdrant":
        return []

    fields = (
        ("hybrid_collection", "qdrant_collection"),
        ("mongodb_parent_collection", "mongodb_parent_collection"),
    )
    errors: list[str] = []
    require_complete_identity = manifest.get("schema_version") in {
        "architecture-evaluation-v6",
        "architecture-evaluation-v7",
        "architecture-evaluation-v8",
        "architecture-evaluation-v9",
    }
    for manifest_key, provenance_key in fields:
        expected = str(manifest.get(manifest_key) or "").strip()
        actual = str(provenance.get(provenance_key) or "").strip()
        if not expected:
            if require_complete_identity:
                errors.append(f"manifest missing storage identity: {manifest_key}")
            continue
        if actual != expected:
            errors.append(
                f"runtime storage mismatch: {provenance_key}={actual!r}, "
                f"expected {expected!r}"
            )
    return errors


def _write(report: dict[str, Any], output_dir: Path, name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = write_report_bundle(report, output_dir / f"{name}.json")
    print(
        json.dumps(
            {"report": paths, "summary": report.get("summary")},
            ensure_ascii=False,
            indent=2,
        )
    )


def _finalize_report(
    report: dict[str, Any], *, expected_n: int, provenance: dict[str, Any],
    profile: str = "full",
) -> dict[str, Any]:
    actual_n = int((report.get("summary") or {}).get("n", 0))
    report["provenance"] = provenance
    complete = actual_n == expected_n
    publication_status = (
        "headline_eligible" if complete else "partial_not_for_headline"
    )
    if complete and provenance.get("benchmark_run_kind") == "post_fix_regression":
        publication_status = "post_fix_regression_not_original_holdout"
    if not provenance.get("dataset_frozen", True):
        publication_status = "draft_dataset_not_for_headline"
    report["completeness"] = {
        "profile": profile,
        "expected_n": expected_n,
        "actual_n": actual_n,
        "complete": complete,
        "publication_status": publication_status,
    }
    if report.get("suite") in {
        "deterministic",
        "retrieval",
        "judge",
        "production",
        "faults",
    }:
        report["gates"] = evaluate_gates(report["suite"], report.get("summary") or {})
        if actual_n != expected_n:
            report["gates"]["passed"] = False
            report["gates"]["reason"] = "partial_report"
    if report.get("suite") == "judge":
        judged_n = int((report.get("summary") or {}).get("judged_n", 0))
        report["completeness"]["judged_n"] = judged_n
        if judged_n != expected_n:
            report["completeness"]["complete"] = False
            report["completeness"]["publication_status"] = "partial_judge_not_for_headline"
            report["gates"]["passed"] = False
            report["gates"]["reason"] = "partial_judge"
    if profile == "smoke":
        # A completed diagnostic sample is never a completed headline suite.
        report["completeness"]["complete"] = False
        report["completeness"]["publication_status"] = "smoke_not_for_headline"
        if "gates" in report:
            report["gates"]["passed"] = False
            report["gates"]["reason"] = "smoke_profile"
    return report


def _checkpoint_context(
    provenance: dict[str, Any], profile: str,
) -> dict[str, Any]:
    return {
        "profile": profile,
        "provenance": {
            key: value for key, value in provenance.items()
            if key not in {"run_at_utc", "platform"}
        },
    }


def _run_retrieval_modes(
    cases: list[dict[str, Any]], args: argparse.Namespace, provenance: dict[str, Any]
) -> None:
    modes = (
        ("full", "no_graph", "vector_only", "vector_primary_graph_supplement")
        if args.ablation == "all"
        else (args.ablation,)
    )
    reports: dict[str, Any] = {}
    for mode in modes:
        report = evaluate_retrieval(
            cases,
            backend=args.backend,
            mode=mode,
            scope=args.retrieval_scope,
            limit=args.limit,
            checkpoint_path=args.output / f"retrieval_{args.retrieval_scope}_{mode}_checkpoint_{args.profile}.json",
            resume=args.resume,
            checkpoint_context=_checkpoint_context(provenance, args.profile),
        )
        _finalize_report(
            report, expected_n=len(cases), provenance=provenance, profile=args.profile,
        )
        reports[mode] = report
        _write(
            report,
            args.output,
            (
                f"retrieval_{args.retrieval_scope}_{args.backend}_"
                f"{mode}_{args.profile}"
            ),
        )
    if len(reports) > 1:
        full = reports["full"]["summary"]
        delta = {
            mode: {
                metric: reports[mode]["summary"].get(metric, 0.0)
                - full.get(metric, 0.0)
                for metric in ("hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")
            }
            for mode in reports
            if mode != "full"
        }
        _write(
            {
                "suite": "retrieval_ablation",
                "summary": {"deltas_vs_full": delta},
                "provenance": provenance,
                "cases": [],
            },
            args.output,
            f"retrieval_ablation_{args.backend}_{args.profile}",
        )


def _pick_stratified_smoke(
    cases: list[dict[str, Any]],
    *,
    suite: str,
    limit: int | None,
) -> list[dict[str, Any]]:
    if not limit or limit >= len(cases):
        return cases

    fields_by_suite = {
        "deterministic": ("case_type", "lookup_group", "eval_split"),
        "retrieval": (
            "cohort",
            "eval_split",
            "question_style",
            "topic",
            "source_topic",
        ),
        "answers": ("case_type", "eval_split", "cohort", "topic"),
        "production": ("scenario", "eval_split", "cohort"),
    }
    fields = fields_by_suite.get(suite, ("cohort", "eval_split"))
    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    seen: dict[str, set[str]] = {field: set() for field in fields}

    def _case_key(case: dict[str, Any], field: str) -> str:
        value = case.get(field)
        if isinstance(value, list):
            return "|".join(str(item) for item in value)
        return str(value or "")

    while len(selected) < limit and len(selected_ids) < len(cases):
        best_index: int | None = None
        best_score = -1
        for index, case in enumerate(cases):
            if index in selected_ids:
                continue
            score = 0
            for field in fields:
                value = _case_key(case, field)
                if value and value not in seen[field]:
                    score += 2
            if case.get("eval_split") == "stress" and not any(
                item.get("eval_split") == "stress" for item in selected
            ):
                score += 4
            if case.get("eval_split") == "realistic" and not any(
                item.get("eval_split") == "realistic" for item in selected
            ):
                score += 2
            if suite == "retrieval":
                source_topic = _case_key(case, "source_topic")
                if source_topic and source_topic not in seen.get("source_topic", set()):
                    score += 4
            if score > best_score:
                best_score = score
                best_index = index
        if best_index is None:
            break
        case = cases[best_index]
        selected.append(case)
        selected_ids.add(best_index)
        for field in fields:
            value = _case_key(case, field)
            if value:
                seen[field].add(value)
    return selected


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(
        description="Unified frozen Evaluation Suite V8 runner"
    )
    parser.add_argument(
        "--suite",
        choices=(
            "validate",
            "deterministic",
            "retrieval",
            "graph",
            "generate",
            "judge",
            "production",
            "faults",
            "all",
        ),
        default="validate",
    )
    parser.add_argument("--profile", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--backend", choices=("qdrant",), default="qdrant")
    parser.add_argument(
        "--ablation",
        choices=(
            "full",
            "no_graph",
            "vector_only",
            "vector_primary_graph_supplement",
            "all",
        ),
        default="vector_primary_graph_supplement",
    )
    parser.add_argument(
        "--retrieval-scope",
        choices=("pure", "end_to_end"),
        default="end_to_end",
        help=(
            "end_to_end scores routing/query-handling and retrieval together; "
            "pure is retained only for retriever-only diagnostics"
        ),
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--human-audit", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--lookup-group", default=None)
    parser.add_argument("--case-type", default=None)
    parser.add_argument(
        "--allow-docstore-drift",
        action="store_true",
        help=(
            "Run a legacy bundle against the current docstore as a compatibility "
            "diagnostic. Only the docstore hash mismatch becomes a warning; all "
            "dataset, source, cohort, count, and schema checks remain strict."
        ),
    )
    parser.add_argument(
        "--allow-draft-dataset",
        action="store_true",
        help=(
            "Validate and run a mutable draft bundle. Every report still records "
            "the Git commit and dataset hashes, but is marked not for headline use."
        ),
    )
    args = parser.parse_args()

    if args.profile == "smoke" and args.limit is None:
        args.limit = 5
    validation = validate_bundle(
        args.dataset,
        DEFAULT_DOCSTORE,
        require_frozen=not args.allow_draft_dataset,
        enforce_docstore_hash=not args.allow_docstore_drift,
    )
    provenance = _provenance(
        args.dataset,
        args.backend,
        allow_docstore_drift=args.allow_docstore_drift,
    )
    manifest = load_json(args.dataset / "manifest.json")
    storage_errors = _runtime_storage_errors(manifest, provenance, args.backend)
    if storage_errors:
        validation["errors"].extend(storage_errors)
        validation["valid"] = False
    validation_report = {
        "suite": "validation",
        "summary": validation,
        "provenance": provenance,
        "cases": [],
    }
    _write(validation_report, args.output, "validation")
    if not validation["valid"]:
        raise SystemExit("Evaluation dataset validation failed; no evaluation was run")
    if args.suite == "validate":
        return

    deterministic_cases = load_json(args.dataset / DATASET_FILES["deterministic"])
    if args.lookup_group:
        deterministic_cases = [
            case
            for case in deterministic_cases
            if case.get("lookup_group") == args.lookup_group
        ]
    if args.case_type:
        deterministic_cases = [
            case for case in deterministic_cases if case.get("case_type") == args.case_type
        ]
    retrieval_cases = load_json(args.dataset / DATASET_FILES["retrieval"])
    answer_cases = load_json(args.dataset / DATASET_FILES["answers"])
    production_cases = load_json(args.dataset / DATASET_FILES["production"])
    eval_limit = args.limit
    if args.profile == "smoke":
        deterministic_cases = _pick_stratified_smoke(
            deterministic_cases,
            suite="deterministic",
            limit=eval_limit,
        )
        retrieval_cases = _pick_stratified_smoke(
            retrieval_cases,
            suite="retrieval",
            limit=eval_limit,
        )
        answer_cases = _pick_stratified_smoke(
            answer_cases,
            suite="answers",
            limit=eval_limit,
        )
        production_cases = _pick_stratified_smoke(
            production_cases,
            suite="production",
            limit=eval_limit,
        )
        args.limit = None

    if args.suite in {"deterministic", "all"}:
        _require_env(
            ("GROQ_ROUTER_API_KEYS", "GROQ_API_KEYS"),
            "A Groq API key pool is required for the Qwen structured router",
        )
        deterministic_contract = _resolve_deterministic_contract(
            manifest, deterministic_cases
        )
        provenance["resolved_deterministic_contract"] = deterministic_contract
        report = evaluate_deterministic_v2(
            deterministic_cases,
            limit=args.limit,
            evaluation_contract=deterministic_contract,
            checkpoint_path=args.output / f"deterministic_checkpoint_{args.profile}.json",
            resume=args.resume,
            checkpoint_context=_checkpoint_context(provenance, args.profile),
        )
        _finalize_report(
            report,
            expected_n=len(deterministic_cases),
            provenance=provenance,
            profile=args.profile,
        )
        _write(report, args.output, f"deterministic_{args.profile}")

    if args.suite in {"retrieval", "all"}:
        if args.backend == "qdrant":
            _require_env(
                ("QDRANT_URL",), "QDRANT_URL is required for headline retrieval"
            )
            _require_env(
                ("MONGODB_URL",),
                "MONGODB_URL is required for headline parent-section retrieval",
            )
        _run_retrieval_modes(retrieval_cases, args, provenance)

    if args.suite in {"graph", "all"}:
        report = evaluate_graph_supplement(limit=args.limit)
        _finalize_report(
            report,
            expected_n=int((report.get("summary") or {}).get("n") or 0),
            provenance=provenance,
            profile=args.profile,
        )
        _write(report, args.output, f"graph_supplement_{args.profile}")

    answer_cache_path = args.output / f"answer_cache_{args.profile}.json"
    answer_expected_n = len(answer_cases)
    if args.suite in {"generate", "all"}:
        _require_env(
            ("GEMINI_API_KEYS",),
            "GEMINI_API_KEYS is required for answer generation",
        )
        _require_env(
            ("QDRANT_URL",), "QDRANT_URL is required for production answer generation"
        )
        _require_env(
            ("MONGODB_URL",),
            "MONGODB_URL is required for production answer generation",
        )
        report = generate_answers(
            answer_cases,
            cache_path=answer_cache_path,
            resume=args.resume,
            limit=args.limit,
            checkpoint_context=_checkpoint_context(provenance, args.profile),
        )
        _finalize_report(
            report,
            expected_n=answer_expected_n,
            provenance=provenance,
            profile=args.profile,
        )
        _write(report, args.output, f"answer_generation_{args.profile}")

    if args.suite in {"judge", "all"}:
        _require_env(
            ("GROQ_API_KEYS",),
            "GROQ_API_KEYS is required for gpt-oss-120b Judge",
        )
        if not answer_cache_path.exists():
            raise SystemExit(
                f"Missing answer cache: {answer_cache_path}; run --suite generate first"
            )
        report = judge_answers(
            answer_cases,
            load_answer_checkpoint(
                answer_cases, answer_cache_path,
                checkpoint_context=_checkpoint_context(provenance, args.profile),
            ),
            checkpoint_path=args.output / f"judge_checkpoint_{args.profile}.json",
            resume=args.resume,
            limit=args.limit,
            checkpoint_context=_checkpoint_context(provenance, args.profile),
        )
        audit_path = args.human_audit or (args.output / "human_audit.json")
        if args.human_audit is None and not audit_path.exists():
            dataset_template = args.dataset / "human_audit_template.json"
            template = (
                load_json(dataset_template)
                if dataset_template.exists()
                else report.get("human_audit_template") or []
            )
            audit_path.write_text(
                json.dumps(template, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        dataset_template_path = args.dataset / "human_audit_template.json"
        audit_template = (
            load_json(dataset_template_path)
            if dataset_template_path.exists()
            else None
        )
        if audit_path.exists():
            report["human_audit"] = summarize_human_audit(
                load_json(audit_path),
                report.get("cases") or [],
                template_rows=audit_template,
            )
        else:
            report["human_audit"] = {
                "required_n": 20,
                "completed_n": 0,
                "complete": False,
                "template": report.get("human_audit_template") or [],
            }
        _finalize_report(
            report,
            expected_n=answer_expected_n,
            provenance=provenance,
            profile=args.profile,
        )
        if not report["human_audit"].get("complete"):
            report["completeness"]["complete"] = False
            report["completeness"]["publication_status"] = "human_audit_pending"
            report["gates"]["passed"] = False
            report["gates"]["reason"] = "human_audit_pending"
        _write(report, args.output, f"generated_answer_judge_{args.profile}")

    if args.suite in {"production", "all"}:
        report = evaluate_production(
            production_cases,
            base_url=args.base_url,
            limit=args.limit,
            checkpoint_path=args.output / f"production_checkpoint_{args.profile}.json",
            resume=args.resume,
            checkpoint_context=_checkpoint_context(provenance, args.profile),
        )
        _finalize_report(
            report, expected_n=len(production_cases), provenance=provenance,
            profile=args.profile,
        )
        _write(report, args.output, f"production_{args.profile}")

    if args.suite in {"faults", "all"}:
        nodes = [
            "tests/test_gemini_client.py::GeminiClientTest::test_streaming_call_times_out_without_chunks",
            "tests/test_gemini_client.py::GeminiClientTest::test_generate_retries_next_key_after_rate_limit",
            "tests/test_gemini_client.py::GeminiClientTest::test_generate_stream_retries_next_key_after_rate_limit",
            "tests/test_gemini_client.py::GeminiClientTest::test_disconnect_is_classified_as_transient",
            "tests/test_gemini_client.py::GeminiClientTest::test_concurrent_generate_uses_request_local_clients",
            "tests/test_gemini_client.py::GeminiKeyPoolTest::test_key_pool_load_balances_between_keys",
            "tests/test_gemini_client.py::GeminiKeyPoolTest::test_key_pool_skips_key_in_cooldown",
            "tests/test_gemini_client.py::GeminiKeyPoolTest::test_key_pool_blocks_daily_exhausted_keys",
            "tests/test_evaluation.py::test_gemini_pool_reports_all_keys_temporarily_limited",
            "tests/test_evaluation.py::test_gemini_empty_response_is_not_success",
            "tests/test_evaluation.py::test_retrieval_exception_stays_in_denominator",
            "tests/test_evaluation.py::test_mongo_parent_miss_cannot_count_as_retrieval_hit",
            "tests/api/test_api_routes.py::ApiRoutesTest::test_chat_returns_busy_when_capacity_is_full",
        ]
        junit_path = args.output / "fault_injection_junit.xml"
        pytest_temp = args.output / f"pytest_fault_tmp_{os.getpid()}"
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                *nodes,
                f"--junitxml={junit_path}",
                f"--basetemp={pytest_temp}",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        junit_root = ET.parse(junit_path).getroot()
        rows = []
        for testcase in junit_root.findall(".//testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")
            rows.append(
                {
                    "id": f"{testcase.get('classname')}::{testcase.get('name')}",
                    "passed": failure is None and error is None,
                    "latency_seconds": float(testcase.get("time") or 0),
                    "failure": (
                        failure.text
                        if failure is not None
                        else error.text
                        if error is not None
                        else None
                    ),
                }
            )
        passed = sum(bool(row["passed"]) for row in rows)
        report = {
            "suite": "faults",
            "summary": {
                "n": len(rows),
                "passed": passed,
                "pass_rate": passed / max(1, len(rows)),
                "pytest_exit_code": completed.returncode,
            },
            "cases": rows,
            "pytest_stdout": completed.stdout[-4000:],
            "pytest_stderr": completed.stderr[-4000:],
        }
        _finalize_report(
            report, expected_n=len(nodes), provenance=provenance, profile=args.profile,
        )
        _write(report, args.output, f"fault_injection_{args.profile}")


if __name__ == "__main__":
    main()
