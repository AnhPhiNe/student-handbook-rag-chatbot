"""Build the V9.1 holdout with routing and retrieval evaluated separately."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_eval_v9_final import current_git_commit  # noqa: E402
from src.evaluation.dataset import (  # noqa: E402
    DATASET_FILES,
    file_hash,
    stable_json_hash,
    validate_bundle,
    write_json,
)


SOURCE_BUNDLE = ROOT / "data" / "eval" / "v9_final_holdout"
DEFAULT_OUTPUT = ROOT / "data" / "eval" / "v9_1_final_holdout"
DOCSTORE_PATH = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"


RETRIEVAL_QUERY_REVISIONS = {
    "v9_ret_005": {
        "query": (
            "K48-K49, công tác sinh viên gồm những hoạt động và nguyên tắc nào?"
        ),
        "question_style": "realistic",
    },
    "v9_ret_011": {
        "query": (
            "Lớp sinh viên K48-K49 được tổ chức và duy trì như thế nào "
            "trong khóa học?"
        ),
        "question_style": "realistic",
    },
    "v9_ret_014": {
        "query": (
            "Ở K48-K49, Phòng Hợp tác Quốc tế có trách nhiệm gì trong "
            "công tác sinh viên?"
        ),
        "question_style": "realistic",
    },
    "v9_ret_020": {
        "query": (
            "Sổ tay sinh viên K48-K49 được dùng để làm gì và đơn vị nào "
            "chịu trách nhiệm xây dựng?"
        ),
        "question_style": "realistic",
    },
    "v9_ret_024": {
        "query": (
            "K48-K49, thủ tục xét khen thưởng cho cá nhân hoặc tập thể lớp "
            "có thành tích xuất sắc gồm những bước nào?"
        ),
        "question_style": "paraphrase",
    },
    "v9_ret_026": {
        "query": (
            "K48-K49, hoat dong thong tin khoa hoc va cong nghe cua sinh "
            "vien duoc to chuc ra sao?"
        ),
        "question_style": "typo_no_accent",
    },
    "v9_ret_030": {
        "query": (
            "Các khoa có trách nhiệm gì trong quản lý công tác sinh viên "
            "K48-K49?"
        ),
        "question_style": "realistic",
    },
    "v9_ret_060": {
        "query": (
            "Với K50, Phòng Công nghệ Thông tin có trách nhiệm gì trong "
            "việc quản lý sinh viên ngoại trú?"
        ),
        "question_style": "realistic",
    },
    "v9_ret_113": {
        "query": (
            "K51, những đơn vị nào chịu trách nhiệm tổ chức thực hiện "
            "Quy chế đào tạo?"
        ),
        "question_style": "realistic",
    },
    "v9_ret_127": {
        "query": (
            "Quy chế đào tạo áp dụng cho K51 có hiệu lực từ khi nào và "
            "thay thế văn bản nào?"
        ),
        "question_style": "stress",
    },
    "v9_ret_158": {
        "query": (
            "Trong chính sách hỗ trợ sinh viên sư phạm, số tháng làm việc "
            "được làm tròn như thế nào?"
        ),
        "question_style": "realistic",
    },
    "v9_ret_175": {
        "query": (
            "Theo quy định ngoại trú, các đơn vị phải báo cáo tình hình "
            "sinh viên ngoại trú như thế nào?"
        ),
        "question_style": "stress",
    },
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _doc_id(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    return str(
        item.get("_id")
        or item.get("parent_section_id")
        or metadata.get("parent_section_id")
        or ""
    )


def _doc_judgment(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    return {
        "parent_section_id": _doc_id(item),
        "grade": 2,
        "cohort": metadata.get("cohort") or item.get("cohort"),
        "document_id": metadata.get("document_id") or item.get("document_id"),
        "content_type": metadata.get("content_type") or "regulation_text",
        "source_section": metadata.get("title")
        or metadata.get("source_section")
        or "",
        "source_pages": metadata.get("source_pages")
        or item.get("source_pages")
        or [],
    }


def _add_equivalent_policy_sources(
    case: dict[str, Any],
    docstore_by_id: dict[str, dict[str, Any]],
) -> None:
    if case.get("id") != "v9_ret_158":
        return
    suffix = "NghiDinhHoTroHocPhiSinhHoatPhiSinhVienSuPham_Chuong1_Dieu2"
    judgments = [
        _doc_judgment(item)
        for parent_id, item in docstore_by_id.items()
        if parent_id.endswith(suffix)
    ]
    if judgments:
        case["relevance_judgments"] = sorted(
            judgments,
            key=lambda item: str(item.get("cohort") or ""),
        )


def _revise_retrieval_cases(
    cases: list[dict[str, Any]],
    docstore_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    old_query_by_id: dict[str, str] = {}
    seen_ids: set[str] = set()
    for case in cases:
        case_id = str(case.get("id") or "")
        revision = RETRIEVAL_QUERY_REVISIONS.get(case_id)
        if revision is None:
            continue
        seen_ids.add(case_id)
        old_query = str(case.get("query") or "")
        old_query_by_id[case_id] = old_query
        case["predecessor_query"] = old_query
        case["query"] = revision["query"]
        case["question_style"] = revision["question_style"]
        case["question_specificity"] = "specific"
        case["expected_path"] = "regulation_rag"
        case["expected_intent"] = "regulation_query"
        case["expected_strategy"] = "hybrid_graph_retrieval"
        case["annotation_status"] = "source_anchored_v9_1_reviewed"
        case["annotation_revision"] = "routing_retrieval_responsibility_split"
        _add_equivalent_policy_sources(case, docstore_by_id)

    missing = sorted(set(RETRIEVAL_QUERY_REVISIONS) - seen_ids)
    if missing:
        raise RuntimeError(f"Missing retrieval cases for V9.1 revisions: {missing}")
    return old_query_by_id


def _propagate_linked_query_revisions(
    datasets: dict[str, list[dict[str, Any]]],
    old_query_by_id: dict[str, str],
) -> None:
    new_query_by_id = {
        case["id"]: case["query"] for case in datasets["retrieval"]
    }
    old_to_new = {
        old_query: new_query_by_id[case_id]
        for case_id, old_query in old_query_by_id.items()
    }
    for suite in ("answers", "production"):
        for case in datasets[suite]:
            predecessor_id = str(case.get("predecessor_case_id") or "")
            old_query = str(case.get("query") or "")
            replacement = new_query_by_id.get(predecessor_id) or old_to_new.get(
                old_query
            )
            if replacement and replacement != old_query:
                case["predecessor_query"] = old_query
                case["query"] = replacement
                case["annotation_revision"] = (
                    "routing_retrieval_responsibility_split"
                )


def _write_readme(output_dir: Path) -> None:
    (output_dir / "README.md").write_text(
        "\n".join(
            [
                "# V9.1 Final Holdout",
                "",
                "V9.1 keeps V9 intact and corrects objectively ambiguous or "
                "misrouted retrieval questions.",
                "",
                "- Pure retrieval is the headline retrieval scope.",
                "- End-to-end routing is reported separately.",
                "- Regulation questions remain source-anchored.",
                "- Structured/directory routing remains covered by the "
                "deterministic and production suites.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def build_bundle(output_dir: Path) -> dict[str, Any]:
    source_manifest = _load_json(SOURCE_BUNDLE / "manifest.json")
    datasets = {
        suite: copy.deepcopy(_load_json(SOURCE_BUNDLE / filename))
        for suite, filename in DATASET_FILES.items()
    }
    docstore = _load_json(DOCSTORE_PATH)
    docstore_by_id = {
        _doc_id(item): item
        for item in docstore
        if isinstance(item, dict) and _doc_id(item)
    }

    old_query_by_id = _revise_retrieval_cases(
        datasets["retrieval"],
        docstore_by_id,
    )
    _propagate_linked_query_revisions(datasets, old_query_by_id)

    output_dir.mkdir(parents=True, exist_ok=True)
    for suite, cases in datasets.items():
        write_json(output_dir / DATASET_FILES[suite], cases)

    audit_template = copy.deepcopy(
        _load_json(SOURCE_BUNDLE / "human_audit_template.json")
    )
    write_json(output_dir / "human_audit_template.json", audit_template)

    manifest = {
        **source_manifest,
        "version": "v9.1-final-routing-retrieval-split",
        "frozen": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "description": (
            "V9.1 final holdout with source-complete student questions and "
            "separate pure-retrieval versus end-to-end routing reports."
        ),
        "counts": {
            suite: len(cases) for suite, cases in datasets.items()
        },
        "dataset_hashes": {
            suite: stable_json_hash(cases)
            for suite, cases in datasets.items()
        },
        "auxiliary_hashes": {
            "human_audit_template": stable_json_hash(audit_template)
        },
        "git_commit": current_git_commit(),
        "docstore_hash": file_hash(DOCSTORE_PATH),
        "predecessor_bundle": "v9_final_holdout",
        "retrieval_evaluation": {
            "headline_scope": "pure",
            "secondary_scope": "end_to_end",
            "pure_scope_policy": (
                "Evaluate only regulation ranking after routing and query "
                "normalization; router decisions are scored separately."
            ),
        },
        "annotation_revision_count": len(RETRIEVAL_QUERY_REVISIONS),
        "annotation_revision_policy": (
            "Only objectively incomplete, malformed, or responsibility-mismatched "
            "queries were replaced; source IDs remain anchored."
        ),
        "holdout_policy": "single_run_no_post_tuning",
    }
    write_json(output_dir / "manifest.json", manifest)
    _write_readme(output_dir)

    validation = validate_bundle(output_dir, DOCSTORE_PATH, require_frozen=True)
    write_json(output_dir / "validation_report.json", validation)
    if not validation["valid"]:
        raise RuntimeError(
            "V9.1 bundle validation failed:\n"
            + "\n".join(validation.get("errors") or [])
        )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build_bundle(args.output.resolve())
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "version": manifest["version"],
                "counts": manifest["counts"],
                "annotation_revision_count": manifest[
                    "annotation_revision_count"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
