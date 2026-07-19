from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


LOW_FAITHFULNESS_THRESHOLD = 0.75
LOW_CORRECTNESS_THRESHOLD = 0.75
LOW_CITATION_THRESHOLD = 0.8
LONG_ANSWER_CHARS = 2500


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_answer_failure_audit(
    *,
    cases_path: Path,
    answers_path: Path,
    judge_path: Path,
) -> dict[str, Any]:
    cases = _index_by_id(load_json(cases_path))
    answers = _index_by_id(load_json(answers_path))
    judge_report = load_json(judge_path)
    judged_cases = judge_report.get("cases") or []

    category_counts: Counter[str] = Counter()
    by_topic: dict[str, Counter[str]] = defaultdict(Counter)
    by_case_type: dict[str, Counter[str]] = defaultdict(Counter)
    by_split: dict[str, Counter[str]] = defaultdict(Counter)
    audited_cases: list[dict[str, Any]] = []

    for judged in judged_cases:
        case_id = str(judged.get("id") or "")
        case = cases.get(case_id, {})
        answer_record = answers.get(case_id, {})
        judge = judged.get("judge") or {}
        scores = judge.get("scores") or {}
        answer = str(answer_record.get("answer") or judged.get("answer") or "")
        categories = _case_failure_categories(scores, answer)

        for category in categories:
            category_counts[category] += 1
            by_topic[str(judged.get("topic") or case.get("topic") or "unknown")][
                category
            ] += 1
            by_case_type[
                str(judged.get("case_type") or case.get("case_type") or "unknown")
            ][category] += 1
            by_split[
                str(judged.get("eval_split") or case.get("eval_split") or "unknown")
            ][category] += 1

        audited_cases.append(
            {
                "id": case_id,
                "query": answer_record.get("query") or case.get("query"),
                "topic": judged.get("topic") or case.get("topic"),
                "case_type": judged.get("case_type") or case.get("case_type"),
                "eval_split": judged.get("eval_split") or case.get("eval_split"),
                "question_style": judged.get("question_style")
                or case.get("question_style"),
                "answer_chars": len(answer),
                "categories": categories,
                "scores": {
                    "faithfulness": scores.get("faithfulness"),
                    "answer_correctness": scores.get("answer_correctness"),
                    "citation_correctness": scores.get("citation_correctness"),
                    "context_precision": scores.get("context_precision"),
                    "context_recall": scores.get("context_recall"),
                    "unsupported_claim": scores.get("unsupported_claim"),
                    "critical_false_pass": scores.get("critical_false_pass"),
                    "required_fact_hit": judged.get("required_fact_hit"),
                    "numeric_accuracy": judged.get("numeric_accuracy"),
                    "abstention_correct": judged.get("abstention_correct"),
                },
                "rationale": scores.get("rationale"),
                "answer_preview": answer[:700],
            }
        )

    return {
        "summary": {
            "n": len(judged_cases),
            "categories": dict(category_counts),
            "by_topic": _nested_counter_to_dict(by_topic),
            "by_case_type": _nested_counter_to_dict(by_case_type),
            "by_split": _nested_counter_to_dict(by_split),
            "source_summary": judge_report.get("summary") or {},
        },
        "cases": sorted(
            audited_cases,
            key=lambda item: (
                -len(item["categories"]),
                item["scores"].get("faithfulness") or 1.0,
                item["id"],
            ),
        ),
    }


def build_human_audit_sample(
    *,
    cases_path: Path,
    answers_path: Path,
    judge_path: Path,
    low_count: int = 20,
    random_count: int = 10,
    seed: int = 84,
) -> list[dict[str, Any]]:
    """Select low-scoring and deterministic-random cases for manual review."""
    cases = _index_by_id(load_json(cases_path))
    answers = _index_by_id(load_json(answers_path))
    judge_report = load_json(judge_path)
    judged = _index_by_id(judge_report)
    failure_audit = build_answer_failure_audit(
        cases_path=cases_path,
        answers_path=answers_path,
        judge_path=judge_path,
    )

    low_candidates = [
        item
        for item in failure_audit["cases"]
        if item.get("categories") != ["pass_or_minor"]
    ]
    low_selected = low_candidates[: max(0, low_count)]
    selected_ids = {str(item["id"]) for item in low_selected}
    remaining_ids = sorted(set(judged) - selected_ids)
    rng = random.Random(seed)
    random_selected_ids = rng.sample(
        remaining_ids,
        min(max(0, random_count), len(remaining_ids)),
    )

    selection = [
        ("low_score", str(item["id"]))
        for item in low_selected
    ] + [("random", case_id) for case_id in random_selected_ids]
    packet: list[dict[str, Any]] = []
    for selection_group, case_id in selection:
        case = cases.get(case_id, {})
        answer = answers.get(case_id, {})
        judged_case = judged.get(case_id, {})
        scores = ((judged_case.get("judge") or {}).get("scores") or {})
        packet.append(
            {
                "id": case_id,
                "selection_group": selection_group,
                "query": answer.get("query") or case.get("query"),
                "cohort": case.get("cohort"),
                "case_type": case.get("case_type"),
                "topic": case.get("topic"),
                "eval_split": case.get("eval_split"),
                "question_style": case.get("question_style"),
                "ground_truth": case.get("ground_truth"),
                "required_facts": case.get("required_facts") or [],
                "forbidden_claims": case.get("forbidden_claims") or [],
                "expected_citations": case.get("expected_citations") or [],
                "answer": answer.get("answer"),
                "citations": answer.get("citations") or [],
                "context_used": answer.get("context_used"),
                "judge_scores": scores,
                "judge_rationale": scores.get("rationale"),
                "human_correctness": None,
                "human_faithfulness": None,
                "human_citation_correctness": None,
                "human_unsupported_claim": None,
                "critical_false_pass": None,
                "notes": "",
            }
        )
    return packet


def _index_by_id(records: Any) -> dict[str, dict[str, Any]]:
    if isinstance(records, dict) and isinstance(records.get("cases"), list):
        records = records["cases"]
    if not isinstance(records, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        if isinstance(record, dict) and record.get("id"):
            indexed[str(record["id"])] = record
    return indexed


def _case_failure_categories(scores: dict[str, Any], answer: str) -> list[str]:
    categories: list[str] = []
    if bool(scores.get("unsupported_claim")):
        categories.append("unsupported_claim")
    if bool(scores.get("critical_false_pass")):
        categories.append("critical_false_pass")
    if _score(scores.get("faithfulness")) < LOW_FAITHFULNESS_THRESHOLD:
        categories.append("low_faithfulness")
    if _score(scores.get("answer_correctness")) < LOW_CORRECTNESS_THRESHOLD:
        categories.append("low_correctness")
    if _score(scores.get("citation_correctness")) < LOW_CITATION_THRESHOLD:
        categories.append("low_citation")
    if len(answer) > LONG_ANSWER_CHARS:
        categories.append("long_answer")
    return categories or ["pass_or_minor"]


def _score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _nested_counter_to_dict(data: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {key: dict(counter) for key, counter in sorted(data.items())}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an offline failure audit from V8 answer and judge reports."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("data/eval/v8_4_holdout/generated_answer_cases.json"),
    )
    parser.add_argument(
        "--answers",
        type=Path,
        default=Path("data/eval/reports/v8_4_holdout/answer_cache_full.json"),
    )
    parser.add_argument(
        "--judge",
        type=Path,
        default=Path("data/eval/reports/v8_4_holdout/generated_answer_judge_full.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/eval/reports/v8_4_holdout/answer_failure_audit.json"),
    )
    parser.add_argument("--human-audit-output", type=Path, default=None)
    parser.add_argument("--low-count", type=int, default=20)
    parser.add_argument("--random-count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=84)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_answer_failure_audit(
        cases_path=args.cases,
        answers_path=args.answers,
        judge_path=args.judge,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(f"Wrote answer failure audit: {args.output}")
    if args.human_audit_output is not None:
        packet = build_human_audit_sample(
            cases_path=args.cases,
            answers_path=args.answers,
            judge_path=args.judge,
            low_count=args.low_count,
            random_count=args.random_count,
            seed=args.seed,
        )
        args.human_audit_output.parent.mkdir(parents=True, exist_ok=True)
        args.human_audit_output.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote human audit packet: {args.human_audit_output}")


if __name__ == "__main__":
    main()
