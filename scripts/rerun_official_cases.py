"""Rerun named cases of an answers run (generation and judge) under its own snapshot.

Used for the official_v4 reranker-timeout rule (data/eval/official_v4/SPEC.md):
the first run's files are left untouched, and each attempt is written to
<run>/reruns/attempt_<n>/. Scores are not printed.
"""
import argparse
import json
import os
from pathlib import Path

from scripts.prepare_official_eval import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="Run directory, e.g. data/eval/reports/official_v4_answers_<stamp>.")
    parser.add_argument("--ids", required=True, help="Comma-separated case ids.")
    parser.add_argument("--attempt", type=int, required=True)
    args = parser.parse_args()

    from src.common.env_loader import load_project_env
    load_project_env()
    run = ROOT / args.run
    snapshot = json.loads((run / "run_snapshot.json").read_text(encoding="utf-8"))
    retrieval_config = snapshot.get("retrieval_config") or "configs/retrieval.yaml"
    if retrieval_config == "configs/retrieval.yaml":
        os.environ.pop("STUDENT_RAG_RETRIEVAL_CONFIG", None)
    else:
        os.environ["STUDENT_RAG_RETRIEVAL_CONFIG"] = retrieval_config
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    os.environ["STUDENT_RAG_EVAL_TELEMETRY"] = "1"
    from src.evaluation.answers import generate_answers, judge_answers, load_answer_checkpoint

    wanted = [case_id.strip() for case_id in args.ids.split(",") if case_id.strip()]
    all_cases = json.loads((ROOT / snapshot["dataset"]).read_text(encoding="utf-8"))
    cases = [case for case in all_cases if case["id"] in wanted]
    if len(cases) != len(wanted):
        raise SystemExit(f"Unknown case ids: {sorted(set(wanted) - {case['id'] for case in cases})}")

    output = run / "reruns" / f"attempt_{args.attempt}"
    output.mkdir(parents=True, exist_ok=False)
    context = {**snapshot, "rerun_of": run.name, "attempt": args.attempt, "rerun_ids": wanted}
    (output / "run_snapshot.json").write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    cache = output / "answer_cache.json"
    generate_answers(cases, cache_path=cache, resume=False, checkpoint_context=context,
                     answer_config=snapshot["composer"]["config"])
    judged = judge_answers(cases, load_answer_checkpoint(cases, cache, checkpoint_context=context),
                           checkpoint_path=output / "judge_checkpoint.json", resume=False,
                           checkpoint_context=context)
    (output / "generated_answer_judge.json").write_text(json.dumps(judged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Reran {len(cases)} cases into {output}; judged {judged['summary']['judged_n']}", flush=True)


if __name__ == "__main__":
    main()
