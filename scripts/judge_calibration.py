"""Compare a second rater's scores with the judge's answer_correctness on a run.

    python -m scripts.judge_calibration --run <answers run directory> \
        --scores data/eval/official_v4/judge_calibration/my_scores.tsv \
        --sample data/eval/official_v4/judge_calibration/sample.json

The sample holds every answer the judge scored below 1.0 and a seeded random
draw of those it scored 1.0; the estimate over the whole run reweights the
draw by its stratum size. A rater label C means the student got a correct
answer to what was asked; I is incomplete; W states something false.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from pathlib import Path

from scripts.report_v4_run import load_rows, score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--scores", required=True)
    parser.add_argument("--sample", required=True)
    args = parser.parse_args()

    rows = {row["id"]: row for row in load_rows(Path(args.run), True)[0]}
    sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    rater = {r["id"]: r for r in csv.DictReader(open(args.scores, encoding="utf-8"), delimiter="\t")}
    low_ids = set(sample["strata"]["judge_below_1"])
    pairs = [(score(rows[i]), float(r["score"]), r["label"], i) for i, r in rater.items()]
    low = [p for p in pairs if p[3] in low_ids]
    top = [p for p in pairs if p[3] not in low_ids]
    n_top = sum(1 for row in rows.values() if score(row) == 1.0)

    def describe(group):
        diffs = [judge - mine for judge, mine, _, _ in group]
        return {
            "n": len(group),
            "judge_mean": round(st.mean(p[0] for p in group), 3),
            "rater_mean": round(st.mean(p[1] for p in group), 3),
            "mean_judge_minus_rater": round(st.mean(diffs), 3),
            "within_0_25": sum(abs(d) <= 0.25 for d in diffs),
        }

    passes = {}
    for threshold in (0.8, 1.0):
        passes[f"judge>={threshold}"] = {
            "both_pass": sum(j >= threshold and lab == "C" for j, _, lab, _ in pairs),
            "judge_only": sorted(i for j, _, lab, i in pairs if j >= threshold and lab != "C"),
            "rater_only": sorted(i for j, _, lab, i in pairs if j < threshold and lab == "C"),
            "neither": sum(j < threshold and lab != "C" for j, _, lab, _ in pairs),
        }
    report = {
        "judge_below_1": describe(low),
        "judge_1_sample": describe(top),
        "run_mean": {
            "judge": round(st.mean(score(row) for row in rows.values()), 3),
            "rater_estimate": round(
                (sum(p[1] for p in low) + n_top * st.mean(p[1] for p in top)) / len(rows), 3
            ),
        },
        "pass_agreement": passes,
        "rater_labels": {lab: sum(p[2] == lab for p in pairs) for lab in ("C", "I", "W")},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
