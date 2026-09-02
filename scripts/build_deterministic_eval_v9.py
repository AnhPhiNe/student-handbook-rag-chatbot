from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "eval" / "architecture_v8"
OUT = ROOT / "data" / "eval" / "architecture_v9_deterministic"
RUNTIME_COMMIT = "7f1fc82bc0d6a02a10cc64f0a7726b3cc7a913a9"
EVALUATOR_COMMIT = "c02cf91351c6e2b020fb97b709c2d8ce0605dd6c"
CONTRACT = "query-plan-grounded-outcome-v9"


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


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_text_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def norm(value: str) -> str:
    text = value.replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())).strip()


def _sentence(value: str) -> str:
    return str(value).strip().rstrip("?.;:")


def _contact_field(query: str) -> tuple[str, str]:
    folded = norm(query)
    for token, field, label in (
        ("website", "website", "website"),
        ("email", "email", "email"),
        ("so dien thoai", "phone", "số điện thoại"),
        ("dia chi", "office", "địa chỉ làm việc"),
    ):
        if token in folded:
            return field, label
    raise ValueError(f"Cannot identify requested contact field: {query}")


def _training_mode(source_id: str) -> str:
    return "vừa làm vừa học" if "vua_lam_vua_hoc" in source_id else "chính quy"


def _single_query(case: dict[str, Any], index: int) -> str:
    group = str(case.get("lookup_group") or "")
    cohort = str(case.get("cohort") or "general")
    evidence = (case.get("gold_evidence") or [{}])[0]
    row = (evidence.get("rows") or [{}])[0]

    if group == "foreign_language":
        certificate = str(row.get("certificate") or row.get("language") or "chứng chỉ này")
        templates = (
            "Em học {cohort}; bảng ngoại ngữ quy đổi {value} sang bậc 3 và bậc 4 thế nào?",
            "Trong bảng áp dụng cho {cohort}, hai mức tương đương của {value} là gì?",
            "Cho em tra dòng {value}: chuẩn bậc 3 và bậc 4 được ghi ra sao?",
        )
        return templates[index % len(templates)].format(cohort=cohort, value=certificate)

    if group == "study_duration":
        source_id = str((case.get("expected_structured_sources") or [{}])[0].get("source_id") or "")
        mode = _training_mode(source_id)
        program = str(row.get("Chương trình đào tạo") or "").lower()
        subject = (
            f"{program} theo hệ {mode}"
            if program
            else f"Sinh viên {cohort} hệ {mode}"
        )
        cohort_prefix = "" if not program else f"Ở {cohort}, "
        return (
            f"{cohort_prefix}{subject} học chuẩn bao lâu và được phép hoàn thành "
            "tối đa trong mấy năm?"
        )

    if group == "scholarship_classification":
        subtype = str(evidence.get("table_subtype") or "")
        if subtype == "scholarship_amount":
            level = row.get("scholarship_level") or row.get("label")
            return (
                f"Mức học bổng {level} của {cohort} dùng hệ số nào và lấy mức học phí "
                "nào làm căn cứ?"
            )
        if subtype == "scholarship_classification":
            if row.get("academic_classification"):
                return (
                    f"Ở {cohort}, học lực {row['academic_classification']} và rèn luyện "
                    f"{row['conduct_classification_condition']} thì được xếp học bổng mức nào?"
                )
            return f"Khoảng điểm nào được xếp học bổng loại {row.get('label')} ở {cohort}?"
        criterion = str(row.get("criterion") or "tiêu chí này")
        return f"Điều kiện học bổng {cohort} ở tiêu chí {criterion.lower()} yêu cầu gì?"

    scoring_queries = {
        0: "Học phần nền tảng của K51 được 8,3 thì quy thành điểm chữ nào?",
        1: "Một môn còn lại ở K51 đạt 5,1 điểm thì nhận điểm chữ gì và có qua không?",
        2: "Điểm học phần 7,6 của sinh viên K50 tương ứng điểm chữ nào?",
        3: "Ở K48-K49, môn học được 4,5 thì đổi sang điểm chữ gì?",
        4: "B+ trong thang điểm K51 bằng bao nhiêu điểm hệ 4?",
        5: "Theo bảng K50, điểm chữ F có giá trị hệ 4 là bao nhiêu?",
        6: "GPA 3,58 của K51 thuộc xếp loại học lực nào?",
        7: "Sinh viên K48-K49 có GPA 0,90 thì xếp học lực gì?",
    }
    if group == "scoring":
        return scoring_queries[index]

    conduct_scores = (31, 58, 72, 85, 88, 96)
    if group == "conduct":
        return f"{conduct_scores[index]} điểm rèn luyện ở {cohort} được xếp loại gì?"

    if group == "formula":
        return (
            "Cách tính GPA có trọng số tín chỉ được viết như thế nào?"
            if index == 0
            else "Công thức điểm dùng để xếp hạng học bổng kết hợp học tập và rèn luyện ra sao?"
        )

    if group in {"office", "faculty"}:
        _, field_label = _contact_field(str(case["query"]))
        name = str(
            evidence.get("unit_name")
            or evidence.get("faculty_name")
            or evidence.get("unit")
        )
        return f"Danh bạ {cohort} ghi {field_label} của {name} là gì?"

    if group == "program":
        return (
            f"Sinh viên {cohort} học ngành {evidence.get('program_name')} thì ngành này "
            "do khoa nào quản lý?"
        )

    if group == "student_service":
        service = _sentence(str(evidence.get("service") or "dịch vụ này"))
        return f"Ở {cohort}, nếu cần {service.lower()} thì em liên hệ đơn vị nào?"

    raise ValueError(f"Unsupported single structured group: {group}")


def _short_document(title: str) -> str:
    folded = norm(title)
    for token, label in (
        ("co van hoc tap", "quy định cố vấn học tập"),
        ("nghien cuu khoa hoc", "quy định nghiên cứu khoa học sinh viên"),
        ("danh gia ket qua ren luyen", "quy chế rèn luyện"),
        ("cong tac sinh vien", "quy chế công tác sinh viên"),
        ("ngoai tru", "quy định ngoại trú"),
        ("dao tao trinh do dai hoc", "quy chế đào tạo đại học"),
        ("nguoi hoc tai nang", "chính sách người học tài năng"),
        ("ho tro tien dong hoc phi", "nghị định hỗ trợ sinh viên sư phạm"),
        ("quy tac ung xu", "quy tắc ứng xử"),
    ):
        if token in folded:
            return label
    return "văn bản trong Sổ tay"


def _boundary_query(case: dict[str, Any]) -> str:
    source = (case.get("gold_evidence") or [{}])[0]
    article = str(source.get("article") or "Điều liên quan").rstrip(".")
    section = str(source.get("source_section") or "nội dung này").lower()
    document = _short_document(str(source.get("document_title") or ""))
    return (
        f"Theo {article} của {document} dành cho {case['cohort']}, phần {section} "
        "quy định những nội dung chính nào?"
    )


CLARIFY_QUERIES = (
    "Em thuộc K50 nhưng lại nhớ năm nhập học là 2025; nên dùng thông tin khóa nào để tra?",
    "Em muốn quy đổi TOEIC bốn kỹ năng nhưng chưa có điểm Nói và Viết.",
    "Cho em xin địa chỉ của khoa đó với.",
    "Em muốn biết mức này được cấp theo tháng hay theo học kỳ, nhưng chưa nói loại hỗ trợ.",
    "Đổi điểm này sang thang còn lại giúp em, em chưa gửi điểm.",
    "Quy định này của K50 hay K51 vậy? Em chưa xác định được khóa.",
    "Cho em thông tin liên hệ của hai phòng vừa nhắc tới.",
    "Chứng chỉ ngoại ngữ này còn hiệu lực không? Em không nhớ loại chứng chỉ và ngày cấp.",
    "Em cần nội dung Điều 16 nhưng chưa rõ đang nói đến văn bản nào.",
    "So sánh thời gian đào tạo của hai khóa giúp em, nhưng em chưa nêu hai khóa.",
    "Em cần hỏi bốn việc riêng: GPA, danh bạ khoa, danh sách ngành và thủ tục nghỉ học.",
    "Tra giúp em bảng IELTS, email Thư viện, khoa quản lý ngành Hóa và quy định chuyển trường.",
)

UNSUPPORTED_QUERIES = (
    "Hồ sơ miễn học phần ngoại ngữ của riêng em đang được ai xử lý?",
    "Khoản học bổng cá nhân của em sẽ vào tài khoản lúc mấy giờ hôm nay?",
    "Lớp học phần sáng mai còn bao nhiêu chỗ trống theo thời gian thực?",
    "Bài thi của em hiện được giảng viên nào chấm?",
    "Ca trực tối nay ở Trạm Y tế có những ai?",
    "Ký túc xá đang còn chính xác bao nhiêu giường để đăng ký ngay?",
    "Mã giao dịch học phí mới nhất trong tài khoản của em là gì?",
    "Cho em danh sách tên sinh viên đang bị cảnh cáo trong lớp.",
)

OOD_QUERIES = (
    "Viết giúp mình một hàm Python sắp xếp danh sách.",
    "Gợi ý món ăn cuối tuần cho bốn người.",
    "Tóm tắt nội dung bộ phim Interstellar.",
    "Xe máy bị hết bình giữa đường thì xử lý thế nào?",
    "Giá Bitcoin hôm nay tăng hay giảm?",
    "Giải phương trình 2x bình cộng 7x trừ 4 bằng 0.",
    "Viết caption quảng cáo cho quán cà phê.",
    "Tạo bảng và index trong MySQL như thế nào?",
)


def _set_fact_lock_contract(case: dict[str, Any]) -> None:
    fact_lock_lookups = {
        "foreign_language",
        "study_duration",
        "scoring",
    }
    structured_evidence = [
        item
        for item in case.get("gold_evidence") or []
        if not item.get("parent_section_id")
        or item.get("content_type") != "regulation_text"
    ]
    task_index = 0
    for outcome in case.get("accepted_outcomes") or []:
        for task in outcome.get("required_tasks") or []:
            if task.get("mode") != "structured":
                continue
            evidence = (
                structured_evidence[task_index]
                if task_index < len(structured_evidence)
                else {}
            )
            task_index += 1
            applicable = task.get("lookup_type") in fact_lock_lookups or str(
                evidence.get("table_subtype") or ""
            ) in {"scholarship_amount", "scholarship_classification"}
            task["fact_lock_applicable"] = applicable
            if applicable:
                if not task.get("expected_resolved_fields"):
                    raise AssertionError(
                        f"{case['id']}: fact-lock task lacks expected_resolved_fields"
                    )
                task["resolved_result_required"] = True
            else:
                task.pop("expected_resolved_fields", None)
                task.pop("resolved_result_required", None)


def build_cases(*, frozen: bool) -> list[dict[str, Any]]:
    source_cases = deepcopy(load(SOURCE / "deterministic_tool_cases.json"))
    old_to_new = {
        case["id"]: str(case["id"]).replace("v8_det_", "v9_det_", 1)
        for case in source_cases
    }
    cases: list[dict[str, Any]] = []
    for index, source in enumerate(source_cases):
        case = deepcopy(source)
        old_id = str(case["id"])
        case["id"] = old_to_new[old_id]
        case["contract_version"] = CONTRACT
        case["frozen"] = frozen
        case["author_review_state"] = (
            "codex_reviewed_frozen_pending_run_approval"
            if frozen
            else "draft_pending_owner_review"
        )
        case["query_origin"] = "v9_source_grounded_rewrite_after_v8_diagnostic"
        case["diagnostic_ancestry_id"] = old_id
        case["near_duplicate_reviewed"] = frozen
        case.pop("duplicate_group", None)
        if case["case_type"] == "single_structured":
            group_index = sum(
                previous.get("lookup_group") == case.get("lookup_group")
                and previous.get("case_type") == "single_structured"
                for previous in cases
            )
            case["query"] = _single_query(case, group_index)
        elif case["case_type"] == "capability_boundary":
            case["query"] = _boundary_query(case)
        elif case["case_type"] == "missing_or_ambiguous":
            case["query"] = CLARIFY_QUERIES[index - 112]
        elif case["case_type"] == "unsupported_in_domain":
            case["query"] = UNSUPPORTED_QUERIES[index - 124]
        elif case["case_type"] == "out_of_domain":
            case["query"] = OOD_QUERIES[index - 132]
        cases.append(case)

    by_id = {case["id"]: case for case in cases}
    for case in cases:
        if case["case_type"] != "compound":
            continue
        component_ids = [
            old_to_new[str(value)] for value in case.pop("v8_component_ids", [])
        ]
        case["v9_component_ids"] = component_ids
        parts = [_sentence(by_id[case_id]["query"]) for case_id in component_ids]
        labels = ("Thứ nhất", "Thứ hai", "Thứ ba")
        count_label = "hai" if len(parts) == 2 else "ba"
        case["query"] = f"Em hỏi {count_label} ý riêng. " + " ".join(
            f"{labels[position]}: {part[0].lower() + part[1:]}?"
            for position, part in enumerate(parts)
        )

    for case in cases:
        _set_fact_lock_contract(case)
    cohort_variant_ids = {"v9_det_073", "v9_det_082"}
    for case in cases:
        if case["id"] in cohort_variant_ids:
            case["duplicate_group"] = "discipline_article_34_cohort_variant"
            case["near_duplicate_reviewed"] = True
            case["near_duplicate_rationale"] = (
                "Intentional K50/K51 cohort coverage for the same article title; "
                "cohort applicability remains independently asserted."
            )
    if len(cases) != 140:
        raise AssertionError(f"Expected 140 deterministic cases, got {len(cases)}")
    return cases


def historical_queries() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for directory in ROOT.joinpath("data", "eval").iterdir():
        if not directory.is_dir() or directory == OUT:
            continue
        for filename in (
            "deterministic_tool_cases.json",
            "retrieval_cases.json",
            "generated_answer_cases.json",
            "production_cases.json",
            "cases.json",
        ):
            path = directory / filename
            if not path.exists():
                continue
            try:
                values = load(path)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(values, list):
                continue
            for item in values:
                if isinstance(item, dict) and str(item.get("query") or "").strip():
                    rows.append(
                        {
                            "id": str(item.get("id") or ""),
                            "query": str(item["query"]),
                            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                        }
                    )
    return rows


def overlap_audit(cases: list[dict[str, Any]]) -> dict[str, Any]:
    history = historical_queries()
    history_norm = [(item, norm(item["query"])) for item in history]
    history_tokens = [set(value.split()) for _, value in history_norm]
    rows: list[dict[str, Any]] = []
    for case in cases:
        current = norm(str(case["query"]))
        current_tokens = set(current.split())
        candidates = sorted(
            (
                len(current_tokens & old_tokens)
                / max(1, len(current_tokens | old_tokens)),
                position,
            )
            for position, old_tokens in enumerate(history_tokens)
        )[-30:]
        scored = sorted(
            [
                (
                    SequenceMatcher(
                        None, current, history_norm[position][1]
                    ).ratio(),
                    history_norm[position][0],
                )
                for _, position in candidates
            ],
            key=lambda value: value[0],
        )[-3:]
        rows.append(
            {
                "id": case["id"],
                "query": case["query"],
                "exact_historical_matches": [
                    {"id": item["id"], "path": item["path"]}
                    for item, old in history_norm
                    if old == current
                ],
                "nearest_lexical": [
                    {
                        "sequence_ratio": round(score, 4),
                        "id": item["id"],
                        "path": item["path"],
                        "query": item["query"],
                    }
                    for score, item in reversed(scored)
                ],
            }
        )
    exact_n = sum(bool(row["exact_historical_matches"]) for row in rows)
    return {
        "policy": "No exact historical query; topical and semantic overlap is allowed for the fixed corpus.",
        "historical_query_count": len(history),
        "exact_historical_match_count": exact_n,
        "lexical_review_threshold": 0.82,
        "lexical_review_count": sum(
            row["nearest_lexical"][0]["sequence_ratio"] >= 0.82 for row in rows
        ),
        "semantic_review": "pending_optional_human_review",
        "cases": rows,
    }


def casebook(cases: list[dict[str, Any]], overlap: dict[str, Any]) -> str:
    split = Counter(case["eval_split"] for case in cases)
    types = Counter(case["case_type"] for case in cases)
    lines = [
        "# Architecture V9 Deterministic — Pre-run review",
        "",
        "> Bộ 140 câu mới cho runtime 7f1fc82b; chưa chứa output của hệ thống.",
        "",
        f"- Realistic: {split['realistic']}; stress: {split['stress']}.",
        f"- Case types: `{dict(types)}`.",
        f"- Exact historical overlap: {overlap['exact_historical_match_count']}.",
        "- `fact_lock_applicable=true` chỉ dùng cho lookup một bảng–một hàng xác định.",
        "- Retrieval/answer/production files đi kèm chỉ để tương thích runner; không phải metric V9 mới.",
        "",
        "| ID | Split | Cohort | Type | Fact lock tasks | Query |",
        "|---|---|---|---|---:|---|",
    ]
    for case in cases:
        fact_locks = sum(
            task.get("fact_lock_applicable") is True
            for outcome in case.get("accepted_outcomes") or []
            for task in outcome.get("required_tasks") or []
        )
        query = str(case["query"]).replace("|", "\\|")
        lines.append(
            f"| `{case['id']}` | `{case['eval_split']}` | `{case['cohort']}` | "
            f"`{case['case_type']}` | {fact_locks} | {query} |"
        )
    return "\n".join(lines) + "\n"


def build_manifest(
    cases: list[dict[str, Any]],
    inherited: dict[str, list[dict[str, Any]]],
    human_audit: list[dict[str, Any]],
    overlap: dict[str, Any],
    *,
    frozen: bool,
) -> dict[str, Any]:
    manifest = deepcopy(load(SOURCE / "manifest.json"))
    datasets = {"deterministic": cases, **inherited}
    manifest.update(
        {
            "bundle": "architecture_v9_deterministic",
            "schema_version": "architecture-evaluation-v9",
            "version": "9.0.0-deterministic",
            "revision": 1,
            "frozen": frozen,
            "review_state": (
                "pre_run_codex_reviewed_frozen_pending_run_approval"
                if frozen
                else "draft_pending_owner_review"
            ),
            "authored_against_runtime_commit": RUNTIME_COMMIT,
            "evaluated_system_commit": RUNTIME_COMMIT,
            "evaluation_harness_commit": EVALUATOR_COMMIT,
            "benchmark_run_kind": "fresh_post_fix_deterministic",
            "headline_eligible_suites": ["deterministic"],
            "inherited_non_headline_suites": {
                "retrieval": "architecture_v8",
                "answers": "architecture_v8",
                "production": "architecture_v8",
            },
            "deterministic_contract": CONTRACT,
            "deterministic_case_type_counts": dict(
                Counter(case["case_type"] for case in cases)
            ),
            "deterministic_lookup_case_types": ["single_structured"],
            "deterministic_lookup_group_counts": dict(
                Counter(
                    case["lookup_group"]
                    for case in cases
                    if case["case_type"] == "single_structured"
                )
            ),
            "dataset_hashes": {
                suite: stable_hash(values) for suite, values in datasets.items()
            },
            "overlap_summary": {
                "exact": overlap["exact_historical_match_count"],
                "lexical_review": overlap["lexical_review_count"],
                "semantic_review": "human_only",
            },
            "system_executed_on_dataset": False,
            "user_review_approved": False,
            "run_authorized": False,
            "limitations": [
                "V9 refreshes only the deterministic suite after V8 exposed runtime and contract defects.",
                "The fixed three-handbook corpus requires reuse of capabilities and source facts; exact query reuse is prohibited but topical overlap is expected.",
                "Retrieval, answer and production files are inherited from V8 solely for runner compatibility and are not V9 headline metrics.",
                "Because V9 was authored after V8 diagnostics, it is a fresh post-fix benchmark rather than a pristine pre-development external holdout.",
            ],
        }
    )
    manifest["versions"].update(
        {
            "planner_prompt": "structured-regulation-v41-explicit-request-count",
            "answer_pipeline": "v62-grounded-fact-locks",
        }
    )
    manifest["config_hashes"].update(
        {
            "ai_router": normalized_text_hash(ROOT / "configs" / "ai_router.yaml"),
            "structured_lookup_registry": normalized_text_hash(
                ROOT / "configs" / "structured_lookup_registry.yaml"
            ),
        }
    )
    manifest["auxiliary_hashes"] = {
        "human_audit_template": stable_hash(human_audit),
        "overlap_audit": stable_hash(overlap),
    }
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    cases = build_cases(frozen=args.freeze)
    overlap = overlap_audit(cases)
    if args.freeze and overlap["exact_historical_match_count"]:
        raise SystemExit("Cannot freeze while exact historical overlap remains")
    inherited = {
        "retrieval": load(SOURCE / "retrieval_cases.json"),
        "answers": load(SOURCE / "generated_answer_cases.json"),
        "production": load(SOURCE / "production_cases.json"),
    }
    human_audit = load(SOURCE / "human_audit_template.json")
    manifest = build_manifest(
        cases,
        inherited,
        human_audit,
        overlap,
        frozen=args.freeze,
    )
    write(OUT / "deterministic_tool_cases.json", cases)
    write(OUT / "retrieval_cases.json", inherited["retrieval"])
    write(OUT / "generated_answer_cases.json", inherited["answers"])
    write(OUT / "production_cases.json", inherited["production"])
    write(OUT / "human_audit_template.json", human_audit)
    write(OUT / "overlap_audit.json", overlap)
    write(OUT / "manifest.json", manifest)
    (OUT / "CASEBOOK_VI.md").write_text(
        casebook(cases, overlap), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(OUT),
                "deterministic_cases": len(cases),
                "fact_lock_tasks": sum(
                    task.get("fact_lock_applicable") is True
                    for case in cases
                    for outcome in case.get("accepted_outcomes") or []
                    for task in outcome.get("required_tasks") or []
                ),
                "exact_historical_matches": overlap[
                    "exact_historical_match_count"
                ],
                "lexical_review": overlap["lexical_review_count"],
                "frozen": args.freeze,
                "system_executed_on_dataset": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
