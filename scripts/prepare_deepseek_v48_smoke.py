"""Prepare/verify one offline experiment snapshot; never call a model/provider."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.build_official_deterministic import build, CONTRACT_V10
from src.evaluation.dataset import _validate_common, validate_deterministic_case

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data/eval/deepseek_v48_smoke"
FREEZE = BUNDLE / "experiment_freeze.json"
REGRESSION_IDS = tuple(f"official_det_{n:03d}" for n in (
    13, 14, 18, 33, 34, 35, 47, 93, 96, 114, 119, 122,
))


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_freeze(path=FREEZE):
    snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
    changed = [name for name, expected in snapshot["sha256"].items()
               if not (ROOT / name).is_file() or file_hash(ROOT / name) != expected]
    if changed:
        raise ValueError(f"Experiment freeze drift: {changed}")
    return snapshot


def build_smoke_cases():
    original = json.loads((ROOT / "data/eval/official_v1/deterministic_tool_cases_v10.json")
                          .read_text(encoding="utf-8"))
    regression = [case for case in original if case["id"] in REGRESSION_IDS]
    if tuple(case["id"] for case in regression) != REGRESSION_IDS:
        raise ValueError("Missing/changed regression IDs")
    development = build(BUNDLE, contract=CONTRACT_V10)
    # Wrong-scale probes may safely ask for clarification instead of returning
    # a reference table. This is development gold, not a V1 outcome change.
    development[1]["accepted_outcomes"].append({
        "name": "scale-clarification", "state": "clarify",
        "allowed_modes": ["clarify"], "task_count": {"min": 1, "max": 1},
        "clarification_question_required": True, "required_tasks": [],
    })
    cases = regression + development
    errors = []
    for case in cases:
        _validate_common(case, "deterministic", errors)
        validate_deterministic_case(case, errors)
    if errors or len(cases) != 18:
        raise ValueError(errors or "Expected 18 smoke cases")
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        snapshot = verify_freeze()
        print(f"Freeze verified: {len(snapshot['sha256'])} files; no inference.")
        return
    target = BUNDLE / "deterministic_tool_cases_v10.json"
    if FREEZE.exists() or target.exists():
        raise FileExistsError("Smoke already prepared; use --verify, do not overwrite frozen artifacts")
    cases = build_smoke_cases()
    target.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files = {*ROOT.glob("src/**/*.py"), *ROOT.glob("configs/**/*.yaml"),
             *ROOT.glob("data/processed/**/*.json"), *BUNDLE.glob("*.yaml"), target,
             ROOT / "data/eval/official_v1/deterministic_tool_cases.json",
             ROOT / "data/eval/official_v1/deterministic_tool_cases_v10.json",
             ROOT / "data/eval/official_v1/deterministic_authoring.yaml",
             ROOT / "scripts/run_official_deterministic.py", Path(__file__),
             ROOT / "scripts/build_official_deterministic.py",
             ROOT / "requirements.txt", ROOT / "requirements-dev.txt"}
    snapshot = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "local_experiment_identity_not_production_release",
        "independent_holdout": False, "prompt_version": "structured-regulation-v48-scale-task-pairing",
        "contract_version": CONTRACT_V10,
        "comparison_scope": "operational_configurations_not_reasoning_only",
        "allowed_reasoning_efforts": ["none", "low"],
        "approved_case_model_runs": 36, "full_ab_approved": False,
        "smoke_case_ids": [case["id"] for case in cases],
        "regression_case_ids": list(REGRESSION_IDS),
        "development_case_ids": [case["id"] for case in cases[12:]],
        "planner_common": {"provider": "deepseek", "model_name": "deepseek-flash",
                           "response_format": "json_object",
                           "temperature": 0.0, "omit_max_tokens": True,
                           "request_timeout_seconds": 20.0, "max_retries": 1},
        "provider_defaults": {"none": 8192, "low": 65536,
                              "checked_on": "2026-09-26",
                              "source": "https://api-docs.deepseek.com/api/create-chat-completion/"},
        "safety_review": {"v48_dev_002": "No resolved_result/resolved_rows arithmetic from a 10-point table for 3,6/4; review separately from contract score."},
        "limitations": ["Provider prompt cache may be used; application router/response caches are disabled or bypassed.",
                        "No hard USD cap; retries and bounded repairs may add requests.",
                        "Unavailable usage on failed requests is unknown, never zero cost.",
                        "Temperature is ineffective in thinking mode; this is not a reasoning-only causal experiment."],
        "sha256": {path.relative_to(ROOT).as_posix(): file_hash(path) for path in sorted(files)},
    }
    FREEZE.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared 18 cases and {len(files)} file hashes; no inference. {FREEZE}")


if __name__ == "__main__":
    main()
