"""Regrade saved deterministic execution without model calls or runtime changes."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.prepare_official_eval import ROOT, BUNDLE
from src.evaluation.deterministic import evaluate_deterministic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    saved = json.loads(args.source.read_text(encoding="utf-8"))
    cases = json.loads((BUNDLE / "deterministic_tool_cases.json").read_text(encoding="utf-8"))
    rows = saved["cases"]
    assert len(rows) == len(cases) == 135
    for case, row in zip(cases, rows):
        assert case["id"] == row["id"] and case["query"] == row["query"]
        assert case["cohort"] == row["cohort"] and case["history"] == row["history"]
        assert "error" not in row

    class SavedExecution:
        def __init__(self):
            self.index = 0

        def _run_retrieval(self, query, cohort=None, **kwargs):
            row = rows[self.index]
            self.index += 1
            assert row["query"] == query and row["cohort"] == cohort
            result = {key: row[key] for key in ("query_plan", "task_results", "structured_result", "citations")}
            # Saved reports retain the plan and execution envelopes, including
            # per-task clarification. No status is fabricated from gold.
            return result

    report = evaluate_deterministic(cases, pipeline_factory=SavedExecution,
                                     evaluation_contract="query-plan-grounded-outcome-v9")
    for row, previous in zip(report["cases"], rows):
        row["latency_ms"] = previous["latency_ms"]
    report["provenance"] = {
        "method": "offline regrade of saved live execution; no new inference",
        "source": args.source.relative_to(ROOT).as_posix(),
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "runtime_snapshot": saved["run_snapshot"],
        "runtime_hashes_matched_after_live_run": saved["post_run_hashes_match"],
        "grading_hashes": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in [BUNDLE / "deterministic_tool_cases.json", Path(__file__),
                                     *ROOT.glob("src/evaluation/*.py")]},
    }
    target = args.source.with_name("deterministic_regraded.json")
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
