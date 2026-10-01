"""Judge every answer of a finished answers run again, without regenerating it.

    STUDENT_RAG_JUDGE_PROVIDER=deepinfra python -m scripts.rejudge_run \
        --run data/eval/reports/official_v4_answers_20260930T152637Z

Answers from rerun attempts replace the first-run answers, as in the report.
The result goes to <run>/judge_<provider>/ and is read with
`python -m scripts.report_v4_run --run <run>/judge_<provider>` (no --reruns).
Compare two runs only when both were judged by the same provider.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def merged_answers(run: Path) -> list[dict]:
    answers = {row["id"]: row for row in json.loads((run / "answer_cache.json").read_text(encoding="utf-8"))}
    for attempt in sorted((run / "reruns").glob("attempt_*")):
        cache = attempt / "answer_cache.json"
        if "INVALID" in attempt.name or not cache.exists():
            continue
        for row in json.loads(cache.read_text(encoding="utf-8")):
            answers[row["id"]] = row
    return list(answers.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    from src.common.env_loader import load_project_env

    load_project_env()
    from src.evaluation.answers import judge_answers

    provider = os.environ.get("STUDENT_RAG_JUDGE_PROVIDER") or "groq"
    run = ROOT / args.run
    out = run / f"judge_{provider}"
    out.mkdir(exist_ok=True)
    snapshot = json.loads((run / "run_snapshot.json").read_text(encoding="utf-8"))
    cases = json.loads((ROOT / snapshot["dataset"]).read_text(encoding="utf-8"))
    context = {**snapshot, "rejudge_of": run.name, "judge_provider": provider}
    (out / "run_snapshot.json").write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    judged = judge_answers(cases, merged_answers(run), checkpoint_path=out / "judge_checkpoint.json",
                           resume=True, checkpoint_context=context)
    (out / "generated_answer_judge.json").write_text(json.dumps(judged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(judged["summary"], ensure_ascii=False)[:600], flush=True)


if __name__ == "__main__":
    main()
