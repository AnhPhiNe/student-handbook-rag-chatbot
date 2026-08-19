"""Judge frozen single-cohort-v2 answer rows with provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from tqdm import tqdm


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_single_cohort_v2 import (  # noqa: E402
    ANSWER_MODEL,
    JUDGE_MODEL,
    JUDGE_PROMPT_VERSION,
)
from src.evaluation.artifact_fingerprint import (  # noqa: E402
    release_artifact_fingerprint,
)
from src.evaluation.judge import GroqJudgeClient, compact_judge_packet  # noqa: E402
from src.evaluation.single_cohort_v2 import BUNDLE_DIR, validate_bundle  # noqa: E402


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _judge_case(case: Mapping[str, Any]) -> dict[str, Any]:
    expected = case.get("expected") or {}
    evidence = [
        request.get("expected_evidence") or {}
        for request in expected.get("atomic_requests") or []
        if request.get("request_kind") == "rag"
    ]
    structured_results = [
        request.get("expected_result")
        for request in expected.get("atomic_requests") or []
        if request.get("request_kind") == "structured"
        and request.get("expected_status") == "ok"
        and request.get("expected_result") is not None
    ]
    ground_truth_parts = [
        json.dumps(value, ensure_ascii=False, sort_keys=True)
        for value in structured_results
    ]
    ground_truth_parts.extend(
        excerpt
        for item in evidence
        for excerpt in item.get("evidence_excerpts") or []
        if excerpt
    )
    return {
        "id": case["id"],
        "query": case["query"],
        "cohort": expected.get("effective_cohort"),
        "answerability": "answerable" if expected.get("outcome") == "execute" else "unanswerable",
        "question_specificity": "specific",
        "expected_answer_behavior": (
            "direct_answer" if expected.get("outcome") == "execute" else "abstain"
        ),
        "ground_truth": "\n".join(ground_truth_parts)[:4000],
        "required_facts": [],
        "forbidden_claims": [],
        "expected_citations": [
            {
                "parent_section_id": binding.get("parent_section_id"),
                "document_id": binding.get("document_id"),
                "cohort": expected.get("effective_cohort"),
            }
            for item in evidence
            for binding in item.get("source_bindings") or []
        ],
    }


def _validated_answer_targets(
    answer_rows: Any,
    cases: Mapping[str, Mapping[str, Any]],
    *,
    split: str,
) -> tuple[list[str], dict[str, Mapping[str, Any]]]:
    if not isinstance(answer_rows, list):
        raise ValueError("Answer report must contain an answers list")
    answer_ids = [str(row.get("id") or "") for row in answer_rows]
    if any(not case_id for case_id in answer_ids):
        raise ValueError("Answer report contains a row without an id")
    if len(answer_ids) != len(set(answer_ids)):
        raise ValueError("Answer report contains duplicate case ids")
    unknown_ids = sorted(set(answer_ids) - set(cases))
    if unknown_ids:
        raise ValueError(f"Answer report contains ids outside {split}: {unknown_ids}")
    return answer_ids, {str(row["id"]): row for row in answer_rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--split", choices=("dev", "hidden"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--confirm-hidden-frozen", action="store_true")
    args = parser.parse_args()

    if args.split == "hidden" and not args.confirm_hidden_frozen:
        parser.error("Hidden judging requires --confirm-hidden-frozen.")

    validation = validate_bundle(require_gold_complete=True)
    if not validation.valid:
        raise SystemExit("Gold bundle is not ready: " + "; ".join(validation.errors))
    cases = {case["id"]: case for case in _load(BUNDLE_DIR / f"{args.split}.json")}
    answer_payload = _load(args.answers)
    if not isinstance(answer_payload, Mapping):
        raise ValueError("Answers input must be a commit-bound evaluation report")
    current_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if answer_payload.get("commit") != current_commit:
        raise ValueError("Answer report commit does not match the current commit")
    if answer_payload.get("dataset_hashes") != validation.hashes:
        raise ValueError("Answer report dataset hashes do not match the gold bundle")
    if answer_payload.get("artifact_fingerprint") != release_artifact_fingerprint(ROOT):
        raise ValueError("Answer report artifact fingerprint does not match current inputs")
    if (answer_payload.get("models") or {}).get("answer") != ANSWER_MODEL:
        raise ValueError("Answer report does not use the pinned answer model")
    answers_report_hash = hashlib.sha256(args.answers.read_bytes()).hexdigest()
    answer_rows = answer_payload.get("answers")
    answer_ids, answers = _validated_answer_targets(
        answer_rows,
        cases,
        split=args.split,
    )
    existing = _load(args.output) if args.resume and args.output.exists() else []
    if any(
        row.get("answer_model") != ANSWER_MODEL
        or row.get("judge_model") != JUDGE_MODEL
        or row.get("judge_prompt_version") != JUDGE_PROMPT_VERSION
        or row.get("answers_report_hash") != answers_report_hash
        for row in existing
    ):
        raise ValueError("Resume judgments do not match the current frozen provenance")
    if any(str(row.get("id") or "") not in answers for row in existing):
        raise ValueError("Resume judgments contain ids outside the supplied answer rows")
    judged = {row["id"]: row for row in existing}
    client = GroqJudgeClient()
    if client.config.model_name != JUDGE_MODEL:
        raise ValueError(
            f"Judge model must be {JUDGE_MODEL}, got {client.config.model_name}"
        )

    # Answer quality is conditional on a correctly planned request. Planner failures
    # remain in exact-plan metrics and must not be relabeled as answer-provider errors.
    for case_id in tqdm(answer_ids, desc="Judge", unit="case", dynamic_ncols=True):
        case = cases[case_id]
        if case_id in judged:
            continue
        answer = answers[case_id]
        if answer.get("model_used") not in {None, ANSWER_MODEL}:
            raise ValueError(f"Wrong answer model for {case_id}: {answer.get('model_used')}")
        result = client.judge(compact_judge_packet(_judge_case(case), answer))
        scores = result.get("scores") or {}
        judged[case_id] = {
            "id": case_id,
            "answer_model": ANSWER_MODEL,
            "judge_model": JUDGE_MODEL,
            "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "answers_report_hash": answers_report_hash,
            "faithfulness": float(scores.get("faithfulness") or 0.0),
            "answer_correctness": float(scores.get("answer_correctness") or 0.0),
            "hallucination": float(bool(scores.get("unsupported_claim"))),
            "critical_false_pass": bool(scores.get("critical_false_pass")),
            "provider_failure": not bool(result.get("ok")),
            "judge_result": result,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                [judged[target_id] for target_id in answer_ids if target_id in judged],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps([judged[target_id] for target_id in answer_ids], ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
