"""Replay the composer on an earlier answers run's evidence packets, then judge.

Only the composer runs: planning and retrieval come from the source run, so a
prompt or model change is measured on identical evidence. See
src/evaluation/composer_replay.py for what is reproduced and its one
approximation.

    python -m scripts.replay_composer --source data/eval/reports/official_v1_answers_<stamp> \
        --answer-config configs/experiments/answer_deepseek_low.yaml
"""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.prepare_official_eval import ROOT


def _write(report: dict, path: Path) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report.get("summary", {}), ensure_ascii=False, indent=2)[:3000], flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Earlier answers run directory to replay.")
    parser.add_argument("--answer-config", default="configs/answer_generation.yaml",
                        help="Composer config for the replay.")
    parser.add_argument("--limit", type=int, help="Replay only the first N cases.")
    parser.add_argument("--output", help="Resume an interrupted replay in this directory.")
    args = parser.parse_args()

    from src.common.env_loader import load_project_env
    load_project_env()
    from src.evaluation.answers import judge_answers, load_answer_checkpoint
    from src.evaluation.composer_replay import replay_answers
    from src.generation.answer_pipeline import create_composer_client
    from src.generation.prompt_builder import ANSWER_PROMPT_VERSION

    source = ROOT / args.source
    source_snapshot = json.loads((source / "run_snapshot.json").read_text(encoding="utf-8"))
    case_path = ROOT / source_snapshot["dataset"]
    if hashlib.sha256(case_path.read_bytes()).hexdigest() != source_snapshot["dataset_sha256"]:
        raise ValueError("Dataset changed since the source run; replay would not be paired")
    cases = json.loads(case_path.read_text(encoding="utf-8"))
    # Verifies the recorded answers belong to that source run and dataset.
    source_rows = load_answer_checkpoint(cases, source / "answer_cache.json",
                                         checkpoint_context=source_snapshot)
    answer_config = yaml.safe_load((ROOT / args.answer_config).read_text(encoding="utf-8"))
    llm = answer_config["llm"]

    resume = bool(args.output)
    if resume:
        output = ROOT / args.output
        snapshot = json.loads((output / "run_snapshot.json").read_text(encoding="utf-8"))
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bundle = Path(source_snapshot["dataset"]).parent.name
        smoke = f"_smoke{args.limit}" if args.limit else ""
        output = ROOT / "data/eval/reports" / f"{bundle}_composer_replay{smoke}_{stamp}"
        output.mkdir(parents=True, exist_ok=False)
        snapshot = {
            "suite": "composer_replay",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "git_dirty": bool(subprocess.check_output(
                ["git", "status", "--porcelain", "--", "src", "configs", "scripts"], cwd=ROOT, text=True).strip()),
            "dataset": source_snapshot["dataset"],
            "dataset_sha256": source_snapshot["dataset_sha256"],
            "source_run": Path(args.source).as_posix(),
            "planner": source_snapshot.get("planner"),
            "retrieval": "evidence packets replayed from source_run",
            "composer": {"provider": llm.get("provider"), "model": llm.get("model_name"),
                         "reasoning_effort": llm.get("reasoning_effort"),
                         "config": Path(args.answer_config).as_posix(),
                         "prompt_version": ANSWER_PROMPT_VERSION},
            "limit": args.limit,
        }
        (output / "run_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
    print(f"Output: {output}", flush=True)

    answer_cache = output / "answer_cache.json"
    generation = replay_answers(
        cases, source_rows, client=create_composer_client(llm), cache_path=answer_cache,
        resume=resume, limit=snapshot["limit"], checkpoint_context=snapshot,
        public_max_sources=int((answer_config.get("citations") or {}).get("public_max_sources", 10)),
    )
    generation.pop("rows", None)
    generation["run_snapshot"] = snapshot
    _write(generation, output / "answer_generation.json")
    judged = judge_answers(cases, load_answer_checkpoint(cases, answer_cache, checkpoint_context=snapshot),
                           checkpoint_path=output / "judge_checkpoint.json", resume=resume,
                           limit=snapshot["limit"], checkpoint_context=snapshot)
    judged["run_snapshot"] = snapshot
    _write(judged, output / "generated_answer_judge.json")


if __name__ == "__main__":
    main()
