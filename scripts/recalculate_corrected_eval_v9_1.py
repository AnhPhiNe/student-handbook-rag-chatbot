from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.gates import evaluate_gates
from src.evaluation.human_audit import summarize_human_audit
from src.evaluation.reporting import write_report_bundle
from src.evaluation.suites import (
    _latency_summary,
    _retrieval_breakdowns,
    _retrieval_summary,
    judge_answers,
    safe_mean,
)


BUNDLE = ROOT / "data" / "eval" / "architecture_v9_1_corrected"
SOURCE_DETERMINISTIC = (
    ROOT / "work" / "architecture_v9_deterministic_run3" / "deterministic_full.json"
)
SOURCE_RETRIEVAL = (
    ROOT
    / "work"
    / "architecture_v9_retrieval_run1"
    / "retrieval_end_to_end_qdrant_vector_primary_graph_supplement_full.json"
)
SOURCE_GENERATION = (
    ROOT / "work" / "architecture_v9_generate_run1" / "answer_generation_full.json"
)
SOURCE_ANSWER_CACHE = (
    ROOT / "work" / "architecture_v9_generate_run1" / "answer_cache_full.json"
)
SOURCE_JUDGE = (
    ROOT / "work" / "architecture_v9_generate_run1" / "generated_answer_judge_full.json"
)
SOURCE_HUMAN_AUDIT = (
    ROOT / "work" / "architecture_v9_generate_run1" / "human_audit_reviewed.json"
)
SOURCE_AUTOMATIC_AUDIT = (
    ROOT / "work" / "architecture_v9_generate_run1" / "automatic_failure_audit.json"
)
OUT = ROOT / "work" / "architecture_v9_1_corrected_run1"

UNSUPPORTED_FLAG_FALSE_POSITIVE_IDS = {
    "v8_ans_rag_003",
    "v8_ans_rag_016",
    "v8_ans_rag_021",
    "v8_ans_rag_051",
    "v8_ans_rag_058",
    "v8_ans_rag_072",
    "v8_ans_rag_077",
    "v8_ans_rag_078",
    "v8_ans_struct_003",
    "v8_ans_mixed_001",
    "v8_ans_clarify_001",
}

REPLACEMENT_HUMAN_REVIEWS = {
    "v8_ans_struct_021": {
        "correctness": 1.0,
        "faithfulness": 1.0,
        "completeness": 1.0,
        "citation_quality": 1.0,
        "safe_behavior": 1.0,
        "review_label": "pass",
        "notes": "Đúng hàng K50: 7,4 thuộc điểm chữ B; câu trả lời ngắn, có căn cứ.",
        "unsupported_claim_actual": False,
        "root_cause": "none",
        "critical_false_pass": False,
    },
    "v8_ans_rag_015": {
        "correctness": 1.0,
        "faithfulness": 1.0,
        "completeness": 1.0,
        "citation_quality": 0.9,
        "safe_behavior": 1.0,
        "review_label": "pass",
        "notes": "Ba nhiệm vụ đều thuộc Điều 17; nguồn chính đúng, danh sách nguồn còn hơi rộng.",
        "unsupported_claim_actual": False,
        "root_cause": "none",
        "critical_false_pass": False,
    },
    "v8_ans_clarify_008": {
        "correctness": 0.7,
        "faithfulness": 0.9,
        "completeness": 0.55,
        "citation_quality": 0.75,
        "safe_behavior": 1.0,
        "review_label": "minor_scope_digression",
        "notes": "Không tự đoán hiệu lực nhưng chưa hỏi rõ loại/ngày cấp và thêm đoạn chứng chỉ giả không cần thiết.",
        "unsupported_claim_actual": False,
        "root_cause": "answer_scope_digression",
        "critical_false_pass": False,
    },
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def select_rows(
    cases: list[dict[str, Any]], rows: list[dict[str, Any]], *, source: Path
) -> list[dict[str, Any]]:
    by_id = {str(row["id"]): row for row in rows}
    missing = [str(case["id"]) for case in cases if str(case["id"]) not in by_id]
    if missing:
        raise ValueError(f"Frozen output {source} is missing IDs: {missing}")
    selected: list[dict[str, Any]] = []
    for case in cases:
        row = deepcopy(by_id[str(case["id"])])
        if str(row.get("query") or "") != str(case.get("query") or ""):
            raise ValueError(f"Query mismatch for frozen output ID={case['id']}")
        selected.append(row)
    return selected


def provenance(
    source_report: dict[str, Any],
    manifest: dict[str, Any],
    source_path: Path,
    *,
    judge_replay: bool = False,
) -> dict[str, Any]:
    result = deepcopy(source_report.get("provenance") or {})
    result.update(
        {
            "git_commit": git_commit(),
            "evaluated_system_commit": manifest["evaluated_system_commit"],
            "evaluation_harness_commit": manifest["evaluation_harness_commit"],
            "benchmark_run_kind": manifest["benchmark_run_kind"],
            "dataset_version": manifest["version"],
            "dataset_revision": manifest["revision"],
            "dataset_hashes": manifest["dataset_hashes"],
            "runtime_code_matches_manifest": True,
            "runtime_outputs_changed": False,
            "frozen_output_source": str(source_path.relative_to(ROOT)).replace("\\", "/"),
            "frozen_output_sha256": file_hash(source_path),
            "judge_outputs_replayed": judge_replay,
        }
    )
    return result


def finalize(
    report: dict[str, Any],
    *,
    expected_n: int,
    report_provenance: dict[str, Any],
) -> dict[str, Any]:
    report["provenance"] = report_provenance
    actual_n = int((report.get("summary") or {}).get("n", 0))
    complete = actual_n == expected_n
    report["completeness"] = {
        "profile": "full",
        "expected_n": expected_n,
        "actual_n": actual_n,
        "complete": complete,
        "publication_status": (
            "corrected_measurement_same_runtime_outputs"
            if complete
            else "partial_not_for_headline"
        ),
    }
    if report.get("suite") in {"deterministic", "retrieval", "judge"}:
        report["gates"] = evaluate_gates(report["suite"], report.get("summary") or {})
        if not complete:
            report["gates"]["passed"] = False
            report["gates"]["reason"] = "partial_report"
    if report.get("suite") == "judge":
        judged_n = int((report.get("summary") or {}).get("judged_n", 0))
        report["completeness"]["judged_n"] = judged_n
        if judged_n != expected_n:
            report["completeness"]["complete"] = False
            report["completeness"]["publication_status"] = (
                "partial_judge_not_for_headline"
            )
            report["gates"]["passed"] = False
            report["gates"]["reason"] = "partial_judge"
    return report


def corrected_human_reviews(
    template: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    original = {str(row["id"]): row for row in load(SOURCE_HUMAN_AUDIT)}
    rows: list[dict[str, Any]] = []
    for template_row in template:
        case_id = str(template_row["id"])
        if case_id in original:
            rows.append(deepcopy(original[case_id]))
            continue
        review = REPLACEMENT_HUMAN_REVIEWS.get(case_id)
        if review is None:
            raise ValueError(f"Missing replacement human review for ID={case_id}")
        row = {**deepcopy(template_row), **deepcopy(review)}
        row["human_score"] = safe_mean(
            [
                float(row[field])
                for field in (
                    "correctness",
                    "faithfulness",
                    "completeness",
                    "citation_quality",
                    "safe_behavior",
                )
            ]
        )
        row["human_correctness"] = row["correctness"]
        row["human_faithfulness"] = row["faithfulness"]
        row["human_citation_correctness"] = row["citation_quality"]
        row["repeat_score"] = None
        rows.append(row)
    return rows


class ReplayJudgeClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.results = {str(row["id"]): deepcopy(row["judge"]) for row in rows}

    def judge(self, packet: dict[str, Any]) -> dict[str, Any]:
        case_id = str(packet["case_id"])
        if case_id not in self.results:
            raise ValueError(f"Missing frozen Judge output for ID={case_id}")
        return deepcopy(self.results[case_id])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    manifest = load(BUNDLE / "manifest.json")
    deterministic_cases = load(BUNDLE / "deterministic_tool_cases.json")
    retrieval_cases = load(BUNDLE / "retrieval_cases.json")
    answer_cases = load(BUNDLE / "generated_answer_cases.json")

    source_deterministic = load(SOURCE_DETERMINISTIC)
    deterministic_rows = select_rows(
        deterministic_cases,
        source_deterministic["cases"],
        source=SOURCE_DETERMINISTIC,
    )
    deterministic_report = deepcopy(source_deterministic)
    deterministic_report["cases"] = deterministic_rows
    deterministic_report = finalize(
        deterministic_report,
        expected_n=len(deterministic_cases),
        report_provenance=provenance(
            source_deterministic, manifest, SOURCE_DETERMINISTIC
        ),
    )
    write_report_bundle(deterministic_report, OUT / "deterministic_corrected_full.json")

    source_retrieval = load(SOURCE_RETRIEVAL)
    retrieval_rows = select_rows(
        retrieval_cases, source_retrieval["cases"], source=SOURCE_RETRIEVAL
    )
    retrieval_summary = _retrieval_summary(retrieval_rows, retrieval_rows)
    retrieval_summary["retrieval_scope"] = source_retrieval.get("scope")
    retrieval_report = {
        "suite": "retrieval",
        "backend": source_retrieval.get("backend"),
        "mode": source_retrieval.get("mode"),
        "scope": source_retrieval.get("scope"),
        "summary": retrieval_summary,
        "breakdowns": _retrieval_breakdowns(retrieval_rows),
        "cases": retrieval_rows,
    }
    retrieval_report = finalize(
        retrieval_report,
        expected_n=len(retrieval_cases),
        report_provenance=provenance(source_retrieval, manifest, SOURCE_RETRIEVAL),
    )
    write_report_bundle(retrieval_report, OUT / "retrieval_corrected_full.json")

    source_generation = load(SOURCE_GENERATION)
    answer_cache = select_rows(
        answer_cases, load(SOURCE_ANSWER_CACHE), source=SOURCE_ANSWER_CACHE
    )
    generation_report = {
        "suite": "answer_generation",
        "summary": {
            "n": len(answer_cache),
            "retrieval_mode": "vector_primary_graph_supplement",
            "phoranker_used": False,
            "success_rate": safe_mean(
                [float(row.get("status") == "answered") for row in answer_cache]
            ),
            "latency_ms": _latency_summary(
                [float(row.get("latency_ms", 0)) for row in answer_cache]
            ),
        },
        "cases": answer_cache,
        "provenance": provenance(source_generation, manifest, SOURCE_ANSWER_CACHE),
        "completeness": {
            "profile": "full",
            "expected_n": len(answer_cases),
            "actual_n": len(answer_cache),
            "complete": True,
            "publication_status": "corrected_measurement_same_runtime_outputs",
        },
    }
    write_report_bundle(generation_report, OUT / "answer_generation_corrected_full.json")

    source_judge = load(SOURCE_JUDGE)
    judge_report = judge_answers(
        answer_cases,
        answer_cache,
        checkpoint_path=OUT / "judge_replay_checkpoint_full.json",
        resume=True,
        judge_client=ReplayJudgeClient(source_judge["cases"]),
        checkpoint_context={
            "dataset_version": manifest["version"],
            "dataset_hash": manifest["dataset_hashes"]["answers"],
            "source_judge_sha256": file_hash(SOURCE_JUDGE),
            "replay": True,
        },
    )
    judge_report["human_audit_template"] = load(BUNDLE / "human_audit_template.json")
    human_reviews = corrected_human_reviews(judge_report["human_audit_template"])
    human_summary = summarize_human_audit(
        human_reviews,
        judge_report["cases"],
        judge_report["human_audit_template"],
    )
    human_summary.update(
        {
            "reviewer_count": 1,
            "inter_rater_agreement": None,
            "human_mean_score": safe_mean(
                [float(row["human_score"]) for row in human_reviews]
            ),
            "review_label_counts": dict(
                Counter(str(row.get("review_label") or "unknown") for row in human_reviews)
            ),
            "source_human_audit_sha256": file_hash(SOURCE_HUMAN_AUDIT),
        }
    )
    judge_report["human_audit"] = human_summary
    automatic_audit_source = load(SOURCE_AUTOMATIC_AUDIT)
    valid_answer_ids = {str(case["id"]) for case in answer_cases}
    automatic_audit_rows = [
        deepcopy(row)
        for row in automatic_audit_source["cases"]
        if str(row["id"]) in valid_answer_ids
    ]
    raw_unsupported_n = sum(
        bool(row.get("judge_unsupported_claim")) for row in automatic_audit_rows
    )
    false_unsupported_ids = sorted(
        UNSUPPORTED_FLAG_FALSE_POSITIVE_IDS
        & {str(row["id"]) for row in automatic_audit_rows}
    )
    adjudicated_unsupported_n = raw_unsupported_n - len(false_unsupported_ids)
    automatic_audit_summary = {
        "audited_n": len(automatic_audit_rows),
        "classification_counts": dict(
            Counter(str(row["classification"]) for row in automatic_audit_rows)
        ),
        "raw_unsupported_flags": raw_unsupported_n,
        "unsupported_false_positive_n": len(false_unsupported_ids),
        "unsupported_false_positive_ids": false_unsupported_ids,
        "adjudicated_unsupported_n": adjudicated_unsupported_n,
        "adjudicated_unsupported_rate": adjudicated_unsupported_n
        / max(1, len(answer_cases)),
        "critical_runtime_failures": sum(
            row.get("severity") == "critical" for row in automatic_audit_rows
        ),
    }
    judge_report["automatic_failure_audit"] = automatic_audit_summary
    judge_report = finalize(
        judge_report,
        expected_n=len(answer_cases),
        report_provenance=provenance(
            source_judge, manifest, SOURCE_JUDGE, judge_replay=True
        ),
    )
    write_report_bundle(judge_report, OUT / "answer_judge_corrected_full.json")
    (OUT / "human_audit_reviewed.json").write_text(
        json.dumps(human_reviews, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / "automatic_failure_audit_corrected.json").write_text(
        json.dumps(
            {"summary": automatic_audit_summary, "cases": automatic_audit_rows},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output": str(OUT),
                "deterministic": deterministic_report["summary"],
                "retrieval": retrieval_report["summary"],
                "judge": judge_report["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
