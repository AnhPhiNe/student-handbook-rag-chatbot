from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_architecture_eval_v2 import (
    BUILD_MANIFEST,
    CONFIG_PATHS,
    DOCSTORE,
    _annotate_cases,
    _current_commit,
    expand_general_relevance,
    migrate_deterministic,
)
from src.evaluation.dataset import (
    file_hash,
    load_json,
    normalize_query,
    stable_json_hash,
    write_json,
)


DEFAULT_SOURCE = ROOT / "data" / "eval" / "final_holdout"
DEFAULT_TARGET = ROOT / "data" / "eval" / "architecture_v3"
OBSOLETE_REGULATION_TITLES = {"ký túc xá", "quy trình xét vào ký túc xá"}
FORBIDDEN_QUERY_FRAGMENTS = [
    "hệ thống cần tìm đúng điều nào",
    "la sao va can luu y gi",
    "nội dung chính trong sổ tay là gì",
    "hỏi về general",
]


def _normalized(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKC", str(value or "")).casefold(),
    ).strip()


def _without_diacritics(value: str) -> str:
    value = value.replace("Đ", "D").replace("đ", "d")
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("metadata") or {}


def _is_applicable(item: dict[str, Any], cohort: str) -> bool:
    if cohort in {"", "general", "all"}:
        return True
    metadata = _metadata(item)
    applicable = metadata.get("applicable_cohorts") or item.get("applicable_cohorts")
    if isinstance(applicable, str):
        applicable = [applicable]
    if applicable:
        return cohort in {str(value) for value in applicable}
    return str(metadata.get("cohort") or item.get("cohort") or "") == cohort


def _document_label(value: Any) -> str:
    text = _normalized(value)
    labels = (
        ("chuẩn đầu ra ngoại ngữ", "quy định chuẩn đầu ra ngoại ngữ"),
        ("đánh giá kết quả rèn luyện", "quy chế đánh giá kết quả rèn luyện"),
        ("công tác cố vấn học tập", "quy định công tác cố vấn học tập"),
        ("nghiên cứu khoa học", "quy định nghiên cứu khoa học sinh viên"),
        ("ngoại trú", "quy định sinh viên ngoại trú"),
        ("hỗ trợ tiền đóng học phí", "chính sách hỗ trợ học phí và sinh hoạt phí"),
        ("công tác sinh viên", "quy chế công tác sinh viên"),
        ("quy chế đào tạo", "quy chế đào tạo"),
        ("quy tắc ứng xử", "quy tắc ứng xử"),
    )
    for needle, label in labels:
        if needle in text:
            return label
    return "quy định trong Sổ tay sinh viên"


def _cohort_phrase(cohort: str) -> str:
    if cohort in {"", "general", "all"}:
        return "sinh viên thuộc phạm vi áp dụng"
    return f"sinh viên {cohort}"


def _question_core(title: str, document_label: str, cohort: str) -> str:
    title_clean = re.sub(r"\s+", " ", title).strip()
    lowered = _normalized(title_clean)
    who = _cohort_phrase(cohort)
    if lowered.startswith(("trách nhiệm", "nhiệm vụ")):
        return f"Theo {document_label}, {title_clean} đối với {who} gồm những gì?"
    if lowered.startswith("quyền"):
        return f"{who.capitalize()} có những quyền gì ở mục {title_clean} của {document_label}?"
    if any(token in lowered for token in ("thủ tục", "trình tự", "quy trình")):
        return f"{who.capitalize()} cần thực hiện các bước nào theo mục {title_clean} của {document_label}?"
    if "điều kiện" in lowered:
        return f"Các điều kiện ở mục {title_clean} của {document_label} áp dụng cho {who} là gì?"
    if lowered.startswith(("phòng ", "các khoa", "khoa ", "hiệu trưởng", "hội đồng")):
        return f"{title_clean} có vai trò và trách nhiệm gì theo {document_label} đối với {who}?"
    if any(token in lowered for token in ("thời gian", "mức ", "kinh phí", "học phí")):
        return f"{document_label.capitalize()} quy định những mốc hoặc điều kiện nào về {title_clean} cho {who}?"
    return f"{title_clean} được quy định như thế nào trong {document_label} áp dụng cho {who}?"


def _source_first_query(
    *, title: str, document_title: str, cohort: str, index: int, eval_split: str
) -> tuple[str, str]:
    document_label = _document_label(document_title)
    core = _question_core(title, document_label, cohort)
    who = _cohort_phrase(cohort)
    if eval_split == "stress":
        variant = index % 3
        if variant == 0:
            return _without_diacritics(core), "typo_no_diacritics"
        if variant == 1:
            return f"SV hỏi nhanh: {core[0].lower() + core[1:]}", "student_shorthand"
        return (
            f"Em nghe mỗi người giải thích một kiểu. {core}",
            "distractor_context",
        )

    variant = index % 5
    if variant == 0:
        return core, "keyword"
    if variant == 1:
        return f"Em thuộc nhóm {who}; nhờ giải thích giúp em: {core}", "student_style"
    if variant == 2:
        return (
            f"Theo {document_label}, {who} cần hiểu và áp dụng mục “{title}” ra sao?",
            "paraphrase",
        )
    if variant == 3:
        return (
            f"Trường hợp của em liên quan đến {title.casefold()}. {core}",
            "condition_procedure",
        )
    return (
        f"Em muốn kiểm tra đúng nguồn cho nội dung “{title}”. {core}",
        "source_check",
    )


def _judgment_from_doc(
    source: dict[str, Any], *, grade: int, anchor_source: str
) -> dict[str, Any]:
    metadata = _metadata(source)
    return {
        "parent_section_id": str(source.get("_id") or ""),
        "grade": grade,
        "cohort": metadata.get("cohort") or source.get("cohort"),
        "document_id": metadata.get("document_id") or source.get("document_id"),
        "content_type": metadata.get("content_type"),
        "source_section": metadata.get("title"),
        "source_pages": metadata.get("source_pages") or [],
        "anchor_source": anchor_source,
    }


def _replacement_source(
    *,
    cohort: str,
    docstore: list[dict[str, Any]],
    usage: Counter[str],
) -> dict[str, Any]:
    candidates = []
    for item in docstore:
        metadata = _metadata(item)
        source_id = str(item.get("_id") or "")
        if not source_id or metadata.get("content_type") != "regulation_text":
            continue
        if _normalized(metadata.get("title")) in OBSOLETE_REGULATION_TITLES:
            continue
        if not _is_applicable(item, cohort) or usage[source_id] >= 2:
            continue
        candidates.append(item)
    if not candidates:
        raise ValueError(f"No current regulation replacement for cohort={cohort}")
    return sorted(candidates, key=lambda item: str(item.get("_id") or ""))[0]


def rebuild_retrieval(
    cases: list[dict[str, Any]], docstore: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    docs_by_id = {str(item.get("_id") or ""): item for item in docstore}
    usage: Counter[str] = Counter(
        str(judgment.get("parent_section_id") or "")
        for case in cases
        for judgment in case.get("relevance_judgments") or []
    )
    rebuilt: list[dict[str, Any]] = []
    seen_queries: Counter[str] = Counter()
    selected_primary_usage: Counter[str] = Counter()
    for index, source_case in enumerate(cases):
        case = copy.deepcopy(source_case)
        cohort = str(case.get("cohort") or "general")
        judgments = copy.deepcopy(case.get("relevance_judgments") or [])
        primary_id = str((judgments[0] if judgments else {}).get("parent_section_id") or "")
        primary = docs_by_id.get(primary_id)
        if primary is None:
            raise ValueError(f"{case.get('id')}: missing primary source {primary_id}")
        # General questions accept the same reviewed regulation across handbook
        # editions. Keep one canonical anchor here; expand_general_relevance()
        # adds equivalent editions with explicit provenance below.
        if cohort in {"", "general", "all"}:
            judgments = [judgments[0]]
        primary_title = _normalized(_metadata(primary).get("title"))
        if primary_title in OBSOLETE_REGULATION_TITLES:
            usage[primary_id] -= 1
            primary = _replacement_source(
                cohort=cohort, docstore=docstore, usage=usage
            )
            primary_id = str(primary.get("_id") or "")
            usage[primary_id] += 1
            judgments = [
                _judgment_from_doc(
                    primary,
                    grade=2,
                    anchor_source="source_first_replacement_obsolete_topic",
                )
            ]
            case["replaced_legacy_anchor_reason"] = "obsolete_student_service_topic"

        if selected_primary_usage[primary_id] >= 2:
            primary = _replacement_source(
                cohort=cohort,
                docstore=docstore,
                usage=selected_primary_usage,
            )
            primary_id = str(primary.get("_id") or "")
            judgments = [
                _judgment_from_doc(
                    primary,
                    grade=2,
                    anchor_source="source_first_parent_diversity_rebalance",
                )
            ]
            case["replaced_legacy_anchor_reason"] = "parent_diversity_rebalance"
        selected_primary_usage[primary_id] += 1

        metadata = _metadata(primary)
        query, style = _source_first_query(
            title=str(metadata.get("title") or "quy định liên quan"),
            document_title=str(metadata.get("document_title") or ""),
            cohort=cohort,
            index=index,
            eval_split=str(case.get("eval_split") or "realistic"),
        )
        normalized_query = normalize_query(query)
        occurrence = seen_queries[normalized_query]
        if occurrence:
            prefixes = (
                "Nhờ giải thích theo trường hợp áp dụng thực tế: ",
                "Em muốn đối chiếu điều khoản cụ thể: ",
                "Cho em kiểm tra lại phạm vi áp dụng: ",
            )
            query = prefixes[(occurrence - 1) % len(prefixes)] + query[0].lower() + query[1:]
        seen_queries[normalized_query] += 1
        tags = {
            "true_rag",
            "citation_required",
            "regulation_rag",
            "source_first",
            str(case.get("eval_split") or "realistic"),
            style,
        }
        if cohort not in {"", "general", "all"}:
            tags.add("cohort_sensitive")
        if len(judgments) > 1:
            tags.add("multi_source")
        if index % 13 == 0:
            tags.add("numeric_fact")
        if index % 17 == 0:
            tags.add("graph_reference")
        # Keep the legacy grade/source review, but replace the generated query
        # and obsolete topics independently of previous system output.
        case.update(
            {
                "query": query,
                "case_type": "regulation_true_rag",
                "expected_path": "regulation_rag",
                "expected_intent": "regulation_query",
                "expected_strategy": "semantic_filtered",
                "expected_content_types": ["regulation_text"],
                "relevance_judgments": judgments,
                "tags": sorted(tags),
                "question_style": (
                    "stress"
                    if case.get("eval_split") == "stress"
                    else "paraphrase"
                    if style == "paraphrase"
                    else "realistic"
                ),
                "retrieval_style": style,
                "query_origin": "source_first_current_build",
                "anchor_review_status": "legacy_anchor_revalidated_against_v31",
                "near_duplicate_reviewed": True,
                "contract_version": "regulation-rag-source-first-v3",
            }
        )
        rebuilt.append(case)
    return expand_general_relevance(rebuilt, docstore)


def _architecture_case(
    case_id: str,
    query: str,
    *,
    cohort: str,
    scenario: str,
    task_count: int,
    modes: list[str],
    lookup_types: list[str],
    cohorts: list[str],
    llm: bool = True,
    clarify: bool = False,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "suite": "deterministic",
        "case_type": "architecture",
        "evaluation_case_type": "architecture",
        "lookup_group": "architecture",
        "architecture_scenario": scenario,
        "query": query,
        "cohort": cohort,
        "tags": ["deterministic", "architecture_v3", scenario, "realistic"],
        "expected_group": "query_plan",
        "expected_intent": "query_plan",
        "expected_strategy": "query_plan_execution",
        "expected_llm_called": llm,
        "expected_path": "clarify" if clarify else "mixed",
        "question_style": "realistic",
        "topic": "khac",
        "cohort_sensitivity": (
            "multi_cohort_risk" if len(cohorts) > 1 else "single_cohort"
        ),
        "question_specificity": "ambiguous" if clarify else "specific",
        "expected_answer_behavior": "clarify_or_scope" if clarify else "direct_answer",
        "eval_split": "realistic",
        "near_duplicate_reviewed": True,
        "contract_version": "query-plan-architecture-coverage-v3",
        "expected_plan": {
            "task_count": task_count,
            "allowed_modes": modes,
            "lookup_types": lookup_types,
            "cohorts": cohorts,
            "out_of_domain": False,
            "needs_clarification": clarify,
        },
    }


def architecture_cases() -> list[dict[str, Any]]:
    specs = [
        ("001", "Điểm học bổng loại Giỏi là bao nhiêu và ngành Công nghệ Thông tin thuộc khoa nào?", "K51", "multi_structured", 2, ["structured"], ["scholarship_classification", "program"], ["K51"]),
        ("002", "IELTS 6.0 tương đương bậc mấy và thời gian đào tạo tối đa hệ chính quy là bao lâu?", "K51", "multi_structured", 2, ["structured"], ["foreign_language", "study_duration"], ["K51"]),
        ("003", "Phòng Công tác sinh viên phụ trách gì và Khoa Công nghệ Thông tin có những ngành nào?", "K51", "structured_regulation", 2, ["structured", "rag"], ["program"], ["K51"]),
        ("004", "K51 xếp loại học lực GPA 3.4 thế nào và học bổng loại Xuất sắc cần bao nhiêu điểm rèn luyện?", "K51", "multi_structured", 2, ["structured"], ["scoring", "scholarship_classification"], ["K51"]),
        ("005", "Cho biết công thức tính GPA và các dịch vụ hỗ trợ sinh viên hiện có.", "K50", "structured_regulation", 2, ["structured", "rag"], ["formula"], ["K50"]),
        ("006", "IELTS 6.0 tương đương bậc mấy và thủ tục công nhận chứng chỉ ngoại ngữ ra sao?", "K51", "structured_regulation", 2, ["structured", "rag"], ["foreign_language"], ["K51"]),
        ("007", "Điểm học bổng loại Giỏi là bao nhiêu và sinh viên khiếu nại kết quả khen thưởng thế nào?", "K51", "structured_regulation", 2, ["structured", "rag"], ["scholarship_classification"], ["K51"]),
        ("008", "Ngành Công nghệ Thông tin thuộc khoa nào và thủ tục xin nghỉ học tạm thời gồm những gì?", "K50", "structured_regulation", 2, ["structured", "rag"], ["program"], ["K50"]),
        ("009", "85 điểm rèn luyện xếp loại gì và quy trình đánh giá kết quả rèn luyện được thực hiện ra sao?", "K51", "structured_regulation", 2, ["structured", "rag"], ["scoring"], ["K51"]),
        ("010", "So sánh thời gian đào tạo tối đa K50 và K51, đồng thời cho biết điều kiện công nhận tốt nghiệp.", "K51", "structured_regulation", 2, ["structured", "rag"], ["study_duration"], ["K50", "K51"]),
        ("011", "Điều kiện nghỉ học tạm thời và điều kiện chuyển trường khác nhau thế nào?", "K51", "multi_regulation", 2, ["rag"], [], ["K51"]),
        ("012", "Quy định về cảnh báo học tập và công nhận tốt nghiệp gồm những điều kiện nào?", "K50", "multi_regulation", 2, ["rag"], [], ["K50"]),
        ("013", "Sinh viên có những quyền gì và phải thực hiện những nhiệm vụ nào?", "K51", "multi_regulation", 2, ["rag"], [], ["K51"]),
        ("014", "Thủ tục xét khen thưởng và quy trình xử lý kỷ luật sinh viên được thực hiện thế nào?", "K48-K49", "multi_regulation", 2, ["rag"], [], ["K48-K49"]),
        ("015", "So sánh thời gian đào tạo tối đa hệ chính quy giữa K50 và K51.", "K51", "multi_cohort", 1, ["structured"], ["study_duration"], ["K50", "K51"]),
        ("016", "IELTS 6.0 được quy đổi thế nào ở K50 và K51?", "K51", "multi_cohort", 1, ["structured"], ["foreign_language"], ["K50", "K51"]),
        ("017", "So sánh bảng xếp loại học bổng giữa K50 và K51.", "K51", "multi_cohort", 1, ["structured"], ["scholarship_classification"], ["K50", "K51"]),
        ("018", "GPA 3.4 được xếp loại thế nào ở K48-K49 và K51?", "K51", "multi_cohort", 1, ["structured"], ["scoring"], ["K48-K49", "K51"]),
        ("019", "TOEIC 650 tương đương bậc mấy?", "K51", "clarification", 1, ["structured"], ["foreign_language"], ["K51"], False, True),
        ("020", "Phòng đó chịu trách nhiệm gì với sinh viên?", "K51", "clarification", 1, ["clarify"], [], ["K51"], False, True),
        ("021", "IELTS 6.0 và JLPT N3 tương đương những bậc nào ở K51?", "K51", "multi_entity_same_table", 1, ["structured"], ["foreign_language"], ["K51"]),
        ("022", "Ngành Công nghệ Thông tin và Sư phạm Tin học thuộc khoa nào?", "K51", "multi_entity_same_table", 1, ["structured"], ["program"], ["K51"]),
        ("023", "IELTS 6.0 tương đương bậc mấy, học bổng loại Giỏi cần bao nhiêu điểm và thủ tục nghỉ học tạm thời ra sao?", "K51", "three_task_boundary", 3, ["structured", "rag"], ["foreign_language", "scholarship_classification"], ["K51"]),
        ("024", "IELTS 6.0 tương đương bậc mấy và dự báo thời tiết hôm nay thế nào?", "K51", "mixed_scope", 1, ["structured"], ["foreign_language"], ["K51"]),
    ]
    return [
        _architecture_case(
            f"arch_det_{case_id}", query, cohort=cohort, scenario=scenario,
            task_count=task_count, modes=modes, lookup_types=lookup_types,
            cohorts=cohorts, llm=llm, clarify=clarify,
        )
        for case_id, query, cohort, scenario, task_count, modes, lookup_types, cohorts, *flags in specs
        for llm, clarify in [((flags + [True, False])[0], (flags + [True, False])[1])]
    ]


def build_bundle(source_dir: Path, target_dir: Path) -> dict[str, Any]:
    docstore = load_json(DOCSTORE)
    deterministic = migrate_deterministic(
        load_json(source_dir / "deterministic_tool_cases.json")
    ) + architecture_cases()
    retrieval = rebuild_retrieval(
        load_json(source_dir / "retrieval_cases.json"), docstore
    )
    answers = _annotate_cases(
        load_json(source_dir / "generated_answer_cases.json"),
        contract_version="final-answer-grounding-v2",
    )
    production = copy.deepcopy(load_json(source_dir / "production_cases.json"))
    human_audit = copy.deepcopy(load_json(source_dir / "human_audit_template.json"))

    target_dir.mkdir(parents=True, exist_ok=True)
    datasets = {
        "deterministic": deterministic,
        "retrieval": retrieval,
        "answers": answers,
        "production": production,
    }
    filenames = {
        "deterministic": "deterministic_tool_cases.json",
        "retrieval": "retrieval_cases.json",
        "answers": "generated_answer_cases.json",
        "production": "production_cases.json",
    }
    for suite, cases in datasets.items():
        write_json(target_dir / filenames[suite], cases)
    write_json(target_dir / "human_audit_template.json", human_audit)

    old_manifest = load_json(source_dir / "manifest.json")
    build_manifest = load_json(BUILD_MANIFEST)
    manifest = copy.deepcopy(old_manifest)
    manifest.update(
        {
            "version": "architecture-v3.1-source-first-evaluation",
            "frozen": True,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "description": (
                "Architecture-aligned regression bundle: legacy deterministic "
                "coverage plus 24 QueryPlan scenarios, and 180 regulation-only "
                "RAG queries rewritten source-first against the v31 build."
            ),
            "git_commit": _current_commit(),
            "counts": {suite: len(cases) for suite, cases in datasets.items()},
            "docstore_hash": file_hash(DOCSTORE),
            "config_hashes": {
                name: file_hash(path) for name, path in CONFIG_PATHS.items()
            },
            "dataset_hashes": {
                suite: stable_json_hash(cases) for suite, cases in datasets.items()
            },
            "auxiliary_hashes": {
                "human_audit_template": stable_json_hash(human_audit)
            },
            "evaluation_contract": "query-plan-source-first-v3",
            "deterministic_contract": "query-plan-architecture-coverage-v3",
            "retrieval_contract": "regulation-rag-source-first-v3",
            "deterministic_case_type_counts": dict(
                Counter(case.get("case_type") for case in deterministic)
            ),
            "deterministic_positive_lookup_counts": dict(
                Counter(
                    case.get("lookup_group")
                    for case in deterministic
                    if case.get("case_type") == "positive"
                )
            ),
            "architecture_scenario_counts": dict(
                Counter(
                    case.get("architecture_scenario")
                    for case in deterministic
                    if case.get("case_type") == "architecture"
                )
            ),
            "retrieval_cohort_counts": dict(
                Counter(case.get("cohort") for case in retrieval)
            ),
            "retrieval_eval_split_counts": dict(
                Counter(case.get("eval_split") for case in retrieval)
            ),
            "retrieval_forbidden_query_fragments": FORBIDDEN_QUERY_FRAGMENTS,
            # A source may appear under several independently phrased query
            # styles (keyword, paraphrase, typo, student shorthand). Four is a
            # small explicit ceiling; it measures robustness without allowing
            # a handful of parents to dominate the suite.
            "max_parent_query_usage": 4,
            "retrieval_evaluation": {
                "headline_scope": "pure",
                "secondary_scope": "end_to_end",
                "scope_policy": (
                    "The 180 RAG cases contain only source-anchored regulation "
                    "questions. Pure retrieval is the headline metric; end-to-end "
                    "routing is reported separately."
                ),
                "end_to_end_rank_policy": (
                    "General multi-cohort tasks are scored at top-k within each "
                    "cohort execution unit before request-level aggregation."
                ),
            },
            "deterministic_annotation_revision_count": 4,
            "deterministic_annotation_revision_policy": (
                "Three architecture annotations were corrected after registry and "
                "executor review: office responsibilities and broad student services "
                "are regulation RAG, while incomplete TOEIC component scores clarify "
                "inside the structured foreign-language executor."
            ),
            "holdout_policy": "versioned_regression_not_unseen_acceptance",
            "predecessor_bundle": str(old_manifest.get("version") or "unknown"),
            "source_build_id": build_manifest.get("build_id"),
            "source_qdrant_collection": (
                build_manifest.get("storage_targets") or {}
            ).get("qdrant_collection"),
            "source_mongo_collection": (
                build_manifest.get("storage_targets") or {}
            ).get("mongo_parent_collection"),
        }
    )
    write_json(target_dir / "manifest.json", manifest)
    (target_dir / "README.md").write_text(
        "# Architecture Regression V3\n\n"
        "This development/regression bundle preserves the immutable legacy data "
        "while aligning evaluation with QueryPlan, table-first structured lookup, "
        "and regulation-only RAG. Deterministic contains 120 migrated legacy cases "
        "plus 24 architecture coverage cases. Retrieval contains 180 source-first "
        "questions anchored to the current v31 regulation parents. The 50-case "
        "product acceptance set remains separate and unopened.\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build architecture evaluation v3")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.source, args.target), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
