"""Break an official suite report down by slice, cohort and question style.

Deterministic reports score each case pass/fail, with a Wilson 95% interval. Judge
reports average one judge score per case (default `answer_correctness`), with a
bootstrap 95% interval. Report rows are joined to the bundle's case file by id, to read
each case's slice (`slice` in official_v2, `category` in official_v1), cohort and style.

A slice is named `family.detail`, for example `memory.cohort_switch`. If the bundle has
a `slice_weights.yaml` mapping families to their expected share of real questions, the
overall score is also reported reweighted to that mix.

    python -m scripts.report_official_slices data/eval/reports/<run>/deterministic.json
    python -m scripts.report_official_slices <run>/generated_answer_judge.json --metric faithfulness
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.metrics import bootstrap_mean_ci, wilson_interval  # noqa: E402

CASE_FILES = {"deterministic": "deterministic_tool_cases.json", "judge": "generated_answer_cases.json"}


def case_score(row: dict, suite: str, metric: str) -> float | None:
    if suite == "deterministic":
        return 1.0 if row.get("passed") else 0.0
    score = ((row.get("judge") or {}).get("scores") or {}).get(metric)
    return None if score is None else float(score)


def summarize(values: list[float], suite: str) -> dict:
    n = len(values)
    mean = sum(values) / n if n else None
    if suite == "deterministic":
        interval = wilson_interval(int(sum(values)), n)
    else:
        interval = bootstrap_mean_ci(values)
    return {"n": n, "mean": mean, "low": interval["low"], "high": interval["high"]}


def slice_of(case: dict) -> str:
    return str(case.get("slice") or case.get("category") or "unlabelled")


def breakdown(report: dict, cases: dict[str, dict], metric: str) -> dict:
    suite = report.get("suite")
    groups: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in report.get("cases") or []:
        case = cases.get(row.get("id"), {})
        score = case_score(row, suite, metric)
        if score is None:
            continue
        name = slice_of(case)
        keys = {
            "overall": "all",
            "family": name.split(".", 1)[0],
            "slice": name,
            "cohort": str(case.get("cohort") or "unknown"),
            "style": str(case.get("question_style") or "unknown"),
            "history": "with history" if case.get("history") else "no history",
        }
        for dimension, key in keys.items():
            groups[dimension][key].append(score)
    return {
        dimension: {key: summarize(values, suite) for key, values in sorted(by_key.items())}
        for dimension, by_key in groups.items()
    }


def reweighted(family_scores: dict[str, dict], weights: dict[str, float]) -> float | None:
    """Mean over families weighted by their expected share of real questions."""

    present = {name: w for name, w in weights.items() if name in family_scores and w > 0}
    total = sum(present.values())
    if not total:
        return None
    return sum(family_scores[name]["mean"] * w for name, w in present.items()) / total


def render(result: dict, title: str, weighted: float | None) -> str:
    def pct(value):
        return "—" if value is None else f"{100 * value:.1f}"

    lines = [f"## {title}", ""]
    overall = result["overall"]["all"]
    lines.append(f"Overall: {pct(overall['mean'])} (95% CI {pct(overall['low'])}–{pct(overall['high'])}), n = {overall['n']}")
    if weighted is not None:
        lines.append(f"Reweighted to the expected real-question mix: {pct(weighted)}")
    for dimension in ("family", "slice", "cohort", "style", "history"):
        lines += ["", f"| {dimension} | n | score | 95% CI |", "|---|---:|---:|---|"]
        for key, stats in result.get(dimension, {}).items():
            lines.append(f"| {key} | {stats['n']} | {pct(stats['mean'])} | {pct(stats['low'])}–{pct(stats['high'])} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report", type=Path)
    parser.add_argument("--bundle", help="Folder under data/eval; defaults to the run snapshot's bundle.")
    parser.add_argument("--metric", default="answer_correctness", help="Judge score to average.")
    parser.add_argument("--json", action="store_true", help="Print the breakdown as JSON.")
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    suite = report.get("suite")
    if suite not in CASE_FILES:
        raise SystemExit(f"Unsupported report suite: {suite!r}")
    bundle_name = args.bundle or (report.get("run_snapshot") or {}).get("bundle") or "official_v1"
    bundle = ROOT / "data/eval" / bundle_name
    cases = {c["id"]: c for c in json.loads((bundle / CASE_FILES[suite]).read_text(encoding="utf-8"))}
    result = breakdown(report, cases, args.metric)
    weights_path = bundle / "slice_weights.yaml"
    weights = yaml.safe_load(weights_path.read_text(encoding="utf-8")) if weights_path.exists() else {}
    weighted = reweighted(result.get("family", {}), weights or {})
    if args.json:
        print(json.dumps({"bundle": bundle_name, "suite": suite, "reweighted": weighted, **result}, indent=2))
        return
    metric = "pass rate" if suite == "deterministic" else args.metric
    print(render(result, f"{bundle_name} · {suite} · {metric}", weighted))


if __name__ == "__main__":
    main()
