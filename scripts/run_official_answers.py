"""Run an official_v1 suite (retrieval, generate+judge, or production) with a run snapshot."""
import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone

import yaml

from scripts.prepare_official_eval import BUNDLE, ROOT

CASE_FILES = {
    "retrieval": "retrieval_cases.json",
    "answers": "generated_answer_cases.json",
    "production": "production_cases.json",
}


def _snapshot(suite: str, case_path) -> dict:
    from src.generation.answer_pipeline import PIPELINE_VERSION
    from src.generation.prompt_builder import ANSWER_PROMPT_VERSION
    from src.retrieval.core.ai_router import ROUTER_PROMPT_VERSION, AIRouter
    from src.retrieval.core.query_plan import QUERY_PLAN_NORMALIZER_VERSION
    from src.retrieval.core.retrieval_mode import DEFAULT_RETRIEVAL_MODE

    router = AIRouter.from_config()
    answer_llm = yaml.safe_load((ROOT / "configs/answer_generation.yaml").read_text(encoding="utf-8"))["llm"]
    reranker = yaml.safe_load((ROOT / "configs/retrieval.yaml").read_text(encoding="utf-8")).get("cohere_reranker", {})
    return {
        "suite": suite,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_dirty": bool(subprocess.check_output(["git", "status", "--porcelain", "--", "src", "configs", "scripts"],
                                                  cwd=ROOT, text=True).strip()),
        "dataset": case_path.relative_to(ROOT).as_posix(),
        "dataset_sha256": hashlib.sha256(case_path.read_bytes()).hexdigest(),
        "pipeline_version": PIPELINE_VERSION,
        "retrieval_mode": DEFAULT_RETRIEVAL_MODE,
        "cohere_reranker": {"enabled": bool(reranker.get("enabled")), "model": reranker.get("model")},
        "planner": {"provider": "groq", "model": router.model_name,
                    "prompt_version": ROUTER_PROMPT_VERSION,
                    "reasoning_effort": router._resolved_reasoning_effort(),
                    "normalizer_version": QUERY_PLAN_NORMALIZER_VERSION},
        "composer": {"model": answer_llm.get("model_name"), "prompt_version": ANSWER_PROMPT_VERSION},
        "storage": {key: os.environ.get(key) for key in
                    ("QDRANT_COLLECTION_NAME", "STUDENT_RAG_HYBRID_COLLECTION", "MONGODB_PARENT_COLLECTION")},
    }


def _write(report: dict, path) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report.get("summary", {}), ensure_ascii=False, indent=2)[:3000], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=tuple(CASE_FILES), required=True)
    parser.add_argument("--output", help="Existing run directory to resume.")
    parser.add_argument("--limit", type=int, help="Smoke-test only the first N cases.")
    parser.add_argument("--bundle", default=BUNDLE.name, help="Folder under data/eval, e.g. official_v2.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000",
                        help="Deployed API to send the production suite requests to.")
    parser.add_argument("--retrieval-mode", help="Retrieval suite only: run an ablation mode "
                        "(no_graph, vector_only) instead of the default.")
    args = parser.parse_args()
    from src.common.env_loader import load_project_env
    load_project_env()
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    from src.evaluation.gates import production_gates
    from src.evaluation.answers import generate_answers, judge_answers, load_answer_checkpoint
    from src.evaluation.production import evaluate_production
    from src.evaluation.retrieval import evaluate_retrieval

    case_path = BUNDLE.parent / args.bundle / CASE_FILES[args.suite]
    cases = json.loads(case_path.read_text(encoding="utf-8"))
    resume = bool(args.output)
    if resume:
        output = ROOT / args.output
        snapshot = json.loads((output / "run_snapshot.json").read_text(encoding="utf-8"))
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        smoke = f"_smoke{args.limit}" if args.limit else ""
        output = ROOT / "data/eval/reports" / f"{args.bundle}_{args.suite}{smoke}_{stamp}"
        output.mkdir(parents=True, exist_ok=False)
        snapshot = {**_snapshot(args.suite, case_path), "limit": args.limit}
        if args.suite == "production":
            snapshot["base_url"] = args.base_url
        if args.retrieval_mode:
            snapshot["retrieval_mode"] = args.retrieval_mode
        (output / "run_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Output: {output}", flush=True)

    if args.suite == "retrieval":
        report = evaluate_retrieval(cases, backend="qdrant", mode=snapshot["retrieval_mode"], scope="end_to_end",
                                    limit=snapshot["limit"], checkpoint_path=output / "retrieval_checkpoint.json",
                                    resume=resume, checkpoint_context=snapshot)
        report["run_snapshot"] = snapshot
        _write(report, output / "retrieval.json")
        return

    if args.suite == "production":
        report = evaluate_production(cases, base_url=snapshot["base_url"], limit=snapshot["limit"],
                                     checkpoint_path=output / "production_checkpoint.json",
                                     resume=resume, checkpoint_context=snapshot)
        report["gates"] = production_gates(report.get("summary") or {})
        report["run_snapshot"] = snapshot
        _write(report, output / "production.json")
        return

    answer_cache = output / "answer_cache.json"
    generation = generate_answers(cases, cache_path=answer_cache, resume=resume, limit=snapshot["limit"],
                                  checkpoint_context=snapshot)
    generation["run_snapshot"] = snapshot
    _write(generation, output / "answer_generation.json")
    judged = judge_answers(cases, load_answer_checkpoint(cases, answer_cache, checkpoint_context=snapshot),
                           checkpoint_path=output / "judge_checkpoint.json", resume=resume,
                           limit=snapshot["limit"], checkpoint_context=snapshot)
    judged["run_snapshot"] = snapshot
    _write(judged, output / "generated_answer_judge.json")


if __name__ == "__main__":
    main()
