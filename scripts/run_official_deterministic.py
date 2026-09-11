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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-worktree", action="store_true")
    parser.add_argument("--bundle", default=BUNDLE.name, help="Folder under data/eval, e.g. official_v2.")
    args = parser.parse_args()
    bundle = BUNDLE.parent / args.bundle
    baseline = verify_runtime(bundle, args.current_worktree)
    from src.common.env_loader import load_project_env
    load_project_env()
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    from src.evaluation.dataset import _validate_common, validate_deterministic_case
    from src.evaluation.deterministic import evaluate_deterministic
    cases = json.loads((bundle / "deterministic_tool_cases.json").read_text(encoding="utf-8"))
    errors = []
    for case in cases:
        _validate_common(case, "deterministic", errors)
        validate_deterministic_case(case, errors)
    if errors or not cases:
        raise ValueError(errors or f"No cases in {bundle.name}")
    expected = {"QDRANT_COLLECTION_NAME": "student_handbook_semantic_v33",
                "STUDENT_RAG_HYBRID_COLLECTION": "student_handbook_semantic_v33",
                "MONGODB_PARENT_COLLECTION": "parent_docs_v33"}
    actual = {key: os.environ.get(key) for key in expected}
    if actual != expected:
        raise ValueError(f"Storage configuration mismatch: {actual}")
    from src.retrieval.core.ai_router import AIRouter
    from src.retrieval.core.query_plan import QUERY_PLAN_NORMALIZER_VERSION
    router = AIRouter.from_config()
    planner = {"provider": "groq", "model": router.model_name,
               "response_format": router._resolved_response_format(),
               "reasoning_effort": router._resolved_reasoning_effort(),
               "normalizer_version": QUERY_PLAN_NORMALIZER_VERSION}
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
             *Path(ROOT / "src/evaluation").glob("*.py"), Path(__file__),
             *frozen_runtime_files]
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    snapshot = {"created_at": stamp, "bundle": args.bundle, "dataset_frozen": False, "release_frozen": False,
                "purpose": "pre-run identity; owner approval required before next suite",
                "hashes": hashes, "storage": actual, "router_cache": False, "planner": planner,
                "runtime_base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "approved_runtime_change": ("Current working tree; see runtime_base_commit and planner"
                                            if args.current_worktree else "Composer timeout 60 -> 20 seconds"),
                "response_cache": "not used: retrieval-only deterministic execution"}
    (output / "run_snapshot.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"Output: {output}", flush=True)
    report = evaluate_deterministic(cases, evaluation_contract="query-plan-grounded-outcome-v9",
                                      checkpoint_path=output / "checkpoint.json", resume=False,
                                      checkpoint_context=snapshot)
    report["run_snapshot"] = snapshot
    report["post_run_hashes_match"] = all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in hashes.items())
    (output / "deterministic.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
