from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_LABELS = [
    "judge_false_positive",
    "minor_unsupported",
    "material_hallucination",
    "critical_false_pass",
    "clean_control",
    "judge_false_negative",
    "incorrect_abstention",
]
ALLOWED_SEVERITIES = ["none", "minor", "material", "critical"]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index_by_id(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row["id"]): dict(row)
        for row in rows
        if isinstance(row, Mapping) and row.get("id")
    }


def build_human_decision_template(
    queue: list[dict[str, Any]],
    *,
    queue_sha256: str,
    commit: str,
) -> dict[str, Any]:
    return {
        "audit_protocol_version": "single-cohort-dev-answer-human-audit-v1",
        "commit": commit,
        "queue_sha256": queue_sha256,
        "status": "pending_human_review",
        "reviewer": None,
        "reviewed_at": None,
        "allowed_labels": ALLOWED_LABELS,
        "allowed_severities": ALLOWED_SEVERITIES,
        "reviews": [
            {
                "id": row["id"],
                "selection_group": row.get("selection_group"),
                "label": None,
                "severity": None,
                "unsupported_claims": [],
                "supported_but_omitted_claims": [],
                "answers_user_need": None,
                "production_impact": None,
                "recommended_layer": None,
                "notes": None,
            }
            for row in queue
        ],
    }


def _request_citations(
    answer: Mapping[str, Any], request_id: str
) -> list[dict[str, Any]]:
    citations = [
        dict(item)
        for item in answer.get("citations") or []
        if isinstance(item, Mapping) and item.get("request_id") == request_id
    ]
    return sorted(
        citations,
        key=lambda item: int(item.get("request_retrieval_rank") or 10_000),
    )


def _gold_rank(
    citations: list[dict[str, Any]], expected_evidence: Mapping[str, Any]
) -> int | None:
    expected_parents = {
        str(value) for value in expected_evidence.get("parent_section_ids") or []
    }
    expected_chunks = {
        str(value) for value in expected_evidence.get("chunk_ids") or []
    }
    for fallback_rank, citation in enumerate(citations[:5], start=1):
        rank = int(citation.get("request_retrieval_rank") or fallback_rank)
        parent_id = str(
            citation.get("parent_section_id")
            or citation.get("source_parent_id")
            or ""
        )
        chunk_id = str(citation.get("chunk_id") or "")
        if parent_id in expected_parents or chunk_id in expected_chunks:
            return rank
    return None


def _citation_summary(citation: Mapping[str, Any], fallback_rank: int) -> dict[str, Any]:
    score_fields = {
        key: citation.get(key)
        for key in (
            "score",
            "dense_score",
            "sparse_score",
            "fused_score",
            "semantic_score",
            "selection_method",
            "child_source",
        )
        if citation.get(key) is not None
    }
    return {
        "rank": int(citation.get("request_retrieval_rank") or fallback_rank),
        "chunk_id": citation.get("chunk_id"),
        "parent_section_id": citation.get("parent_section_id")
        or citation.get("source_parent_id"),
        "document_id": citation.get("document_id"),
        "cohort": citation.get("cohort") or citation.get("request_cohort"),
        "title": citation.get("title"),
        "source_pages": citation.get("source_pages") or [],
        "content_preview": str(citation.get("content") or "")[:900],
        "retrieval_provenance": score_fields,
    }


def build_rank5_technical_audit(
    cases: list[dict[str, Any]],
    answers: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
    *,
    commit: str,
) -> dict[str, Any]:
    answer_by_id = _index_by_id(answers)
    judgment_by_id = _index_by_id(judgments)
    rows: list[dict[str, Any]] = []
    rank_distribution: dict[str, int] = {}

    for case in cases:
        answer = answer_by_id.get(str(case.get("id") or ""), {})
        for request in (case.get("expected") or {}).get("atomic_requests") or []:
            if (
                request.get("request_kind") != "rag"
                or request.get("expected_status") != "ok"
            ):
                continue
            request_id = str(request.get("request_id") or "")
            citations = _request_citations(answer, request_id)
            expected_evidence = request.get("expected_evidence") or {}
            rank = _gold_rank(citations, expected_evidence)
            rank_distribution[str(rank)] = rank_distribution.get(str(rank), 0) + 1
            if rank != 5:
                continue
            judgment = judgment_by_id.get(str(case.get("id") or ""), {})
            rows.append(
                {
                    "id": case.get("id"),
                    "category": case.get("category"),
                    "request_id": request_id,
                    "query": case.get("query"),
                    "query_span": request.get("query_span"),
                    "effective_cohort": (case.get("expected") or {}).get(
                        "effective_cohort"
                    ),
                    "gold_rank": rank,
                    "gold": {
                        "document_ids": expected_evidence.get("document_ids") or [],
                        "parent_section_ids": expected_evidence.get(
                            "parent_section_ids"
                        )
                        or [],
                        "chunk_ids": expected_evidence.get("chunk_ids") or [],
                        "source_pages": expected_evidence.get("source_pages") or [],
                        "relevance_grade": expected_evidence.get("relevance_grade"),
                        "evidence_excerpts": expected_evidence.get(
                            "evidence_excerpts"
                        )
                        or [],
                    },
                    "top5_candidates": [
                        _citation_summary(citation, index)
                        for index, citation in enumerate(citations[:5], start=1)
                    ],
                    "answer": answer.get("answer"),
                    "answer_status": answer.get("status"),
                    "judge": {
                        "hallucination": judgment.get("hallucination"),
                        "faithfulness": judgment.get("faithfulness"),
                        "answer_correctness": judgment.get("answer_correctness"),
                        "critical_false_pass": judgment.get(
                            "critical_false_pass"
                        ),
                        "rationale": (judgment.get("judge_result") or {}).get(
                            "rationale"
                        ),
                    },
                    "technical_review": {
                        "gold_is_directly_relevant": None,
                        "higher_ranked_candidates_are_directly_relevant": None,
                        "gold_needed_for_answer": None,
                        "safe_to_filter_before_composer": None,
                        "proposed_evidence_policy_signal": None,
                        "reviewer_notes": None,
                    },
                }
            )

    return {
        "audit_protocol_version": "single-cohort-rank5-technical-audit-v1",
        "commit": commit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rank_definition": (
            "First request-scoped runtime citation among ranks 1..5 whose "
            "parent_section_id or chunk_id matches human-approved gold."
        ),
        "rank_distribution": rank_distribution,
        "rank5_count": len(rows),
        "rows": rows,
    }


def _render_rank5_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Technical audit: RAG gold at rank 5",
        "",
        f"- Commit: `{report.get('commit')}`",
        f"- Rank-5 requests: `{report.get('rank5_count')}`",
        f"- Rank distribution: `{json.dumps(report.get('rank_distribution'), ensure_ascii=False)}`",
        "",
        "This report is diagnostic. Do not edit gold labels here and do not use hidden cases.",
        "",
    ]
    for row in report.get("rows") or []:
        lines.extend(
            [
                f"## {row['id']} / {row['request_id']}",
                "",
                f"- Query: {row.get('query')}",
                f"- Query span: `{row.get('query_span')}`",
                f"- Cohort: `{row.get('effective_cohort')}`",
                f"- Gold parents: `{row['gold'].get('parent_section_ids')}`",
                "",
                "| Rank | Parent section | Title | Pages |",
                "|---:|---|---|---|",
            ]
        )
        for candidate in row.get("top5_candidates") or []:
            lines.append(
                "| {rank} | `{parent}` | {title} | {pages} |".format(
                    rank=candidate.get("rank"),
                    parent=candidate.get("parent_section_id"),
                    title=str(candidate.get("title") or "").replace("|", "\\|"),
                    pages=candidate.get("source_pages"),
                )
            )
        lines.extend(["", "Review the full content/provenance in the JSON artifact.", ""])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the frozen dev answer human-audit and rank-5 technical-audit artifacts."
    )
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = _load_json(args.cases)
    answers_report = _load_json(args.answers)
    answers = answers_report.get("answers") or []
    judgments = _load_json(args.judgments)
    queue = _load_json(args.queue)

    if not isinstance(cases, list) or not isinstance(answers, list):
        raise ValueError("Cases and answer rows must be JSON lists.")
    if not isinstance(judgments, list) or not isinstance(queue, list):
        raise ValueError("Judgments and human-audit queue must be JSON lists.")
    if len(queue) != 30:
        raise ValueError(f"Expected 30 human-audit rows, found {len(queue)}.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    decisions = build_human_decision_template(
        queue,
        queue_sha256=_sha256(args.queue),
        commit=args.commit,
    )
    rank5 = build_rank5_technical_audit(
        cases,
        answers,
        judgments,
        commit=args.commit,
    )
    if rank5["rank5_count"] != 6:
        raise ValueError(
            "Rank-5 audit is fail-closed: expected 6 requests for this frozen run, "
            f"found {rank5['rank5_count']}."
        )

    (args.output_dir / "dev_answer_human_audit_decisions.json").write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "dev_rank5_technical_audit.json").write_text(
        json.dumps(rank5, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "dev_rank5_technical_audit.md").write_text(
        _render_rank5_markdown(rank5),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "human_review_rows": len(decisions["reviews"]),
                "rank5_rows": rank5["rank5_count"],
                "output_dir": str(args.output_dir),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
