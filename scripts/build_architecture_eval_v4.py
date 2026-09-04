from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_architecture_eval_v2 import BUILD_MANIFEST, CONFIG_PATHS, _current_commit
from src.common.cohort import admission_years_for_cohort, is_cohort_applicable
from src.evaluation.dataset import (
    _structured_source_index,
    file_hash,
    load_json,
    normalize_query,
    stable_json_hash,
    validate_bundle,
    write_json,
)


SOURCE = ROOT / "data" / "eval" / "architecture_v3"
TARGET = ROOT / "data" / "eval" / "architecture_v4"
DOCSTORE = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"
COHORTS = ("K48-K49", "K50", "K51")
GENERATION_MODEL = "gemini-3.1-flash-lite"
JUDGE_MODEL = "openai/gpt-oss-120b"

ANSWER_COUNTS = {
    "regulation_true_rag": 72,
    "structured_answer": 30,
    "mixed_answer": 18,
    "clarification": 10,
    "unanswerable": 10,
    "out_of_domain": 10,
}

EXCLUDED_RAG_TITLES = {
    "hiệu lực thi hành",
    "giải thích từ ngữ",
    "phạm vi điều chỉnh và đối tượng áp dụng",
}


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("metadata") or {}


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _ascii_text(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value)
        if unicodedata.category(character) != "Mn"
    )


def _document_scope_label(document_title: str) -> str:
    """Return a short, user-facing regulation name for ambiguous article titles."""

    label = _compact(document_title)
    for marker in (
        " cho sinh viên",
        " đối với sinh viên",
        " tại Trường",
        " của Trường",
    ):
        position = label.casefold().find(marker.casefold())
        if position > 0:
            label = label[:position]
            break
    return label.rstrip(" .,-")


def _topic_from_title(title: str) -> str:
    normalized = _compact(title).casefold()
    if normalized.startswith("phòng ") or "hội đồng" in normalized or "hệ thống tổ chức" in normalized:
        return "phong_ban"
    rules = (
        ("hoc_bong", ("học bổng",)),
        ("hoc_phi", ("học phí", "bồi hoàn", "kinh phí hỗ trợ", "chi phí bồi hoàn", "mức hỗ trợ")),
        ("nghi_hoc", ("nghỉ học", "thôi học", "tạm dừng tiến độ")),
        ("ngoai_ngu", ("ngoại ngữ",)),
        ("tot_nghiep", ("tốt nghiệp", "công nhận kết quả học tập", "chuyển đổi tín chỉ")),
        ("ren_luyen", ("rèn luyện", "kỷ luật", "khen thưởng")),
        ("nganh_hoc", ("ngành", "các khoa", "nghiên cứu khoa học", "chương trình đào tạo")),
    )
    for topic, needles in rules:
        if any(needle in normalized for needle in needles):
            return topic
    return "khac"


def _judgment(source: dict[str, Any], *, grade: int = 2) -> dict[str, Any]:
    metadata = _metadata(source)
    return {
        "parent_section_id": str(source.get("_id") or ""),
        "grade": grade,
        "cohort": metadata.get("cohort") or source.get("cohort"),
        "document_id": metadata.get("document_id") or source.get("document_id"),
        "content_type": metadata.get("content_type"),
        "source_section": metadata.get("title"),
        "source_pages": metadata.get("source_pages") or [],
        "anchor_source": "architecture_v4_human_auditable_source",
    }


def _reference_text(source: dict[str, Any]) -> str:
    content = str(source.get("content") or "").strip()
    if "Nội dung:\n" in content:
        content = content.split("Nội dung:\n", 1)[1].strip()
    return content


def _required_facts_from_text(
    source: dict[str, Any],
    limit: int = 3,
    prefer_terms: tuple[str, ...] = (),
    cohort: str | None = None,
) -> list[str]:
    metadata = _metadata(source)
    title = _compact(metadata.get("title"))
    article = _compact(metadata.get("article"))
    # PDF extraction preserves physical line breaks that do not represent semantic
    # boundaries. Collapse them before splitting so a fact is a complete clause,
    # not a truncated generic-reference fragment.
    content = _compact(_reference_text(source))
    pieces = re.split(r"(?<=[.;!?])\s+", content)
    facts: list[str] = []
    for piece in pieces:
        fact = _compact(piece).strip("-–• ")
        if not (35 <= len(fact) <= 320):
            continue
        normalized_fact = normalize_query(fact)
        admission_years = admission_years_for_cohort(cohort)
        if admission_years:
            older_match = re.search(
                r"tu nam\s+(20\d{2})\s+tro ve truoc",
                normalized_fact,
            )
            newer_match = re.search(
                r"tu nam\s+(20\d{2})(?:\s+tro ve sau)?",
                normalized_fact,
            )
            if older_match and min(admission_years) > int(older_match.group(1)):
                continue
            if (
                newer_match
                and not older_match
                and max(admission_years) < int(newer_match.group(1))
            ):
                continue
        normalized_title = normalize_query(title)
        if title:
            heading_forms = {
                normalized_title,
                normalize_query(f"{article} {title}"),
            }
            is_numbered_heading = bool(
                re.fullmatch(
                    rf"{re.escape(normalized_title)}\s+(?:buoc\s+)?\d+",
                    normalized_fact,
                )
            )
            if normalized_fact in heading_forms or is_numbered_heading:
                continue
        if fact not in facts:
            facts.append(fact)
    if not facts:
        facts = [f"Nội dung phải bám đúng {article} — {title}.".strip()]
    if prefer_terms:
        preferred: list[str] = []
        for term in prefer_terms:
            normalized_term = normalize_query(term)
            preferred.extend(
                fact
                for fact in facts
                if normalized_term in normalize_query(fact) and fact not in preferred
            )
        facts = preferred + [fact for fact in facts if fact not in preferred]
    return facts[:limit]


def _readme_text() -> str:
    return """# Architecture v4 evaluation bundle

This is the frozen-candidate evaluation contract for the current QueryPlan/Composer
architecture. It evaluates four different layers separately so a high score in one
layer cannot hide a defect in another.

## Suite inventory

| Suite | Cases | What it isolates | Primary metrics |
|---|---:|---|---|
| Deterministic tools | 144 | Router, cohort resolution, structured lookup and execution contract | exact path/tool/source match, resolution accuracy |
| Retrieval | 180 | Evidence discovery before answer generation | Hit@1/3/5, MRR, nDCG, cohort leakage |
| Answer quality | 150 | Final answer behavior across all supported paths | correctness, completeness, faithfulness, citation correctness, path/handling accuracy |
| Production | 60 | Deployed API behavior and operational regressions | pass rate, TTFT, latency, stream/metadata contract, availability |

The 150 answer cases are distributed as follows:

- 72 regulation RAG cases: 18 each for K48-K49, K50, K51 and cohort-neutral questions.
- 30 structured cases: 10 lookup groups x 3 cohorts.
- 18 related mixed cases: 6 policy-plus-structured scenarios x 3 cohorts.
- 10 clarification cases with genuinely missing decision-critical information.
- 10 in-domain unanswerable cases whose requested personal/live data is absent.
- 10 clearly out-of-domain cases.

## Why the suites are not merged into one score

- Deterministic exactness answers whether the system selected and executed the right path.
- Retrieval metrics answer whether the needed evidence was found.
- Answer metrics answer whether Composer used that evidence correctly.
- Production metrics answer whether the deployed service still meets its API and latency contract.

Report each family separately. A weighted global score is allowed only as a secondary
dashboard value and must never replace the component metrics.

## Answer-quality protocol

Ground truth and required facts are derived from frozen parent sections or structured
records before any new model output is generated. Every answer case declares its
expected path, answerability, evidence identity and forbidden claims where applicable.

Recommended evaluation stages:

1. Generate exactly one fresh answer for all 150 cases with run metadata recorded.
2. Run the project judge over all 150 cases and keep raw per-case judgments.
3. Run RAGAS on a frozen 60-case answerable subset: 30 RAG, 15 structured and 15 mixed.
4. Human-review the stratified 30-case template; repeat 6 cases to estimate reviewer consistency.
5. Human-review every automatic failure before classifying it as a system defect,
   evaluation-case issue or acceptable minor limitation.

RAGAS faithfulness/relevancy is diagnostic for answerable cases only. Clarification,
abstention and OOD cases are evaluated with handling/path accuracy rather than being
forced into a faithfulness metric that does not fit their contract.

## Headline and diagnostic metrics

Suitable headline metrics:

- deterministic path-and-resolution exactness;
- retrieval Hit@5 and cohort leakage;
- human-reviewed answer correctness and faithfulness;
- production smoke pass rate and TTFT/latency percentiles.

Diagnostic metrics include Hit@1/3, MRR, nDCG, citation correctness, completeness,
RAGAS faithfulness/context precision/context recall/answer relevancy, per-path pass
rates and failure taxonomy. Always publish the denominator beside a percentage.

## Leakage and validity guards

- The bundle must be frozen before generation or judging.
- Source identity includes document, cohort and canonical parent section.
- Cross-cohort evidence is invalid unless explicit applicability metadata permits it.
- Mixed cases require both a structured source and regulation evidence.
- Duplicate normalized queries, missing ground truth and incomplete coverage fail the build.
- Model outputs are not used to author or repair reference answers after a run begins.

`coverage_report.json` records the static audit. `human_audit_template.json` defines
the stratified manual sample, and `ragas_subset.json` pins the 60-case diagnostic
subset before answers are generated. `manifest.json` pins dataset/config/docstore
hashes and states whether the bundle is frozen.
"""


def _base_case(
    *,
    case_id: str,
    case_type: str,
    query: str,
    cohort: str,
    expected_path: str,
    topic: str,
    answerability: str,
    behavior: str,
    eval_split: str = "realistic",
) -> dict[str, Any]:
    return {
        "id": case_id,
        "suite": "answers",
        "case_type": case_type,
        "query": query,
        "cohort": cohort,
        "tags": [
            "architecture_v4",
            "answer_quality",
            eval_split,
            expected_path,
        ],
        "topic": topic,
        "query_style": "student_realistic" if eval_split == "realistic" else "stress",
        "question_style": "realistic" if eval_split == "realistic" else "stress",
        "expected_intent": (
            "query_plan" if expected_path in {"mixed", "clarify"} else f"{expected_path}_query"
        ),
        "expected_strategy": (
            "query_plan_execution" if expected_path == "mixed" else expected_path
        ),
        "expected_path": expected_path,
        "cohort_sensitivity": "single_cohort" if cohort != "general" else "none",
        "question_specificity": (
            "ambiguous"
            if expected_path == "clarify"
            else "unanswerable"
            if answerability == "unanswerable"
            else "specific"
        ),
        "expected_answer_behavior": behavior,
        "eval_split": eval_split,
        "answerability": answerability,
        "relevance_judgments": [],
        "expected_structured_sources": [],
        "expected_citations": [],
        "forbidden_claims": [],
        "near_duplicate_reviewed": False,
        "annotation_status": "source_grounded_pre_output_review",
        "generation_model": GENERATION_MODEL,
        "judge_model": JUDGE_MODEL,
        "contract_version": "answer-quality-source-grounded-v4",
    }


def _natural_rag_query(
    source_title: str,
    cohort: str,
    topic: str,
    *,
    stress: bool,
    variant: int,
    document_scope: str | None = None,
) -> str:
    scope = f"sinh viên {cohort}" if cohort != "general" else "sinh viên HCMUE"
    scope_sentence = scope[0].upper() + scope[1:]
    scoped_title = source_title
    if document_scope:
        scoped_title = f"{source_title} trong {document_scope}"
    normalized_title = _compact(source_title).casefold()
    if stress:
        short_title = _ascii_text(scoped_title).casefold()
        templates = (
            f"{cohort if cohort != 'general' else 'HCMUE'} hỏi nhanh: {short_title} là sao vậy?",
            f"Cho tui hỏi {scope}: {short_title} áp dụng thế nào?",
        )
        return templates[variant % len(templates)]
    if (
        topic == "phong_ban"
        or normalized_title.startswith(("phòng ", "các khoa", "hội đồng", "hiệu trưởng"))
    ):
        return f"{scoped_title} có vai trò và trách nhiệm gì đối với {scope}?"
    if "quy trình" in normalized_title or "thủ tục" in normalized_title:
        return (
            f"Trình tự/thủ tục theo mục {scoped_title} gồm những bước nào, "
            f"mỗi bước do ai thực hiện và áp dụng ra sao cho {scope}?"
        )
    if any(
        term in normalized_title
        for term in ("điều kiện", "tiêu chuẩn", "các trường hợp", "các hành vi")
    ):
        return f"{scoped_title} gồm những nội dung nào và áp dụng ra sao cho {scope}?"
    templates = (
        f"Cho em hỏi quy định chính về {scoped_title} áp dụng cho {scope}?",
        f"{scope_sentence} cần lưu ý gì về {scoped_title} theo sổ tay?",
        f"Bạn tóm tắt giúp em mục {scoped_title} dành cho {scope}?",
    )
    return templates[variant % len(templates)]


def _select_rag_cases(
    retrieval: list[dict[str, Any]], docs_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in retrieval:
        judgments = case.get("relevance_judgments") or []
        source = docs_by_id.get(str((judgments[0] if judgments else {}).get("parent_section_id") or ""))
        if not source:
            continue
        title = normalize_query(str(_metadata(source).get("title") or ""))
        if title in {normalize_query(value) for value in EXCLUDED_RAG_TITLES} or len(str(case.get("query") or "")) > 280:
            continue
        case = copy.deepcopy(case)
        case["topic"] = _topic_from_title(str(_metadata(source).get("title") or ""))
        by_cohort[str(case.get("cohort") or "general")].append(case)

    selected: list[dict[str, Any]] = []
    for cohort in ("K48-K49", "K50", "K51", "general"):
        pool = by_cohort[cohort]
        topic_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for case in pool:
            topic_buckets[str(case.get("topic") or "khac")].append(case)
        cohort_selected: list[dict[str, Any]] = []
        selected_titles: set[str] = set()
        topics = sorted(topic_buckets)
        while topics and len(cohort_selected) < 18:
            next_topics: list[str] = []
            for topic in topics:
                bucket = topic_buckets[topic]
                while bucket and len(cohort_selected) < 18:
                    candidate = bucket.pop(0)
                    judgments = candidate.get("relevance_judgments") or []
                    source = docs_by_id.get(
                        str((judgments[0] if judgments else {}).get("parent_section_id") or "")
                    ) or {}
                    candidate_title = normalize_query(
                        str(_metadata(source).get("title") or "")
                    )
                    if candidate_title in selected_titles:
                        continue
                    selected_titles.add(candidate_title)
                    cohort_selected.append(candidate)
                    break
                if bucket:
                    next_topics.append(topic)
            topics = next_topics
        if len(cohort_selected) != 18:
            raise ValueError(f"Need 18 RAG answer cases for {cohort}, found {len(cohort_selected)}")
        selected.extend(cohort_selected)

    answers: list[dict[str, Any]] = []
    for index, retrieval_case in enumerate(selected, 1):
        judgments = copy.deepcopy(retrieval_case.get("relevance_judgments") or [])
        primary = docs_by_id[str(judgments[0]["parent_section_id"])]
        source_title = _compact(_metadata(primary).get("title"))
        cohort = str(retrieval_case.get("cohort") or "general")
        topic = str(retrieval_case.get("topic") or "khac")
        source_metadata = _metadata(primary)
        # Answer-quality cases must identify their governing document. Generic
    # broad section titles otherwise produce a
        # semantically different question from the frozen parent used as the
        # reference answer. Retrieval robustness is measured in its own suite;
        # this suite isolates whether Composer uses known evidence correctly.
        document_scope = _document_scope_label(
            str(source_metadata.get("document_title") or "")
        ) or None
        query = _natural_rag_query(
            source_title,
            cohort,
            topic,
            stress=str(retrieval_case.get("eval_split") or "realistic") == "stress",
            variant=index - 1,
            document_scope=document_scope,
        )
        case = _base_case(
            case_id=f"v4_ans_rag_{index:03d}",
            case_type="regulation_true_rag",
            query=query,
            cohort=cohort,
            expected_path="regulation_rag",
            topic=topic,
            answerability="answerable",
            behavior=str(retrieval_case.get("expected_answer_behavior") or "scoped_summary"),
            eval_split=str(retrieval_case.get("eval_split") or "realistic"),
        )
        case.update(
            {
                "tags": sorted(set(case["tags"] + list(retrieval_case.get("tags") or []) + ["citation_required", "source_first"])),
                "source_topic": source_title,
                "source_relation": "direct_parent_section",
                "linked_retrieval_case_id": retrieval_case.get("id"),
                "relevance_judgments": judgments,
                "expected_citations": copy.deepcopy(judgments),
                "ground_truth": _reference_text(primary),
                "required_facts": _required_facts_from_text(primary, cohort=cohort),
                "forbidden_claims": [
                    "Không áp dụng quy định của khóa khác nếu nguồn không xác nhận phạm vi áp dụng.",
                    "Không bổ sung điều kiện, thời hạn hoặc ngoại lệ không có trong evidence.",
                ],
                "near_duplicate_reviewed": True,
            }
        )
        answers.append(case)
    return answers


STRUCTURED_SPECS: dict[str, dict[str, Any]] = {
    "foreign_language": {
        "query": "{cohort}: IELTS 5.5 trong bảng quy đổi tương đương bậc ngoại ngữ nào?",
        "source": {cohort: "K50_foreign_language_equivalency_dieu8" for cohort in COHORTS},
        "topic": "ngoai_ngu",
        "expected": "IELTS 5.5 nằm trong khoảng 5.5-6.5, tương đương bậc 4.",
    },
    "study_duration": {
        "query": "Sinh viên {cohort} hệ chính quy được học tối đa bao nhiêu năm?",
        "source": {
            "K48-K49": "K48_49_QuyCheDaoTao_Chuong1_Dieu3_study_duration_chinh_quy",
            "K50": "K50_QuyCheDaoTao_Chuong1_Dieu3_study_duration_chinh_quy",
            "K51": "K51_QuyCheDaoTao_Chuong1_Dieu3_study_duration_chinh_quy",
        },
        "topic": "tot_nghiep",
        "expected": {
            "K48-K49": "Hệ chính quy cấp bằng thứ nhất có thời gian học tối đa 8 năm.",
            "K50": "Hệ chính quy cấp bằng thứ nhất có thời gian học tối đa 8 năm.",
            "K51": "Hệ chính quy có thời gian học tối đa 6 năm.",
        },
    },
    "scholarship": {
        "query": "Mức học bổng Xuất sắc của {cohort} được tính theo công thức nào?",
        "source": {
            "K48-K49": "K48-K49_K48-K49_scoring_tables_6",
            "K50": "K50_K50_scoring_tables_6",
            "K51": "K51_K51_scoring_tables_8",
        },
        "topic": "hoc_bong",
        "expected": "Học bổng Xuất sắc = số tín chỉ x định mức học phí 01 tín chỉ x 1,5.",
    },
    "scoring": {
        "query": "Ở {cohort}, điểm 7,9 trên thang 10 được quy đổi thành điểm chữ nào?",
        "source": {
            "K48-K49": "K48_49_QuyCheDaoTao_Chuong3_Dieu10_grade_scale_general",
            "K50": "K50_QuyCheDaoTao_Chuong3_Dieu10_grade_scale_general",
            "K51": "K51_QuyCheDaoTao_Chuong3_Dieu10_grade_scale_foundation",
        },
        "topic": "diem",
        "expected": "Điểm 7,9 thuộc khoảng 7,8-8,4 và được quy đổi thành B+.",
    },
    "conduct": {
        "query": "Điểm rèn luyện 85 của sinh viên {cohort} được xếp loại gì?",
        "source": {
            "K48-K49": "K48_49_QuyCheDanhGiaKetQuaRenLuyen_Chuong3_Dieu9_conduct_classification",
            "K50": "K50_QuyCheDanhGiaKetQuaRenLuyen_Chuong3_Dieu9_conduct_classification",
            "K51": "K51_QuyCheDanhGiaRenLuyen_Chuong3_Dieu9_conduct_classification",
        },
        "topic": "ren_luyen",
        "expected": "85 điểm rèn luyện thuộc khoảng từ 80 đến dưới 90 điểm, xếp loại Tốt.",
    },
    "service": {
        "query": "Tài khoản sinh viên của {cohort} bị lỗi thì đơn vị nào hỗ trợ?",
        "source": {
            cohort: f"{cohort}_{cohort}_phong_cong_nghe_thong_tin_service_3"
            for cohort in COHORTS
        },
        "topic": "phong_ban",
        "expected": "Đơn vị hỗ trợ tài khoản sinh viên là Phòng Công nghệ Thông tin.",
    },
    "office": {
        "query": "Cho em email và địa chỉ Phòng Đào tạo theo danh bạ {cohort}.",
        "source": {cohort: f"{cohort}_phong_dao_tao" for cohort in COHORTS},
        "topic": "phong_ban",
        "expected": "Trả đúng email và địa chỉ Phòng Đào tạo trong record của cohort được chọn.",
    },
    "faculty": {
        "query": "Khoa Công nghệ Thông tin trong danh bạ {cohort} có email và văn phòng ở đâu?",
        "source": {
            cohort: f"{cohort}_{cohort}_faculty_1_khoa_cong_nghe_thong_tin"
            for cohort in COHORTS
        },
        "topic": "phong_ban",
        "expected": "Trả đúng email và văn phòng Khoa Công nghệ Thông tin trong record của cohort được chọn.",
    },
    "program": {
        "query": "Ngành Công nghệ Thông tin của {cohort} thuộc khoa nào?",
        "source": {
            "K48-K49": "K48-K49_program_2",
            "K50": "K50_program_2",
            "K51": "K51_program_2",
        },
        "topic": "nganh_hoc",
        "expected": {
            "K48-K49": "Ngành Công nghệ Thông tin thuộc Khoa Công nghệ – Thông tin.",
            "K50": "Ngành Công nghệ Thông tin thuộc Khoa Công nghệ Thông tin.",
            "K51": "Ngành Công nghệ Thông tin thuộc Khoa Công nghệ Thông tin.",
        },
    },
    "formula": {
        "query": "Công thức tính điểm trung bình chung tích lũy của {cohort} là gì?",
        "source": {cohort: f"{cohort}_{cohort}_formula_rules_1" for cohort in COHORTS},
        "topic": "diem",
        "expected": "Điểm trung bình chung A = Σ(ai × ni) / Σ(ni), với ni là số tín chỉ của học phần i.",
    },
}


def _record_ground_truth(record: dict[str, Any]) -> str:
    keep = {
        key: record.get(key)
        for key in (
            "table_name",
            "title",
            "name",
            "unit",
            "unit_name",
            "program_name",
            "faculty_name",
            "service",
            "summary",
            "formula_text",
            "variables",
            "rows",
            "phone",
            "phones",
            "email",
            "emails",
            "office",
            "offices",
            "website",
            "websites",
            "applicability",
        )
        if record.get(key) not in (None, "", [], {})
    }
    return json.dumps(keep, ensure_ascii=False, indent=2)


def _expected_structured_fact(
    lookup_group: str,
    spec: dict[str, Any],
    cohort: str,
    record: dict[str, Any],
) -> str:
    """Return the exact fact requested by the query, never an arbitrary first row."""
    if lookup_group in {"office", "faculty"}:
        unit = (
            record.get("faculty_name")
            or record.get("unit_name")
            or record.get("unit")
            or "Đơn vị"
        )
        email = record.get("email") or next(iter(record.get("emails") or []), "")
        office = record.get("office") or next(iter(record.get("offices") or []), "")
        return (
            f"{_compact(unit)}: email {_compact(email)}; "
            f"địa chỉ {_compact(office).rstrip('.')}."
        )
    expected = spec["expected"]
    return str(expected.get(cohort) if isinstance(expected, dict) else expected)


def _structured_answers(
    structured_index: dict[tuple[str, str], dict[str, Any]]
) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    index = 0
    for lookup_group, spec in STRUCTURED_SPECS.items():
        for cohort in COHORTS:
            index += 1
            source_id = spec["source"][cohort]
            record = structured_index.get((lookup_group, source_id))
            if record is None:
                raise ValueError(f"Missing structured source {lookup_group}:{source_id}")
            if not is_cohort_applicable(record, cohort):
                raise ValueError(f"Structured source {source_id} does not apply to {cohort}")
            case = _base_case(
                case_id=f"v4_ans_struct_{index:03d}",
                case_type="structured_answer",
                query=spec["query"].format(cohort=cohort),
                cohort=cohort,
                expected_path="structured",
                topic=spec["topic"],
                answerability="answerable",
                behavior="direct_answer",
            )
            case.update(
                {
                    "lookup_group": lookup_group,
                    "duplicate_group": f"v4_structured_{lookup_group}_cohort_variants",
                    "near_duplicate_reviewed": True,
                    "expected_content_types": ["structured_lookup"],
                    "expected_structured_sources": [
                        {"catalog": lookup_group, "source_id": source_id}
                    ],
                    "ground_truth": _record_ground_truth(record),
                    "required_facts": [
                        _expected_structured_fact(lookup_group, spec, cohort, record)
                    ],
                    "forbidden_claims": [
                        "Không dùng dữ liệu của cohort khác nếu record không xác nhận phạm vi áp dụng.",
                        "Không sao chép toàn bộ bảng vào phần trả lời khi UI đã render bảng riêng.",
                    ],
                    "source_relation": "deterministic_structured_record",
                    "tags": sorted(set(case["tags"] + [lookup_group, "structured_provenance_required"])),
                }
            )
            answers.append(case)
    return answers


MIXED_SPECS = (
    ("foreign_language", "Công nhận đạt chuẩn đầu ra ngoại ngữ để xét tốt nghiệp", "IELTS 5.5 tương đương bậc nào và quy định công nhận chuẩn ngoại ngữ để xét tốt nghiệp ra sao?", "ngoai_ngu"),
    ("scholarship", "Trình tự và thủ tục xét cấp học bổng", "Mức học bổng Xuất sắc tính thế nào và thủ tục xét cấp học bổng gồm những bước gì?", "hoc_bong"),
    ("study_duration", "Nghỉ học tạm thời, tạm dừng tiến độ học tập và tiếp nhận sinh viên trở lại học", "Em được học tối đa bao lâu và nếu cần nghỉ học tạm thời thì điều kiện, hồ sơ thế nào?", "nghi_hoc"),
    ("scoring", "Công nhận tốt nghiệp và cấp bằng tốt nghiệp", "Điểm 7,9 quy đổi thành điểm chữ gì và điều kiện được công nhận tốt nghiệp gồm những gì?", "tot_nghiep"),
    ("conduct", "Quy trình đánh giá kết quả rèn luyện sinh viên", "85 điểm rèn luyện xếp loại gì và quy trình đánh giá kết quả rèn luyện diễn ra thế nào?", "ren_luyen"),
    ("office", "Quyền khiếu nại", "Cho em thông tin liên hệ Phòng Thanh tra Đào tạo và quyền khiếu nại của sinh viên được quy định thế nào?", "phong_ban"),
)

MIXED_FACT_TERMS: dict[str, tuple[str, ...]] = {
    "foreign_language": ("tối thiểu bậc 3/6", "được công nhận đạt chuẩn"),
    "scholarship": ("căn cứ vào quỹ", "để xét học bổng"),
    "study_duration": ("về kết quả học tập", "hồ sơ nghỉ học tạm thời bao gồm"),
    "scoring": ("được xét và công nhận tốt nghiệp", "điểm trung bình tích lũy"),
    "conduct": ("CVHT thông báo", "sinh viên căn cứ"),
    "office": ("có quyền khiếu nại", "trong vòng 07 ngày"),
}


def _find_regulation_source(
    docs: list[dict[str, Any]], cohort: str, title: str
) -> dict[str, Any]:
    wanted = normalize_query(title)
    candidates = [
        item
        for item in docs
        if _metadata(item).get("content_type") == "regulation_text"
        and normalize_query(str(_metadata(item).get("title") or "")) == wanted
        and is_cohort_applicable(item, cohort)
    ]
    if not candidates and "ngoại ngữ" in wanted:
        candidates = [
            item
            for item in docs
            if _metadata(item).get("content_type") == "regulation_text"
            and normalize_query(str(_metadata(item).get("title") or "")) == wanted
            and (_metadata(item).get("cohort") == "K50")
        ]
    if not candidates:
        raise ValueError(f"No regulation source for {cohort}: {title}")
    return sorted(candidates, key=lambda item: str(item.get("_id") or ""))[0]


def _mixed_answers(
    docs: list[dict[str, Any]], structured_index: dict[tuple[str, str], dict[str, Any]]
) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    index = 0
    for cohort in COHORTS:
        for lookup_group, source_title, query, topic in MIXED_SPECS:
            index += 1
            structured_spec = STRUCTURED_SPECS[lookup_group]
            source_id = structured_spec["source"][cohort]
            record = structured_index[(lookup_group, source_id)]
            source = _find_regulation_source(docs, cohort, source_title)
            judgment = _judgment(source)
            if lookup_group == "office":
                source_id = f"{cohort}_phong_thanh_tra_dao_tao"
                record = structured_index[("office", source_id)]
            case = _base_case(
                case_id=f"v4_ans_mixed_{index:03d}",
                case_type="mixed_answer",
                query=f"{cohort}: {query}",
                cohort=cohort,
                expected_path="mixed",
                topic=topic,
                answerability="answerable",
                behavior="direct_answer",
                eval_split="stress" if index % 6 == 0 else "realistic",
            )
            case.update(
                {
                    "lookup_group": lookup_group,
                    "duplicate_group": f"v4_mixed_{lookup_group}_cohort_variants",
                    "near_duplicate_reviewed": True,
                    "expected_content_types": ["structured_lookup", "regulation_text"],
                    "expected_structured_sources": [
                        {"catalog": lookup_group, "source_id": source_id}
                    ],
                    "relevance_judgments": [judgment],
                    "expected_citations": [copy.deepcopy(judgment)],
                    "ground_truth": (
                        "Structured evidence:\n"
                        + _record_ground_truth(record)
                        + "\n\nRegulation evidence:\n"
                        + _reference_text(source)
                    ),
                    "required_facts": [
                        _expected_structured_fact(
                            lookup_group,
                            structured_spec,
                            cohort,
                            record,
                        )
                    ]
                    + _required_facts_from_text(
                        source,
                        limit=2,
                        prefer_terms=MIXED_FACT_TERMS[lookup_group],
                        cohort=cohort,
                    ),
                    "forbidden_claims": [
                        "Không nhập hai answer target thành một khái niệm duy nhất.",
                        "Không bỏ sót một trong hai phần độc lập của câu hỏi.",
                    ],
                    "source_relation": "structured_plus_related_regulation",
                    "tags": sorted(set(case["tags"] + [lookup_group, "multi_intent", "citation_required"])),
                }
            )
            answers.append(case)
    return answers


CLARIFICATION_QUERIES = (
    ("Em chỉ biết tổng TOEIC là 650, vậy có xác định được bậc ngoại ngữ chưa?", "Cần điểm Nghe, Đọc, Nói và Viết của TOEIC 4 kỹ năng.", "ngoai_ngu"),
    ("Phòng đó nằm ở đâu vậy?", "Cần tên phòng hoặc đơn vị cụ thể.", "phong_ban"),
    ("Học bổng của em được bao nhiêu tiền?", "Cần loại học bổng, số tín chỉ và định mức học phí một tín chỉ.", "hoc_bong"),
    ("Điểm 7,0 thì xếp loại gì?", "Cần biết thang điểm và loại xếp hạng đang hỏi.", "diem"),
    ("Em được học tối đa bao lâu?", "Cần hình thức đào tạo và loại chương trình.", "tot_nghiep"),
    ("Khoa này hiện có những ngành nào?", "Cần tên khoa cụ thể.", "nganh_hoc"),
    ("Điểm ngoại ngữ này đủ chuẩn chưa?", "Cần loại chứng chỉ, điểm hoặc cấp độ và chuẩn cần đối chiếu.", "ngoai_ngu"),
    ("Cho em xin email liên hệ.", "Cần tên phòng, khoa hoặc đơn vị cần liên hệ.", "phong_ban"),
    ("Mức cảnh báo của em là bao nhiêu?", "Cần làm rõ cảnh báo học tập, rèn luyện hay kỷ luật.", "khac"),
    ("Điều 16 quy định gì?", "Cần tên quy chế hoặc tài liệu vì nhiều văn bản có Điều 16.", "khac"),
)


UNANSWERABLE_QUERIES = (
    ("Mã số sinh viên của tôi là gì?", "Hệ thống không có hồ sơ cá nhân để xác định mã số sinh viên.", "khac"),
    ("Điểm trung bình học kỳ này của tôi hiện là bao nhiêu?", "Sổ tay không chứa bảng điểm cá nhân.", "diem"),
    ("Hồ sơ xin nghỉ học của tôi đã được duyệt chưa?", "Sổ tay không chứa trạng thái xử lý hồ sơ cá nhân.", "nghi_hoc"),
    ("Lịch thi riêng của tôi tuần tới gồm những môn nào?", "Sổ tay không chứa lịch thi cá nhân theo thời gian thực.", "khac"),
    ("Mật khẩu cổng sinh viên của tôi là gì?", "Hệ thống không lưu hoặc cung cấp mật khẩu cá nhân.", "khac"),
    ("Tài khoản của tôi còn nợ chính xác bao nhiêu học phí?", "Sổ tay không chứa số dư học phí cá nhân.", "hoc_phi"),
    ("Điểm rèn luyện hiện tại của tôi đã được cập nhật chưa?", "Sổ tay không chứa trạng thái điểm rèn luyện cá nhân.", "ren_luyen"),
    ("Tiết 3 hôm nay lớp tôi học phòng nào?", "Sổ tay không chứa thời khóa biểu lớp theo thời gian thực.", "khac"),
    ("Cố vấn học tập của lớp tôi tên gì và số điện thoại bao nhiêu?", "Sổ tay không xác định cố vấn của từng lớp hiện tại.", "phong_ban"),
    ("Hồ sơ tốt nghiệp của tôi sẽ nhận bằng đúng ngày nào?", "Sổ tay không chứa lịch trả kết quả của hồ sơ cá nhân.", "tot_nghiep"),
)


OOD_QUERIES = (
    "Dự báo thời tiết TP.HCM ngày mai thế nào?",
    "Gợi ý quán ăn ngon gần đây cho cuối tuần.",
    "Giá cổ phiếu Nvidia hôm nay bao nhiêu?",
    "Viết giúp tôi một hàm Python sắp xếp danh sách.",
    "Sáng tác một bài thơ tình bốn câu.",
    "Đội nào vô địch Champions League mùa này?",
    "Lập lịch du lịch Đà Lạt ba ngày hai đêm.",
    "Nên mua điện thoại Android nào trong tầm giá 15 triệu?",
    "Mở một bài nhạc thư giãn giúp tôi.",
    "Cách nấu món bò kho ngon tại nhà là gì?",
)


def _negative_answers() -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    for index, (query, clarification, topic) in enumerate(CLARIFICATION_QUERIES, 1):
        cohort = COHORTS[(index - 1) % len(COHORTS)]
        case = _base_case(
            case_id=f"v4_ans_clarify_{index:03d}",
            case_type="clarification",
            query=query,
            cohort=cohort,
            expected_path="clarify",
            topic=topic,
            answerability="unanswerable",
            behavior="clarify_or_scope",
            eval_split="stress",
        )
        case.update(
            {
                "ground_truth": clarification,
                "required_facts": [clarification],
                "forbidden_claims": ["Không tự chọn một cách hiểu hoặc một record khi câu hỏi chưa xác định duy nhất."],
                "tags": sorted(set(case["tags"] + ["ambiguity_required"])),
            }
        )
        answers.append(case)

    for index, (query, reason, topic) in enumerate(UNANSWERABLE_QUERIES, 1):
        cohort = COHORTS[(index - 1) % len(COHORTS)]
        case = _base_case(
            case_id=f"v4_ans_unanswerable_{index:03d}",
            case_type="unanswerable",
            query=query,
            cohort=cohort,
            expected_path="regulation_rag",
            topic=topic,
            answerability="unanswerable",
            behavior="abstain",
            eval_split="stress",
        )
        case.update(
            {
                "ground_truth": reason,
                "required_facts": [reason],
                "forbidden_claims": ["Không bịa dữ liệu cá nhân, trạng thái giao dịch hoặc dữ liệu thời gian thực."],
                "tags": sorted(set(case["tags"] + ["safe_abstention", "in_domain_no_evidence"])),
            }
        )
        answers.append(case)

    for index, query in enumerate(OOD_QUERIES, 1):
        case = _base_case(
            case_id=f"v4_ans_ood_{index:03d}",
            case_type="out_of_domain",
            query=query,
            cohort="general",
            expected_path="out_of_domain",
            topic="khac",
            answerability="unanswerable",
            behavior="abstain",
            eval_split="stress",
        )
        case.update(
            {
                "ground_truth": "Yêu cầu nằm ngoài phạm vi Sổ tay sinh viên HCMUE.",
                "required_facts": ["Nêu ngắn gọn rằng yêu cầu nằm ngoài phạm vi trợ lý Sổ tay sinh viên."],
                "forbidden_claims": ["Không dùng RAG hoặc structured catalog để bịa câu trả lời ngoài phạm vi."],
                "tags": sorted(set(case["tags"] + ["safe_ood"])),
            }
        )
        answers.append(case)
    return answers


def _coverage_report(answers: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    ids = [str(case.get("id") or "") for case in answers]
    queries = [normalize_query(str(case.get("query") or "")) for case in answers]
    if len(ids) != len(set(ids)):
        errors.append("duplicate answer case id")
    if len(queries) != len(set(queries)):
        errors.append("duplicate normalized answer query")
    actual_types = Counter(case.get("case_type") for case in answers)
    if dict(actual_types) != ANSWER_COUNTS:
        errors.append(f"answer type counts mismatch: {dict(actual_types)}")
    rag_cohorts = Counter(
        case.get("cohort")
        for case in answers
        if case.get("case_type") == "regulation_true_rag"
    )
    expected_rag_cohorts = {"K48-K49": 18, "K50": 18, "K51": 18, "general": 18}
    if dict(rag_cohorts) != expected_rag_cohorts:
        errors.append(f"RAG cohort counts mismatch: {dict(rag_cohorts)}")
    structured_groups = Counter(
        case.get("lookup_group")
        for case in answers
        if case.get("case_type") == "structured_answer"
    )
    if set(structured_groups) != set(STRUCTURED_SPECS) or any(
        count != 3 for count in structured_groups.values()
    ):
        errors.append(f"structured group coverage mismatch: {dict(structured_groups)}")
    rag_sources = [
        judgment.get("parent_section_id")
        for case in answers
        if case.get("case_type") == "regulation_true_rag"
        for judgment in case.get("relevance_judgments") or []
        if judgment.get("parent_section_id")
    ]
    for case in answers:
        if not str(case.get("ground_truth") or "").strip():
            errors.append(f"{case.get('id')}: empty ground truth")
        if not case.get("required_facts"):
            errors.append(f"{case.get('id')}: empty required facts")
        if case.get("case_type") == "mixed_answer" and not (
            case.get("relevance_judgments") and case.get("expected_structured_sources")
        ):
            errors.append(f"{case.get('id')}: mixed case missing one evidence family")
    return {
        "contract": "architecture-v4-static-coverage-audit",
        "ok": not errors,
        "errors": errors,
        "answer_count": len(answers),
        "case_type_counts": dict(actual_types),
        "path_counts": dict(Counter(case.get("expected_path") for case in answers)),
        "cohort_counts": dict(Counter(case.get("cohort") for case in answers)),
        "rag_cohort_counts": dict(rag_cohorts),
        "rag_topic_counts": dict(
            sorted(
                Counter(
                    case.get("topic")
                    for case in answers
                    if case.get("case_type") == "regulation_true_rag"
                ).items()
            )
        ),
        "rag_unique_parent_sources": len(set(rag_sources)),
        "rag_parent_source_uses": len(rag_sources),
        "structured_lookup_counts": dict(structured_groups),
        "eval_split_counts": dict(Counter(case.get("eval_split") for case in answers)),
        "answerability_counts": dict(Counter(case.get("answerability") for case in answers)),
        "ground_truth_policy": "Derived only from frozen parent sections or structured records; no model output was inspected.",
    }


def _human_audit_template(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def even_picks(pool: list[dict[str, Any]], quota: int) -> list[dict[str, Any]]:
        if quota == 1:
            return pool[:1]
        return [pool[round(i * (len(pool) - 1) / (quota - 1))] for i in range(quota)]

    selected_cases: list[dict[str, Any]] = []
    for cohort in (*COHORTS, "general"):
        pool = [
            case
            for case in answers
            if case.get("case_type") == "regulation_true_rag"
            and case.get("cohort") == cohort
        ]
        selected_cases.extend(even_picks(pool, 3))
    for cohort in COHORTS:
        pool = [
            case
            for case in answers
            if case.get("case_type") == "structured_answer"
            and case.get("cohort") == cohort
        ]
        selected_cases.extend(even_picks(pool, 2))
    for cohort, quota in zip(COHORTS, (2, 2, 1), strict=True):
        pool = [
            case
            for case in answers
            if case.get("case_type") == "mixed_answer" and case.get("cohort") == cohort
        ]
        selected_cases.extend(even_picks(pool, quota))
    selected_cases.extend(
        [case for case in answers if case.get("case_type") == "clarification"][:2]
    )
    selected_cases.extend(
        [case for case in answers if case.get("case_type") == "unanswerable"][1:3]
    )
    selected_cases.extend(
        [case for case in answers if case.get("case_type") == "out_of_domain"][:3]
    )

    selected: list[dict[str, Any]] = []
    repeated_types: set[str] = set()
    for case in selected_cases:
        case_type = str(case["case_type"])
        repeat = case_type not in repeated_types
        if repeat:
            repeated_types.add(case_type)
        selected.append(
            {
                "id": case["id"],
                "case_type": case_type,
                "query": case["query"],
                "cohort": case["cohort"],
                "repeat_for_consistency": repeat,
                "human_verdict": None,
                "correctness": None,
                "faithfulness": None,
                "citation_correctness": None,
                "completeness": None,
                "notes": "",
            }
        )
    return selected


def _ragas_subset(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(case["id"]): case for case in answers}
    selected_ids: list[str] = []

    rag_quotas = {"K48-K49": 8, "K50": 8, "K51": 7, "general": 7}
    for cohort, quota in rag_quotas.items():
        pool = [
            case
            for case in answers
            if case.get("case_type") == "regulation_true_rag"
            and case.get("cohort") == cohort
        ]
        selected_ids.extend(
            case["id"]
            for case in [
                pool[round(i * (len(pool) - 1) / (quota - 1))]
                for i in range(quota)
            ]
        )

    structured = [
        case for case in answers if case.get("case_type") == "structured_answer"
    ]
    structured_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in structured:
        structured_by_group[str(case["lookup_group"])].append(case)
    groups = list(STRUCTURED_SPECS)
    for group_index, group in enumerate(groups):
        cohort = COHORTS[group_index % len(COHORTS)]
        selected_ids.append(
            next(
                case["id"]
                for case in structured_by_group[group]
                if case.get("cohort") == cohort
            )
        )
    for group_index, group in enumerate(groups[:5]):
        cohort = COHORTS[(group_index + 1) % len(COHORTS)]
        selected_ids.append(
            next(
                case["id"]
                for case in structured_by_group[group]
                if case.get("cohort") == cohort
            )
        )

    mixed = [case for case in answers if case.get("case_type") == "mixed_answer"]
    omitted_lookup_by_cohort = {
        "K48-K49": "foreign_language",
        "K50": "study_duration",
        "K51": "conduct",
    }
    selected_ids.extend(
        case["id"]
        for case in mixed
        if case.get("lookup_group")
        != omitted_lookup_by_cohort[str(case.get("cohort"))]
    )

    subset: list[dict[str, Any]] = []
    for case_id in selected_ids:
        case = by_id[case_id]
        subset.append(
            {
                "id": case_id,
                "case_type": case["case_type"],
                "cohort": case["cohort"],
                "user_input": case["query"],
                "reference": case["ground_truth"],
                "response": None,
                "retrieved_contexts": [],
                "expected_citations": case.get("expected_citations") or [],
                "expected_structured_sources": case.get("expected_structured_sources") or [],
            }
        )
    return subset


def build_bundle(target_dir: Path, *, freeze: bool) -> dict[str, Any]:
    docs = load_json(DOCSTORE)
    docs_by_id = {str(item.get("_id") or ""): item for item in docs}
    structured_index = _structured_source_index(ROOT)
    retrieval = copy.deepcopy(load_json(SOURCE / "retrieval_cases.json"))
    answers = (
        _select_rag_cases(retrieval, docs_by_id)
        + _structured_answers(structured_index)
        + _mixed_answers(docs, structured_index)
        + _negative_answers()
    )
    coverage = _coverage_report(answers)
    if not coverage["ok"]:
        raise ValueError("Static coverage audit failed: " + "; ".join(coverage["errors"]))

    datasets = {
        "deterministic": copy.deepcopy(load_json(SOURCE / "deterministic_tool_cases.json")),
        "retrieval": retrieval,
        "answers": answers,
        "production": copy.deepcopy(load_json(SOURCE / "production_cases.json")),
    }
    target_dir.mkdir(parents=True, exist_ok=True)
    filenames = {
        "deterministic": "deterministic_tool_cases.json",
        "retrieval": "retrieval_cases.json",
        "answers": "generated_answer_cases.json",
        "production": "production_cases.json",
    }
    for suite, cases in datasets.items():
        write_json(target_dir / filenames[suite], cases)
    audit_template = _human_audit_template(answers)
    ragas_subset = _ragas_subset(answers)
    audit_type_counts = Counter(row["case_type"] for row in audit_template)
    ragas_type_counts = Counter(row["case_type"] for row in ragas_subset)
    expected_audit_types = {
        "regulation_true_rag": 12,
        "structured_answer": 6,
        "mixed_answer": 5,
        "clarification": 2,
        "unanswerable": 2,
        "out_of_domain": 3,
    }
    expected_ragas_types = {
        "regulation_true_rag": 30,
        "structured_answer": 15,
        "mixed_answer": 15,
    }
    auxiliary_errors: list[str] = []
    if len(audit_template) != 30 or len({row["id"] for row in audit_template}) != 30:
        auxiliary_errors.append("human audit must contain 30 unique cases")
    if dict(audit_type_counts) != expected_audit_types:
        auxiliary_errors.append(f"human audit type counts mismatch: {dict(audit_type_counts)}")
    if sum(bool(row["repeat_for_consistency"]) for row in audit_template) != 6:
        auxiliary_errors.append("human audit must mark 6 consistency repeats")
    if len(ragas_subset) != 60 or len({row["id"] for row in ragas_subset}) != 60:
        auxiliary_errors.append("RAGAS subset must contain 60 unique cases")
    if dict(ragas_type_counts) != expected_ragas_types:
        auxiliary_errors.append(f"RAGAS type counts mismatch: {dict(ragas_type_counts)}")
    if auxiliary_errors:
        raise ValueError("Auxiliary coverage audit failed: " + "; ".join(auxiliary_errors))
    coverage.update(
        {
            "human_audit_case_type_counts": dict(audit_type_counts),
            "human_audit_cohort_counts": dict(
                Counter(row["cohort"] for row in audit_template)
            ),
            "human_audit_consistency_repeat_count": sum(
                bool(row["repeat_for_consistency"]) for row in audit_template
            ),
            "ragas_subset_case_type_counts": dict(ragas_type_counts),
            "ragas_subset_cohort_counts": dict(
                Counter(row["cohort"] for row in ragas_subset)
            ),
        }
    )
    write_json(target_dir / "human_audit_template.json", audit_template)
    write_json(target_dir / "ragas_subset.json", ragas_subset)
    write_json(target_dir / "coverage_report.json", coverage)

    old_manifest = load_json(SOURCE / "manifest.json")
    build_manifest = load_json(BUILD_MANIFEST)
    manifest = copy.deepcopy(old_manifest)
    manifest.update(
        {
            "version": "architecture-v4.0-comprehensive-answer-evaluation",
            "frozen": freeze,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "description": (
                "Comprehensive source-grounded answer evaluation with realistic RAG, "
                "all structured lookup groups, related mixed tasks, clarification, "
                "in-domain abstention, and out-of-domain handling."
            ),
            "git_commit": _current_commit(),
            "counts": {suite: len(cases) for suite, cases in datasets.items()},
            "dataset_hashes": {
                suite: stable_json_hash(cases) for suite, cases in datasets.items()
            },
            "auxiliary_hashes": {
                "human_audit_template": stable_json_hash(audit_template),
                "ragas_subset": stable_json_hash(ragas_subset),
                "coverage_report": stable_json_hash(coverage),
            },
            "docstore_hash": file_hash(DOCSTORE),
            "config_hashes": {
                name: file_hash(path) for name, path in CONFIG_PATHS.items()
            },
            "evaluation_contract": "comprehensive-source-grounded-answer-v4",
            "answer_contract": "answer-quality-source-grounded-v4",
            "answer_case_type_counts": dict(Counter(case["case_type"] for case in answers)),
            "answer_path_counts": dict(Counter(case["expected_path"] for case in answers)),
            "answer_eval_split_counts": dict(Counter(case["eval_split"] for case in answers)),
            "answer_cohort_counts": dict(Counter(case["cohort"] for case in answers)),
            "answer_rag_cohort_counts": {
                "K48-K49": 18,
                "K50": 18,
                "K51": 18,
                "general": 18,
            },
            "answer_structured_lookup_counts": {
                lookup: 3 for lookup in STRUCTURED_SPECS
            },
            "human_audit_required_n": 30,
            "human_audit_repeat_n": 6,
            "holdout_policy": "frozen_before_generation_and_judging",
            "predecessor_bundle": old_manifest.get("version"),
            "annotation_policy": (
                "Questions and labels were authored from current source evidence before "
                "new model outputs. Ambiguous cohort-conflict cases and unrelated synthetic "
                "mixed pairs from v3 were not inherited."
            ),
            "ragas_subset_policy": (
                "Select 60 stratified answerable cases after bundle freeze: 30 RAG, "
                "15 structured, 15 mixed. Do not use clarification, abstention or OOD "
                "for RAGAS faithfulness/relevancy headline metrics."
            ),
            "source_build_id": build_manifest.get("build_id"),
            "source_qdrant_collection": build_manifest.get("qdrant_collection")
            or old_manifest.get("source_qdrant_collection"),
            "source_mongo_collection": build_manifest.get("mongo_collection")
            or old_manifest.get("source_mongo_collection"),
        }
    )
    write_json(target_dir / "manifest.json", manifest)
    (target_dir / "README.md").write_text(_readme_text(), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    manifest = build_bundle(args.target, freeze=args.freeze)
    validation = validate_bundle(
        args.target,
        DOCSTORE,
        require_frozen=args.freeze,
        enforce_docstore_hash=True,
    )
    # Keep CLI output portable on Windows consoles whose default code page cannot
    # encode Vietnamese characters. Dataset files themselves remain UTF-8.
    print(json.dumps({"manifest": manifest, "validation": validation}, ensure_ascii=True, indent=2))
    if validation.get("errors"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
