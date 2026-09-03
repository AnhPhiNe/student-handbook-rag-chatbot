from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "eval" / "architecture_v9_deterministic"
OUT = ROOT / "data" / "eval" / "architecture_v9_1_corrected"
EVALUATOR_COMMIT = "943d9b3805842ae764de7e3c893eceb1dbe96e7c"

RETRIEVAL_EXCLUSIONS = {
    "v8_ret_047": "Tiêu đề Điều 1 dùng chung; query không xác định văn bản K51.",
    "v8_ret_051": "Tiêu đề Điều 1 dùng chung; query không xác định văn bản K50.",
    "v8_ret_118": "Tiêu đề Điều 1 dùng chung; query không xác định Nghị định/văn bản.",
    "v8_ret_141": "Query nói hai việc nhưng liệt kê ba target; gold không bao phủ target thứ ba.",
    "v8_ret_151": "Hai tiêu đề chung không xác định hai văn bản mà gold ngầm chọn.",
}

ANSWER_EXCLUSIONS = {
    "v8_ans_rag_005": "Query không xác định văn bản K51 nhưng gold chọn riêng một Điều 1.",
    "v8_ans_rag_009": "Query không xác định văn bản K50 nhưng gold chọn riêng một Điều 1.",
    "v8_ans_rag_057": "Tên mục chung không xác định văn bản cố vấn học tập.",
    "v8_ans_rag_069": "Query CVHT/BCS không xác định văn bản ngoại trú mà gold ngầm chọn.",
    "v8_ans_rag_085": "Gold ghép nội dung khen thưởng NCKH ngoài phạm vi query học bổng.",
    "v8_ans_rag_086": "Gold ghép hiệu lực văn bản ngoài phạm vi query về đơn vị.",
    "v8_ans_rag_088": "Gold ghép nghỉ học tạm thời ngoài phạm vi query tổ chức quản lý.",
    "v8_ans_rag_089": "Gold ghép thời gian làm việc ngoài phạm vi mục ứng xử được hỏi.",
    "v8_ans_rag_090": "Gold ghép trách nhiệm quản lý ngoài phạm vi mục ứng xử được hỏi.",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def filter_cases(
    cases: list[dict[str, Any]], exclusions: dict[str, str]
) -> list[dict[str, Any]]:
    available = {str(case.get("id")) for case in cases}
    missing = sorted(set(exclusions) - available)
    if missing:
        raise ValueError(f"Correction IDs are absent from source bundle: {missing}")
    return [deepcopy(case) for case in cases if str(case.get("id")) not in exclusions]


def corrected_human_audit(
    source_template: list[dict[str, Any]],
    answer_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    valid_ids = {str(case["id"]) for case in answer_cases}
    selected = [deepcopy(row) for row in source_template if str(row["id"]) in valid_ids]
    selected_ids = {str(row["id"]) for row in selected}
    candidates = sorted(
        (case for case in answer_cases if str(case["id"]) not in selected_ids),
        key=lambda case: hashlib.sha256(
            f"v9.1-corrected-human-audit:{case['id']}".encode()
        ).hexdigest(),
    )
    for case in candidates[: 40 - len(selected)]:
        selected.append(
            {
                "id": case["id"],
                "case_type": case.get("case_type"),
                "cohort": case.get("cohort"),
                "query": case.get("query"),
                "correctness": None,
                "faithfulness": None,
                "completeness": None,
                "citation_quality": None,
                "safe_behavior": None,
                "review_label": None,
                "notes": "",
                "repeat_for_consistency": False,
            }
        )
    if len(selected) != 40:
        raise ValueError(f"Expected 40 human-audit cases, found {len(selected)}")
    return selected


def counter(cases: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(Counter(str(case.get(field)) for case in cases))


def build_manifest(
    manifest: dict[str, Any],
    datasets: dict[str, list[dict[str, Any]]],
    human_audit: list[dict[str, Any]],
    correction_audit: dict[str, Any],
) -> dict[str, Any]:
    deterministic = datasets["deterministic"]
    retrieval = datasets["retrieval"]
    answers = datasets["answers"]
    production = datasets["production"]
    result = deepcopy(manifest)
    result.update(
        {
            "bundle": "architecture_v9_1_corrected",
            "version": "9.1.0-corrected-evaluation",
            "revision": 1,
            "frozen": True,
            "review_state": "owner_approved_corrected_evaluation_frozen",
            "evaluation_harness_commit": EVALUATOR_COMMIT,
            "benchmark_run_kind": "same-runtime-output-corrected-measurement",
            "counts": {name: len(rows) for name, rows in datasets.items()},
            "deterministic_case_type_counts": counter(deterministic, "case_type"),
            "retrieval_cohort_counts": counter(retrieval, "cohort"),
            "retrieval_eval_split_counts": counter(retrieval, "eval_split"),
            "answer_case_type_counts": counter(answers, "case_type"),
            "answer_eval_split_counts": counter(answers, "eval_split"),
            "answer_path_counts": counter(answers, "expected_path"),
            "answer_rag_cohort_counts": counter(
                [case for case in answers if case.get("case_type") == "regulation_true_rag"],
                "cohort",
            ),
            "production_scenario_counts": counter(production, "scenario"),
            "human_audit_required_n": 40,
            "human_audit_selection_policy": (
                "Original frozen selection retained after exclusions; replacements selected "
                "by stable SHA256 order without changing system outputs."
            ),
            "dataset_hashes": {
                name: stable_hash(rows) for name, rows in datasets.items()
            },
            "auxiliary_hashes": {
                "human_audit_template": stable_hash(human_audit),
                "overlap_audit": stable_hash(load(SOURCE / "overlap_audit.json")),
                "correction_audit": stable_hash(correction_audit),
            },
            "system_executed_on_dataset": True,
            "generated_outputs_reused_without_mutation": True,
            "user_review_approved": True,
            "run_authorized": True,
            "headline_eligible_suites": ["deterministic", "retrieval", "answers"],
            "inherited_non_headline_suites": {"production": "architecture_v8"},
            "limitations": [
                "V9.1 is a post-hoc correction of measurement contracts, not a new holdout.",
                "Runtime outputs are reused unchanged; no Planner, Composer or retrieval code is modified.",
                "Five retrieval and nine answer cases are excluded because human audit found the query/gold contract non-identifiable or out of scope.",
                "Numeric accuracy is N/A unless a case explicitly declares numeric_assertions.",
                "Retrieval and answer scores must publish their corrected denominators (155 and 141).",
            ],
        }
    )
    result["answer_structured_lookup_counts"] = counter(
        [case for case in answers if case.get("case_type") == "structured_answer"],
        "lookup_group",
    )
    return result


def correction_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# V9.1 evaluation correction audit",
        "",
        "V9.1 changes only evaluation eligibility and evaluator semantics. Runtime and frozen outputs are unchanged.",
        "",
        "## Retrieval exclusions",
        "",
        "| ID | Reason |",
        "|---|---|",
    ]
    lines.extend(
        f"| `{case_id}` | {reason} |"
        for case_id, reason in audit["retrieval_exclusions"].items()
    )
    lines.extend(["", "## Answer exclusions", "", "| ID | Reason |", "|---|---|"])
    lines.extend(
        f"| `{case_id}` | {reason} |"
        for case_id, reason in audit["answer_exclusions"].items()
    )
    lines.extend(
        [
            "",
            "## Evaluator corrections",
            "",
            "- Metrics with no applicable assertion are reported as `N/A` and excluded from their denominator.",
            "- Numeric accuracy uses only explicit `numeric_assertions`; numbers embedded in prose gold are not silently treated as assertions.",
            "- Citation exact match is `N/A` when a case declares no expected citation IDs.",
            "- Safe missing-data language counts as abstention even when transport status remains `answered`.",
            "",
        ]
    )
    return "\n".join(lines)


def casebook_markdown(manifest: dict[str, Any]) -> str:
    counts = manifest["counts"]
    return "\n".join(
        [
            "# Architecture V9.1 — Corrected evaluation view",
            "",
            "V9.1 giữ nguyên runtime và output V9/V8, chỉ sửa eligibility và semantics của evaluator sau human audit.",
            "",
            f"- Deterministic: {counts['deterministic']} case.",
            f"- Retrieval: {counts['retrieval']} case.",
            f"- Generate + Judge: {counts['answers']} case.",
            f"- Production (inherited, non-headline): {counts['production']} case.",
            "- Evaluated system commit: `7f1fc82bc0d6a02a10cc64f0a7726b3cc7a913a9`.",
            "- Không có câu trả lời hoặc kết quả retrieval nào được sinh lại.",
            "- Xem `CORRECTION_AUDIT.md` để biết đầy đủ case loại và lý do.",
            "",
        ]
    )


def main() -> None:
    deterministic = load(SOURCE / "deterministic_tool_cases.json")
    retrieval = filter_cases(
        load(SOURCE / "retrieval_cases.json"), RETRIEVAL_EXCLUSIONS
    )
    answers = filter_cases(
        load(SOURCE / "generated_answer_cases.json"), ANSWER_EXCLUSIONS
    )
    production = load(SOURCE / "production_cases.json")
    human_audit = corrected_human_audit(
        load(SOURCE / "human_audit_template.json"), answers
    )
    correction_audit = {
        "source_bundle": "architecture_v9_deterministic",
        "evaluated_system_commit": load(SOURCE / "manifest.json")[
            "evaluated_system_commit"
        ],
        "evaluation_harness_commit": EVALUATOR_COMMIT,
        "runtime_changed": False,
        "outputs_changed": False,
        "retrieval_exclusions": RETRIEVAL_EXCLUSIONS,
        "answer_exclusions": ANSWER_EXCLUSIONS,
    }
    datasets = {
        "deterministic": deterministic,
        "retrieval": retrieval,
        "answers": answers,
        "production": production,
    }
    manifest = build_manifest(
        load(SOURCE / "manifest.json"), datasets, human_audit, correction_audit
    )

    filenames = {
        "deterministic": "deterministic_tool_cases.json",
        "retrieval": "retrieval_cases.json",
        "answers": "generated_answer_cases.json",
        "production": "production_cases.json",
    }
    for suite, rows in datasets.items():
        write(OUT / filenames[suite], rows)
    write(OUT / "human_audit_template.json", human_audit)
    write(OUT / "overlap_audit.json", load(SOURCE / "overlap_audit.json"))
    write(OUT / "correction_audit.json", correction_audit)
    write(OUT / "manifest.json", manifest)
    (OUT / "CORRECTION_AUDIT.md").write_text(
        correction_markdown(correction_audit), encoding="utf-8"
    )
    (OUT / "CASEBOOK_VI.md").write_text(
        casebook_markdown(manifest), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(OUT),
                "counts": manifest["counts"],
                "runtime_changed": False,
                "outputs_changed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
