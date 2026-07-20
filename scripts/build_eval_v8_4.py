"""Build V8.4 holdout from the audited V8.3 bundle.

V8.4 keeps the frozen V8.3 cases that still match the production architecture,
replaces retrieval cases that belong to another suite, and regenerates answer
and production cases from the cleaned bundle.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_eval_v8 import (  # noqa: E402
    AI_ROUTER_CONFIG_PATH,
    ANSWER_CONFIG_PATH,
    COHORTS,
    DOCSTORE_PATH,
    LOOKUP_REGISTRY_PATH,
    RETRIEVAL_CONFIG_PATH,
    UNANSWERABLE_QUERIES,
    _structured_source_for_case,
    build_production_cases_v83,
    clean_topic,
    cohort_of,
    content_of,
    content_type_of,
    document_id_of,
    enrich_case,
    metadata,
    parent_id,
    required_facts,
    source_excerpt,
    title_of,
    topic_group,
)
from src.evaluation.dataset import (  # noqa: E402
    file_hash,
    normalize_query,
    stable_json_hash,
    validate_bundle,
    write_json,
)
from src.evaluation.suites import build_human_audit_template  # noqa: E402
from src.generation.io_utils import load_yaml  # noqa: E402


SOURCE_BUNDLE = ROOT / "data" / "eval" / "v8_3_holdout"
SOURCE_AUDIT = (
    ROOT
    / "data"
    / "eval"
    / "reports"
    / "v8_3_holdout"
    / "retrieval_v8_3_failure_audit.json"
)
DEFAULT_OUTPUT = ROOT / "data" / "eval" / "v8_4_holdout"

DATASET_FILES = {
    "deterministic": "deterministic_tool_cases.json",
    "retrieval": "retrieval_cases.json",
    "answers": "generated_answer_cases.json",
    "production": "production_cases.json",
}
RETRIEVAL_COHORT_COUNTS = {"K48-K49": 46, "K50": 45, "K51": 45, "general": 44}
RETRIEVAL_SPLIT_COUNTS = {"realistic": 135, "stress": 45}
NON_HEADLINE_AUDIT_CATEGORIES = {
    "broad_or_under_anchored_query",
    "expected_supplemental_source",
    "structured_or_directory_case",
}
STRUCTURED_TOPICS = {"phong_ban", "bieu_mau", "nganh_hoc"}
LINKED_REALISTIC_QUOTAS = {"K48-K49": 13, "K50": 13, "K51": 13, "general": 12}
LINKED_STRESS_QUOTAS = {"K48-K49": 5, "K50": 4, "K51": 4, "general": 2}
INDEPENDENT_REALISTIC_QUOTAS = {"K48-K49": 5, "K50": 5, "K51": 5, "general": 5}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ascii_fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def is_production_regulation_doc(item: dict[str, Any]) -> bool:
    meta = metadata(item)
    source_id = parent_id(item)
    title = title_of(item)
    return (
        bool(source_id)
        and content_type_of(item) == "regulation_text"
        and meta.get("source_type") != "supplemental_regulation"
        and "Supplement_" not in source_id
        and len(content_of(item)) >= 220
        and "muc luc" not in ascii_fold(title)
        and topic_group(title) not in STRUCTURED_TOPICS
    )


def source_metadata(item: dict[str, Any]) -> dict[str, Any]:
    meta = metadata(item)
    return {
        "parent_section_id": parent_id(item),
        "grade": 2,
        "cohort": cohort_of(item),
        "document_id": document_id_of(item),
        "content_type": content_type_of(item),
        "source_section": title_of(item),
        "source_pages": meta.get("source_pages") or item.get("source_pages") or [],
    }


def replacement_query(
    *,
    cohort: str,
    source_topic: str,
    question_style: str,
    index: int,
) -> tuple[str, str]:
    topic = clean_topic(source_topic)
    if cohort == "general":
        scope = "Trong sổ tay"
        suffix_scope = "trong sổ tay"
    else:
        scope = f"Em thuộc {cohort}"
        suffix_scope = f"cho sinh viên {cohort}"

    if question_style == "typo_no_accent":
        query = (
            f"{ascii_fold(scope)}, muc \"{ascii_fold(topic)}\" "
            f"quy dinh yeu cau nao {ascii_fold(suffix_scope)}?"
        )
        return query, "typo_no_accent"
    if question_style == "paraphrase":
        return (
            f"{scope}, phần \"{topic}\" yêu cầu sinh viên cần làm gì?",
            "paraphrase",
        )
    if question_style == "stress":
        return (
            f"Nguồn quy định trực tiếp về \"{topic}\" {suffix_scope} là mục nào?",
            "stress",
        )
    variants = (
        f"{scope}, ở mục \"{topic}\" sinh viên cần đáp ứng những yêu cầu nào?",
        f"{scope}, mục \"{topic}\" áp dụng những quy định cụ thể nào?",
        f"{scope}, cho em hỏi chính sách trong mục \"{topic}\" yêu cầu những gì?",
    )
    return variants[index % len(variants)], "keyword"


def expected_replacement_quotas(
    retrieval_cases: list[dict[str, Any]],
    non_headline_ids: set[str],
) -> list[dict[str, str]]:
    removed = [case for case in retrieval_cases if case["id"] in non_headline_ids]
    quotas: list[dict[str, str]] = []
    for case in removed:
        quotas.append(
            {
                "cohort": str(case.get("cohort") or "general"),
                "eval_split": str(case.get("eval_split") or "realistic"),
                "question_style": str(case.get("question_style") or "realistic"),
            }
        )
    return quotas


def usage_by_source(cases: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    usage: Counter[tuple[str, str]] = Counter()
    seen: set[tuple[str, str, str]] = set()
    for case in cases:
        normalized = normalize_query(str(case.get("query") or ""))
        for judgment in case.get("relevance_judgments") or []:
            source_id = str(judgment.get("parent_section_id") or "")
            key = (str(case.get("cohort") or ""), source_id, normalized)
            if source_id and key not in seen:
                seen.add(key)
                usage[(str(case.get("cohort") or ""), source_id)] += 1
    return usage


def candidate_docs_for_quota(
    docs: list[dict[str, Any]],
    *,
    cohort: str,
    excluded_source_ids: set[str],
) -> list[dict[str, Any]]:
    candidates = [item for item in docs if is_production_regulation_doc(item)]
    if cohort != "general":
        candidates = [item for item in candidates if cohort_of(item) == cohort]
    else:
        candidates = [item for item in candidates if cohort_of(item) in set(COHORTS)]
    candidates = [item for item in candidates if parent_id(item) not in excluded_source_ids]
    candidates.sort(
        key=lambda item: (
            topic_group(title_of(item)) == "khac",
            cohort_of(item),
            document_id_of(item),
            title_of(item).lower(),
            parent_id(item),
        )
    )
    return candidates


def build_replacements(
    *,
    docs: list[dict[str, Any]],
    quotas: list[dict[str, str]],
    remaining_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    usage = usage_by_source(remaining_cases)
    used_source_ids = {
        str(judgment.get("parent_section_id") or "")
        for case in remaining_cases
        for judgment in case.get("relevance_judgments") or []
    }
    normalized_queries = {
        normalize_query(str(case.get("query") or "")) for case in remaining_cases
    }
    replacements: list[dict[str, Any]] = []
    for index, quota in enumerate(quotas, start=1):
        cohort = quota["cohort"]
        selected_doc: dict[str, Any] | None = None
        selected_query = ""
        selected_query_style = "keyword"
        candidates = candidate_docs_for_quota(
            docs,
            cohort=cohort,
            excluded_source_ids=used_source_ids,
        )
        for item in candidates:
            source_id = parent_id(item)
            if usage[(cohort, source_id)] >= 2:
                continue
            query, query_style = replacement_query(
                cohort=cohort,
                source_topic=title_of(item),
                question_style=quota["question_style"],
                index=index,
            )
            normalized = normalize_query(query)
            if normalized in normalized_queries:
                continue
            selected_doc = item
            selected_query = query
            selected_query_style = query_style
            break
        if selected_doc is None:
            raise RuntimeError(f"Could not find replacement document for quota={quota}")

        source_id = parent_id(selected_doc)
        normalized_queries.add(normalize_query(selected_query))
        used_source_ids.add(source_id)
        usage[(cohort, source_id)] += 1
        case_id = f"v84_ret_new_{index:03d}"
        source_topic = title_of(selected_doc)
        topic = topic_group(f"{source_topic} {content_of(selected_doc)[:400]}")
        tags = [
            "true_rag",
            "citation_required",
            selected_query_style,
            "cohort_sensitive" if cohort != "general" else "cross_cohort_general",
            "v8.4_replacement",
            "regulation_rag",
            quota["eval_split"],
        ]
        replacements.append(
            {
                "id": case_id,
                "suite": "retrieval",
                "case_type": "regulation_true_rag",
                "query": selected_query,
                "cohort": cohort,
                "tags": list(dict.fromkeys(tags)),
                "topic": topic,
                "query_style": selected_query_style,
                "expected_intent": "regulation_query",
                "expected_strategy": "hybrid_graph_retrieval",
                "expected_content_types": ["regulation_text"],
                "relevance_judgments": [source_metadata(selected_doc)],
                "near_duplicate_reviewed": True,
                "annotation_status": "v8_4_replacement_source_anchored",
                "source_topic": source_topic,
                "question_style": quota["question_style"],
                "expected_path": "regulation_rag",
                "cohort_sensitivity": "none"
                if cohort == "general"
                else "multi_cohort_risk",
                "question_specificity": "specific",
                "expected_answer_behavior": "direct_answer",
                "eval_split": quota["eval_split"],
                "duplicate_group": f"v84_source_query_{case_id}",
            }
        )
    return replacements


def select_cases_by_quota(
    cases: list[dict[str, Any]],
    quotas: dict[str, int],
    *,
    eval_split: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    selected_source_keys: set[tuple[str, str]] = set()
    source_usage = usage_by_source(cases)
    for cohort, count in quotas.items():
        cohort_cases: list[dict[str, Any]] = []
        for case in cases:
            if not (
                case.get("case_type") == "regulation_true_rag"
                and case.get("eval_split") == eval_split
                and case.get("cohort") == cohort
            ):
                continue
            source_ids = [
                str(judgment.get("parent_section_id") or "")
                for judgment in case.get("relevance_judgments") or []
            ]
            source_keys = {(cohort, source_id) for source_id in source_ids if source_id}
            if any(source_usage[key] >= 2 for key in source_keys):
                continue
            if source_keys & selected_source_keys:
                continue
            cohort_cases.append(case)
        if len(cohort_cases) < count:
            raise RuntimeError(
                f"Not enough {eval_split} retrieval cases for cohort={cohort}: "
                f"needed {count}, found {len(cohort_cases)}"
            )
        for case in cohort_cases[:count]:
            selected.append(case)
            selected_ids.add(str(case["id"]))
            for judgment in case.get("relevance_judgments") or []:
                source_id = str(judgment.get("parent_section_id") or "")
                if source_id:
                    selected_source_keys.add((cohort, source_id))
    if len(selected_ids) != sum(quotas.values()):
        raise RuntimeError(f"Duplicate selected answer source ids: {selected_ids}")
    return selected


def independent_answer_query(
    *,
    cohort: str,
    source_topic: str,
    index: int,
) -> tuple[str, str]:
    topic = clean_topic(source_topic)
    if cohort == "general":
        variants = (
            f"Trong sổ tay, mục \"{topic}\" nêu những quy định chính nào?",
            f"Sinh viên cần hiểu gì từ mục \"{topic}\" trong sổ tay?",
            f"Mục \"{topic}\" trong sổ tay áp dụng nội dung gì cho sinh viên?",
        )
    else:
        variants = (
            f"Em thuộc {cohort}, mục \"{topic}\" quy định những điểm chính nào?",
            f"Sinh viên {cohort} cần lưu ý gì trong mục \"{topic}\"?",
            f"Với {cohort}, mục \"{topic}\" yêu cầu sinh viên đáp ứng gì?",
        )
    return variants[index % len(variants)], "realistic"


def build_independent_answer_sources(
    docs: list[dict[str, Any]],
    retrieval_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    retrieval_queries = {
        normalize_query(str(case.get("query") or "")) for case in retrieval_cases
    }
    used_source_ids = {
        str(judgment.get("parent_section_id") or "")
        for case in retrieval_cases
        for judgment in case.get("relevance_judgments") or []
    }
    selected: list[dict[str, Any]] = []
    selected_source_ids: set[str] = set()
    selected_queries: set[str] = set()
    for cohort, count in INDEPENDENT_REALISTIC_QUOTAS.items():
        cohort_selected = 0
        for item in candidate_docs_for_quota(
            docs,
            cohort=cohort,
            excluded_source_ids=used_source_ids | selected_source_ids,
        ):
            source_id = parent_id(item)
            query, query_style = independent_answer_query(
                cohort=cohort,
                source_topic=title_of(item),
                index=len(selected) + 1,
            )
            normalized_query = normalize_query(query)
            if (
                normalized_query in retrieval_queries
                or normalized_query in selected_queries
            ):
                continue
            source_topic = title_of(item)
            case_id = f"v84_ans_ind_src_{len(selected) + 1:03d}"
            selected.append(
                {
                    "id": case_id,
                    "suite": "answers",
                    "case_type": "regulation_true_rag",
                    "query": query,
                    "cohort": cohort,
                    "tags": [
                        "true_rag",
                        "citation_required",
                        "independent_answer_holdout",
                        "regulation_rag",
                        query_style,
                        "realistic",
                    ],
                    "topic": topic_group(f"{source_topic} {content_of(item)[:400]}"),
                    "query_style": query_style,
                    "expected_intent": "regulation_query",
                    "expected_strategy": "hybrid_graph_retrieval",
                    "expected_content_types": ["regulation_text"],
                    "relevance_judgments": [source_metadata(item)],
                    "near_duplicate_reviewed": True,
                    "annotation_status": "v8_4_independent_answer_source_anchored",
                    "source_topic": source_topic,
                    "question_style": query_style,
                    "expected_path": "regulation_rag",
                    "cohort_sensitivity": "none"
                    if cohort == "general"
                    else "multi_cohort_risk",
                    "question_specificity": "specific",
                    "expected_answer_behavior": "direct_answer",
                    "eval_split": "realistic",
                    "duplicate_group": f"v84_independent_answer_{case_id}",
                    "source_relation": "independent",
                }
            )
            selected_source_ids.add(source_id)
            selected_queries.add(normalized_query)
            cohort_selected += 1
            if cohort_selected == count:
                break
        if cohort_selected != count:
            raise RuntimeError(
                f"Could not select {count} independent answer cases for {cohort}; "
                f"selected {cohort_selected}"
            )
    return selected


def build_regulation_answer_case(
    *,
    source_case: dict[str, Any],
    source_doc: dict[str, Any],
    answer_id: str,
    source_relation: str,
) -> dict[str, Any]:
    duplicate_group = str(
        source_case.get("duplicate_group") or f"v84_answer_{source_case['id']}"
    )
    query = str(source_case.get("query") or "")
    return enrich_case(
        {
            **source_case,
            "id": answer_id,
            "suite": "answers",
            "query": query,
            "ground_truth": source_excerpt(source_doc, limit=750),
            "required_facts": required_facts(source_doc),
            "forbidden_claims": [],
            "answerability": "answerable",
            "expected_citations": source_case["relevance_judgments"],
            "duplicate_group": duplicate_group,
            "source_relation": source_relation,
            "linked_retrieval_case_id": source_case.get("id")
            if source_relation == "retrieval_linked"
            else None,
            "generation_model": "gemini-3.1-flash-lite",
            "judge_model": "openai/gpt-oss-120b",
        },
        eval_split=str(source_case.get("eval_split") or "realistic"),
    )


def build_structured_answer_cases(
    deterministic_cases: list[dict[str, Any]],
    *,
    starting_index: int,
) -> list[dict[str, Any]]:
    structured_sources = [
        case
        for case in deterministic_cases
        if case.get("case_type") == "positive"
        and case.get("lookup_group")
        in {"office", "service", "program", "foreign_language"}
    ][:4]
    answers: list[dict[str, Any]] = []
    for source_case in structured_sources:
        structured_source = _structured_source_for_case(source_case)
        group = str(source_case.get("lookup_group") or "structured")
        answer_index = starting_index + len(answers)
        structured_query = {
            "foreign_language": (
                f"Case {answer_index}: em thuộc {source_case.get('cohort')}, "
                "nhờ giải thích bảng quy đổi ngoại ngữ cho chứng chỉ phổ biến."
            ),
            "office": (
                f"Case {answer_index}: em học {source_case.get('cohort')}, "
                "cần tra thông tin liên hệ của một phòng ban trong trường."
            ),
            "service": (
                f"Case {answer_index}: {source_case.get('cohort')} muốn biết "
                "đơn vị phụ trách một việc sinh viên thường làm thì tra catalog nào?"
            ),
            "program": (
                f"Case {answer_index}: sinh viên {source_case.get('cohort')} "
                "muốn xem ngành thuộc khoa nào thì trả lời từ danh mục nào?"
            ),
        }.get(group, str(source_case.get("query") or "Tra dữ liệu structured."))
        answers.append(
            enrich_case(
                {
                    **source_case,
                    "id": f"v84_ans_{answer_index:03d}",
                    "suite": "answers",
                    "case_type": "structured_mixed",
                    "query": structured_query,
                    "expected_path": "structured",
                    "ground_truth": (
                        "Trả lời trực tiếp bằng dữ liệu structured catalog đúng "
                        "cohort và đúng nguồn."
                    ),
                    "required_facts": [
                        "Dùng dữ liệu structured catalog đúng cohort.",
                    ],
                    "forbidden_claims": [
                        "Không tự suy đoán thông tin ngoài catalog.",
                    ],
                    "answerability": "answerable",
                    "relevance_judgments": [],
                    "expected_citations": [],
                    "expected_structured_sources": [structured_source],
                    "source_relation": "structured",
                    "generation_model": "gemini-3.1-flash-lite",
                    "judge_model": "openai/gpt-oss-120b",
                },
                eval_split="realistic",
            )
        )
    return answers


def build_unanswerable_answer_cases(*, starting_index: int) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    for index, query in enumerate(UNANSWERABLE_QUERIES):
        answer_index = starting_index + len(answers)
        answers.append(
            enrich_case(
                {
                    "id": f"v84_ans_{answer_index:03d}",
                    "suite": "answers",
                    "case_type": "unanswerable",
                    "query": query,
                    "cohort": COHORTS[index % 3],
                    "tags": ["unanswerable", "abstention"],
                    "topic": "khac",
                    "query_style": "adversarial_unanswerable",
                    "expected_intent": "regulation_query",
                    "expected_strategy": "semantic_filtered",
                    "expected_path": "regulation_rag",
                    "expected_content_types": ["regulation_text"],
                    "relevance_judgments": [],
                    "ground_truth": (
                        "Sổ tay không cung cấp căn cứ để khẳng định nội dung này; "
                        "hệ thống cần nói rõ không tìm thấy thông tin phù hợp."
                    ),
                    "required_facts": ["Không tìm thấy căn cứ trong sổ tay."],
                    "forbidden_claims": [
                        "khẳng định chính sách không có nguồn",
                    ],
                    "answerability": "unanswerable",
                    "expected_citations": [],
                    "source_relation": "unanswerable",
                    "generation_model": "gemini-3.1-flash-lite",
                    "judge_model": "openai/gpt-oss-120b",
                },
                eval_split="stress",
            )
        )
    return answers


def build_answer_cases_v84(
    retrieval_cases: list[dict[str, Any]],
    deterministic_cases: list[dict[str, Any]],
    docs_by_id: dict[str, dict[str, Any]],
    docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    linked_realistic = select_cases_by_quota(
        retrieval_cases,
        LINKED_REALISTIC_QUOTAS,
        eval_split="realistic",
    )
    linked_stress = select_cases_by_quota(
        retrieval_cases,
        LINKED_STRESS_QUOTAS,
        eval_split="stress",
    )
    linked_sources = [*linked_realistic, *linked_stress]
    independent_sources = build_independent_answer_sources(docs, retrieval_cases)

    answers: list[dict[str, Any]] = []
    for source_case in linked_sources:
        primary_id = source_case["relevance_judgments"][0]["parent_section_id"]
        answers.append(
            build_regulation_answer_case(
                source_case=source_case,
                source_doc=docs_by_id[primary_id],
                answer_id=f"v84_ans_{len(answers) + 1:03d}",
                source_relation="retrieval_linked",
            )
        )
    for source_case in independent_sources:
        primary_id = source_case["relevance_judgments"][0]["parent_section_id"]
        answers.append(
            build_regulation_answer_case(
                source_case=source_case,
                source_doc=docs_by_id[primary_id],
                answer_id=f"v84_ans_{len(answers) + 1:03d}",
                source_relation="independent",
            )
        )

    answers.extend(
        build_structured_answer_cases(
            deterministic_cases,
            starting_index=len(answers) + 1,
        )
    )
    answers.extend(build_unanswerable_answer_cases(starting_index=len(answers) + 1))
    if len(answers) != 100:
        raise RuntimeError(f"Expected 100 V8.4 answer cases, built {len(answers)}")
    relation_counts = Counter(str(case.get("source_relation")) for case in answers)
    expected_relations = {
        "retrieval_linked": 66,
        "independent": 20,
        "structured": 4,
        "unanswerable": 10,
    }
    if dict(relation_counts) != expected_relations:
        raise RuntimeError(f"Unexpected answer source relation mix: {relation_counts}")
    return answers


def current_git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def write_readme(output_dir: Path) -> None:
    readme = """# Evaluation Suite V8.4 Holdout

V8.4 is a cleaned holdout derived after auditing V8.3 retrieval failures.
It does not mutate V8.3. Cases that were not valid pure regulation retrieval
targets were replaced with source-anchored production-valid regulation cases.

## Counts

- deterministic_tool_cases.json: 120 cases.
- retrieval_cases.json: 180 regulation RAG cases.
- generated_answer_cases.json: 100 answer cases:
  66 retrieval-linked regulation, 20 independent regulation, 4 structured/mixed,
  and 10 unanswerable.
- production_cases.json: 60 latency/robustness requests.

## Policy

Use V8.4 for the next headline run. Retrieval and deterministic sets are kept
fixed after passing gates. The answer set mixes retrieval-linked and independent
cases before any full judge run. If V8.4 failures are used to tune the system,
create V8.5 before publishing new headline numbers.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")


def build_bundle(output_dir: Path) -> dict[str, Any]:
    docs = load_json(DOCSTORE_PATH)
    docs_by_id = {parent_id(item): item for item in docs if parent_id(item)}
    audit = load_json(SOURCE_AUDIT)
    deterministic = load_json(SOURCE_BUNDLE / DATASET_FILES["deterministic"])
    retrieval_v83 = load_json(SOURCE_BUNDLE / DATASET_FILES["retrieval"])

    non_headline_ids = {
        str(case["id"])
        for case in audit["cases"]
        if case["audit_category"] in NON_HEADLINE_AUDIT_CATEGORIES
    }
    remaining_retrieval = [
        case for case in retrieval_v83 if case["id"] not in non_headline_ids
    ]
    quotas = expected_replacement_quotas(retrieval_v83, non_headline_ids)
    replacements = build_replacements(
        docs=docs,
        quotas=quotas,
        remaining_cases=remaining_retrieval,
    )
    retrieval = [*remaining_retrieval, *replacements]
    retrieval.sort(
        key=lambda case: (
            list(RETRIEVAL_COHORT_COUNTS).index(str(case.get("cohort")))
            if str(case.get("cohort")) in RETRIEVAL_COHORT_COUNTS
            else 99,
            str(case.get("eval_split")),
            str(case.get("id")),
        )
    )
    for case in retrieval:
        case["duplicate_group"] = str(
            case.get("duplicate_group") or f"v84_answer_{case['id']}"
        )

    answers = build_answer_cases_v84(retrieval, deterministic, docs_by_id, docs)
    production = build_production_cases_v83(answers, deterministic)
    datasets = {
        "deterministic": deterministic,
        "retrieval": retrieval,
        "answers": answers,
        "production": production,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    for suite, cases in datasets.items():
        write_json(output_dir / DATASET_FILES[suite], cases)
    audit_template = build_human_audit_template(
        answers,
        [{"id": case["id"]} for case in answers],
    )
    write_json(output_dir / "human_audit_template.json", audit_template)

    answer_config = load_yaml(ANSWER_CONFIG_PATH)
    router_config = load_yaml(AI_ROUTER_CONFIG_PATH)
    manifest = {
        "version": "v8.4-clean-retrieval-holdout",
        "frozen": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "description": (
            "Full-system holdout with V8.3 retrieval label audit applied; "
            "non-headline retrieval cases were replaced, not tuned."
        ),
        "annotation_method": (
            "source-anchored questions plus V8.3 failure audit categories; "
            "V8.4 replacement cases avoid supplemental, directory, and under-anchored labels"
        ),
        "counts": {suite: len(cases) for suite, cases in datasets.items()},
        "dataset_hashes": {
            suite: stable_json_hash(cases) for suite, cases in datasets.items()
        },
        "auxiliary_hashes": {
            "human_audit_template": stable_json_hash(audit_template),
        },
        "git_commit": current_git_commit(),
        "config_hashes": {
            "answer_generation": file_hash(ANSWER_CONFIG_PATH),
            "retrieval": file_hash(RETRIEVAL_CONFIG_PATH),
            "ai_router": file_hash(AI_ROUTER_CONFIG_PATH),
            "structured_lookup_registry": file_hash(LOOKUP_REGISTRY_PATH),
        },
        "docstore_hash": file_hash(DOCSTORE_PATH),
        "generation_provider": str((answer_config.get("llm") or {}).get("provider") or ""),
        "generation_model": str((answer_config.get("llm") or {}).get("model_name") or ""),
        "query_rewriter_model": (
            str((answer_config.get("query_rewriter") or {}).get("model_name") or "")
            if (answer_config.get("query_rewriter") or {}).get("enabled")
            else None
        ),
        "router_provider": str(router_config.get("provider") or "groq"),
        "router_model": str(router_config.get("model_name") or ""),
        "judge_provider": "groq",
        "judge_model": "openai/gpt-oss-120b",
        "headline_backend": "qdrant_cloud+mongodb",
        "legacy_eval_policy": "development_only",
        "holdout_policy": "single_run_no_post_tuning",
        "predecessor_bundles": ["v8", "v8_2_holdout", "v8_3_holdout"],
        "v8_3_retrieval_audit": {
            "source_report": audit.get("source_report"),
            "non_headline_replaced": len(non_headline_ids),
            "replacement_case_ids": [case["id"] for case in replacements],
            "true_misses_carried_forward": [
                case["id"]
                for case in audit["cases"]
                if case["audit_category"] == "true_retrieval_miss"
            ],
        },
        "answer_eval_policy": (
            "100 generated-answer cases: 66 retrieval-linked regulation cases, "
            "20 independent regulation answer holdout cases, 4 structured/mixed "
            "cases, and 10 unanswerable cases. The answer set was finalized "
            "before the full Gemini generation and gpt-oss-120b judge run."
        ),
        "answer_source_relation_counts": dict(
            Counter(str(case.get("source_relation")) for case in answers)
        ),
        "realistic_stress_split": {
            suite: dict(Counter(str(case.get("eval_split")) for case in cases))
            for suite, cases in datasets.items()
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    write_readme(output_dir)

    validation = validate_bundle(output_dir, DOCSTORE_PATH)
    write_json(output_dir / "validation_report.json", validation)
    if not validation["valid"]:
        raise RuntimeError(
            "V8.4 bundle validation failed:\n"
            + "\n".join(validation["errors"][:80])
        )
    return {
        "manifest": manifest,
        "validation": validation,
        "replacement_summary": {
            "removed_non_headline": len(non_headline_ids),
            "added_replacements": len(replacements),
            "replacement_quotas": {
                f"{cohort}:{split}": count
                for (cohort, split), count in Counter(
                    (q["cohort"], q["eval_split"]) for q in quotas
                ).items()
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and freeze V8.4 holdout.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
