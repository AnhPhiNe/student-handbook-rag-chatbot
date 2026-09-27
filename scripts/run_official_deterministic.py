"""Run a deterministic suite (default official_v1) with a pre-run hash snapshot."""
import hashlib
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.prepare_official_eval import BUNDLE, ROOT


def verify_runtime(bundle=BUNDLE, current_worktree=False):
    freeze = bundle / "runtime_freeze.json"
    if not freeze.exists():
        # Bundles authored after official_v1 have no frozen runtime of their own;
        # they always measure the current worktree.
        if not current_worktree:
            raise ValueError(f"{bundle.name} has no runtime_freeze.json; pass --current-worktree")
        baseline = {"file_hashes": {}}
    else:
        baseline = json.loads(freeze.read_text(encoding="utf-8"))
    if current_worktree:
        # Explicit owner-approved rerun on the changed runtime. Keep the old
        # snapshot intact; the new run records actual pre/post hashes instead.
        build = json.loads((ROOT / "data/processed/metadata/build_manifest.json").read_text(encoding="utf-8"))
        for artifact in build["artifacts"].values():
            if hashlib.sha256((ROOT / artifact["path"]).read_bytes()).hexdigest() != artifact["sha256"]:
                raise ValueError(f"Corpus artifact drift: {artifact['path']}")
        return baseline
    for name, expected in baseline["file_hashes"].items():
        content = (ROOT / name).read_bytes()
        if name == "configs/answer_generation.yaml":
            # Verify only the explicitly approved 60 -> 20 second change.
            content = content.replace(b"request_timeout_seconds: 20", b"request_timeout_seconds: 60", 1)
            original = subprocess.check_output(["git", "show", f"{baseline['evaluated_system_commit']}:{name}"], cwd=ROOT)
            if content.replace(b"\r\n", b"\n") != original.replace(b"\r\n", b"\n"):
                raise ValueError(f"Unexpected configuration drift: {name}")
            continue
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Unexpected runtime drift: {name}")
    return baseline


def select_case_ids(cases, requested_ids=None):
    """Select explicit cases in dataset order; never silently ignore bad IDs."""
    if requested_ids is None:
        return cases
    requested = set(requested_ids)
    if not requested or len(requested) != len(requested_ids):
        raise ValueError("case IDs must be non-empty and unique")
    unknown = requested - {case["id"] for case in cases}
    if unknown:
        raise ValueError(f"Unknown case IDs: {sorted(unknown)}")
    return [case for case in cases if case["id"] in requested]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-worktree", action="store_true")
    parser.add_argument("--capture-planner-diagnostics", action="store_true",
                        help="Save structural raw/normalized planner decisions for synthetic cases.")
    parser.add_argument("--bundle", default=BUNDLE.name, help="Folder under data/eval, e.g. official_v2.")
    parser.add_argument("--contract", choices=("v9", "v10"), default="v9",
                        help="Use the immutable V9 baseline or separately compiled V10 outcomes.")
    parser.add_argument("--limit", type=int, help="Run only the first N cases for an operational smoke test.")
    parser.add_argument("--case-ids", nargs="+",
                        help="Run only these exact case IDs, in dataset order.")
    parser.add_argument("--max-consecutive-runtime-failures", type=int, default=3,
                        help="Stop after this many request/runtime failures; must be positive.")
    args = parser.parse_args()
    if args.max_consecutive_runtime_failures < 1 or (args.limit is not None and args.limit < 1):
        parser.error("limit and max-consecutive-runtime-failures must be positive")
    bundle = BUNDLE.parent / args.bundle
    baseline = verify_runtime(bundle, args.current_worktree)
    from src.common.env_loader import load_project_env
    load_project_env()
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    from src.evaluation.dataset import _validate_common, validate_deterministic_case
    from src.evaluation.deterministic import evaluate_deterministic
    case_file = "deterministic_tool_cases_v10.json" if args.contract == "v10" else "deterministic_tool_cases.json"
    cases = json.loads((bundle / case_file).read_text(encoding="utf-8"))
    errors = []
    for case in cases:
        _validate_common(case, "deterministic", errors)
        validate_deterministic_case(case, errors)
    if errors or not cases:
        raise ValueError(errors or f"No cases in {bundle.name}")
    source_dataset_n = len(cases)
    cases = select_case_ids(cases, args.case_ids)
    expected = {"QDRANT_COLLECTION_NAME": "student_handbook_semantic_v33",
                "STUDENT_RAG_HYBRID_COLLECTION": "student_handbook_semantic_v33",
                "MONGODB_PARENT_COLLECTION": "parent_docs_v33"}
    actual = {key: os.environ.get(key) for key in expected}
    if actual != expected:
        raise ValueError(f"Storage configuration mismatch: {actual}")
    from src.retrieval.core.ai_router import ROUTER_PROMPT_VERSION, AIRouter
    from src.retrieval.core.query_plan import (
        QUERY_PLAN_NORMALIZER_VERSION, QUERY_PLAN_STRICT_SCHEMA_VERSION,
    )
    router = AIRouter.from_config()
    planner = {"provider": router.provider, "model": router.model_name,
               "prompt_version": ROUTER_PROMPT_VERSION,
               "response_format": f"strict_json_schema_{QUERY_PLAN_STRICT_SCHEMA_VERSION}",
               "reasoning_effort": router.reasoning_effort,
               "normalizer_version": QUERY_PLAN_NORMALIZER_VERSION}
    planner.update({name: getattr(router, name) for name in (
        "max_output_tokens", "output_tokens_per_task",
        "hard_max_output_tokens", "request_timeout_seconds", "max_retries")})
    planner["key_pool"] = {name: getattr(router.key_pool.config, name) for name in (
        "rpm_limit_per_key", "rpd_limit_per_key", "tpm_limit_per_key", "tpd_limit_per_key",
        "cooldown_seconds", "wait_when_limited", "max_wait_seconds")}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "data/eval/reports" / f"{args.bundle}_deterministic_{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    frozen_runtime_files = []
    for name in baseline["file_hashes"]:
        path = ROOT / name
        if path.exists():
            frozen_runtime_files.append(path)
        elif not args.current_worktree:
            raise FileNotFoundError(f"Frozen runtime file is missing: {name}")
    files = [*bundle.glob("*.json"), *bundle.glob("*.yaml"),
             *ROOT.glob("src/**/*.py"), *ROOT.glob("configs/**/*.yaml"),
             *ROOT.glob("data/processed/directories/*.json"),
             *Path(ROOT / "src/evaluation").glob("*.py"), Path(__file__),
             *frozen_runtime_files]
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    snapshot = {"created_at": stamp, "bundle": args.bundle, "dataset_frozen": False, "release_frozen": False,
                "capture_planner_diagnostics": args.capture_planner_diagnostics,
                "case_limit": args.limit,
                "source_dataset_n": source_dataset_n,
                "selected_case_ids": [case["id"] for case in cases[:args.limit]],
                "max_consecutive_runtime_failures": args.max_consecutive_runtime_failures,
                "purpose": "pre-run identity; owner approval required before next suite",
                "hashes": hashes, "storage": actual, "router_cache": False, "planner": planner,
                "runtime_base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "approved_runtime_change": ("Current working tree; see runtime_base_commit and planner"
                                            if args.current_worktree else "Composer timeout 60 -> 20 seconds"),
                "response_cache": "not used: retrieval-only deterministic execution"}
    (output / "run_snapshot.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"Output: {output}", flush=True)
    report = evaluate_deterministic(cases, limit=args.limit,
                                      evaluation_contract=f"query-plan-grounded-outcome-{args.contract}",
                                      checkpoint_path=output / "checkpoint.json", resume=False,
                                      checkpoint_context=snapshot)
    report["run_snapshot"] = snapshot
    report["post_run_hashes_match"] = all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in hashes.items())
    (output / "deterministic.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2), flush=True)
    if report["summary"]["stopped_reason"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
