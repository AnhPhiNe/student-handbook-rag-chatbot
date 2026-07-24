"""Build the V9 final holdout for the cleaned production dataset.

V9 is intentionally dataset-only. It does not change runtime retrieval,
generation, routing, or storage code.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
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
    clean_topic,
    content_of,
    content_type_of,
    document_id_of,
    enrich_case,
    metadata,
    parent_id,
    required_facts as base_required_facts,
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
from src.generation.io_utils import load_yaml  # noqa: E402


SOURCE_BUNDLE = ROOT / "data" / "eval" / "v8_4_holdout"
DEFAULT_OUTPUT = ROOT / "data" / "eval" / "v9_final_holdout"
DATASET_FILES = {
    "deterministic": "deterministic_tool_cases.json",
    "retrieval": "retrieval_cases.json",
    "answers": "generated_answer_cases.json",
    "production": "production_cases.json",
}

CONDUCT_POSITIVE_QUERIES = (
    "{cohort}: diem ren luyen 85 diem duoc xep loai nao?",
    "{cohort}: xep loai ren luyen Tot ung voi khoang diem nao?",
)
CONDUCT_NEGATIVE_QUERIES = (
    "{cohort}: neu diem ren luyen thap thi sinh vien bi xu ly theo quy dinh nao?",
    "{cohort}: co duoc xin nang diem ren luyen neu thieu minh chung khong?",
    "{cohort}: quy trinh khieu nai ket qua ren luyen gom nhung buoc nao?",
    "{cohort}: diem ren luyen kem anh huong hoc bong va tot nghiep ra sao?",
)

STRUCTURED_QUERY_TEMPLATES = {
    "foreign_language": (
        "{cohort}: giai thich bang quy doi ngoai ngu cho IELTS/JLPT.",
        "{cohort}: neu xem bang ngoai ngu thi IELTS va JLPT duoc quy doi ra sao?",
    ),
    "study_duration": (
        "{cohort}: tom tat bang thoi gian hoc chuan va toi da.",
        "{cohort}: bang thoi gian dao tao cho biet gioi han hoc toi da the nao?",
    ),
    "scholarship": (
        "{cohort}: giai thich bang xep loai hoc bong theo diem.",
        "{cohort}: bang hoc bong khuyen khich hoc tap chia muc nhu the nao?",
    ),
    "scoring": (
        "{cohort}: giai thich bang quy doi diem chu va thang 4.",
        "{cohort}: bang diem chu, diem so va thang 4 nen doc nhu the nao?",
    ),
    "conduct": (
        "{cohort}: diem ren luyen duoc xep loai theo bang nao?",
        "{cohort}: bang phan loai ket qua ren luyen co cac muc nao?",
    ),
    "service": (
        "{cohort}: neu can mot viec sinh vien thuong lam thi tra don vi phu trach the nao?",
        "{cohort}: hoi ve dich vu sinh vien thi catalog chi ra don vi nao phu trach?",
    ),
    "office": (
        "{cohort}: tra email, so dien thoai va dia chi phong ban nhu the nao?",
        "{cohort}: neu can lien he phong ban thi lay thong tin lien he tu dau?",
    ),
    "faculty": (
        "{cohort}: tra thong tin lien he cua khoa tu catalog nao?",
        "{cohort}: thong tin khoa, email va van phong khoa duoc tra theo nguon nao?",
    ),
    "program": (
        "{cohort}: nganh hoc thuoc khoa nao va danh sach nganh tra ra sao?",
        "{cohort}: danh muc nganh hoc theo khoa trong khoa tuyen sinh duoc doc the nao?",
    ),
    "formula": (
        "{cohort}: cac cong thuc GPA va diem hoc bong duoc trinh bay the nao?",
        "{cohort}: khi hoi cong thuc diem thi he thong tra cong thuc tu catalog nao?",
    ),
}

STRUCTURED_SOURCE_PATHS = {
    "foreign_language": ROOT / "data/processed/tables/structured_tables_registry.json",
    "study_duration": ROOT / "data/processed/tables/structured_tables_registry.json",
    "scholarship": ROOT / "data/processed/tables/scoring_tables.json",
    "scoring": ROOT / "data/processed/tables/structured_tables_registry.json",
    "conduct": ROOT / "data/processed/tables/structured_tables_registry.json",
    "service": ROOT / "data/processed/directories/student_service_directory.json",
    "office": ROOT / "data/processed/directories/student_office_profiles.json",
    "faculty": ROOT / "data/processed/directories/student_faculty_profiles.json",
    "program": ROOT / "data/processed/directories/program_directory.json",
    "formula": ROOT / "data/processed/tables/formula_rules.json",
}

SOURCE_ID_FIELDS = (
    "record_id",
    "service_id",
    "office_profile_id",
    "faculty_profile_id",
    "program_id",
    "table_id",
    "rule_id",
    "formula_id",
    "source_record_id",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def current_git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def record_id(record: dict[str, Any]) -> str:
    for field in SOURCE_ID_FIELDS:
        value = record.get(field)
        if value:
            return str(value)
    return ""


def cohort_of_doc(item: dict[str, Any]) -> str:
    meta = metadata(item)
    return str(meta.get("cohort") or item.get("cohort") or "")


def source_metadata(item: dict[str, Any]) -> dict[str, Any]:
    meta = metadata(item)
    return {
        "parent_section_id": parent_id(item),
        "grade": 2,
        "cohort": cohort_of_doc(item),
        "document_id": document_id_of(item),
        "content_type": content_type_of(item),
        "source_section": title_of(item),
        "source_pages": meta.get("source_pages") or item.get("source_pages") or [],
    }


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def required_facts(item: dict[str, Any]) -> list[str]:
    facts = base_required_facts(item)
    cleaned = [fact for fact in facts if not is_layout_required_fact(fact)]
    return cleaned[:2] or facts[:1]


def is_layout_required_fact(text: str) -> bool:
    normalized = normalize_query(strip_accents(str(text or "")))
    layout_markers = (
        "bo giao duc va dao tao",
        "cong hoa xa hoi chu nghia viet nam",
        "doc lap tu do hanh phuc",
        "thanh pho ho chi minh ngay",
        "so qd dhsp",
        "dang chinh nghia",
    )
    return any(marker in normalized for marker in layout_markers)


def short_source_terms(case: dict[str, Any]) -> str:
    judgments = case.get("relevance_judgments") or []
    section = ""
    if judgments and isinstance(judgments[0], dict):
        section = str(judgments[0].get("source_section") or "")
    if not section:
        section = str(case.get("topic") or "quy dinh")
    section = strip_accents(section).casefold()
    words = [
        word.strip(".,;:()[]")
        for word in section.replace("/", " ").replace("-", " ").split()
        if word.strip(".,;:()[]")
    ]
    useful = [
        word
        for word in words
        if word.casefold() not in {"điều", "dieu", "về", "ve", "và", "va", "của", "cua"}
    ]
    stopwords = {
        "dieu",
        "ve",
        "va",
        "cua",
        "cac",
        "cho",
        "doi",
        "voi",
        "nguoi",
        "co",
        "sinh",
        "vien",
        "quy",
        "dinh",
        "chuong",
    }
    useful = [word for word in useful if word not in stopwords and len(word) > 1]
    return " ".join(useful[:5]) or "quy dinh"


def short_query_for_case(case: dict[str, Any], index: int) -> str:
    cohort = str(case.get("cohort") or "")
    prefix = "" if cohort == "general" else f"{cohort} "
    terms = short_source_terms(case)
    if terms == "hieu truong":
        return f"{prefix}trach nhiem cua hieu truong trong so tay la gi?".strip()
    templates = (
        f"{prefix}quy dinh ve {terms}?",
        f"{prefix}{terms} duoc quy dinh sao?",
        f"{prefix}hoi ve {terms} trong so tay?",
    )
    query = templates[index % len(templates)]
    return " ".join(query.split())


def expected_catalog_for_group(group: str) -> str:
    return {
        "conduct": "scoring",
        "student_service": "service",
    }.get(group, group)


def structured_source_for_group(group: str, cohort: str | None) -> dict[str, str]:
    path = STRUCTURED_SOURCE_PATHS[group]
    records = load_json(path)
    if not isinstance(records, list):
        raise RuntimeError(f"Structured source file must contain a list: {path}")
    table_type_by_group = {
        "foreign_language": "foreign_language",
        "study_duration": "study_duration",
        "scholarship": "scholarship",
        "scoring": "scoring",
        "conduct": "conduct",
    }
    for record in records:
        if not isinstance(record, dict):
            continue
        if cohort and str(record.get("cohort") or "") not in {"", cohort}:
            continue
        expected_table_type = table_type_by_group.get(group)
        if expected_table_type:
            table_type = record.get("table_type")
            table_id = record.get("table_id")
            table_name = str(record.get("table_name") or "").lower()
            if table_type != expected_table_type:
                if group == "scholarship" and (
                    table_id == "scholarship_classification" or "học bổng" in table_name
                ):
                    pass
                else:
                    continue
        source_id = record_id(record)
        if source_id:
            return {"catalog": expected_catalog_for_group(group), "source_id": source_id}
    raise RuntimeError(f"No structured source found for group={group}, cohort={cohort}")


def structured_record_for_source(group: str, source_id: str) -> dict[str, Any]:
    records = load_json(STRUCTURED_SOURCE_PATHS[group])
    if not isinstance(records, list):
        return {}
    for record in records:
        if isinstance(record, dict) and record_id(record) == source_id:
            return record
    return {}


def structured_query_for_group(
    group: str,
    cohort: str,
    variant_index: int,
    record: dict[str, Any],
) -> str:
    templates = STRUCTURED_QUERY_TEMPLATES[group]
    if group == "service":
        service = str(record.get("service") or "dịch vụ sinh viên")
        unit = str(record.get("unit_name") or record.get("unit") or "")
        if unit:
            return f"{cohort}: {unit} phu trach viec gi va lien he o dau?"
        return f"{cohort}: viec {service[:60]} thi lien he don vi nao?"
    if group == "office":
        unit = str(record.get("unit_name") or record.get("unit") or "phong ban")
        return f"{cohort}: {unit} o dau, email va so dien thoai la gi?"
    if group == "faculty":
        faculty = str(
            record.get("faculty_name")
            or record.get("unit_name")
            or record.get("unit")
            or "khoa"
        )
        return f"{cohort}: {faculty} o dau va lien he the nao?"
    if group == "program":
        faculty = str(record.get("faculty_name") or record.get("faculty") or "khoa")
        return f"{cohort}: cac nganh thuoc {faculty} gom nhung nganh nao?"
    return templates[variant_index % len(templates)].format(cohort=cohort)


def normalize_deterministic_case(case: dict[str, Any], index: int) -> dict[str, Any]:
    item = dict(case)
    original_id = str(item.get("id") or f"legacy_{index:03d}")
    item["predecessor_case_id"] = original_id
    item["id"] = f"v9_det_{index:03d}"
    item["duplicate_group"] = str(item.get("duplicate_group") or item["id"])
    item["near_duplicate_reviewed"] = True
    if item.get("lookup_group") == "form":
        cohort = str(item.get("cohort") or COHORTS[index % len(COHORTS)])
        if item.get("case_type") == "positive":
            positive_index = int(item.get("_form_positive_index") or 0)
            item.update(
                {
                    "lookup_group": "conduct",
                    "query": CONDUCT_POSITIVE_QUERIES[positive_index % 2].format(
                        cohort=cohort
                    ),
                    "tags": ["deterministic", "positive", "conduct", "v9_final"],
                    "expected_group": "structured",
                    "expected_intent": "structured_query",
                    "expected_strategy": "structured_table",
                    "expected_lookup_type": "scoring",
                    "expected_llm_called": True,
                    "expected_citation_cohort": cohort,
                    "expected_citation_content_type": "structured_lookup",
                    "expected_item_count": 1,
                }
            )
            item.pop("expected_contains_any", None)
        elif item.get("case_type") == "hard_negative":
            negative_index = int(item.get("_form_negative_index") or 0)
            item.update(
                {
                    "lookup_group": "conduct",
                    "query": CONDUCT_NEGATIVE_QUERIES[negative_index % 4].format(
                        cohort=cohort
                    ),
                    "tags": [
                        "deterministic_safety",
                        "hard_negative",
                        "conduct",
                        "v9_final",
                    ],
                    "expected_group": "rag",
                    "expected_intent": "regulation_query",
                    "expected_strategy": "semantic_filtered",
                    "forbidden_strategy": "structured_table",
                    "expected_llm_called": True,
                }
            )
    else:
        item["tags"] = list(dict.fromkeys([*(item.get("tags") or []), "v9_final"]))
    for private_key in ("_form_positive_index", "_form_negative_index"):
        item.pop(private_key, None)
    return item


def build_deterministic_cases(source_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    form_positive = 0
    form_negative = 0
    prepared: list[dict[str, Any]] = []
    for case in source_cases:
        item = dict(case)
        if item.get("lookup_group") == "form" and item.get("case_type") == "positive":
            item["_form_positive_index"] = form_positive
            form_positive += 1
        if item.get("lookup_group") == "form" and item.get("case_type") == "hard_negative":
            item["_form_negative_index"] = form_negative
            form_negative += 1
        prepared.append(item)
    cases = [normalize_deterministic_case(case, index) for index, case in enumerate(prepared, start=1)]
    positive_groups = Counter(
        case.get("lookup_group") for case in cases if case.get("case_type") == "positive"
    )
    if "form" in positive_groups or positive_groups.get("conduct") != 6:
        raise RuntimeError(f"Unexpected V9 positive groups: {positive_groups}")
    return cases


def build_retrieval_cases(source_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index, case in enumerate(source_cases, start=1):
        item = dict(case)
        item["predecessor_case_id"] = str(item.get("id") or "")
        item["id"] = f"v9_ret_{index:03d}"
        if index <= 30:
            item["query"] = short_query_for_case(item, index)
            item["query_style"] = "short_natural" if index % 3 else "typo_no_accent"
        item["duplicate_group"] = str(item.get("duplicate_group") or item["id"])
        item["near_duplicate_reviewed"] = True
        item["tags"] = list(dict.fromkeys([*(item.get("tags") or []), "v9_final"]))
        cases.append(item)
    return cases


def build_regulation_answer(
    source_case: dict[str, Any],
    source_doc: dict[str, Any],
    *,
    answer_id: str,
    source_relation: str,
) -> dict[str, Any]:
    return enrich_case(
        {
            **source_case,
            "id": answer_id,
            "suite": "answers",
            "case_type": "regulation_true_rag",
            "ground_truth": source_excerpt(source_doc, limit=750),
            "required_facts": required_facts(source_doc),
            "forbidden_claims": [],
            "answerability": "answerable",
            "expected_citations": source_case["relevance_judgments"],
            "source_relation": source_relation,
            "linked_retrieval_case_id": source_case.get("id")
            if source_relation == "retrieval_linked"
            else None,
            "generation_model": "gemini-3.1-flash-lite",
            "judge_model": "openai/gpt-oss-120b",
        },
        eval_split=str(source_case.get("eval_split") or "realistic"),
    )


def build_structured_answer(
    source_case: dict[str, Any],
    *,
    answer_id: str,
    group: str,
    variant_index: int,
) -> dict[str, Any]:
    cohort = str(source_case.get("cohort") or COHORTS[0])
    structured_source = structured_source_for_group(group, cohort)
    source_record = structured_record_for_source(
        group, structured_source["source_id"]
    )
    query = structured_query_for_group(
        group,
        cohort,
        variant_index,
        source_record,
    )
    return enrich_case(
        {
            "id": answer_id,
            "suite": "answers",
            "case_type": "structured_answer",
            "query": query,
            "cohort": cohort,
            "tags": ["structured", group, "v9_final", "realistic"],
            "topic": {
                "foreign_language": "ngoai_ngu",
                "study_duration": "diem",
                "scholarship": "hoc_bong",
                "scoring": "diem",
                "conduct": "ren_luyen",
                "service": "phong_ban",
                "office": "phong_ban",
                "faculty": "nganh_hoc",
                "program": "nganh_hoc",
                "formula": "diem",
            }[group],
            "lookup_group": group,
            "query_style": "realistic",
            "expected_intent": "structured_query",
            "expected_strategy": "structured_table",
            "expected_path": "structured",
            "expected_content_types": ["structured_lookup"],
            "relevance_judgments": [],
            "expected_structured_sources": [structured_source],
            "ground_truth": "Tra loi dua tren structured catalog dung cohort va dung source.",
            "required_facts": ["Dung structured catalog dung cohort."],
            "forbidden_claims": ["Khong tu suy doan ngoai structured catalog."],
            "answerability": "answerable",
            "expected_citations": [],
            "source_relation": "structured",
            "generation_model": "gemini-3.1-flash-lite",
            "judge_model": "openai/gpt-oss-120b",
            "duplicate_group": f"v9_structured_{answer_id}",
            "near_duplicate_reviewed": True,
        },
        eval_split="realistic",
    )


def build_mixed_answer(
    source_case: dict[str, Any],
    source_doc: dict[str, Any],
    *,
    answer_id: str,
    group: str,
) -> dict[str, Any]:
    cohort = str(source_case.get("cohort") or "general")
    source_cohort = cohort if cohort in COHORTS else cohort_of_doc(source_doc)
    structured_source = structured_source_for_group(group, source_cohort)
    topic = clean_topic(str(source_case.get("source_topic") or title_of(source_doc)))
    return enrich_case(
        {
            **source_case,
            "id": answer_id,
            "suite": "answers",
            "case_type": "mixed_answer",
            "query": (
                f"{source_cohort}: dua tren bang {group} va quy dinh ve '{topic}', "
                "em can hieu ket luan chinh nao?"
            ),
            "cohort": source_cohort,
            "tags": ["mixed", group, "regulation_rag", "v9_final", "realistic"],
            "topic": topic_group(f"{topic} {group}"),
            "lookup_group": group,
            "query_style": "realistic",
            "expected_path": "mixed",
            "expected_intent": "regulation_query",
            "expected_strategy": "semantic_filtered",
            "relevance_judgments": source_case["relevance_judgments"],
            "expected_structured_sources": [structured_source],
            "ground_truth": source_excerpt(source_doc, limit=650),
            "required_facts": required_facts(source_doc)[:3]
            or ["Ket hop structured fact voi quy dinh lien quan."],
            "forbidden_claims": ["Khong tron cohort hoac suy doan ngoai nguon."],
            "answerability": "answerable",
            "expected_citations": source_case["relevance_judgments"],
            "source_relation": "mixed",
            "generation_model": "gemini-3.1-flash-lite",
            "judge_model": "openai/gpt-oss-120b",
            "duplicate_group": f"v9_mixed_{answer_id}",
        },
        eval_split="realistic",
    )


def build_unanswerable_answer(query: str, index: int) -> dict[str, Any]:
    return enrich_case(
        {
            "id": f"v9_ans_{index:03d}",
            "suite": "answers",
            "case_type": "unanswerable",
            "query": query,
            "cohort": COHORTS[(index - 1) % len(COHORTS)],
            "tags": ["unanswerable", "clarify", "abstention", "v9_final"],
            "topic": "khac",
            "query_style": "unanswerable",
            "expected_intent": "clarification_query",
            "expected_strategy": "clarify_or_abstain",
            "expected_path": "clarify",
            "expected_content_types": ["regulation_text"],
            "relevance_judgments": [],
            "ground_truth": "He thong can hoi lai hoac noi ro khong tim thay can cu trong so tay.",
            "required_facts": ["Khong tim thay can cu trong so tay."],
            "forbidden_claims": ["khẳng định chính sách không có nguồn"],
            "answerability": "unanswerable",
            "expected_citations": [],
            "source_relation": "unanswerable",
            "generation_model": "gemini-3.1-flash-lite",
            "judge_model": "openai/gpt-oss-120b",
            "duplicate_group": f"v9_unanswerable_{index:03d}",
        },
        eval_split="stress",
    )


def cohort_bucket(case: dict[str, Any]) -> str:
    cohort = str(case.get("cohort") or "")
    return cohort if cohort in {*COHORTS, "general"} else "general"


def take_by_cohort(
    cases: list[dict[str, Any]],
    quotas: dict[str, int],
    *,
    used_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    used_ids = used_ids or set()
    selected: list[dict[str, Any]] = []
    for cohort, count in quotas.items():
        cohort_cases = [
            case
            for case in cases
            if cohort_bucket(case) == cohort and str(case.get("id")) not in used_ids
        ]
        if len(cohort_cases) < count:
            raise RuntimeError(
                f"Not enough retrieval cases for cohort={cohort}: "
                f"need {count}, found {len(cohort_cases)}"
            )
        selected.extend(cohort_cases[:count])
    return selected


def has_single_source_cohort(case: dict[str, Any]) -> bool:
    expected = cohort_bucket(case)
    judgment_cohorts = {
        str(judgment.get("cohort") or "")
        for judgment in case.get("relevance_judgments") or []
        if isinstance(judgment, dict)
    }
    judgment_cohorts.discard("")
    if expected == "general":
        return len(judgment_cohorts) <= 1
    return not judgment_cohorts or judgment_cohorts == {expected}


def choose_structured_sources(
    cases: list[dict[str, Any]], group_index: int, count: int = 2
) -> list[dict[str, Any]]:
    by_cohort = {
        cohort: next(
            (case for case in cases if str(case.get("cohort") or "") == cohort),
            None,
        )
        for cohort in COHORTS
    }
    rotated = [*COHORTS[group_index % len(COHORTS) :], *COHORTS[: group_index % len(COHORTS)]]
    selected = [by_cohort[cohort] for cohort in rotated if by_cohort.get(cohort)]
    if len(selected) < count:
        selected.extend(case for case in cases if case not in selected)
    return selected[:count]


def build_answer_cases(
    retrieval_cases: list[dict[str, Any]],
    deterministic_cases: list[dict[str, Any]],
    docs_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    realistic_retrieval = [
        case for case in retrieval_cases if case.get("eval_split") == "realistic"
    ]
    stress_retrieval = [
        case for case in retrieval_cases if case.get("eval_split") == "stress"
    ]
    answers: list[dict[str, Any]] = []
    used_retrieval_ids: set[str] = set()
    regulation_sources = [
        *take_by_cohort(
            realistic_retrieval,
            {"K48-K49": 11, "K50": 11, "K51": 11, "general": 12},
        ),
        *take_by_cohort(
            stress_retrieval,
            {"K48-K49": 4, "K50": 4, "K51": 4, "general": 3},
        ),
    ]
    for source_case in regulation_sources:
        answer_index = len(answers) + 1
        if answer_index <= 18:
            source_case = {
                **source_case,
                "query": short_query_for_case(source_case, answer_index),
                "query_style": "short_natural"
                if answer_index % 3
                else "typo_no_accent",
            }
        primary_id = source_case["relevance_judgments"][0]["parent_section_id"]
        answers.append(
            build_regulation_answer(
                source_case,
                docs_by_id[primary_id],
                answer_id=f"v9_ans_{answer_index:03d}",
                source_relation="retrieval_linked",
            )
        )
        used_retrieval_ids.add(str(source_case["id"]))

    positive_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in deterministic_cases:
        if case.get("case_type") == "positive":
            positive_by_group[str(case.get("lookup_group"))].append(case)
    structured_groups = [
        "foreign_language",
        "study_duration",
        "scholarship",
        "scoring",
        "conduct",
        "service",
        "office",
        "faculty",
        "program",
        "formula",
    ]
    for group_index, group in enumerate(structured_groups):
        for variant_index, source_case in enumerate(
            choose_structured_sources(positive_by_group[group], group_index)
        ):
            answers.append(
                build_structured_answer(
                    source_case,
                    answer_id=f"v9_ans_{len(answers) + 1:03d}",
                    group=group,
                    variant_index=variant_index,
                )
            )

    mixed_groups = [
        "foreign_language",
        "study_duration",
        "scholarship",
        "scoring",
        "conduct",
        "service",
        "office",
        "faculty",
        "program",
        "formula",
    ]
    mixed_pool = [case for case in realistic_retrieval if has_single_source_cohort(case)]
    mixed_sources = take_by_cohort(
        mixed_pool,
        {"K48-K49": 4, "K50": 3, "K51": 3},
        used_ids=used_retrieval_ids,
    )
    for source_case, group in zip(mixed_sources, mixed_groups, strict=True):
        primary_id = source_case["relevance_judgments"][0]["parent_section_id"]
        answers.append(
            build_mixed_answer(
                source_case,
                docs_by_id[primary_id],
                answer_id=f"v9_ans_{len(answers) + 1:03d}",
                group=group,
            )
        )

    for query in UNANSWERABLE_QUERIES[:10]:
        answers.append(build_unanswerable_answer(query, len(answers) + 1))

    if len(answers) != 100:
        raise RuntimeError(f"Expected 100 V9 answer cases, built {len(answers)}")
    return answers


def production_case(
    case_id: str,
    source: dict[str, Any],
    scenario: str,
    *,
    concurrency: int = 1,
    repeat_of: str | None = None,
) -> dict[str, Any]:
    return enrich_case(
        {
            "id": case_id,
            "suite": "production",
            "scenario": scenario,
            "query": source["query"],
            "cohort": source.get("cohort"),
            "tags": ["production", scenario, *(source.get("tags") or [])[:3]],
            "expected_intent": source.get("expected_intent"),
            "expected_strategy": source.get("expected_strategy"),
            "expected_path": source.get("expected_path"),
            "concurrency": concurrency,
            "stream": scenario == "streaming",
            "repeat_of": repeat_of,
            "duplicate_group": source.get("duplicate_group") or case_id,
            "near_duplicate_reviewed": True,
        },
        eval_split=str(source.get("eval_split") or "realistic"),
    )


def build_production_cases(
    answer_cases: list[dict[str, Any]], deterministic_cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    regulation = [case for case in answer_cases if case.get("case_type") == "regulation_true_rag"]
    structured = [case for case in answer_cases if case.get("case_type") == "structured_answer"]
    mixed = [case for case in answer_cases if case.get("case_type") == "mixed_answer"]
    clarify = [case for case in answer_cases if case.get("case_type") == "unanswerable"]
    deterministic = [case for case in deterministic_cases if case.get("case_type") == "positive"]

    cold_sources = [*regulation[:10], *structured[:4], *mixed[:4], *clarify[:2]]
    streaming_sources = [*regulation[10:16], *structured[4:6], *mixed[4:5], clarify[2]]
    burst_sources = [*regulation[16:21], *structured[6:8], *mixed[5:7], clarify[3]]
    cases: list[dict[str, Any]] = []
    cold_ids: list[str] = []
    for source in cold_sources:
        case_id = f"v9_prod_cold_{len(cold_ids) + 1:02d}"
        cases.append(production_case(case_id, source, "cold_rag"))
        cold_ids.append(case_id)
    for index, source in enumerate(deterministic[:10], start=1):
        cases.append(production_case(f"v9_prod_det_{index:02d}", source, "deterministic"))
    for index, source in enumerate(cold_sources[:10], start=1):
        cases.append(
            production_case(
                f"v9_prod_warm_{index:02d}",
                source,
                "warm_cache",
                repeat_of=cold_ids[index - 1],
            )
        )
    for index, source in enumerate(streaming_sources, start=1):
        cases.append(production_case(f"v9_prod_stream_{index:02d}", source, "streaming"))
    for index, source in enumerate(burst_sources, start=1):
        cases.append(
            production_case(
                f"v9_prod_burst_{index:02d}",
                source,
                "burst",
                concurrency=3 if index <= 5 else 5,
            )
        )
    if len(cases) != 60:
        raise RuntimeError(f"Expected 60 V9 production cases, built {len(cases)}")
    return cases


def build_human_audit_template(answer_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    quotas = {
        "regulation_true_rag": 12,
        "structured_answer": 4,
        "mixed_answer": 4,
        "unanswerable": 5,
    }
    selected: list[dict[str, Any]] = []
    for case_type, count in quotas.items():
        selected.extend(
            [case for case in answer_cases if case.get("case_type") == case_type][:count]
        )
    return [
        {
            "id": case["id"],
            "case_type": case.get("case_type"),
            "cohort": case.get("cohort"),
            "eval_split": case.get("eval_split"),
            "selection_reason": "v9_stratified_audit",
            "human_score": None,
            "human_correctness": None,
            "human_faithfulness": None,
            "human_citation_correctness": None,
            "unsupported_claim_actual": None,
            "root_cause": None,
            "critical_false_pass": None,
            "notes": "",
            "repeat_for_consistency": index < 5,
            "repeat_score": None,
        }
        for index, case in enumerate(selected)
    ]


def write_readme(output_dir: Path) -> None:
    (output_dir / "README.md").write_text(
        "# Evaluation Suite V9 Final Holdout\n\n"
        "V9 targets the cleaned three-cohort student-handbook backend. It removes "
        "form lookup from headline evaluation and covers regulation RAG, structured "
        "catalog/table reasoning, mixed cases, clarification/unanswerable behavior, "
        "and production latency/robustness.\n",
        encoding="utf-8",
    )


def build_bundle(output_dir: Path) -> dict[str, Any]:
    docs = load_json(DOCSTORE_PATH)
    docs_by_id = {parent_id(item): item for item in docs if parent_id(item)}
    deterministic_source = load_json(SOURCE_BUNDLE / DATASET_FILES["deterministic"])
    retrieval_source = load_json(SOURCE_BUNDLE / DATASET_FILES["retrieval"])

    deterministic = build_deterministic_cases(deterministic_source)
    retrieval = build_retrieval_cases(retrieval_source)
    answers = build_answer_cases(retrieval, deterministic, docs_by_id)
    production = build_production_cases(answers, deterministic)
    datasets = {
        "deterministic": deterministic,
        "retrieval": retrieval,
        "answers": answers,
        "production": production,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    for suite, cases in datasets.items():
        write_json(output_dir / DATASET_FILES[suite], cases)
    audit_template = build_human_audit_template(answers)
    write_json(output_dir / "human_audit_template.json", audit_template)

    answer_config = load_yaml(ANSWER_CONFIG_PATH)
    router_config = load_yaml(AI_ROUTER_CONFIG_PATH)
    manifest = {
        "version": "v9-final-clean-docstore-holdout",
        "frozen": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "description": "Final cleaned holdout for the current backend: regulation RAG plus structured table/directory/formula, no form lookup.",
        "counts": {suite: len(cases) for suite, cases in datasets.items()},
        "dataset_hashes": {suite: stable_json_hash(cases) for suite, cases in datasets.items()},
        "auxiliary_hashes": {"human_audit_template": stable_json_hash(audit_template)},
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
        "router_provider": str(router_config.get("provider") or "groq"),
        "router_model": str(router_config.get("model_name") or ""),
        "judge_provider": "groq",
        "judge_model": "openai/gpt-oss-120b",
        "headline_backend": "qdrant_cloud+mongodb",
        "strict_structured_sources": True,
        "strict_cohort_conflicts": True,
        "strict_query_duplicates": True,
        "structured_catalogs": [
            "foreign_language",
            "study_duration",
            "scholarship",
            "scoring",
            "conduct",
            "service",
            "office",
            "faculty",
            "program",
            "formula",
        ],
        "excluded_catalogs": ["form"],
        "answer_case_type_counts": {
            "regulation_true_rag": 60,
            "structured_answer": 20,
            "mixed_answer": 10,
            "unanswerable": 10,
        },
        "answer_eval_split_counts": {"realistic": 75, "stress": 25},
        "human_audit_required_n": 25,
        "human_audit_repeat_n": 5,
        "holdout_policy": "single_run_no_post_tuning",
        "predecessor_bundle": "v8_4_holdout",
    }
    write_json(output_dir / "manifest.json", manifest)
    write_readme(output_dir)

    validation = validate_bundle(output_dir, DOCSTORE_PATH)
    write_json(output_dir / "validation_report.json", validation)
    if not validation["valid"]:
        raise RuntimeError(
            "V9 bundle validation failed:\n"
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
                "answer_case_type_counts": manifest["answer_case_type_counts"],
                "human_audit_required_n": manifest["human_audit_required_n"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
