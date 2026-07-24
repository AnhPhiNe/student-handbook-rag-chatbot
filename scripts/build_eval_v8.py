from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.dataset import (
    file_hash,
    normalize_query,
    stable_json_hash,
    validate_bundle,
    write_json,
)
from src.generation.io_utils import load_yaml
from src.evaluation.suites import build_human_audit_template


DEFAULT_OUTPUT = ROOT / "data" / "eval" / "v8"
DOCSTORE_PATH = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"
ANSWER_CONFIG_PATH = ROOT / "configs" / "answer_generation.yaml"
RETRIEVAL_CONFIG_PATH = ROOT / "configs" / "retrieval.yaml"
AI_ROUTER_CONFIG_PATH = ROOT / "configs" / "ai_router.yaml"
LOOKUP_REGISTRY_PATH = ROOT / "configs" / "structured_lookup_registry.yaml"
GRAPH_PATH = ROOT / "data" / "processed" / "graphs" / "document_edges.json"


COHORTS = ["K48-K49", "K50", "K51"]
REGULATION_COUNTS = {"K48-K49": 30, "K50": 30, "K51": 30, "general": 30}
V83_REGULATION_COUNTS = {"K48-K49": 34, "K50": 34, "K51": 34, "general": 33}
V83_STRESS_COUNTS = {"K48-K49": 12, "K50": 11, "K51": 11, "general": 11}

SYNTHETIC_CONTENT_TYPES = [
    "student_service_directory",
    "student_office_profile",
    "structured_lookup",
    "foreign_language_equivalency",
    "formula_rule",
    "program_directory",
    "faculty_program_directory",
    "threshold_rule",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def metadata(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("metadata") or {}


def parent_id(item: dict[str, Any]) -> str:
    meta = metadata(item)
    return str(item.get("_id") or meta.get("parent_section_id") or "").strip()


def cohort_of(item: dict[str, Any]) -> str:
    return str(metadata(item).get("cohort") or item.get("cohort") or "").strip()


def document_id_of(item: dict[str, Any]) -> str:
    return str(
        metadata(item).get("document_id") or item.get("document_id") or ""
    ).strip()


def content_type_of(item: dict[str, Any]) -> str:
    return str(
        metadata(item).get("content_type") or item.get("content_type") or ""
    ).strip()


def title_of(item: dict[str, Any]) -> str:
    meta = metadata(item)
    value = meta.get("title") or meta.get("source_section") or item.get("title")
    return re.sub(r"\s+", " ", str(value or "Nội dung trong sổ tay")).strip()


def content_of(item: dict[str, Any]) -> str:
    return re.sub(
        r"\s+", " ", str(item.get("content") or item.get("text") or "")
    ).strip()


def clean_topic(title: str) -> str:
    topic = re.sub(
        r"^\s*Điều\s+\d+[a-zA-Z]?\s*[.:-]?\s*", "", title, flags=re.IGNORECASE
    )
    topic = re.sub(r"\s+", " ", topic).strip(" .:-")
    return topic or title


def _ascii_fold(value: str) -> str:
    import unicodedata

    text = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"\s+", " ", text.lower()).strip()


def topic_group(value: str) -> str:
    text = _ascii_fold(value)
    if any(term in text for term in ("hoc bong", "mien giam", "tro cap")):
        return "hoc_bong"
    if any(term in text for term in ("hoc phi", "sinh hoat phi", "chi phi")):
        return "hoc_phi"
    if any(term in text for term in ("tam nghi", "bao luu", "nghi hoc", "thoi hoc")):
        return "nghi_hoc"
    if any(term in text for term in ("diem", "thang 4", "thang 10", "hoc luc")):
        return "diem"
    if any(term in text for term in ("ren luyen", "ky luat")):
        return "ren_luyen"
    if any(term in text for term in ("tot nghiep", "chuan dau ra", "cong nhan")):
        return "tot_nghiep"
    if any(term in text for term in ("ngoai ngu", "ielts", "toeic", "jlpt", "toefl")):
        return "ngoai_ngu"
    if any(term in text for term in ("phong", "trung tam", "email", "lien he", "ktx")):
        return "phong_ban"
    if any(term in text for term in ("nganh", "khoa", "chuong trinh dao tao")):
        return "nganh_hoc"
    return "khac"


def question_style_from_case(case: dict[str, Any]) -> str:
    case_type = str(case.get("case_type") or "")
    query_style = str(case.get("query_style") or "")
    tags = set(case.get("tags") or [])
    if case_type == "unanswerable" or "unanswerable" in tags:
        return "unanswerable"
    if case_type == "ambiguous" or "ambiguous" in tags:
        return "ambiguous"
    if "typo" in query_style or "typo_no_diacritics" in tags:
        return "typo_no_accent"
    if "stress" in query_style or "adversarial" in query_style:
        return "stress"
    if "paraphrase" in query_style or "paraphrase" in tags:
        return "paraphrase"
    return "realistic"


def expected_path_from_case(case: dict[str, Any]) -> str:
    expected_group = case.get("expected_group")
    expected_strategy = str(case.get("expected_strategy") or "")
    case_type = str(case.get("case_type") or "")
    if expected_group == "guardrail" or expected_strategy == "none":
        return "out_of_domain"
    if expected_group == "clarification_or_rag" or case_type == "ambiguous":
        return "clarify"
    if expected_group in {"deterministic", "structured"} or case_type == "positive":
        return "structured"
    if case_type == "structured_mixed":
        return "mixed"
    if "structured" in expected_strategy and "semantic" in expected_strategy:
        return "mixed"
    return "regulation_rag"


def cohort_sensitivity_from_case(case: dict[str, Any]) -> str:
    cohort = str(case.get("cohort") or "")
    tags = set(case.get("tags") or [])
    if cohort in {"", "general", "all", "None"}:
        return "multi_cohort_risk" if "cross_cohort_general" in tags else "none"
    return "multi_cohort_risk" if "cohort_sensitive" in tags else "single_cohort"


def question_specificity_from_case(case: dict[str, Any]) -> str:
    text = normalize_query(
        " ".join(
            str(value or "")
            for value in (
                case.get("query"),
                case.get("question_style"),
                case.get("case_type"),
            )
        )
    )
    tags = set(case.get("tags") or [])
    if case.get("answerability") == "unanswerable" or "unanswerable" in tags:
        return "unanswerable"
    if case.get("expected_path") == "clarify" or "ambiguous" in tags:
        return "ambiguous"
    broad_cues = (
        "nhu the nao",
        "quy dinh cu the",
        "noi dung chinh",
        "can luu y",
        "ra sao",
        "giai thich",
        "nguon nao",
        "nguon nao moi dung",
        "nguon nao moi ung",
        "khoa khac noi khac",
        "la sao",
    )
    if any(cue in text for cue in broad_cues):
        return "broad"
    if any(tag in tags for tag in ("numeric_fact", "table_heavy", "direct_lookup")):
        return "specific"
    return "specific"


def expected_answer_behavior_from_case(case: dict[str, Any]) -> str:
    specificity = case.get("question_specificity") or question_specificity_from_case(case)
    if specificity == "unanswerable" or case.get("expected_path") == "out_of_domain":
        return "abstain"
    if specificity == "ambiguous" or case.get("expected_path") == "clarify":
        return "clarify_or_scope"
    if specificity == "broad":
        return "scoped_summary"
    return "direct_answer"


def enrich_case(case: dict[str, Any], *, eval_split: str | None = None) -> dict[str, Any]:
    item = dict(case)
    source_topic = item.get("source_topic") or item.get("topic")
    if source_topic and str(source_topic) not in {
        "hoc_bong",
        "hoc_phi",
        "nghi_hoc",
        "diem",
        "ren_luyen",
        "tot_nghiep",
        "ngoai_ngu",
        "phong_ban",
        "bieu_mau",
        "nganh_hoc",
        "khac",
    }:
        item["source_topic"] = source_topic
    item["topic"] = topic_group(
        " ".join(
            str(value or "")
            for value in (
                item.get("query"),
                item.get("source_topic"),
                item.get("lookup_group"),
                item.get("expected_lookup_type"),
            )
        )
    )
    item["question_style"] = item.get("question_style") or question_style_from_case(item)
    item["expected_path"] = item.get("expected_path") or expected_path_from_case(item)
    item["cohort_sensitivity"] = item.get(
        "cohort_sensitivity"
    ) or cohort_sensitivity_from_case(item)
    item["question_specificity"] = question_specificity_from_case(item)
    item["expected_answer_behavior"] = expected_answer_behavior_from_case(item)
    item["eval_split"] = eval_split or item.get("eval_split") or (
        "stress"
        if item["question_style"] in {"stress", "ambiguous", "unanswerable"}
        or item.get("case_type") in {"hard_negative", "out_of_domain"}
        else "realistic"
    )
    tags = list(dict.fromkeys([*(item.get("tags") or []), item["question_style"], item["expected_path"], item["eval_split"]]))
    item["tags"] = tags
    return item


def source_excerpt(item: dict[str, Any], limit: int = 900) -> str:
    sentences = _source_sentences(item)
    value = " ".join(sentences[:3]) or content_of(item)
    return value[:limit].rsplit(" ", 1)[0] if len(value) > limit else value


def _source_sentences(item: dict[str, Any]) -> list[str]:
    text = content_of(item)
    body_marker = re.search(r"\bNội dung:\s*", text, flags=re.IGNORECASE)
    if body_marker:
        text = text[body_marker.end() :].strip()
    title = title_of(item)
    if text.lower().startswith(title.lower()):
        text = text[len(title) :].lstrip(" .:-")
    candidates = [
        part.strip()
        for part in re.split(r"(?<=[.!?;])\s+|\n+", text)
        if part.strip()
    ]
    sentences: list[str] = []
    title_norm = normalize_query(title)
    for candidate in candidates:
        sentence = re.sub(r"^[0-9]+[.)]\s*", "", candidate).strip()
        sentence = re.sub(r"^[a-zA-ZÀ-ỹ][.)]\s*", "", sentence).strip()
        sentence_norm = normalize_query(sentence)
        if len(sentence) < 35:
            continue
        if sentence_norm == title_norm or sentence_norm.startswith("dieu "):
            continue
        if not re.search(r"[a-zA-ZÀ-ỹ]{4,}", sentence):
            continue
        sentences.append(sentence)
    return sentences


def required_facts(item: dict[str, Any]) -> list[str]:
    sentences = _source_sentences(item)
    numeric = [sentence for sentence in sentences if re.search(r"\d", sentence)]
    facts: list[str] = []
    if numeric:
        facts.append(numeric[0][:320])
    if sentences:
        first_fact = sentences[0][:320]
        if normalize_query(first_fact) not in {normalize_query(fact) for fact in facts}:
            facts.append(first_fact)
    fallback = source_excerpt(item, limit=320)
    return facts[:2] or ([fallback] if fallback else [])


def question_for_source(
    item: dict[str, Any], index: int, *, general: bool = False
) -> str:
    cohort = cohort_of(item)
    topic = clean_topic(title_of(item)).lower()
    prefixes = [
        "Cho em hỏi",
        "Em chưa rõ",
        "Trong sổ tay",
        "Nhờ giải thích giúp em",
        "Nếu cần áp dụng đúng quy định",
        "Sinh viên cần hiểu thế nào về",
    ]
    suffixes = [
        "được quy định cụ thể như thế nào?",
        "có những điều kiện và mốc nào cần lưu ý?",
        "thì em cần thực hiện hoặc đáp ứng những gì?",
        "có điểm nào dễ bị hiểu nhầm không?",
        "áp dụng cho sinh viên ra sao?",
        "nội dung chính trong sổ tay là gì?",
    ]
    prefix = prefixes[index % len(prefixes)]
    suffix = suffixes[(index * 5 + 1) % len(suffixes)]
    scope = "" if general else f"Em thuộc {cohort}, "
    if index % 7 == 3:
        return f"{scope}{topic} la sao va can luu y gi theo so tay?"
    return f"{scope}{prefix} {topic} {suffix}"


def _source_metadata(item: dict[str, Any], grade: int = 2) -> dict[str, Any]:
    meta = metadata(item)
    return {
        "parent_section_id": parent_id(item),
        "grade": grade,
        "cohort": cohort_of(item),
        "document_id": meta.get("document_id") or item.get("document_id"),
        "content_type": content_type_of(item),
        "source_section": title_of(item),
        "source_pages": meta.get("source_pages") or item.get("source_pages") or [],
    }


def build_regulation_cases(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    graph_edges = (
        json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        if GRAPH_PATH.exists()
        else []
    )
    graph_node_ids = {
        str(edge.get(field) or "")
        for edge in graph_edges
        for field in ("source", "target")
        if edge.get(field)
    }
    regulation = [
        item
        for item in docs
        if content_type_of(item) == "regulation_text"
        and parent_id(item)
        and len(content_of(item)) >= 180
        and "mục lục" not in title_of(item).lower()
    ]
    by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in regulation:
        by_cohort[cohort_of(item)].append(item)
    for items in by_cohort.values():
        items.sort(key=lambda item: (title_of(item).lower(), parent_id(item)))

    selected_by_cohort: dict[str, list[dict[str, Any]]] = {}
    for cohort in COHORTS:
        candidates = by_cohort[cohort]
        step = max(1, len(candidates) // REGULATION_COUNTS[cohort])
        selected = candidates[::step][: REGULATION_COUNTS[cohort]]
        if len(selected) < REGULATION_COUNTS[cohort]:
            selected_ids = {parent_id(item) for item in selected}
            selected.extend(
                item for item in candidates if parent_id(item) not in selected_ids
            )
        selected_by_cohort[cohort] = selected[: REGULATION_COUNTS[cohort]]
    all_primary_ids = {
        parent_id(item) for items in selected_by_cohort.values() for item in items
    }
    docs_by_id = {parent_id(item): item for item in docs if parent_id(item)}
    outbound: dict[str, list[str]] = defaultdict(list)
    for edge in graph_edges:
        outbound[str(edge.get("source") or "")].append(str(edge.get("target") or ""))
    used_support_ids: set[str] = set()

    cases: list[dict[str, Any]] = []
    for cohort in COHORTS:
        selected = selected_by_cohort[cohort]
        for item in selected:
            index = len(cases)
            support_id = next(
                (
                    target
                    for target in outbound.get(parent_id(item), [])
                    if target in docs_by_id
                    and target not in all_primary_ids
                    and target not in used_support_ids
                    and cohort_of(docs_by_id[target]) == cohort
                    and document_id_of(docs_by_id[target]) == document_id_of(item)
                ),
                None,
            )
            judgments = [_source_metadata(item)]
            if support_id:
                judgments.append(_source_metadata(docs_by_id[support_id], 1))
                used_support_ids.add(support_id)
            style = [
                "keyword",
                "paraphrase",
                "student_style",
                "typo_no_diacritics",
                "numeric_or_fact",
                "condition_procedure",
                "graph_reference",
                "cohort_sensitive",
            ][index % 8]
            if support_id:
                style = "graph_reference"
            elif style == "graph_reference" and parent_id(item) not in graph_node_ids:
                style = "condition_procedure"
            tags = [
                "true_rag",
                "citation_required",
                "numeric_fact" if re.search(r"\d", content_of(item)) else "text_fact",
                style,
                "cohort_sensitive",
            ]
            cases.append(
                {
                    "id": f"v8_ret_reg_{index + 1:03d}",
                    "suite": "retrieval",
                    "case_type": "regulation_true_rag",
                    "query": (
                        f"Em thuộc {cohort}, mục {clean_topic(title_of(item)).lower()} "
                        "có dẫn chiếu tới Điều nào và nội dung liên quan ra sao?"
                        if support_id
                        else question_for_source(item, index)
                    ),
                    "cohort": cohort,
                    "tags": tags,
                    "topic": clean_topic(title_of(item)),
                    "query_style": style,
                    "expected_intent": "regulation_query",
                    "expected_strategy": "hybrid_graph_retrieval",
                    "expected_content_types": ["regulation_text"],
                    "relevance_judgments": judgments,
                    "near_duplicate_reviewed": True,
                    "annotation_status": "source_anchored",
                }
            )

    title_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in regulation:
        key = clean_topic(title_of(item)).lower()
        title_groups[key].append(item)
    general_candidates = [
        items
        for _, items in sorted(title_groups.items())
        if len({cohort_of(item) for item in items}) >= 2
    ]
    for items in general_candidates[: REGULATION_COUNTS["general"]]:
        representative = items[0]
        index = len(cases)
        judgments = [
            _source_metadata(item, 2 if item_index == 0 else 1)
            for item_index, item in enumerate(items[:3])
        ]
        cases.append(
            {
                "id": f"v8_ret_reg_{index + 1:03d}",
                "suite": "retrieval",
                "case_type": "regulation_true_rag",
                "query": question_for_source(representative, index, general=True),
                "cohort": "general",
                "tags": [
                    "true_rag",
                    "citation_required",
                    "cross_cohort_general",
                    "multi_source",
                ],
                "topic": clean_topic(title_of(representative)),
                "query_style": ["keyword", "paraphrase", "student_style"][index % 3],
                "expected_intent": "regulation_query",
                "expected_strategy": "hybrid_graph_retrieval",
                "expected_content_types": ["regulation_text"],
                "relevance_judgments": judgments,
                "near_duplicate_reviewed": True,
                "annotation_status": "source_anchored",
            }
        )
    if len(cases) != 120:
        raise RuntimeError(f"Expected 120 regulation cases, built {len(cases)}")
    return cases


def build_synthetic_cases(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for cohort in COHORTS:
        candidates = [
            item
            for item in docs
            if cohort_of(item) == cohort
            and content_type_of(item) in SYNTHETIC_CONTENT_TYPES
            and parent_id(item)
            and len(content_of(item)) >= 40
        ]
        candidates.sort(
            key=lambda item: (
                SYNTHETIC_CONTENT_TYPES.index(content_type_of(item)),
                title_of(item).lower(),
                parent_id(item),
            )
        )
        selected: list[dict[str, Any]] = []
        used_types: set[str] = set()
        for item in candidates:
            content_type = content_type_of(item)
            if content_type not in used_types:
                selected.append(item)
                used_types.add(content_type)
            if len(selected) == 9:
                break
        selected_ids = {parent_id(item) for item in selected}
        selected.extend(
            item for item in candidates if parent_id(item) not in selected_ids
        )
        selected = selected[:10]
        for item in selected:
            index = len(cases)
            content_type = content_type_of(item)
            cases.append(
                {
                    "id": f"v8_ret_syn_{index + 1:03d}",
                    "suite": "retrieval",
                    "case_type": "synthetic_fallback",
                    "query": synthetic_fallback_query(item, cohort, index),
                    "cohort": cohort,
                    "tags": ["synthetic_fallback", "content_type_filter", content_type],
                    "topic": clean_topic(title_of(item)),
                    "query_style": "ambiguous_fallback",
                    "expected_intent": "regulation_query",
                    "expected_strategy": "semantic_filtered",
                    "expected_content_types": [content_type],
                    "relevance_judgments": [_source_metadata(item)],
                    "near_duplicate_reviewed": True,
                    "annotation_status": "source_anchored",
                }
            )
    if len(cases) != 30:
        raise RuntimeError(f"Expected 30 synthetic cases, built {len(cases)}")
    return cases


def _primary_usage(cases: list[dict[str, Any]]) -> dict[str, int]:
    usage: dict[str, int] = defaultdict(int)
    for case in cases:
        for judgment in case.get("relevance_judgments") or []:
            source_id = str(judgment.get("parent_section_id") or "")
            if source_id:
                usage[source_id] += 1
    return usage


def _regulation_pool(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in docs
        if content_type_of(item) == "regulation_text"
        and parent_id(item)
        and len(content_of(item)) >= 180
        and "mục lục" not in title_of(item).lower()
    ]


def _select_v83_extra_docs(
    docs: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    counts: dict[str, int],
) -> dict[str, list[dict[str, Any]]]:
    usage = _primary_usage(cases)
    by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in _regulation_pool(docs):
        if usage.get(parent_id(item), 0) >= 2:
            continue
        by_cohort[cohort_of(item)].append(item)
    for items in by_cohort.values():
        items.sort(key=lambda item: (usage.get(parent_id(item), 0), title_of(item), parent_id(item)))

    selected: dict[str, list[dict[str, Any]]] = {}
    for cohort in COHORTS:
        selected[cohort] = by_cohort[cohort][: counts.get(cohort, 0)]
        for item in selected[cohort]:
            usage[parent_id(item)] += 1

    title_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in _regulation_pool(docs):
        if usage.get(parent_id(item), 0) >= 2:
            continue
        title_groups[clean_topic(title_of(item)).lower()].append(item)
    general: list[dict[str, Any]] = []
    for _, items in sorted(title_groups.items()):
        cohorts = {cohort_of(item) for item in items}
        if len(cohorts) < 2:
            continue
        representative = sorted(
            items,
            key=lambda item: (usage.get(parent_id(item), 0), cohort_of(item), parent_id(item)),
        )[0]
        general.append(representative)
        usage[parent_id(representative)] += 1
        if len(general) >= counts.get("general", 0):
            break
    selected["general"] = general
    return selected


def build_retrieval_cases_v83(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases = [enrich_case(case, eval_split="realistic") for case in build_regulation_cases(docs)]

    realistic_extra_counts = {"K48-K49": 4, "K50": 4, "K51": 4, "general": 3}
    realistic_extra = _select_v83_extra_docs(docs, cases, realistic_extra_counts)
    for cohort, items in realistic_extra.items():
        for item in items:
            index = len(cases)
            case = {
                "id": f"v83_ret_real_{index + 1:03d}",
                "suite": "retrieval",
                "case_type": "regulation_true_rag",
                "query": question_for_source(item, index, general=cohort == "general"),
                "cohort": cohort,
                "tags": ["true_rag", "citation_required", "realistic"],
                "topic": clean_topic(title_of(item)),
                "query_style": "student_style",
                "expected_intent": "regulation_query",
                "expected_strategy": "hybrid_graph_retrieval",
                "expected_content_types": ["regulation_text"],
                "relevance_judgments": [_source_metadata(item)],
                "near_duplicate_reviewed": True,
                "annotation_status": "source_anchored",
            }
            cases.append(enrich_case(case, eval_split="realistic"))

    stress_extra = _select_v83_extra_docs(docs, cases, V83_STRESS_COUNTS)
    stress_templates = (
        "Em nghe mỗi người nói một kiểu về {topic}; nếu em thuộc {cohort} thì quy định chính xác trong sổ tay là gì?",
        "{cohort} hoi ve {topic} ma em khong go dau, he thong can tim dung dieu nao?",
        "Nếu trường hợp của em hơi khác bình thường, {topic} của {cohort} được hiểu thế nào theo sổ tay?",
        "Bạn em khóa khác nói khác về {topic}; với {cohort} thì nguồn nào mới đúng?",
    )
    for cohort, items in stress_extra.items():
        for item in items:
            index = len(cases)
            topic = clean_topic(title_of(item)).lower()
            query = stress_templates[index % len(stress_templates)].format(
                cohort=cohort,
                topic=topic,
            )
            case = {
                "id": f"v83_ret_stress_{index + 1:03d}",
                "suite": "retrieval",
                "case_type": "regulation_true_rag",
                "query": query,
                "cohort": cohort,
                "tags": [
                    "true_rag",
                    "citation_required",
                    "stress",
                    "cohort_sensitive",
                ],
                "topic": clean_topic(title_of(item)),
                "query_style": "stress",
                "expected_intent": "regulation_query",
                "expected_strategy": "hybrid_graph_retrieval",
                "expected_content_types": ["regulation_text"],
                "relevance_judgments": [_source_metadata(item)],
                "near_duplicate_reviewed": True,
                "annotation_status": "source_anchored",
            }
            cases.append(enrich_case(case, eval_split="stress"))

    for index, case in enumerate(cases, start=1):
        case["id"] = f"v83_ret_{index:03d}"
    if len(cases) != 180:
        raise RuntimeError(f"Expected 180 V8.3 retrieval cases, built {len(cases)}")
    return cases


def synthetic_fallback_query(item: dict[str, Any], cohort: str, index: int) -> str:
    topic = clean_topic(title_of(item)).lower()
    content_type = content_type_of(item)
    if content_type in {"student_service_directory", "student_office_profile"}:
        return f"Em học {cohort}, cần tìm đầu mối về {topic}; bên nào phụ trách và liên hệ thế nào ạ?"
    if content_type in {"program_directory", "faculty_program_directory"}:
        return f"Sinh viên {cohort} muốn biết thêm thông tin về {topic} thì xem ở đâu?"
    if content_type == "foreign_language_equivalency":
        return f"Khóa {cohort} tra bảng {topic} như thế nào?"
    if content_type in {"structured_lookup", "threshold_rule", "formula_rule"}:
        return f"Cho sinh viên {cohort} tra nội dung {topic} và các mốc liên quan với."
    variants = (
        f"Em thuộc {cohort}, cho em hỏi thông tin về {topic}.",
        f"Trong sổ tay {cohort} có nói gì về {topic}?",
    )
    return variants[index % len(variants)]


DETERMINISTIC_GROUPS = {
    "foreign_language": (
        "foreign_language_lookup_query",
        "foreign_language_lookup",
        "foreign_language_equivalency",
    ),
    "study_duration": (
        "study_duration_lookup_query",
        "study_duration_lookup",
        "study_duration",
    ),
    "scholarship": (
        "scholarship_classification_lookup_query",
        "scholarship_classification_lookup",
        "scholarship_classification",
    ),
    "scoring": ("score_lookup_query", "structured_lookup", "score_conversion"),
    "service": ("office_query", "student_service_lookup", "office_directory"),
    "office": ("office_query", "office_lookup", "office_directory"),
    "program": ("faculty_query", "program_lookup", "program_directory"),
    "faculty": ("faculty_query", "program_lookup", "program_directory"),
    "formula": ("formula_query", "formula_lookup", "formula"),
}

EXPECTED_CITATION_TYPES = {
    "foreign_language": "structured_lookup",
    "study_duration": "structured_lookup",
    "scholarship": "structured_lookup",
    "scoring": "structured_lookup",
    "service": "office_directory",
    "office": "office_directory",
    "program": "program_directory",
    "faculty": "program_directory",
    "formula": "formula",
}


def deterministic_assertions(group: str, template_index: int) -> dict[str, Any]:
    expected_values = {
        "foreign_language": (("bac_4",), ("bac_4",)),
        "study_duration": (("8 năm học",), ("4 năm học",)),
        "scholarship": (("Xuất sắc",), ("Giỏi",)),
        "scoring": (("B+",), ("3.5", "3,5")),
        "service": (
            ("Phòng Công nghệ Thông tin",),
            ("Phòng Công tác chính trị và Học sinh, sinh viên",),
        ),
        "office": (("phongcntt@hcmue.edu.vn",), ("Ký túc xá",)),
        "program": (("Khoa Công nghệ Thông tin",), ("Khoa Công nghệ Thông tin",)),
        "faculty": (("Khoa",), ("ngành",)),
        "formula": (("Σ(ai × ni) / Σ(ni)",), ("điểm học bổng",)),
    }
    payload: dict[str, Any] = {
        "expected_contains_any": list(expected_values[group][template_index]),
    }
    if group == "foreign_language":
        payload["expected_item_count"] = 1
    if group == "scoring":
        payload["expected_lookup_type"] = (
            "grade_10_to_letter" if template_index == 0 else "letter_to_grade_4"
        )
    return payload


def negative_route_expectation(query: str) -> tuple[str, str]:
    normalized = normalize_query(query)
    if any(term in normalized for term in ("quy trinh", "trinh tu", "thu tuc", "cac buoc")):
        return "procedure_query", "semantic_filtered_rerank"
    return "regulation_query", "semantic_filtered"


POSITIVE_QUERIES = {
    "foreign_language": [
        "{cohort} IELTS 5.5 tương đương bậc ngoại ngữ nào?",
        "Với {cohort}, chứng chỉ JLPT N3 được quy đổi sang bậc mấy?",
    ],
    "study_duration": [
        "Sinh viên {cohort} hệ chính quy được học tối đa bao nhiêu năm?",
        "{cohort} thời gian chuẩn của đào tạo đại học cấp bằng thứ nhất là mấy năm?",
    ],
    "scholarship": [
        "{cohort} điểm học bổng 3.7 được xếp loại gì?",
        "Mức điểm học bổng loại giỏi của {cohort} nằm trong khoảng nào?",
    ],
    "scoring": [
        "{cohort} điểm 7.9 quy đổi thành điểm chữ gì?",
        "Điểm chữ B+ của {cohort} tương ứng bao nhiêu trên thang 4?",
    ],
    "service": [
        "{cohort} em bị lỗi tài khoản sinh viên thì liên hệ đơn vị nào?",
        "Sinh viên {cohort} cần xin giấy xác nhận đang học thì hỏi phòng nào?",
    ],
    "office": [
        "Email Phòng Công nghệ Thông tin dành cho sinh viên {cohort} là gì?",
        "{cohort} cho em địa chỉ làm việc của ký túc xá với?",
    ],
    "program": [
        "{cohort} ngành Công nghệ Thông tin do khoa nào phụ trách?",
        "Với {cohort}, khoa phụ trách CNTT đang quản lý các ngành đào tạo nào?",
    ],
    "faculty": [
        "{cohort} cho em xem thông tin khoa quản lý ngành Công nghệ Thông tin.",
        "Sinh viên {cohort} hỏi khoa nào phụ trách các ngành sư phạm?",
    ],
    "formula": [
        "Công thức tính điểm trung bình chung của {cohort} là gì?",
        "{cohort} cho em công thức tính điểm học bổng.",
    ],
}

NEGATIVE_QUERIES = {
    "foreign_language": [
        "{cohort} chưa có IELTS thì có được xin nợ chuẩn ngoại ngữ không?",
        "Chứng chỉ IELTS hết hạn có được {cohort} xét tốt nghiệp không?",
        "Thủ tục nộp chứng chỉ ngoại ngữ của {cohort} gồm những bước nào?",
        "{cohort} không có chứng chỉ ngoại ngữ thì bị xử lý ra sao?",
    ],
    "study_duration": [
        "{cohort} vượt thời gian học tối đa thì có bị buộc thôi học không?",
        "Muốn gia hạn thời gian học ở {cohort} cần thủ tục gì?",
        "Nếu {cohort} nghỉ học tạm thời thì thời gian đó có tính vào khóa học không?",
        "{cohort} học chậm tiến độ thì nhà trường xử lý thế nào?",
    ],
    "scholarship": [
        "{cohort} nợ học phí có được nhận học bổng không?",
        "Điều kiện xét học bổng của {cohort} gồm những gì?",
        "{cohort} bị kỷ luật thì còn được xét học bổng không?",
        "Quy trình nộp hồ sơ học bổng cho {cohort} ra sao?",
    ],
    "scoring": [
        "{cohort} bị điểm F thì phải học lại như thế nào?",
        "Điểm thấp có khiến sinh viên {cohort} bị cảnh báo học tập không?",
        "{cohort} được phúc khảo điểm trong trường hợp nào?",
        "Nếu cải thiện điểm thì kết quả cũ của {cohort} được xử lý ra sao?",
    ],
    "service": [
        "Phòng sinh viên xử lý khiếu nại của {cohort} theo quy trình nào?",
        "{cohort} mất tài khoản thì có bị ảnh hưởng đăng ký học phần không?",
        "Đơn vị hỗ trợ có chịu trách nhiệm giải quyết hồ sơ trễ của {cohort} không?",
        "{cohort} cần điều kiện gì để được cấp giấy xác nhận sinh viên?",
    ],
    "office": [
        "Ký túc xá xử lý vi phạm nội trú của {cohort} như thế nào?",
        "Phòng CNTT có quyền khóa tài khoản sinh viên {cohort} khi nào?",
        "{cohort} muốn chuyển phòng ban giải quyết hồ sơ thì thủ tục ra sao?",
        "Trách nhiệm của phòng đào tạo với sinh viên {cohort} là gì?",
    ],
    "program": [
        "{cohort} muốn chuyển sang ngành Công nghệ Thông tin cần điều kiện gì?",
        "Học cùng lúc hai ngành ở {cohort} được quy định ra sao?",
        "{cohort} có được tự chọn khoa quản lý khi chuyển ngành không?",
        "Điều kiện tốt nghiệp ngành Công nghệ Thông tin của {cohort} là gì?",
    ],
    "faculty": [
        "{cohort} muốn chuyển khoa thì điều kiện và quy trình ra sao?",
        "Khoa quản lý có được tự ý thay đổi kết quả học tập của {cohort} không?",
        "Sinh viên {cohort} học sai ngành thì hậu quả theo quy định là gì?",
        "{cohort} muốn xin ngoại lệ chuyển ngành thì hỏi theo điều nào?",
    ],
    "formula": [
        "Điểm trung bình thấp thì {cohort} có bị cảnh báo học tập không?",
        "{cohort} có được làm tròn điểm học bổng trong trường hợp đặc biệt không?",
        "Công thức điểm thay đổi thì quyền lợi học bổng {cohort} xử lý thế nào?",
        "{cohort} có được khiếu nại kết quả tính điểm không?",
    ],
}


def build_deterministic_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for group_index, (group, (intent, strategy, lookup_type)) in enumerate(
        DETERMINISTIC_GROUPS.items()
    ):
        for cohort_index, cohort in enumerate(COHORTS):
            for template_index, template in enumerate(POSITIVE_QUERIES[group]):
                index = len(cases)
                cases.append(
                    {
                        "id": f"v8_det_pos_{index + 1:03d}",
                        "suite": "deterministic",
                        "case_type": "positive",
                        "lookup_group": group,
                        "query": template.format(cohort=cohort),
                        "cohort": cohort,
                        "tags": ["deterministic", "positive", group],
                        "expected_group": "deterministic",
                        "expected_intent": intent,
                        "expected_strategy": strategy,
                        "expected_lookup_type": lookup_type,
                        "expected_llm_called": False,
                        "expected_citation_cohort": cohort,
                        "expected_citation_content_type": EXPECTED_CITATION_TYPES[
                            group
                        ],
                        **deterministic_assertions(group, template_index),
                        "near_duplicate_reviewed": True,
                    }
                )
        for negative_index, template in enumerate(NEGATIVE_QUERIES[group]):
            cohort = COHORTS[(group_index + negative_index) % len(COHORTS)]
            index = len(cases)
            query = template.format(cohort=cohort)
            expected_intent, expected_strategy = negative_route_expectation(query)
            cases.append(
                {
                    "id": f"v8_det_neg_{index + 1:03d}",
                    "suite": "deterministic",
                    "case_type": "hard_negative",
                    "lookup_group": group,
                    "query": query,
                    "cohort": cohort,
                    "tags": ["deterministic_safety", "hard_negative", group],
                    "expected_group": "rag",
                    "expected_intent": expected_intent,
                    "expected_strategy": expected_strategy,
                    "forbidden_strategy": strategy,
                    "expected_llm_called": True,
                    "near_duplicate_reviewed": True,
                }
            )

    ambiguous_queries = [
        "Cho em hỏi mức này được tính sao?",
        "Trường hợp đó thì em liên hệ ai?",
        "Biểu mẫu kia lấy ở đâu vậy?",
        "Điểm như vậy có ổn không?",
        "Em học tối đa được bao lâu nhỉ?",
        "Chứng chỉ đó có dùng được không?",
        "Ngành này thuộc khoa nào vậy?",
        "Công thức này áp dụng thế nào?",
        "Học bổng loại đó tính ra sao?",
        "Phòng đó nằm chỗ nào?",
        "Em cần làm thủ tục này thì bắt đầu từ đâu?",
        "Quy định của khóa em trong trường hợp này là gì?",
    ]
    for index, query in enumerate(ambiguous_queries):
        cases.append(
            {
                "id": f"v8_det_amb_{index + 1:03d}",
                "suite": "deterministic",
                "case_type": "ambiguous",
                "lookup_group": "ambiguous",
                "query": query,
                "cohort": COHORTS[index % 3],
                "tags": ["ambiguous", "missing_slot"],
                "expected_group": "clarification_or_rag",
                "expected_intent": None,
                "expected_strategy": None,
                "expected_llm_called": None,
            }
        )

    out_of_domain = [
        "Cuối tuần này khu trung tâm thành phố có mưa lớn không?",
        "Giá Bitcoin hôm nay bao nhiêu?",
        "Viết giúp em một bài thơ tình.",
        "Đội tuyển Việt Nam tối nay đá lúc mấy giờ?",
        "Máy tính của em bị xanh màn hình sửa sao?",
        "Quán ăn nào gần trường ngon nhất?",
        "Dịch câu này sang tiếng Pháp giúp em.",
        "Cho em mã giảm giá mua laptop.",
    ]
    for index, query in enumerate(out_of_domain):
        cases.append(
            {
                "id": f"v8_det_ood_{index + 1:03d}",
                "suite": "deterministic",
                "case_type": "out_of_domain",
                "lookup_group": "guardrail",
                "query": query,
                "cohort": COHORTS[index % 3],
                "tags": ["guardrail", "out_of_domain"],
                "expected_group": "guardrail",
                "expected_intent": "out_of_domain",
                "expected_strategy": "none",
                "expected_llm_called": False,
            }
        )
    if len(cases) != 120:
        raise RuntimeError(f"Expected 120 deterministic cases, built {len(cases)}")
    return cases


HOLDOUT_POSITIVE_QUERIES = {
    "foreign_language": [
        "Sinh viên {cohort} có IELTS 5.5 thì bảng quy đổi ghi nhận bậc nào?",
        "JLPT N3 trong bảng của {cohort} nằm ở bậc ngoại ngữ nào?",
    ],
    "study_duration": [
        "Theo bảng dành cho {cohort}, hệ chính quy được phép học nhiều nhất mấy năm?",
        "{cohort}, chương trình đại học cấp bằng thứ nhất có thời gian thiết kế chuẩn bao nhiêu năm?",
    ],
    "scholarship": [
        "{cohort}, mức 3.7 thuộc hạng học bổng nào?",
        "Khoảng điểm ứng với học bổng Giỏi của {cohort} là bao nhiêu?",
    ],
    "scoring": [
        "{cohort}, 7.9 trên thang 10 đổi ra điểm chữ nào?",
        "Ở {cohort}, B+ được tính bao nhiêu điểm trên hệ 4?",
    ],
    "service": [
        "Tài khoản cổng sinh viên bị lỗi, {cohort} nên liên hệ đơn vị nào?",
        "Muốn xin xác nhận đang học ở {cohort}, em cần hỏi bộ phận nào?",
    ],
    "office": [
        "Địa chỉ email của Phòng Công nghệ Thông tin cho {cohort} là gì?",
        "Văn phòng Ký túc xá dành cho {cohort} nằm ở đâu?",
    ],
    "program": [
        "Ngành Công nghệ Thông tin của {cohort} trực thuộc khoa nào?",
        "Đối với {cohort}, Khoa CNTT phụ trách danh sách ngành nào?",
    ],
    "faculty": [
        "{cohort} cho em tra khoa quản lý các ngành sư phạm.",
        "Khoa Công nghệ Thông tin trong danh mục {cohort} gắn với những ngành nào?",
    ],
    "formula": [
        "Cách tính điểm trung bình tích lũy của {cohort} là gì?",
        "Điểm học bổng của {cohort} dùng công thức nào?",
    ],
}

HOLDOUT_NEGATIVE_QUERIES = {
    "foreign_language": [
        "{cohort} có được tốt nghiệp khi chứng chỉ IELTS đã quá hạn không?",
        "Chưa đạt chuẩn ngoại ngữ thì {cohort} được xử lý thế nào?",
        "Hồ sơ công nhận chứng chỉ ngoại ngữ của {cohort} nộp theo trình tự nào?",
        "{cohort} có thể xin gia hạn thời điểm nộp chứng chỉ không?",
    ],
    "study_duration": [
        "Quá thời hạn đào tạo thì sinh viên {cohort} bị xử lý thế nào?",
        "Trình tự xin kéo dài thời gian học cho {cohort} ra sao?",
        "Thời gian bảo lưu có bị cộng vào giới hạn học của {cohort} không?",
        "Nếu chậm tiến độ, {cohort} cần đáp ứng điều kiện nào để tiếp tục học?",
    ],
    "scholarship": [
        "Sinh viên {cohort} đang nợ học phí có được xét học bổng không?",
        "Tiêu chí để {cohort} được đưa vào danh sách học bổng là gì?",
        "Khi bị kỷ luật, quyền xét học bổng của {cohort} thay đổi thế nào?",
        "Trình tự nhà trường xét và cấp học bổng cho {cohort} gồm các bước nào?",
    ],
    "scoring": [
        "Nhận điểm F thì sinh viên {cohort} phải xử lý học phần ra sao?",
        "Điểm trung bình thấp ảnh hưởng cảnh báo học tập của {cohort} thế nào?",
        "Thủ tục đề nghị phúc khảo điểm cho {cohort} gồm những gì?",
        "Sau khi học cải thiện, điểm cũ của {cohort} được xử lý thế nào?",
    ],
    "service": [
        "Đơn vị sinh viên giải quyết khiếu nại của {cohort} theo quy trình nào?",
        "Tài khoản bị khóa gây ảnh hưởng đăng ký học phần của {cohort} ra sao?",
        "Bộ phận hỗ trợ chịu trách nhiệm gì nếu hồ sơ {cohort} bị trễ?",
        "Điều kiện để {cohort} được cấp giấy xác nhận đang học là gì?",
    ],
    "office": [
        "Ký túc xá xử lý sinh viên {cohort} vi phạm nội trú theo quy định nào?",
        "Khi nào Phòng CNTT được phép khóa tài khoản của {cohort}?",
        "Muốn đổi nơi tiếp nhận hồ sơ, {cohort} phải làm thủ tục nào?",
        "Phòng Đào tạo có trách nhiệm gì đối với kết quả học tập của {cohort}?",
    ],
    "program": [
        "Điều kiện để {cohort} chuyển vào ngành Công nghệ Thông tin là gì?",
        "Sinh viên {cohort} đăng ký học hai ngành theo quy trình nào?",
        "{cohort} có được tự đổi khoa quản lý chương trình không?",
        "Chuẩn tốt nghiệp của ngành Công nghệ Thông tin cho {cohort} gồm gì?",
    ],
    "faculty": [
        "{cohort} đổi khoa quản lý thì cần điều kiện nào?",
        "Khoa có quyền buộc sinh viên {cohort} chuyển ngành không?",
        "Sinh viên {cohort} muốn khiếu nại khoa phụ trách thì quy trình ra sao?",
        "{cohort} có ngoại lệ nào khi chuyển khoa không?",
    ],
    "formula": [
        "Điểm trung bình thấp khiến {cohort} bị cảnh báo theo quy định nào?",
        "{cohort} có được làm tròn điểm học bổng trong trường hợp ngoại lệ không?",
        "Nếu cách tính thay đổi, quyền lợi học bổng của {cohort} được xử lý ra sao?",
        "Thủ tục khiếu nại kết quả tính điểm của {cohort} thế nào?",
    ],
}


def build_deterministic_holdout_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for group_index, (group, (intent, strategy, lookup_type)) in enumerate(
        DETERMINISTIC_GROUPS.items()
    ):
        for cohort in COHORTS:
            for template_index, template in enumerate(HOLDOUT_POSITIVE_QUERIES[group]):
                assertion = deterministic_assertions(group, template_index)
                cases.append(
                    {
                        "id": f"v8h_det_pos_{len(cases) + 1:03d}",
                        "suite": "deterministic",
                        "case_type": "positive",
                        "lookup_group": group,
                        "query": template.format(cohort=cohort),
                        "cohort": cohort,
                        "tags": ["deterministic", "positive", group, "holdout"],
                        "expected_group": "deterministic",
                        "expected_intent": intent,
                        "expected_strategy": strategy,
                        "expected_lookup_type": lookup_type,
                        "expected_llm_called": False,
                        "expected_citation_cohort": cohort,
                        "expected_citation_content_type": EXPECTED_CITATION_TYPES[group],
                        **assertion,
                        "near_duplicate_reviewed": True,
                    }
                )
        for negative_index, template in enumerate(HOLDOUT_NEGATIVE_QUERIES[group]):
            cohort = COHORTS[(group_index + negative_index) % len(COHORTS)]
            query = template.format(cohort=cohort)
            expected_intent, expected_strategy = negative_route_expectation(query)
            cases.append(
                {
                    "id": f"v8h_det_neg_{len(cases) + 1:03d}",
                    "suite": "deterministic",
                    "case_type": "hard_negative",
                    "lookup_group": group,
                    "query": query,
                    "cohort": cohort,
                    "tags": ["deterministic_safety", "hard_negative", group, "holdout"],
                    "expected_group": "rag",
                    "expected_intent": expected_intent,
                    "expected_strategy": expected_strategy,
                    "forbidden_strategy": strategy,
                    "expected_llm_called": True,
                    "near_duplicate_reviewed": True,
                }
            )

    ambiguous = [
        "Mức vừa nói áp dụng thế nào?",
        "Vậy trường hợp kia em phải hỏi ai?",
        "Tờ mẫu đó em tìm ở đâu?",
        "Kết quả điểm như thế có đạt không?",
        "Em được học trong thời gian bao lâu vậy?",
        "Loại chứng chỉ vừa nêu còn dùng được chứ?",
        "Chương trình này do khoa nào quản lý?",
        "Cách tính đó dùng cho trường hợp nào?",
        "Mức học bổng ấy được xác định sao?",
        "Đơn vị vừa nói có địa chỉ ở đâu?",
        "Em nên bắt đầu hồ sơ đó từ bước nào?",
        "Trường hợp của em thì quy định khóa nào được áp dụng?",
    ]
    for index, query in enumerate(ambiguous):
        cases.append(
            {
                "id": f"v8h_det_amb_{index + 1:03d}",
                "suite": "deterministic",
                "case_type": "ambiguous",
                "lookup_group": "ambiguous",
                "query": query,
                "cohort": COHORTS[index % 3],
                "tags": ["ambiguous", "missing_slot", "holdout"],
                "expected_group": "clarification_or_rag",
                "expected_intent": None,
                "expected_strategy": None,
                "expected_llm_called": None,
            }
        )

    out_of_domain = [
        "Tỷ giá đô la hôm nay đang tăng hay giảm?",
        "Gợi ý thực đơn tối nay cho gia đình bốn người.",
        "Viết một truyện ngắn khoa học viễn tưởng.",
        "Lịch thi đấu vòng loại World Cup tuần này thế nào?",
        "Điện thoại bị treo logo thì khắc phục ra sao?",
        "Nhà hàng chay nào ở trung tâm được đánh giá cao?",
        "Dịch đoạn văn này sang tiếng Đức.",
        "Có mã khuyến mại vé máy bay nào không?",
    ]
    for index, query in enumerate(out_of_domain):
        cases.append(
            {
                "id": f"v8h_det_ood_{index + 1:03d}",
                "suite": "deterministic",
                "case_type": "out_of_domain",
                "lookup_group": "guardrail",
                "query": query,
                "cohort": COHORTS[index % 3],
                "tags": ["guardrail", "out_of_domain", "holdout"],
                "expected_group": "guardrail",
                "expected_intent": "out_of_domain",
                "expected_strategy": "none",
                "expected_llm_called": False,
            }
        )
    if len(cases) != 120:
        raise RuntimeError(f"Expected 120 deterministic holdout cases, built {len(cases)}")
    return cases


HOLDOUT_V82_POSITIVE_QUERIES = {
    "foreign_language": [
        "Em khoa {cohort}, IELTS dat 5.5 thi bang quy doi xep vao bac nao?",
        "Cho em tra JLPT N3 tuong ung bac may doi voi sinh vien {cohort}.",
    ],
    "study_duration": [
        "Hoc chinh quy khoa {cohort} thi tong thoi gian duoc hoc nhieu nhat la may nam?",
        "Chuong trinh dai hoc cap bang dau tien cua {cohort} duoc thiet ke chuan trong bao lau?",
    ],
    "scholarship": [
        "Voi {cohort}, 3.7 diem xet hoc bong duoc goi la muc nao?",
        "Nhan Gioi trong bang hoc bong {cohort} ung voi khoang diem nao?",
    ],
    "scoring": [
        "Em khoa {cohort} duoc 7.9 tren thang 10, bang quy doi cho ra diem chu gi?",
        "Neu ket qua la B+ thi he 4 ghi bao nhieu diem cho {cohort}?",
    ],
    "service": [
        "Cong sinh vien khong dang nhap duoc, em thuoc {cohort} nen tim don vi nao?",
        "Em {cohort} muon xin giay chung minh dang theo hoc thi bo phan nao phu trach?",
    ],
    "office": [
        "Cho sinh vien {cohort} xin hop thu dien tu cua Phong Cong nghe Thong tin.",
        "Co so lam viec cua Ky tuc xa cho khoa {cohort} co dia chi o dau?",
    ],
    "program": [
        "Hoc nganh Cong nghe Thong tin khoa {cohort} thi don vi hoc thuat nao quan ly?",
        "Khoa CNTT dang phu trach nhung nganh nao cua {cohort}?",
    ],
    "formula": [
        "Bieu thuc tong co trong so de tinh diem trung binh cua {cohort} viet the nao?",
        "Cho em cong thuc ket hop diem hoc tap va ren luyen de ra diem hoc bong {cohort}.",
    ],
}

HOLDOUT_V82_NEGATIVE_QUERIES = {
    "foreign_language": [
        "Ban scan IELTS cua {cohort} co duoc chap nhan thay ban goc khong?",
        "Sinh vien {cohort} no chuan ngoai ngu thi han nop bo sung duoc quy dinh the nao?",
        "Quy trinh nop minh chung ngoai ngu cho {cohort} gom nhung khau nao?",
        "Khong dat chuan tieng Anh thi {cohort} bi anh huong tot nghiep ra sao?",
    ],
    "study_duration": [
        "Het thoi gian hoc toi da, {cohort} co duoc xin hoc them mot hoc ky khong?",
        "Bao luu ket qua cua {cohort} co bi tru vao thoi han dao tao khong?",
        "Hoc cham tien do thi sinh vien {cohort} bi canh bao theo quy dinh nao?",
        "Dieu kien xin keo dai khoa hoc cua {cohort} la gi?",
    ],
    "scholarship": [
        "Dat 3.7 nhung con no hoc phi thi {cohort} co nhan hoc bong khong?",
        "Duoc xep loai Gioi co dong nghia {cohort} chac chan nhan hoc bong khong?",
        "Sinh vien {cohort} khieu nai ket qua xet hoc bong bang cach nao?",
        "Bi khien trach thi {cohort} con du dieu kien duyet hoc bong khong?",
    ],
    "scoring": [
        "Diem B+ cua {cohort} co duoc dang ky hoc cai thien khong?",
        "Neu 7.9 bi nhap sai, {cohort} lam thu tuc phuc khao the nao?",
        "Nhan diem F+ thi sinh vien {cohort} phai xu ly hoc phan ra sao?",
        "Ren luyen bi xep thap se anh huong {cohort} theo quy dinh nao?",
    ],
    "service": [
        "Phong CNTT xu ly du lieu tai khoan bi mat cua {cohort} theo quy trinh nao?",
        "Can dap ung gi thi {cohort} moi duoc cap giay xac nhan dang hoc?",
        "Ho so dich vu bi tu choi thi {cohort} khieu nai voi don vi nao va ra sao?",
        "Don vi phu trach phai giai quyet yeu cau cua {cohort} trong bao lau?",
    ],
    "office": [
        "Phong Dao tao co quyen huy ket qua dang ky cua {cohort} trong truong hop nao?",
        "Trach nhiem cua Ky tuc xa khi sinh vien {cohort} vi pham noi tru la gi?",
        "Muon chuyen noi tiep nhan ho so, {cohort} phai lam thu tuc nao?",
        "Phong CNTT xu ly tai khoan {cohort} bi khoa theo quy dinh nao?",
    ],
    "program": [
        "Sinh vien {cohort} muon chuyen vao CNTT phai thoa dieu kien nao?",
        "Dang hoc mot nganh, {cohort} co the hoc them nganh thu hai theo thu tuc nao?",
        "Neu mot nganh ngung tuyen sinh thi quyen loi cua {cohort} duoc xu ly ra sao?",
        "Chuan dau ra rieng cua nganh CNTT khoa {cohort} gom nhung yeu cau gi?",
    ],
    "formula": [
        "Diem trung binh cua {cohort} co duoc lam tron de tranh canh bao khong?",
        "Neu nha truong doi cong thuc, ket qua cu cua {cohort} duoc bao luu the nao?",
        "{cohort} muon khieu nai phep tinh diem hoc bong thi can lam gi?",
        "Truong hop nao diem hoc phan khong duoc tinh vao GPA cua {cohort}?",
    ],
}

HOLDOUT_V82_AMBIGUOUS_QUERIES = [
    "Muc vua noi cua em thuoc loai nao vay?",
    "Cho em xin thong tin lien he cua ben do.",
    "Mau ay em tai cho nao?",
    "Neu diem nhu tren thi quy doi ra sao?",
    "Thoi han cua chuong trinh nay la bao lau?",
    "Chung chi kia duoc tinh o muc nao?",
    "Nganh do nam trong khoa gi?",
    "Phep tinh nay can nhung so nao?",
    "Loai hoc bong vua de cap co moc bao nhieu?",
    "Van phong ay co email khong?",
    "Thu tuc do bat dau tu dau?",
    "Quy dinh nay ap dung cho khoa cua em chu?",
]

HOLDOUT_V82_OOD_QUERIES = [
    "Gia vang trong nuoc sang nay bao nhieu?",
    "Lap lich tap gym ba buoi moi tuan cho toi.",
    "Viet email xin viec bang tieng Anh.",
    "Tran bong da toi nay phat tren kenh nao?",
    "May anh nao chup du lich dep trong tam gia?",
    "Goi y quan ca phe yen tinh o quan 3.",
    "Sua loi cong thuc trong file Excel cua toi.",
    "Tim ma giam gia cho ve xem phim cuoi tuan.",
]


def build_deterministic_holdout_v82_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for group_index, (group, (intent, strategy, lookup_type)) in enumerate(
        DETERMINISTIC_GROUPS.items()
    ):
        for cohort in COHORTS:
            for template_index, template in enumerate(
                HOLDOUT_V82_POSITIVE_QUERIES[group]
            ):
                cases.append(
                    {
                        "id": f"v82_det_pos_{len(cases) + 1:03d}",
                        "suite": "deterministic",
                        "case_type": "positive",
                        "lookup_group": group,
                        "query": template.format(cohort=cohort),
                        "cohort": cohort,
                        "tags": ["deterministic", "positive", group, "v8.2_holdout"],
                        "expected_group": "deterministic",
                        "expected_intent": intent,
                        "expected_strategy": strategy,
                        "expected_lookup_type": lookup_type,
                        "expected_llm_called": False,
                        "expected_citation_cohort": cohort,
                        "expected_citation_content_type": EXPECTED_CITATION_TYPES[
                            group
                        ],
                        **deterministic_assertions(group, template_index),
                        "near_duplicate_reviewed": True,
                    }
                )
        for negative_index, template in enumerate(
            HOLDOUT_V82_NEGATIVE_QUERIES[group]
        ):
            cohort = COHORTS[(group_index + negative_index) % len(COHORTS)]
            query = template.format(cohort=cohort)
            expected_intent, expected_strategy = negative_route_expectation(query)
            cases.append(
                {
                    "id": f"v82_det_neg_{len(cases) + 1:03d}",
                    "suite": "deterministic",
                    "case_type": "hard_negative",
                    "lookup_group": group,
                    "query": query,
                    "cohort": cohort,
                    "tags": [
                        "deterministic_safety",
                        "hard_negative",
                        group,
                        "v8.2_holdout",
                    ],
                    "expected_group": "rag",
                    "expected_intent": expected_intent,
                    "expected_strategy": expected_strategy,
                    "forbidden_strategy": strategy,
                    "expected_llm_called": True,
                    "near_duplicate_reviewed": True,
                }
            )

    for index, query in enumerate(HOLDOUT_V82_AMBIGUOUS_QUERIES):
        cases.append(
            {
                "id": f"v82_det_amb_{index + 1:03d}",
                "suite": "deterministic",
                "case_type": "ambiguous",
                "lookup_group": "ambiguous",
                "query": query,
                "cohort": COHORTS[index % 3],
                "tags": ["ambiguous", "missing_slot", "v8.2_holdout"],
                "expected_group": "clarification_or_rag",
                "expected_intent": None,
                "expected_strategy": None,
                "expected_llm_called": None,
            }
        )

    for index, query in enumerate(HOLDOUT_V82_OOD_QUERIES):
        cases.append(
            {
                "id": f"v82_det_ood_{index + 1:03d}",
                "suite": "deterministic",
                "case_type": "out_of_domain",
                "lookup_group": "guardrail",
                "query": query,
                "cohort": COHORTS[index % 3],
                "tags": ["guardrail", "out_of_domain", "v8.2_holdout"],
                "expected_group": "guardrail",
                "expected_intent": "out_of_domain",
                "expected_strategy": "none",
                "expected_llm_called": False,
            }
        )
    if len(cases) != 120:
        raise RuntimeError(f"Expected 120 V8.2 holdout cases, built {len(cases)}")
    return cases


UNANSWERABLE_QUERIES = [
    "K50 có được miễn toàn bộ học phí nếu gia đình ở xa trường không?",
    "K51 có chính sách cấp laptop miễn phí cho mọi sinh viên không?",
    "K48-K49 được bảo đảm có việc làm sau tốt nghiệp trong bao lâu?",
    "Trường có hoàn tiền ký túc xá nếu sinh viên đổi ý giữa tháng không?",
    "Điểm rèn luyện có được mua thêm bằng hoạt động bên ngoài trường không?",
    "Sinh viên K50 được tự động nâng điểm nếu tham gia nghiên cứu khoa học không?",
    "K51 có thể bỏ qua chuẩn ngoại ngữ bằng cách đóng phí thay thế không?",
    "Trường có cam kết mọi đơn phúc khảo đều được tăng điểm không?",
    "Sinh viên có được chọn bất kỳ tháng nào để nhận bằng tốt nghiệp không?",
    "K48-K49 có được chuyển trường mà không cần bất kỳ hồ sơ nào không?",
]


def build_answer_cases(
    retrieval_cases: list[dict[str, Any]],
    docs_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    regulation = [
        case for case in retrieval_cases if case["case_type"] == "regulation_true_rag"
    ]
    synthetic = [
        case for case in retrieval_cases if case["case_type"] == "synthetic_fallback"
    ]
    selected: list[dict[str, Any]] = []
    for cohort in [*COHORTS, "general"]:
        selected.extend([case for case in regulation if case["cohort"] == cohort][:20])
    selected.extend(synthetic[:10])

    answers: list[dict[str, Any]] = []
    for source_case in selected:
        primary_id = source_case["relevance_judgments"][0]["parent_section_id"]
        source_doc = docs_by_id[primary_id]
        duplicate_group = f"v8_source_query_{source_case['id']}"
        source_case["duplicate_group"] = duplicate_group
        answer_case = {
            **source_case,
            "id": f"v8_ans_{len(answers) + 1:03d}",
            "suite": "answers",
            "ground_truth": source_excerpt(source_doc, limit=750),
            "required_facts": required_facts(source_doc),
            "forbidden_claims": [],
            "answerability": "answerable",
            "expected_citations": source_case["relevance_judgments"],
            "duplicate_group": duplicate_group,
            "generation_model": "gemini-3.1-flash-lite",
            "judge_model": "openai/gpt-oss-120b",
        }
        answers.append(answer_case)

    for index, query in enumerate(UNANSWERABLE_QUERIES):
        answers.append(
            {
                "id": f"v8_ans_{len(answers) + 1:03d}",
                "suite": "answers",
                "case_type": "unanswerable",
                "query": query,
                "cohort": COHORTS[index % 3],
                "tags": ["unanswerable", "abstention"],
                "topic": "unsupported_policy_claim",
                "query_style": "adversarial_unanswerable",
                "expected_intent": "regulation_query",
                "expected_strategy": "semantic_filtered",
                "expected_content_types": ["regulation_text"],
                "relevance_judgments": [],
                "ground_truth": "Sổ tay không cung cấp căn cứ để khẳng định nội dung này; hệ thống cần nói rõ không tìm thấy thông tin phù hợp.",
                "required_facts": ["Không tìm thấy căn cứ trong sổ tay."],
                "forbidden_claims": ["khẳng định chính sách không có nguồn"],
                "answerability": "unanswerable",
                "expected_citations": [],
                "generation_model": "gemini-3.1-flash-lite",
                "judge_model": "openai/gpt-oss-120b",
            }
        )
    if len(answers) != 100:
        raise RuntimeError(f"Expected 100 answer cases, built {len(answers)}")
    return answers


STRUCTURED_SOURCE_FILES = {
    "office": ROOT / "data" / "processed" / "directories" / "student_office_profiles.json",
    "service": ROOT / "data" / "processed" / "directories" / "student_service_directory.json",
    "program": ROOT / "data" / "processed" / "directories" / "program_directory.json",
    "foreign_language": ROOT / "data" / "processed" / "tables" / "structured_tables_registry.json",
}


def _record_id(record: dict[str, Any]) -> str:
    for key in (
        "service_id",
        "office_profile_id",
        "program_id",
        "table_id",
            "rule_id",
        "formula_id",
        "source_record_id",
    ):
        value = record.get(key)
        if value:
            return str(value)
    return ""


def _structured_source_for_case(case: dict[str, Any]) -> dict[str, str]:
    group = str(case.get("lookup_group") or "")
    path = STRUCTURED_SOURCE_FILES.get(group)
    if not path or not path.exists():
        return {"catalog": group, "source_id": group}
    records = load_json(path)
    expected_cohort = str(case.get("cohort") or "")
    for record in records:
        if expected_cohort and str(record.get("cohort") or "") not in {
            expected_cohort,
            "",
        }:
            continue
        record_id = _record_id(record)
        if record_id:
            return {"catalog": group, "source_id": record_id}
    return {"catalog": group, "source_id": group}


def normalize_v83_structured_expectations(case: dict[str, Any]) -> dict[str, Any]:
    item = dict(case)
    if item.get("case_type") != "positive":
        return item
    group = str(item.get("lookup_group") or "")
    item["expected_group"] = "structured"
    item["expected_intent"] = "structured_query"
    item["expected_strategy"] = "structured_table"
    item["expected_lookup_type"] = group
    item["expected_llm_called"] = True
    item.pop("expected_contains_any", None)
    item.pop("expected_numeric_value", None)
    item.pop("numeric_tolerance", None)
    if group in {"foreign_language", "study_duration", "scholarship", "scoring"}:
        item["expected_item_count"] = 1
    return item


def build_answer_cases_v83(
    retrieval_cases: list[dict[str, Any]],
    deterministic_cases: list[dict[str, Any]],
    docs_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    realistic_regulation = [
        case
        for case in retrieval_cases
        if case.get("eval_split") == "realistic"
        and case.get("case_type") == "regulation_true_rag"
    ][:71]
    stress_regulation = [
        case
        for case in retrieval_cases
        if case.get("eval_split") == "stress"
        and case.get("case_type") == "regulation_true_rag"
    ][:15]
    structured_sources = [
        case
        for case in deterministic_cases
        if case.get("case_type") == "positive"
        and case.get("lookup_group")
        in {"office", "service", "program", "foreign_language"}
    ][:4]

    answers: list[dict[str, Any]] = []
    for source_case in [*realistic_regulation, *stress_regulation]:
        primary_id = source_case["relevance_judgments"][0]["parent_section_id"]
        source_doc = docs_by_id[primary_id]
        duplicate_group = f"v83_source_query_{source_case['id']}"
        source_case["duplicate_group"] = duplicate_group
        answers.append(
            enrich_case(
                {
                    **source_case,
                    "id": f"v83_ans_{len(answers) + 1:03d}",
                    "suite": "answers",
                    "ground_truth": source_excerpt(source_doc, limit=750),
                    "required_facts": required_facts(source_doc),
                    "forbidden_claims": [],
                    "answerability": "answerable",
                    "expected_citations": source_case["relevance_judgments"],
                    "duplicate_group": duplicate_group,
                    "generation_model": "gemini-3.1-flash-lite",
                    "judge_model": "openai/gpt-oss-120b",
                },
                eval_split=str(source_case.get("eval_split") or "realistic"),
            )
        )

    for source_case in structured_sources:
        structured_source = _structured_source_for_case(source_case)
        group = str(source_case.get("lookup_group") or "structured")
        answer_index = len(answers) + 1
        structured_query = {
            "foreign_language": f"Case {answer_index}: em thuộc {source_case.get('cohort')}, nhờ giải thích bảng quy đổi ngoại ngữ cho chứng chỉ phổ biến như IELTS hoặc JLPT.",
            "office": f"Case {answer_index}: em học {source_case.get('cohort')}, cần tra thông tin liên hệ của một phòng ban trong trường thì hệ thống dùng nguồn nào?",
            "service": f"Case {answer_index}: {source_case.get('cohort')} muốn biết đơn vị phụ trách một việc sinh viên thường làm thì tra catalog dịch vụ ra sao?",
            "program": f"Case {answer_index}: sinh viên {source_case.get('cohort')} muốn xem ngành thuộc khoa nào thì trả lời từ danh mục chương trình thế nào?",
        }.get(group, str(source_case.get("query") or "Tra dữ liệu structured."))
        answers.append(
            enrich_case(
                {
                    **source_case,
                    "id": f"v83_ans_{len(answers) + 1:03d}",
                    "suite": "answers",
                    "case_type": "structured_mixed",
                    "query": structured_query,
                    "expected_path": "structured",
                    "ground_truth": "Trả lời trực tiếp bằng dữ liệu structured catalog đúng cohort và đúng nguồn.",
                    "required_facts": [
                        "Dùng dữ liệu structured catalog đúng cohort.",
                    ],
                    "forbidden_claims": [
                        "Không tự suy đoán thông tin ngoài catalog.",
                    ],
                    "answerability": "answerable",
                    "relevance_judgments": [],
                    "expected_citations": [],
                    "expected_structured_sources": [
                        structured_source,
                    ],
                    "generation_model": "gemini-3.1-flash-lite",
                    "judge_model": "openai/gpt-oss-120b",
                },
                eval_split="realistic",
            )
        )

    for index, query in enumerate(UNANSWERABLE_QUERIES):
        answers.append(
            enrich_case(
                {
                    "id": f"v83_ans_{len(answers) + 1:03d}",
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
                    "ground_truth": "Sổ tay không cung cấp căn cứ để khẳng định nội dung này; hệ thống cần nói rõ không tìm thấy thông tin phù hợp.",
                    "required_facts": ["Không tìm thấy căn cứ trong sổ tay."],
                    "forbidden_claims": ["khẳng định chính sách không có nguồn"],
                    "answerability": "unanswerable",
                    "expected_citations": [],
                    "generation_model": "gemini-3.1-flash-lite",
                    "judge_model": "openai/gpt-oss-120b",
                },
                eval_split="stress",
            )
        )

    if len(answers) != 100:
        raise RuntimeError(f"Expected 100 V8.3 answer cases, built {len(answers)}")
    return answers


def _production_case(
    case_id: str,
    source: dict[str, Any],
    scenario: str,
    *,
    concurrency: int = 1,
    duplicate_group: str | None = None,
    repeat_of: str | None = None,
) -> dict[str, Any]:
    return enrich_case({
        "id": case_id,
        "suite": "production",
        "scenario": scenario,
        "query": source["query"],
        "cohort": source.get("cohort"),
        "tags": ["production", scenario],
        "expected_intent": source.get("expected_intent"),
        "expected_strategy": source.get("expected_strategy"),
        "concurrency": concurrency,
        "stream": scenario == "streaming",
        "repeat_of": repeat_of,
        "duplicate_group": duplicate_group,
        "near_duplicate_reviewed": True,
    }, eval_split=str(source.get("eval_split") or "realistic"))


def build_production_cases(
    answer_cases: list[dict[str, Any]],
    deterministic_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    answerable = [
        case for case in answer_cases if case["answerability"] == "answerable"
    ]
    deterministic = [
        case for case in deterministic_cases if case["case_type"] == "positive"
    ]
    cases: list[dict[str, Any]] = []
    cold_ids: list[str] = []
    for source in answerable[:20]:
        case_id = f"v8_prod_cold_{len(cold_ids) + 1:02d}"
        group = source.get("duplicate_group") or f"prod_{case_id}"
        source["duplicate_group"] = group
        cases.append(
            _production_case(case_id, source, "cold_rag", duplicate_group=group)
        )
        cold_ids.append(case_id)
    for index, source in enumerate(deterministic[:10], start=1):
        group = f"v8_prod_det_{index:02d}"
        source["duplicate_group"] = group
        cases.append(
            _production_case(
                f"v8_prod_det_{index:02d}",
                source,
                "deterministic",
                duplicate_group=group,
            )
        )
    for index, source in enumerate(answerable[:10], start=1):
        group = source.get("duplicate_group")
        cases.append(
            _production_case(
                f"v8_prod_warm_{index:02d}",
                source,
                "warm_cache",
                duplicate_group=group,
                repeat_of=cold_ids[index - 1],
            )
        )
    for index, source in enumerate(answerable[20:30], start=1):
        group = source.get("duplicate_group") or f"v8_prod_stream_{index:02d}"
        source["duplicate_group"] = group
        cases.append(
            _production_case(
                f"v8_prod_stream_{index:02d}",
                source,
                "streaming",
                duplicate_group=group,
            )
        )
    for index, source in enumerate(answerable[30:40], start=1):
        group = source.get("duplicate_group") or f"v8_prod_burst_{index:02d}"
        source["duplicate_group"] = group
        concurrency = 3 if index <= 5 else 5
        cases.append(
            _production_case(
                f"v8_prod_burst_{index:02d}",
                source,
                "burst",
                concurrency=concurrency,
                duplicate_group=group,
            )
        )
    if len(cases) != 60:
        raise RuntimeError(f"Expected 60 production cases, built {len(cases)}")
    return cases


def build_production_cases_v83(
    answer_cases: list[dict[str, Any]],
    deterministic_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    answerable = [
        case for case in answer_cases if case["answerability"] == "answerable"
    ]
    realistic = [case for case in answerable if case.get("eval_split") == "realistic"]
    stress = [case for case in answerable if case.get("eval_split") == "stress"]
    deterministic = [
        case for case in deterministic_cases if case["case_type"] == "positive"
    ]

    cases: list[dict[str, Any]] = []
    cold_sources = [*realistic[:10], *stress[:10]]
    cold_ids: list[str] = []
    for source in cold_sources:
        case_id = f"v83_prod_cold_{len(cold_ids) + 1:02d}"
        group = source.get("duplicate_group") or f"prod_{case_id}"
        source["duplicate_group"] = group
        cases.append(
            _production_case(case_id, source, "cold_rag", duplicate_group=group)
        )
        cold_ids.append(case_id)

    for index, source in enumerate(deterministic[:10], start=1):
        group = f"v83_prod_det_{index:02d}"
        source["duplicate_group"] = group
        cases.append(
            _production_case(
                f"v83_prod_det_{index:02d}",
                source,
                "deterministic",
                duplicate_group=group,
            )
        )

    for index, source in enumerate(cold_sources[:10], start=1):
        group = source.get("duplicate_group")
        cases.append(
            _production_case(
                f"v83_prod_warm_{index:02d}",
                source,
                "warm_cache",
                duplicate_group=group,
                repeat_of=cold_ids[index - 1],
            )
        )

    streaming_sources = [*realistic[10:15], *stress[10:15]]
    for index, source in enumerate(streaming_sources, start=1):
        group = source.get("duplicate_group") or f"v83_prod_stream_{index:02d}"
        source["duplicate_group"] = group
        cases.append(
            _production_case(
                f"v83_prod_stream_{index:02d}",
                source,
                "streaming",
                duplicate_group=group,
            )
        )

    burst_sources = realistic[15:25]
    for index, source in enumerate(burst_sources, start=1):
        group = source.get("duplicate_group") or f"v83_prod_burst_{index:02d}"
        source["duplicate_group"] = group
        concurrency = 3 if index <= 5 else 5
        cases.append(
            _production_case(
                f"v83_prod_burst_{index:02d}",
                source,
                "burst",
                concurrency=concurrency,
                duplicate_group=group,
            )
        )
    if len(cases) != 60:
        raise RuntimeError(f"Expected 60 V8.3 production cases, built {len(cases)}")
    return cases


def current_git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def build_bundle(
    output_dir: Path,
    *,
    deterministic_cases: list[dict[str, Any]] | None = None,
    version: str = "v8",
    holdout_of: str | None = None,
    additional_predecessors: list[str] | None = None,
) -> dict[str, Any]:
    docs = load_json(DOCSTORE_PATH)
    answer_config = load_yaml(ANSWER_CONFIG_PATH)
    router_config = load_yaml(AI_ROUTER_CONFIG_PATH)
    generation_model = str((answer_config.get("llm") or {}).get("model_name") or "")
    if generation_model != "gemini-3.1-flash-lite":
        raise RuntimeError(
            "V8 requires configs/answer_generation.yaml to pin gemini-3.1-flash-lite"
        )
    docs_by_id = {parent_id(item): item for item in docs if parent_id(item)}
    deterministic = deterministic_cases or build_deterministic_cases()
    retrieval = [*build_regulation_cases(docs), *build_synthetic_cases(docs)]
    answers = build_answer_cases(retrieval, docs_by_id)
    production = build_production_cases(answers, deterministic)

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
        write_json(output_dir / filenames[suite], cases)
    audit_template = build_human_audit_template(
        answers, [{"id": case["id"]} for case in answers]
    )
    write_json(output_dir / "human_audit_template.json", audit_template)

    manifest = {
        "version": version,
        "frozen": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "description": "Source-anchored frozen benchmark for deterministic, retrieval, answer and production evaluation.",
        "annotation_method": "deterministic source anchoring; human audit required for 20 judged answers",
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
        "generation_provider": str(
            (answer_config.get("llm") or {}).get("provider") or ""
        ),
        "generation_model": generation_model,
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
    }
    if holdout_of:
        predecessor_bundles = [holdout_of, *(additional_predecessors or [])]
        predecessors = {
            bundle: load_json(
                ROOT / "data" / "eval" / bundle / "deterministic_tool_cases.json"
            )
            for bundle in predecessor_bundles
        }
        predecessor_queries = {
            normalize_query(case["query"])
            for cases in predecessors.values()
            for case in cases
        }
        overlaps = [
            case["id"]
            for case in deterministic
            if normalize_query(case["query"]) in predecessor_queries
        ]
        if overlaps:
            raise RuntimeError(f"Holdout reuses predecessor queries: {overlaps[:10]}")
        manifest.update(
            {
                "holdout_for": ["deterministic"],
                "predecessor_bundle": holdout_of,
                "predecessor_deterministic_hash": stable_json_hash(
                    predecessors[holdout_of]
                ),
                "predecessor_bundles": predecessor_bundles,
                "predecessor_deterministic_hashes": {
                    bundle: stable_json_hash(cases)
                    for bundle, cases in predecessors.items()
                },
                "holdout_policy": "single_run_no_post_tuning",
            }
        )
    write_json(output_dir / "manifest.json", manifest)
    validation = validate_bundle(output_dir, DOCSTORE_PATH)
    write_json(output_dir / "validation_report.json", validation)
    if not validation["valid"]:
        raise RuntimeError(
            "V8 bundle validation failed:\n" + "\n".join(validation["errors"][:30])
        )
    return {"manifest": manifest, "validation": validation}


def build_bundle_v83(output_dir: Path) -> dict[str, Any]:
    docs = load_json(DOCSTORE_PATH)
    answer_config = load_yaml(ANSWER_CONFIG_PATH)
    router_config = load_yaml(AI_ROUTER_CONFIG_PATH)
    generation_model = str((answer_config.get("llm") or {}).get("model_name") or "")
    if generation_model != "gemini-3.1-flash-lite":
        raise RuntimeError(
            "V8.3 requires configs/answer_generation.yaml to pin gemini-3.1-flash-lite"
        )
    docs_by_id = {parent_id(item): item for item in docs if parent_id(item)}
    deterministic = [
        enrich_case(normalize_v83_structured_expectations(case))
        for case in build_deterministic_holdout_cases()
    ]
    retrieval = build_retrieval_cases_v83(docs)
    answers = build_answer_cases_v83(retrieval, deterministic, docs_by_id)
    production = build_production_cases_v83(answers, deterministic)

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
        write_json(output_dir / filenames[suite], cases)

    audit_template = build_human_audit_template(
        answers,
        [{"id": case["id"]} for case in answers],
    )
    write_json(output_dir / "human_audit_template.json", audit_template)

    manifest = {
        "version": "v8.3-full-holdout",
        "frozen": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "description": "Full-system holdout benchmark with realistic and stress splits for the student handbook RAG system.",
        "annotation_method": "source-anchored questions with deterministic structured metadata and human audit requirements",
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
        "generation_provider": str(
            (answer_config.get("llm") or {}).get("provider") or ""
        ),
        "generation_model": generation_model,
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
        "predecessor_bundles": ["v8", "v8_2_holdout"],
        "realistic_stress_split": {
            suite: dict(
                __import__("collections").Counter(
                    str(case.get("eval_split")) for case in cases
                )
            )
            for suite, cases in datasets.items()
        },
    }
    write_json(output_dir / "manifest.json", manifest)

    readme = """# Evaluation Suite V8.3 Holdout

V8.3 is the full-system holdout benchmark for the current production architecture.
It separates realistic student questions from stress/adversarial questions and must
not be edited after failures are used to tune the system.

## Counts

- deterministic_tool_cases.json: 120 cases.
- retrieval_cases.json: 180 regulation RAG cases.
- generated_answer_cases.json: 100 answer cases.
- production_cases.json: 60 latency/robustness requests.

## Policy

Use V8.3 once for headline metrics. If failures are used for fixes, create a new
holdout version before publishing new headline numbers.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    validation = validate_bundle(output_dir, DOCSTORE_PATH)
    write_json(output_dir / "validation_report.json", validation)
    if not validation["valid"]:
        raise RuntimeError(
            "V8.3 bundle validation failed:\n"
            + "\n".join(validation["errors"][:50])
        )
    return {"manifest": manifest, "validation": validation}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build and freeze the V8 evaluation bundle."
    )
    parser.add_argument(
        "--variant",
        choices=[
            "main",
            "deterministic-holdout",
            "deterministic-holdout-v8.2",
            "full-holdout-v8.3",
        ],
        default="main",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.variant == "full-holdout-v8.3":
        output = args.output or ROOT / "data" / "eval" / "v8_3_holdout"
        report = build_bundle_v83(output)
    elif args.variant == "deterministic-holdout-v8.2":
        output = args.output or ROOT / "data" / "eval" / "v8_2_holdout"
        report = build_bundle(
            output,
            deterministic_cases=build_deterministic_holdout_v82_cases(),
            version="v8.2-deterministic-holdout",
            holdout_of="v8",
            additional_predecessors=["v8_holdout"],
        )
    elif args.variant == "deterministic-holdout":
        output = args.output or ROOT / "data" / "eval" / "v8_holdout"
        report = build_bundle(
            output,
            deterministic_cases=build_deterministic_holdout_cases(),
            version="v8.1-deterministic-holdout",
            holdout_of="v8",
        )
    else:
        report = build_bundle(args.output or DEFAULT_OUTPUT)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
