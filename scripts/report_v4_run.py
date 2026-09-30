"""Report one official_v4 run against the metrics fixed before it (SPEC.md).

Headline: mean `answer_correctness` over the 246 cases, with a 95% interval
bootstrapped over the 229 clusters, because near-duplicate cases do not carry
independent information. Secondary and descriptive figures follow the same
document. Reruns of individual cases replace their first-run rows.

    python -m scripts.report_v4_run --run <run directory> [--reruns]
"""
import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data/eval/official_v4/generated_answer_cases.json"
FAMILIES_REPORTED_ALONE = 24  # SPEC: families of 24 or more get their own figure


def cluster_ci(values_by_cluster: dict[str, list[float]], rounds: int = 10_000) -> tuple[float, float]:
    """Resample whole clusters, so 17 near-duplicate cases cannot narrow the interval."""

    clusters = list(values_by_cluster)
    if len(clusters) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(20260930)
    means = []
    for _ in range(rounds):
        drawn = [value for _ in clusters
                 for value in values_by_cluster[clusters[rng.randrange(len(clusters))]]]
        means.append(statistics.fmean(drawn))
    means.sort()
    return (means[int(0.025 * rounds)], means[int(0.975 * rounds)])


def load_rows(run: Path, use_reruns: bool) -> tuple[list[dict[str, Any]], list[str]]:
    rows = {row["id"]: row for row in
            json.loads((run / "generated_answer_judge.json").read_text(encoding="utf-8"))["cases"]}
    replaced: list[str] = []
    if use_reruns:
        for attempt in sorted((run / "reruns").glob("attempt_*")):
            if attempt.name.endswith("INVALID") or "INVALID" in attempt.name:
                continue
            path = attempt / "generated_answer_judge.json"
            if not path.exists():
                continue
            for row in json.loads(path.read_text(encoding="utf-8"))["cases"]:
                # A failed judge carries no score, so it never replaces a row
                # that has one: attempts are ordered by name, and a judge-only
                # retry may sort after the full rerun that already succeeded.
                if not (row.get("judge") or {}).get("ok") and score(rows.get(row["id"], {})) is not None:
                    continue
                rows[row["id"]] = row
                replaced.append(f"{row['id']}@{attempt.name}")
    return list(rows.values()), replaced


def score(row: dict[str, Any]) -> float | None:
    judge = row.get("judge") or {}
    return (judge.get("scores") or {}).get("answer_correctness") if judge.get("ok") else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--reruns", action="store_true", help="Let rerun attempts replace first-run rows.")
    parser.add_argument("--compare", help="A second run directory, reported case by case against --run.")
    args = parser.parse_args()

    cases = {case["id"]: case for case in json.loads(CASES.read_text(encoding="utf-8"))}
    run = Path(args.run)
    rows, replaced = load_rows(run, args.reruns)
    snapshot = json.loads((run / "run_snapshot.json").read_text(encoding="utf-8"))
    answers = json.loads((run / "answer_cache.json").read_text(encoding="utf-8"))

    integrity = {
        "commit": snapshot["git_commit"][:8], "tree_dirty": snapshot["git_dirty"],
        "reranker": snapshot["reranker"], "dataset_sha256": snapshot["dataset_sha256"][:16],
        "answers": len(answers), "exceptions": sum(a.get("status") == "exception" for a in answers),
        "judged": len(rows), "judge_failed": sum(1 for r in rows if score(r) is None),
        "cases_replaced_by_a_rerun": replaced,
    }
    scored = [(cases[r["id"]], s) for r in rows if (s := score(r)) is not None]
    by_cluster: dict[str, list[float]] = defaultdict(list)
    for case, value in scored:
        by_cluster[case["cluster"]].append(value)
    low, high = cluster_ci(by_cluster)

    def mean_of(predicate) -> dict[str, Any]:
        values = [v for c, v in scored if predicate(c)]
        return {"n": len(values), "mean": round(statistics.fmean(values), 3) if values else None}

    families = sorted({case["topic"] for case in cases.values()})
    report = {
        "integrity": integrity,
        "headline": {"metric": "answer_correctness", "n": len(scored),
                     "clusters": len(by_cluster),
                     "mean": round(statistics.fmean(v for _, v in scored), 3),
                     "ci95_over_clusters": [round(low, 3), round(high, 3)]},
        "secondary": {
            "by_family": {f: mean_of(lambda c, f=f: c["topic"] == f) for f in families
                          if sum(1 for c in cases.values() if c["topic"] == f) >= FAMILIES_REPORTED_ALONE},
            "hallucination_rate": round(statistics.fmean(
                float(bool(((r.get("judge") or {}).get("scores") or {}).get("unsupported_claim")))
                for r in rows if score(r) is not None), 3),
            "critical_false_passes": sum(
                bool(((r.get("judge") or {}).get("scores") or {}).get("critical_false_pass"))
                for r in rows if score(r) is not None),
        },
        "descriptive": {
            "small_families": {f: mean_of(lambda c, f=f: c["topic"] == f) for f in families
                               if sum(1 for c in cases.values() if c["topic"] == f) < FAMILIES_REPORTED_ALONE},
            "by_style": {s: mean_of(lambda c, s=s: c["question_style"] == s)
                         for s in sorted({c["question_style"] for c in cases.values()})},
            "by_expected_behavior": {b: mean_of(lambda c, b=b: c["expected_answer_behavior"] == b)
                                     for b in sorted({c["expected_answer_behavior"] for c in cases.values()})},
            "by_cell": {t: mean_of(lambda c, t=t: c["case_type"] == t)
                        for t in sorted({c["case_type"] for c in cases.values()})},
        },
    }

    if args.compare:
        other_rows, _ = load_rows(Path(args.compare), args.reruns)
        other = {r["id"]: score(r) for r in other_rows}
        moved = [{"id": c["id"], "family": c["topic"], "cell": c["case_type"],
                  "this_run": v, "other_run": other.get(c["id"])}
                 for c, v in scored if other.get(c["id"]) is not None and abs(other[c["id"]] - v) >= 0.25]
        report["compare"] = {
            "other_run": Path(args.compare).name,
            "better_here": sorted(m["id"] for m in moved if m["this_run"] > m["other_run"]),
            "worse_here": sorted(m["id"] for m in moved if m["this_run"] < m["other_run"]),
            "cases": moved,
        }

    (run / "v4_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    printable = {k: v for k, v in report.items() if k != "compare"}
    print(json.dumps(printable, ensure_ascii=False, indent=1))
    if "compare" in report:
        print(json.dumps({k: v for k, v in report["compare"].items() if k != "cases"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
