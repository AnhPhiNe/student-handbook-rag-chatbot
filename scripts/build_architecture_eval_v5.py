from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_architecture_eval_v2 import CONFIG_PATHS
from scripts.build_architecture_eval_v4 import (
    COHORTS,
    GENERATION_MODEL,
    JUDGE_MODEL,
    _compact,
    _document_scope_label,
    _judgment,
    _metadata,
    _record_ground_truth,
    _reference_text,
    _required_facts_from_text,
    _topic_from_title,
)
from src.common.cohort import is_cohort_applicable
from src.evaluation.dataset import (
    _structured_source_index,
    file_hash,
    load_json,
    normalize_query,
    stable_json_hash,
    validate_bundle,
    write_json,
)


TARGET = ROOT / "data" / "eval" / "architecture_v5_holdout"
DOCSTORE = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"
BUILD_MANIFEST = ROOT / "data" / "processed" / "metadata" / "build_manifest.json"
EVALUATED_SYSTEM_COMMIT = "71e5ad5ca68142d4c583082bee6585089cc33c1b"

COUNTS = {
    "deterministic": 140,
    "retrieval": 160,
    "answers": 150,
    "production": 60,
}
ANSWER_TYPES = {
    "regulation_true_rag": 72,
    "structured_answer": 30,
    "mixed_answer": 18,
    "clarification": 10,
    "unanswerable": 10,
    "out_of_domain": 10,
}
DETERMINISTIC_TYPES = {
    "positive": 60,
    "hard_negative": 36,
    "ambiguous": 12,
    "out_of_domain": 8,
    "architecture": 24,
}
RETRIEVAL_COHORTS = {"K48-K49": 40, "K50": 40, "K51": 40, "general": 40}
RETRIEVAL_SPLITS = {"realistic": 120, "stress": 40}

EXCLUDED_TITLES = {
    "hiệu lực thi hành",
    "điều khoản thi hành",
    "giải thích từ ngữ",
    "phạm vi điều chỉnh và đối tượng áp dụng",
    "phạm vi và đối tượng áp dụng",
    "tổ chức thực hiện",
}

EXCLUDED_TITLE_FRAGMENTS = (
    "hieu luc",
    "quy dinh chuyen tiep",
    "dieu khoan thi hanh",
)


def _ascii(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )


def _topic_key(source: dict[str, Any]) -> tuple[str, str, str]:
    metadata = _metadata(source)
    return (
        normalize_query(str(metadata.get("document_title") or "")),
        normalize_query(str(metadata.get("title") or "")),
        normalize_query(str(metadata.get("article") or "")),
    )


def _is_excluded_title(value: str) -> bool:
    normalized = normalize_query(value)
    ascii_normalized = normalize_query(_ascii(value))
    exact = {normalize_query(item) for item in EXCLUDED_TITLES}
    return normalized in exact or any(
        fragment in ascii_normalized for fragment in EXCLUDED_TITLE_FRAGMENTS
    )


def _iter_rows(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        yield from (row for row in value if isinstance(row, dict))
    elif isinstance(value, dict) and isinstance(value.get("cases"), list):
        yield from (row for row in value["cases"] if isinstance(row, dict))


def _safe_json_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for current, dirs, files in os.walk(root, topdown=True, onerror=lambda _: None):
        dirs[:] = [
            name
            for name in dirs
            if not name.startswith("pytest")
            and name
            not in {TARGET.name, "architecture_v5_preview", ".hf_deploy_temp"}
        ]
        for filename in files:
            if filename.endswith(".json"):
                yield Path(current) / filename


def _old_material(docs_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    queries: dict[str, dict[str, str]] = {}
    anchor_ids: set[str] = set()
    scanned_files = 0
    for root in (ROOT / "data" / "eval", ROOT / "work"):
        for path in _safe_json_files(root):
            if TARGET in path.parents:
                continue
            try:
                value = load_json(path)
            except (OSError, json.JSONDecodeError, PermissionError):
                continue
            scanned_files += 1
            for row in _iter_rows(value):
                query = row.get("query") or row.get("user_input")
                if query:
                    normalized = normalize_query(str(query))
                    if normalized:
                        queries.setdefault(
                            normalized,
                            {"query": str(query), "path": path.relative_to(ROOT).as_posix()},
                        )
                for field in ("relevance_judgments", "expected_citations"):
                    for judgment in row.get(field) or []:
                        if isinstance(judgment, dict) and judgment.get("parent_section_id"):
                            anchor_ids.add(str(judgment["parent_section_id"]))
    anchor_topic_keys = {
        _topic_key(docs_by_id[source_id])
        for source_id in anchor_ids
        if source_id in docs_by_id
    }
    return {
        "queries": queries,
        "anchor_ids": anchor_ids,
        "anchor_topic_keys": anchor_topic_keys,
        "scanned_files": scanned_files,
    }


def _round_robin_sources(
    sources: list[dict[str, Any]], count: int
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in sorted(sources, key=lambda item: str(item.get("_id") or "")):
        buckets[_topic_from_title(str(_metadata(source).get("title") or ""))].append(source)
    selected: list[dict[str, Any]] = []
    names = sorted(buckets)
    while names and len(selected) < count:
        remaining: list[str] = []
        for name in names:
            if buckets[name] and len(selected) < count:
                selected.append(buckets[name].pop(0))
            if buckets[name]:
                remaining.append(name)
        names = remaining
    if len(selected) != count:
        raise ValueError(f"Need {count} sources, found {len(selected)}")
    return selected


def _retrieval_query(
    source: dict[str, Any], cohort: str, style_index: int
) -> tuple[str, str, str]:
    metadata = _metadata(source)
    title = _compact(metadata.get("title"))
    document = _document_scope_label(str(metadata.get("document_title") or ""))
    article = _compact(metadata.get("article"))
    scope = f"sinh viên {cohort}" if cohort != "general" else "sinh viên HCMUE"
    normalized_title = normalize_query(_ascii(title))
    if normalized_title.startswith("trach nhiem"):
        subject = title.split(" của ", 1)[-1]
        natural = f"{subject} có những trách nhiệm gì liên quan đến {scope}?"
    elif normalized_title.startswith("danh gia"):
        natural = f"{title} được xem xét theo những nội dung nào đối với {scope}?"
    elif normalized_title.startswith("quyen"):
        natural = f"{scope.capitalize()} có những quyền gì theo mục {title}?"
    elif normalized_title.startswith("nhiem vu"):
        natural = f"{title} gồm những việc cụ thể nào đối với {scope}?"
    elif normalized_title.startswith("yeu cau"):
        natural = f"{title} gồm những nội dung bắt buộc nào đối với {scope}?"
    elif normalized_title.startswith(("trinh tu", "thu tuc")):
        natural = f"Quy trình và hồ sơ về {title.lower()} gồm những gì cho {scope}?"
    elif normalized_title.startswith(("xu ly", "thu hoi")):
        natural = f"{title} được thực hiện thế nào đối với {scope}?"
    elif normalized_title.startswith("thoi gian"):
        natural = f"{title} được xác định vào thời điểm nào đối với {scope}?"
    elif normalized_title.startswith(("phong ", "trung tam", "tram ")):
        natural = f"{title} có nhiệm vụ hỗ trợ gì cho {scope}?"
    else:
        natural = f"Quy định về {title.lower()} áp dụng thế nào cho {scope}?"
    variants = (
        (
            f"Theo {article} của {document}, mục {title} quy định gì cho {scope}?",
            "keyword",
            "realistic",
        ),
        (
            natural,
            "paraphrase",
            "paraphrase",
        ),
        (
            f"Cho em hỏi {natural[0].lower() + natural[1:]}",
            "student_style",
            "realistic",
        ),
        (
            _ascii(
                f"{cohort if cohort != 'general' else 'HCMUE'}: {title} trong {document} quy dinh sao?"
            ).casefold(),
            "typo_no_diacritics",
            "typo_no_accent",
        ),
    )
    return variants[style_index % len(variants)]


def _retrieval_case(
    *,
    case_id: str,
    sources: list[dict[str, Any]],
    cohort: str,
    style_index: int,
) -> dict[str, Any]:
    primary = sources[0]
    metadata = _metadata(primary)
    query, retrieval_style, question_style = _retrieval_query(
        primary, cohort, style_index
    )
    topic = _topic_from_title(str(metadata.get("title") or ""))
    tags = {
        "citation_required",
        "source_first",
        "true_rag",
        "regulation_rag",
        retrieval_style,
    }
    if cohort != "general":
        tags.add("cohort_sensitive")
    if any(char.isdigit() for char in _reference_text(primary)):
        tags.add("numeric_fact")
    normalized_title = normalize_query(str(metadata.get("title") or ""))
    if any(term in normalized_title for term in ("trinh tu", "thu tuc", "dieu kien")):
        tags.add("condition_procedure")
    judgments = [
        _judgment(source, grade=2 if ordinal == 0 else 1)
        for ordinal, source in enumerate(sources)
    ]
    if len(judgments) > 1:
        tags.add("multi_source")
    if style_index % 9 == 0:
        tags.add("graph_reference")
    eval_split = "stress" if style_index % 4 == 3 else "realistic"
    return {
        "id": case_id,
        "suite": "retrieval",
        "case_type": "regulation_true_rag",
        "query": query,
        "cohort": cohort,
        "tags": sorted(tags),
        "topic": topic,
        "query_style": retrieval_style,
        "expected_intent": "regulation_query",
        "expected_strategy": "semantic_filtered",
        "expected_content_types": ["regulation_text"],
        "relevance_judgments": judgments,
        "near_duplicate_reviewed": True,
        "near_duplicate_review_reason": (
            "Source-first case has a distinct frozen document/article/title target."
        ),
        "annotation_status": "source_anchored_pre_run",
        "source_topic": _compact(metadata.get("title")),
        "question_style": question_style,
        "expected_path": "regulation_rag",
        "cohort_sensitivity": "multi_cohort_risk" if cohort != "general" else "none",
        "question_specificity": "specific",
        "expected_answer_behavior": "scoped_summary",
        "eval_split": eval_split,
        "duplicate_group": (
            "v5_retrieval_topic_"
            + stable_json_hash(list(_topic_key(primary)))[:16]
        ),
        "retrieval_style": retrieval_style,
        "query_origin": "source_first_unseen_topic_v32",
        "anchor_review_status": "frozen_before_execution",
        "contract_version": "regulation-rag-unseen-source-v5",
        "relevance_scope": "requested_cohort" if cohort != "general" else "cross_edition",
    }


def _build_retrieval(
    docs: list[dict[str, Any]], old: dict[str, Any]
) -> list[dict[str, Any]]:
    fresh = [
        source
        for source in docs
        if _topic_key(source) not in old["anchor_topic_keys"]
        and not _is_excluded_title(str(_metadata(source).get("title") or ""))
        and len(_reference_text(source)) >= 120
    ]
    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for source in fresh:
        by_key[_topic_key(source)].append(source)

    multi_groups = [
        sorted(group, key=lambda item: str(item.get("_id") or ""))
        for group in by_key.values()
        if len({_metadata(item).get("cohort") for item in group}) >= 2
    ]
    multi_groups.sort(
        key=lambda group: (
            -len({_metadata(item).get("cohort") for item in group}),
            _topic_from_title(str(_metadata(group[0]).get("title") or "")),
            _topic_key(group[0]),
        )
    )
    general_groups = multi_groups[:40]
    if len(general_groups) != 40:
        raise ValueError(f"Need 40 fresh multi-cohort groups, found {len(general_groups)}")

    cases: list[dict[str, Any]] = []
    index = 0
    for group in general_groups:
        index += 1
        cases.append(
            _retrieval_case(
                case_id=f"v5_ret_{index:03d}",
                sources=group,
                cohort="general",
                style_index=index - 1,
            )
        )

    for cohort in COHORTS:
        pool = [
            source
            for source in fresh
            if _metadata(source).get("cohort") == cohort
        ]
        for source in _round_robin_sources(pool, 40):
            index += 1
            cases.append(
                _retrieval_case(
                    case_id=f"v5_ret_{index:03d}",
                    sources=[source],
                    cohort=cohort,
                    style_index=index - 1,
                )
            )
    if len(cases) != COUNTS["retrieval"]:
        raise AssertionError(len(cases))
    return cases


POSITIVE_QUERIES: dict[str, tuple[str, str]] = {
    "foreign_language": (
        "{cohort}: TOEFL iBT 45 nằm ở bậc tương đương nào trong bảng?",
        "TOPIK II mức 150 được bảng của {cohort} xếp vào bậc mấy?",
    ),
    "study_duration": (
        "Bảng {cohort} ghi cả thời gian chuẩn và giới hạn tối đa của hệ chính quy là bao lâu?",
        "Nếu học chính quy ở {cohort}, mốc thời gian nào là chuẩn và mốc nào là trần?",
    ),
    "scholarship": (
        "Học bổng loại Giỏi của {cohort} sử dụng hệ số tiền bao nhiêu?",
        "Bảng {cohort} mô tả điều kiện xếp mức học bổng Khá thế nào?",
    ),
    "scoring": (
        "Theo bảng điểm {cohort}, 6,8 được chuyển thành điểm chữ gì?",
        "Khoảng điểm hệ 10 nào của {cohort} tương ứng với điểm A?",
    ),
    "service": (
        "Wi-Fi sinh viên gặp sự cố thì {cohort} nên tìm đơn vị hỗ trợ nào?",
        "Đơn vị nào quản lý email mang tên miền Trường cho sinh viên {cohort}?",
    ),
    "office": (
        "Tra giúp số liên hệ của Phòng Kế hoạch – Tài chính trong danh bạ {cohort}.",
        "Danh bạ {cohort} ghi Phòng Khảo thí và Đảm bảo chất lượng ở địa chỉ nào?",
    ),
    "program": (
        "Sư phạm Toán học của {cohort} do khoa nào quản lý?",
        "Danh mục {cohort} ghi Khoa Toán – Tin học phụ trách những ngành nào?",
    ),
    "faculty": (
        "Khoa Toán – Tin học của {cohort} có thông tin email nào?",
        "Văn phòng Khoa Toán – Tin học trong danh bạ {cohort} nằm ở đâu?",
    ),
    "conduct": (
        "Sinh viên {cohort} đạt 72 điểm rèn luyện thì thuộc loại nào?",
        "55 điểm rèn luyện được bảng {cohort} xếp ở mức nào?",
    ),
    "formula": (
        "Điểm dùng để xét học bổng ở {cohort} kết hợp điểm học tập và rèn luyện ra sao?",
        "Trong biểu thức trung bình tích lũy của {cohort}, điểm học phần và tín chỉ được gắn trọng số thế nào?",
    ),
}

POSITIVE_EXPECTED = {
    "foreign_language": (("30", "45", "bậc 3"), ("150", "bậc 4")),
    "study_duration": ((), ()),
    "scholarship": (("1.25", "1,25", "Giỏi"), ("Khá",)),
    "scoring": (("C+",), ("A", "8.5", "8,5")),
    "service": (("Phòng Công nghệ Thông tin",), ("Phòng Công nghệ Thông tin",)),
    "office": (("Phòng Kế hoạch",), ("Phòng Khảo thí",)),
    "program": (("Khoa Toán",), ("Sư phạm Toán",)),
    "faculty": (("Khoa Toán",), ("Khoa Toán",)),
    "conduct": (("Khá",), ("Trung bình",)),
    "formula": (("80", "25", "20"), ("Σ", "ni", "ai")),
}


HARD_NEGATIVE_QUERIES = (
    ("foreign_language", "K48-K49", "Ai có thẩm quyền công nhận chứng chỉ ngoại ngữ nộp muộn của K48-K49?"),
    ("foreign_language", "K50", "K50 cần nộp minh chứng ngoại ngữ theo thủ tục và thời điểm nào?"),
    ("foreign_language", "K51", "Chứng chỉ ngoại ngữ giả bị xử lý theo quy định nào đối với K51?"),
    ("foreign_language", "K50", "Quy định về tổ chức thi chuẩn đầu ra ngoại ngữ cho K50 gồm những trách nhiệm gì?"),
    ("study_duration", "K48-K49", "Thời gian nghỉ vì nghĩa vụ quân sự có được tính vào tiến độ học K48-K49 không?"),
    ("study_duration", "K50", "K50 bị buộc thôi học khi vượt tiến độ theo điều kiện nào?"),
    ("study_duration", "K51", "Ai quyết định cho sinh viên K51 trở lại học sau thời gian tạm nghỉ?"),
    ("study_duration", "K51", "Việc chuyển trường ảnh hưởng thời gian học còn lại của K51 ra sao?"),
    ("scholarship", "K48-K49", "Nguồn quỹ học bổng tài trợ cho K48-K49 được tiếp nhận và thông báo thế nào?"),
    ("scholarship", "K50", "Sinh viên liên thông K50 có thuộc đối tượng nhận học bổng khuyến khích không?"),
    ("scholarship", "K51", "Thứ tự xét học bổng cho sinh viên năm cuối K51 được quy định ra sao?"),
    ("scholarship", "K50", "Khiếu nại kết quả xét học bổng K50 được gửi theo quy trình nào?"),
    ("scoring", "K48-K49", "K48-K49 được đăng ký thi cải thiện điểm trong trường hợp nào?"),
    ("scoring", "K50", "Điểm thi kết thúc học phần của K50 được công bố và phúc khảo ra sao?"),
    ("scoring", "K51", "Học phần không đạt của K51 phải đăng ký học lại theo nguyên tắc nào?"),
    ("scoring", "K51", "Điểm học phần bị hủy khi sinh viên K51 vi phạm thi cử thế nào?"),
    ("service", "K48-K49", "Hồ sơ hỗ trợ sinh viên khuyết tật K48-K49 được tiếp nhận theo trách nhiệm nào?"),
    ("service", "K50", "Đơn vị hỗ trợ có nghĩa vụ phản hồi kiến nghị của K50 ra sao?"),
    ("service", "K51", "Sinh viên K51 cần làm gì khi dịch vụ hành chính trả hồ sơ trễ?"),
    ("service", "K51", "Quy trình xác minh phản ánh về chất lượng phục vụ cho K51 được quy định ở đâu?"),
    ("office", "K48-K49", "Phòng Kế hoạch – Tài chính có trách nhiệm gì khi xác nhận nợ học phí K48-K49?"),
    ("office", "K50", "Phòng Khảo thí giải quyết đề nghị xem lại kết quả thi của K50 thế nào?"),
    ("office", "K51", "Trạm Y tế thực hiện nhiệm vụ chăm sóc sinh viên K51 theo quy định nào?"),
    ("office", "K51", "Phòng Hợp tác Quốc tế hỗ trợ hoạt động trao đổi sinh viên K51 ra sao?"),
    ("program", "K48-K49", "K48-K49 muốn học chương trình thứ hai phải đáp ứng điều kiện nào?"),
    ("program", "K50", "Việc chuyển ngành của K50 được xét vào thời điểm và theo thủ tục nào?"),
    ("program", "K51", "K51 có được công nhận tín chỉ khi chuyển chương trình đào tạo không?"),
    ("program", "K51", "Điều kiện học cùng lúc hai chương trình đối với K51 gồm những gì?"),
    ("faculty", "K48-K49", "Trường khoa chịu trách nhiệm gì trong việc tổ chức kế hoạch học tập K48-K49?"),
    ("faculty", "K50", "Khoa đào tạo xử lý đề nghị nghỉ học của sinh viên K50 theo trách nhiệm nào?"),
    ("faculty", "K51", "Khoa quản lý đánh giá rèn luyện sinh viên K51 qua những bước nào?"),
    ("faculty", "K51", "Khoa có trách nhiệm tư vấn đăng ký học phần cho K51 ra sao?"),
    ("conduct", "K50", "Điểm rèn luyện của K50 bị trừ khi vi phạm nội quy theo nguyên tắc nào?"),
    ("conduct", "K51", "Sinh viên K51 khiếu nại kết quả rèn luyện trong thời hạn nào?"),
    ("formula", "K48-K49", "Những học phần nào được tính vào điểm trung bình tích lũy K48-K49?"),
    ("formula", "K50", "Kết quả học cải thiện được dùng thay thế điểm cũ của K50 theo quy định nào?"),
)

AMBIGUOUS_QUERIES = (
    "Em muốn tra mức đó nhưng chưa nhớ đang nói về điểm hay tiền.",
    "Đơn vị phụ trách việc này nằm ở cơ sở nào?",
    "Chứng chỉ em vừa nhắc có được chấp nhận không?",
    "Ngành ấy thuộc khoa nào trong khóa của em?",
    "Mốc thời gian trên áp dụng cho hệ học nào vậy?",
    "Điểm này cần đối chiếu bảng học tập hay bảng rèn luyện?",
    "Điều 12 em đang xem thuộc quy chế nào?",
    "Thủ tục đó bắt đầu từ phòng nào?",
    "Loại học bổng vừa nói cần điều kiện gì?",
    "Khoa đó có email liên hệ nào?",
    "Kết quả vừa nêu được bảo lưu trong trường hợp nào?",
    "Quy định này dành cho khóa nào của em?",
)

OOD_QUERIES = (
    "So sánh hai mẫu máy ảnh du lịch mới nhất giúp mình.",
    "Tính lượng calo phù hợp cho thực đơn giảm cân một tuần.",
    "Viết lời quảng cáo cho cửa hàng giày thể thao.",
    "Tóm tắt diễn biến trận bóng tối qua.",
    "Nên chọn cổ phiếu nào để đầu tư ngắn hạn?",
    "Tạo lịch tập chạy marathon trong ba tháng.",
    "Chỉ mình cách sửa máy giặt không thoát nước.",
    "Gợi ý một bộ phim trinh thám để xem cuối tuần.",
)

ARCHITECTURE_SPECS = (
    ("K51", "TOPIK II 150 tương đương bậc nào và Sư phạm Toán học thuộc khoa nào?", ["structured"], ["foreign_language", "program"], ["K51"], False),
    ("K50", "72 điểm rèn luyện xếp loại gì và số điện thoại Phòng Kế hoạch – Tài chính là gì?", ["structured"], ["scoring", "office"], ["K50"], False),
    ("K48-K49", "Hệ số tiền học bổng Giỏi là bao nhiêu và đơn vị nào hỗ trợ Wi-Fi sinh viên?", ["structured"], ["scholarship_classification", "student_service"], ["K48-K49"], False),
    ("K51", "Điểm 6,8 đổi thành chữ gì và Khoa Toán – Tin học quản lý những ngành nào?", ["structured"], ["scoring", "program"], ["K51"], False),
    ("K50", "Công thức điểm xét học bổng là gì và email Khoa Toán – Tin học là gì?", ["structured"], ["formula", "faculty"], ["K50"], False),
    ("K51", "TOPIK II 150 tương đương bậc nào và thủ tục công nhận chuẩn ngoại ngữ thực hiện ra sao?", ["structured", "rag"], ["foreign_language"], ["K51"], False),
    ("K50", "Hệ số học bổng Giỏi là bao nhiêu và sinh viên được khiếu nại kết quả xét thế nào?", ["structured", "rag"], ["scholarship_classification"], ["K50"], False),
    ("K48-K49", "Sư phạm Toán học thuộc khoa nào và điều kiện học chương trình thứ hai là gì?", ["structured", "rag"], ["program"], ["K48-K49"], False),
    ("K51", "72 điểm rèn luyện thuộc loại gì và việc đánh giá rèn luyện được tổ chức qua các bước nào?", ["structured", "rag"], ["scoring"], ["K51"], False),
    ("K50", "Cho em địa chỉ Phòng Khảo thí và quy trình phúc khảo điểm học phần.", ["structured", "rag"], ["office"], ["K50"], False),
    ("K51", "Giới hạn thời gian học chính quy và các điều kiện công nhận tốt nghiệp của K51 là gì?", ["structured", "rag"], ["study_duration"], ["K51"], False),
    ("K50", "Quy định về sinh viên ngoại trú và hoạt động nghiên cứu khoa học có những trách nhiệm nào?", ["rag"], [], ["K50"], False),
    ("K51", "Trách nhiệm của cố vấn học tập và xử lý vi phạm sinh viên được quy định thế nào?", ["rag"], [], ["K51"], False),
    ("K48-K49", "Sinh viên sư phạm phải bồi hoàn hỗ trợ khi nào và gia đình có trách nhiệm gì?", ["rag"], [], ["K48-K49"], False),
    ("K51", "Quy tắc trang phục và ứng xử trong khi thực tập của người học gồm những gì?", ["rag"], [], ["K51"], False),
    ("K51", "So sánh điểm 6,8 quy đổi ở K50 và K51.", ["structured"], ["scoring"], ["K50", "K51"], False),
    ("K51", "Sư phạm Toán học thuộc khoa nào ở K48-K49 và K51?", ["structured"], ["program"], ["K48-K49", "K51"], False),
    ("K51", "So sánh hệ số tiền học bổng Giỏi giữa K50 và K51.", ["structured"], ["scholarship_classification"], ["K50", "K51"], False),
    ("K51", "TOPIK II 150 được quy đổi thế nào cho sinh viên K48-K49 và K51?", ["structured"], ["foreign_language"], ["K48-K49", "K51"], False),
    ("K51", "Phòng phụ trách dịch vụ đó có số liên hệ nào?", ["clarify"], [], [], True),
    ("K51", "TOEIC bốn kỹ năng của em mới có tổng điểm, đã xác định được bậc chưa?", ["structured"], ["foreign_language"], ["K51"], True),
    ("K51", "Sư phạm Toán học và Toán ứng dụng lần lượt thuộc khoa nào?", ["structured"], ["program"], ["K51"], False),
    ("K50", "Cho em thông tin liên hệ Phòng Kế hoạch – Tài chính và Phòng Khảo thí.", ["structured"], ["office"], ["K50"], False),
    ("K51", "TOPIK II 150 tương đương bậc nào, 72 điểm rèn luyện xếp loại gì và quy định khiếu nại kết quả ra sao?", ["structured", "rag"], ["foreign_language", "scoring"], ["K51"], False),
)


def _retag_common(case: dict[str, Any], case_id: str, query: str) -> dict[str, Any]:
    result = copy.deepcopy(case)
    result.update(
        {
            "id": case_id,
            "query": query,
            "near_duplicate_reviewed": False,
            "duplicate_group": None,
            "predecessor_case_id": None,
            "contract_version": "query-plan-unseen-holdout-v5",
        }
    )
    result["tags"] = sorted(
        {tag for tag in result.get("tags") or [] if not str(tag).startswith("v9")}
        | {"architecture_v5", "unseen_holdout"}
    )
    return result


def _build_deterministic() -> list[dict[str, Any]]:
    source = load_json(ROOT / "data" / "eval" / "architecture_v4" / "deterministic_tool_cases.json")
    positives = [case for case in source if case.get("case_type") == "positive"]
    positive_ordinals: Counter[tuple[str, str]] = Counter()
    result: list[dict[str, Any]] = []
    index = 0
    for old_case in positives:
        lookup_group = str(old_case["lookup_group"])
        cohort = str(old_case["cohort"])
        ordinal = positive_ordinals[(lookup_group, cohort)]
        positive_ordinals[(lookup_group, cohort)] += 1
        query = POSITIVE_QUERIES[lookup_group][ordinal].format(cohort=cohort)
        index += 1
        case = _retag_common(old_case, f"v5_det_{index:03d}", query)
        case["duplicate_group"] = f"v5_det_{lookup_group}_{ordinal}"
        case["expected_contains_any"] = list(POSITIVE_EXPECTED[lookup_group][ordinal])
        case.pop("expected_numeric_value", None)
        case.pop("numeric_tolerance", None)
        result.append(case)

    hard_template = next(case for case in source if case.get("case_type") == "hard_negative")
    for lookup_group, cohort, query in HARD_NEGATIVE_QUERIES:
        index += 1
        case = _retag_common(hard_template, f"v5_det_{index:03d}", query)
        case.update(
            {
                "lookup_group": lookup_group,
                "cohort": cohort,
                "expected_group": "rag",
                "expected_intent": "open_question",
                "expected_strategy": "query_plan_execution",
                "expected_lookup_type": None,
                "expected_llm_called": True,
                "expected_citation_cohort": cohort,
                "expected_citation_content_type": "regulation_text",
                "topic": "khac",
                "expected_path": "regulation_rag",
                "expected_plan": {
                    "task_count": 1,
                    "allowed_modes": ["rag"],
                    "lookup_types": [],
                    "cohorts": [cohort],
                    "out_of_domain": False,
                    "needs_clarification": False,
                },
                "expected_intents": [],
                "expected_strategies": ["query_plan_execution"],
            }
        )
        case.pop("expected_contains_any", None)
        result.append(case)

    ambiguous_template = next(case for case in source if case.get("case_type") == "ambiguous")
    for ordinal, query in enumerate(AMBIGUOUS_QUERIES):
        index += 1
        cohort = COHORTS[ordinal % len(COHORTS)]
        case = _retag_common(ambiguous_template, f"v5_det_{index:03d}", query)
        case.update(
            {
                "lookup_group": "ambiguous",
                "cohort": cohort,
                "expected_group": "clarification",
                "expected_intent": "clarification",
                "expected_strategy": "query_plan_execution",
                "expected_lookup_type": None,
                "expected_llm_called": False,
                "expected_citation_cohort": None,
                "expected_citation_content_type": None,
                "topic": "khac",
                "question_style": "ambiguous",
                "expected_path": "clarify",
                "question_specificity": "ambiguous",
                "expected_answer_behavior": "clarify_or_scope",
                "eval_split": "stress",
                "expected_plan": {
                    "task_count": 1,
                    "allowed_modes": ["clarify"],
                    "lookup_types": [],
                    "cohorts": [],
                    "out_of_domain": False,
                    "needs_clarification": True,
                },
                "expected_intents": ["clarification"],
                "expected_strategies": ["query_plan_execution"],
            }
        )
        result.append(case)

    ood_template = next(case for case in source if case.get("case_type") == "out_of_domain")
    for ordinal, query in enumerate(OOD_QUERIES):
        index += 1
        cohort = COHORTS[ordinal % len(COHORTS)]
        case = _retag_common(ood_template, f"v5_det_{index:03d}", query)
        case.update(
            {
                "lookup_group": "guardrail",
                "cohort": cohort,
                "expected_group": "guardrail",
                "expected_intent": "out_of_domain",
                "expected_strategy": "out_of_domain",
                "expected_lookup_type": None,
                "expected_llm_called": False,
                "expected_citation_cohort": None,
                "expected_citation_content_type": None,
                "topic": "khac",
                "question_style": "stress",
                "expected_path": "out_of_domain",
                "question_specificity": "unanswerable",
                "expected_answer_behavior": "abstain",
                "eval_split": "stress",
                "expected_plan": {
                    "task_count": 0,
                    "allowed_modes": [],
                    "lookup_types": [],
                    "cohorts": [],
                    "out_of_domain": True,
                    "needs_clarification": False,
                },
                "expected_intents": ["out_of_domain"],
                "expected_strategies": ["out_of_domain"],
            }
        )
        result.append(case)

    architecture_template = next(case for case in source if case.get("case_type") == "architecture")
    for cohort, query, modes, lookup_types, cohorts, clarify in ARCHITECTURE_SPECS:
        index += 1
        case = _retag_common(architecture_template, f"v5_det_{index:03d}", query)
        expected_path = "clarify" if modes == ["clarify"] else "mixed" if len(modes) > 1 else "structured" if modes == ["structured"] else "regulation_rag"
        task_count = 1 if clarify or len(modes) == 1 else len(lookup_types) + (1 if "rag" in modes else 0)
        if len(cohorts) > 1 and len(modes) == 1:
            task_count = 1
        case.update(
            {
                "lookup_group": "architecture",
                "cohort": cohort,
                "expected_group": "clarification" if modes == ["clarify"] else "structured" if modes == ["structured"] else "rag" if modes == ["rag"] else "clarification_or_structured" if clarify else "structured",
                "expected_intent": "query_plan",
                "expected_strategy": "query_plan_execution",
                "expected_lookup_type": None,
                "expected_llm_called": True,
                "expected_citation_cohort": cohort,
                "expected_citation_content_type": None,
                "topic": "khac",
                "question_style": "stress" if len(modes) > 1 else "realistic",
                "expected_path": expected_path,
                "cohort_sensitivity": "multi_cohort_risk" if len(cohorts) > 1 else "single_cohort",
                "question_specificity": "ambiguous" if clarify else "specific",
                "expected_answer_behavior": "clarify_or_scope" if clarify else "direct_answer",
                "eval_split": "stress" if len(modes) > 1 or clarify else "realistic",
                "expected_plan": {
                    "task_count": task_count,
                    "allowed_modes": modes,
                    "lookup_types": lookup_types,
                    "cohorts": cohorts,
                    "out_of_domain": False,
                    "needs_clarification": clarify,
                },
                "expected_intents": [],
                "expected_strategies": ["query_plan_execution"],
            }
        )
        case.pop("expected_contains_any", None)
        result.append(case)
    if len(result) != COUNTS["deterministic"]:
        raise AssertionError(len(result))
    return result


STRUCTURED_SPECS: dict[str, dict[str, Any]] = {
    "foreign_language": {
        "query": "Theo bảng áp dụng cho {cohort}, TOPIK II đạt 150 tương đương bậc ngoại ngữ nào?",
        "sources": {cohort: "K50_foreign_language_equivalency_dieu8" for cohort in COHORTS},
        "required": "TOPIK II 150 tương đương bậc 4.",
        "topic": "ngoai_ngu",
    },
    "study_duration": {
        "query": "Bảng {cohort} cho biết đồng thời thời gian chuẩn và tối đa của hệ chính quy là bao nhiêu?",
        "sources": {
            "K48-K49": "K48_49_QuyCheDaoTao_Chuong1_Dieu3_study_duration_chinh_quy",
            "K50": "K50_QuyCheDaoTao_Chuong1_Dieu3_study_duration_chinh_quy",
            "K51": "K51_QuyCheDaoTao_Chuong1_Dieu3_study_duration_chinh_quy",
        },
        "required": {
            "K48-K49": "Hệ chính quy cấp bằng thứ nhất có thời gian học tối đa 8 năm.",
            "K50": "Hệ chính quy cấp bằng thứ nhất có thời gian học tối đa 8 năm.",
            "K51": "Hệ chính quy có thời gian học tối đa 6 năm.",
        },
        "topic": "tot_nghiep",
    },
    "scholarship": {
        "query": "Mức tiền học bổng loại Giỏi của {cohort} dùng hệ số bao nhiêu?",
        "sources": {
            "K48-K49": "K48-K49_K48-K49_scoring_tables_6",
            "K50": "K50_K50_scoring_tables_6",
            "K51": "K51_K51_scoring_tables_8",
        },
        "required": "Mức tiền học bổng Giỏi = số tín chỉ x định mức học phí 01 tín chỉ x 1,25.",
        "topic": "hoc_bong",
    },
    "scoring": {
        "query": "Điểm 6,8 của {cohort} được bảng thang 10 quy đổi thành điểm chữ nào?",
        "sources": {
            "K48-K49": "K48_49_QuyCheDaoTao_Chuong3_Dieu10_grade_scale_general",
            "K50": "K50_QuyCheDaoTao_Chuong3_Dieu10_grade_scale_general",
            "K51": "K51_QuyCheDaoTao_Chuong3_Dieu10_grade_scale_foundation",
        },
        "required": "Điểm 6,8 thuộc khoảng 6,3-6,9 và được quy đổi thành C+.",
        "topic": "diem",
    },
    "conduct": {
        "query": "Với 72 điểm rèn luyện, sinh viên {cohort} được xếp loại nào?",
        "sources": {
            "K48-K49": "K48_49_QuyCheDanhGiaKetQuaRenLuyen_Chuong3_Dieu9_conduct_classification",
            "K50": "K50_QuyCheDanhGiaKetQuaRenLuyen_Chuong3_Dieu9_conduct_classification",
            "K51": "K51_QuyCheDanhGiaRenLuyen_Chuong3_Dieu9_conduct_classification",
        },
        "required": "72 điểm rèn luyện thuộc loại Khá.",
        "topic": "ren_luyen",
    },
    "service": {
        "query": "Sinh viên {cohort} cần hỗ trợ kết nối Wi-Fi thì nên tìm đơn vị nào?",
        "sources": {
            "K48-K49": "K48-K49_phong_cong_nghe_thong_tin",
            "K50": "K50_phong_cong_nghe_thong_tin",
            "K51": "K51_phong_cong_nghe_thong_tin",
        },
        "required": "Phòng Công nghệ Thông tin hỗ trợ kết nối mạng và Wi-Fi sinh viên.",
        "topic": "phong_ban",
    },
    "office": {
        "query": "Danh bạ {cohort} ghi số điện thoại và địa chỉ Phòng Kế hoạch – Tài chính thế nào?",
        "sources": {cohort: f"{cohort}_phong_ke_hoach_tai_chinh" for cohort in COHORTS},
        "required": "Trả đúng số điện thoại và địa chỉ Phòng Kế hoạch – Tài chính của cohort.",
        "topic": "phong_ban",
    },
    "faculty": {
        "query": "Cho em email và vị trí văn phòng Khoa Toán – Tin học trong danh bạ {cohort}.",
        "sources": {
            "K48-K49": "K48-K49_faculty_2",
            "K50": "K50_faculty_2",
            "K51": "K51_faculty_2",
        },
        "required": "Trả đúng email và văn phòng Khoa Toán – Tin học của cohort.",
        "topic": "phong_ban",
    },
    "program": {
        "query": "Ngành Sư phạm Toán học trong danh mục {cohort} thuộc khoa nào?",
        "sources": {
            "K48-K49": "K48-K49_program_3",
            "K50": "K50_program_3",
            "K51": "K51_program_37",
        },
        "required": "Ngành Sư phạm Toán học thuộc Khoa Toán – Tin học.",
        "topic": "nganh_hoc",
    },
    "formula": {
        "query": "Điểm xét học bổng của {cohort} kết hợp điểm học tập và điểm rèn luyện theo biểu thức nào?",
        "sources": {
            "K48-K49": "K48-K49_K48-K49_formula_rules_2",
            "K50": "K50_K50_formula_rules_2",
            "K51": "K51_K51_formula_rules_2",
        },
        "required": "Điểm học bổng = (Điểm học tập × 80 + Điểm rèn luyện / 25 × 20) / 100.",
        "topic": "hoc_bong",
    },
}


def _answer_base(
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
        "tags": ["architecture_v5", "answer_quality", "unseen_holdout", eval_split, expected_path],
        "topic": topic,
        "query_style": "student_realistic" if eval_split == "realistic" else "stress",
        "question_style": "realistic" if eval_split == "realistic" else "stress",
        "expected_intent": "query_plan" if expected_path in {"mixed", "clarify"} else f"{expected_path}_query",
        "expected_strategy": "query_plan_execution" if expected_path == "mixed" else expected_path,
        "expected_path": expected_path,
        "cohort_sensitivity": "single_cohort" if cohort != "general" else "none",
        "question_specificity": "ambiguous" if expected_path == "clarify" else "unanswerable" if answerability == "unanswerable" else "specific",
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
        "contract_version": "answer-quality-unseen-holdout-v5",
    }


def _rag_answers(
    retrieval: list[dict[str, Any]], docs_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for cohort in ("K48-K49", "K50", "K51", "general"):
        selected.extend([case for case in retrieval if case["cohort"] == cohort][:18])
    answers: list[dict[str, Any]] = []
    for index, retrieval_case in enumerate(selected, 1):
        judgments = copy.deepcopy(retrieval_case["relevance_judgments"])
        sources = [docs_by_id[str(item["parent_section_id"])] for item in judgments]
        ground_truth = "\n\n--- Equivalent source edition ---\n\n".join(
            dict.fromkeys(_reference_text(source) for source in sources)
        )
        case = _answer_base(
            case_id=f"v5_ans_rag_{index:03d}",
            case_type="regulation_true_rag",
            query=retrieval_case["query"],
            cohort=retrieval_case["cohort"],
            expected_path="regulation_rag",
            topic=retrieval_case["topic"],
            answerability="answerable",
            behavior="scoped_summary",
            eval_split=retrieval_case["eval_split"],
        )
        case.update(
            {
                "tags": sorted(set(case["tags"] + retrieval_case["tags"])),
                "duplicate_group": retrieval_case["duplicate_group"],
                "near_duplicate_reviewed": True,
                "linked_retrieval_case_id": retrieval_case["id"],
                "relevance_judgments": judgments,
                "expected_citations": copy.deepcopy(judgments),
                "ground_truth": ground_truth,
                "required_facts": _required_facts_from_text(
                    sources[0], cohort=retrieval_case["cohort"]
                ),
                "forbidden_claims": [
                    "Không dùng quy định của cohort khác nếu evidence không xác nhận applicability.",
                    "Không thêm điều kiện, con số hoặc ngoại lệ ngoài evidence.",
                ],
                "source_relation": "fresh_direct_parent_section",
            }
        )
        answers.append(case)
    return answers


def _structured_answers(
    structured_index: dict[tuple[str, str], dict[str, Any]]
) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    index = 0
    for catalog, spec in STRUCTURED_SPECS.items():
        for cohort in COHORTS:
            index += 1
            source_id = spec["sources"][cohort]
            record = structured_index.get((catalog, source_id))
            if record is None:
                raise ValueError(f"Missing structured source {catalog}:{source_id}")
            if not is_cohort_applicable(record, cohort):
                raise ValueError(f"Structured source {source_id} does not apply to {cohort}")
            required = spec["required"]
            required_fact = required[cohort] if isinstance(required, dict) else required
            case = _answer_base(
                case_id=f"v5_ans_struct_{index:03d}",
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
                    "lookup_group": catalog,
                    "expected_content_types": ["structured_lookup"],
                    "expected_structured_sources": [{"catalog": catalog, "source_id": source_id}],
                    "ground_truth": _record_ground_truth(record),
                    "required_facts": [required_fact],
                    "forbidden_claims": [
                        "Không thay đổi giá trị deterministic đã được bảng xác lập.",
                        "Không sao chép toàn bộ bảng vào Markdown khi UI render bảng riêng.",
                    ],
                    "source_relation": "deterministic_structured_record",
                    "duplicate_group": f"v5_structured_{catalog}",
                    "tags": sorted(set(case["tags"] + [catalog, "structured_provenance_required"])),
                }
            )
            answers.append(case)
    return answers


MIXED_PREFIX = {
    "foreign_language": "TOPIK II 150 tương đương bậc nào",
    "scholarship": "mức tiền học bổng Giỏi dùng hệ số bao nhiêu",
    "study_duration": "thời gian tối đa của hệ chính quy là bao lâu",
    "scoring": "điểm 6,8 đổi thành điểm chữ gì",
    "conduct": "72 điểm rèn luyện thuộc loại nào",
    "office": "Phòng Kế hoạch – Tài chính có số liên hệ nào",
}


def _mixed_answers(
    retrieval: list[dict[str, Any]],
    docs_by_id: dict[str, dict[str, Any]],
    structured_index: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    catalogs = tuple(MIXED_PREFIX)
    answers: list[dict[str, Any]] = []
    index = 0
    for cohort in COHORTS:
        pool = [case for case in retrieval if case["cohort"] == cohort]
        for ordinal, catalog in enumerate(catalogs):
            index += 1
            regulation_case = pool[18 + ordinal]
            judgment = copy.deepcopy(regulation_case["relevance_judgments"][0])
            source = docs_by_id[str(judgment["parent_section_id"])]
            spec = STRUCTURED_SPECS[catalog]
            source_id = spec["sources"][cohort]
            record = structured_index[(catalog, source_id)]
            required = spec["required"]
            required_fact = required[cohort] if isinstance(required, dict) else required
            query = (
                f"Đối với {cohort}, {MIXED_PREFIX[catalog]}; đồng thời "
                f"{regulation_case['query'][0].lower() + regulation_case['query'][1:]}"
            )
            case = _answer_base(
                case_id=f"v5_ans_mixed_{index:03d}",
                case_type="mixed_answer",
                query=query,
                cohort=cohort,
                expected_path="mixed",
                topic=regulation_case["topic"],
                answerability="answerable",
                behavior="direct_answer",
                eval_split="stress" if ordinal == len(catalogs) - 1 else "realistic",
            )
            case.update(
                {
                    "lookup_group": catalog,
                    "duplicate_group": f"v5_mixed_{index:03d}",
                    "expected_content_types": ["structured_lookup", "regulation_text"],
                    "expected_structured_sources": [{"catalog": catalog, "source_id": source_id}],
                    "relevance_judgments": [judgment],
                    "expected_citations": [copy.deepcopy(judgment)],
                    "ground_truth": "Structured evidence:\n" + _record_ground_truth(record) + "\n\nRegulation evidence:\n" + _reference_text(source),
                    "required_facts": [required_fact] + _required_facts_from_text(source, limit=2, cohort=cohort),
                    "forbidden_claims": [
                        "Không nhập hai answer target thành một khái niệm duy nhất.",
                        "Không bỏ sót structured fact hoặc phần quy định độc lập.",
                    ],
                    "source_relation": "structured_plus_fresh_regulation",
                    "tags": sorted(set(case["tags"] + [catalog, "multi_intent", "citation_required"])),
                }
            )
            answers.append(case)
    return answers


CLARIFICATION = (
    ("Em có một chứng chỉ tiếng Anh nhưng chưa nói loại và điểm, có đạt chuẩn không?", "Cần loại chứng chỉ và mức điểm hoặc từng kỹ năng.", "ngoai_ngu"),
    ("Em muốn liên hệ khoa đó, cho em địa chỉ với.", "Cần tên khoa cụ thể.", "phong_ban"),
    ("Khoản học bổng này em nhận được bao nhiêu?", "Cần loại học bổng, số tín chỉ và định mức học phí.", "hoc_bong"),
    ("Điểm này được xếp mức nào vậy?", "Cần giá trị điểm và loại bảng cần đối chiếu.", "diem"),
    ("Em học chương trình đó tối đa đến năm nào?", "Cần cohort và hình thức hoặc chương trình đào tạo.", "tot_nghiep"),
    ("Ngành vừa nhắc hiện thuộc đơn vị nào?", "Cần tên ngành cụ thể.", "nganh_hoc"),
    ("Hồ sơ ấy phải gửi trước bốn tuần hay sau bốn tuần?", "Cần xác định loại hồ sơ và quy chế áp dụng.", "nghi_hoc"),
    ("Phòng phụ trách chuyện này có email nào?", "Cần nêu dịch vụ hoặc tên phòng cần liên hệ.", "phong_ban"),
    ("Điều 8 áp dụng cho em thế nào?", "Cần tên tài liệu hoặc quy chế chứa Điều 8.", "khac"),
    ("Mức cảnh báo đó được xóa lúc nào?", "Cần làm rõ cảnh báo học tập hay quyết định kỷ luật.", "khac"),
)

UNANSWERABLE = (
    ("Hệ thống cho biết hôm nay hồ sơ miễn học phí của em đang ở bước nào.", "Không có trạng thái hồ sơ cá nhân theo thời gian thực.", "hoc_phi"),
    ("Em còn thiếu chính xác bao nhiêu tín chỉ để tốt nghiệp?", "Không có hồ sơ học tập cá nhân.", "tot_nghiep"),
    ("Điểm thi môn gần nhất của em đã được nhập chưa?", "Không có bảng điểm cá nhân hiện tại.", "diem"),
    ("Cho em biết số phòng ký túc xá đã được xếp.", "Không có dữ liệu phân phòng cá nhân.", "phong_ban"),
    ("Đơn xin chuyển ngành của em được ai duyệt rồi?", "Không có trạng thái xử lý đơn cá nhân.", "nganh_hoc"),
    ("Tháng này tài khoản em bị trừ bao nhiêu tiền học phí?", "Không có giao dịch tài chính cá nhân.", "hoc_phi"),
    ("Điểm rèn luyện của em đang đứng thứ mấy trong lớp?", "Không có bảng xếp hạng cá nhân của lớp.", "ren_luyen"),
    ("Ngày mai cố vấn học tập của lớp em có lịch trực không?", "Không có lịch trực thời gian thực.", "phong_ban"),
    ("Chứng chỉ em tải lên đã được xác minh thật giả chưa?", "Không có trạng thái xác minh hồ sơ cá nhân.", "ngoai_ngu"),
    ("Bao giờ tiền học bổng kỳ này vào tài khoản của em?", "Không có lịch chi trả cá nhân theo thời gian thực.", "hoc_bong"),
)

ANSWER_OOD = (
    "Giúp mình chọn tai nghe chống ồn tốt để đi máy bay.",
    "Hướng dẫn làm bánh mì bơ tỏi tại nhà.",
    "Dự đoán tỷ số trận bóng cuối tuần này.",
    "Viết một đoạn mã JavaScript tạo hiệu ứng tuyết rơi.",
    "Lên kế hoạch đầu tư vàng trong sáu tháng.",
    "Đề xuất lịch trình du lịch Huế trong hai ngày.",
    "Tư vấn cách chăm sóc cây cảnh bị vàng lá.",
    "Viết lời chúc sinh nhật vui nhộn cho bạn thân.",
    "So sánh giá ba mẫu điện thoại mới ra mắt.",
    "Tạo thực đơn ăn chay giàu protein một tuần.",
)


def _negative_answers() -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    for index, (query, clarification, topic) in enumerate(CLARIFICATION, 1):
        cohort = COHORTS[(index - 1) % len(COHORTS)]
        case = _answer_base(case_id=f"v5_ans_clarify_{index:03d}", case_type="clarification", query=query, cohort=cohort, expected_path="clarify", topic=topic, answerability="unanswerable", behavior="clarify_or_scope", eval_split="stress")
        case.update({"ground_truth": clarification, "required_facts": [clarification], "forbidden_claims": ["Không tự chọn một cách hiểu khi thiếu slot quyết định."], "tags": sorted(set(case["tags"] + ["ambiguity_required"]))})
        answers.append(case)
    for index, (query, reason, topic) in enumerate(UNANSWERABLE, 1):
        cohort = COHORTS[(index - 1) % len(COHORTS)]
        case = _answer_base(case_id=f"v5_ans_unanswerable_{index:03d}", case_type="unanswerable", query=query, cohort=cohort, expected_path="regulation_rag", topic=topic, answerability="unanswerable", behavior="abstain", eval_split="stress")
        case.update({"ground_truth": reason, "required_facts": [reason], "forbidden_claims": ["Không bịa dữ liệu cá nhân hoặc trạng thái thời gian thực."], "tags": sorted(set(case["tags"] + ["safe_abstention", "in_domain_no_evidence"]))})
        answers.append(case)
    for index, query in enumerate(ANSWER_OOD, 1):
        case = _answer_base(case_id=f"v5_ans_ood_{index:03d}", case_type="out_of_domain", query=query, cohort="general", expected_path="out_of_domain", topic="khac", answerability="unanswerable", behavior="abstain", eval_split="stress")
        case.update({"ground_truth": "Yêu cầu nằm ngoài phạm vi Sổ tay sinh viên HCMUE.", "required_facts": ["Nêu ngắn gọn rằng yêu cầu nằm ngoài phạm vi trợ lý."], "forbidden_claims": ["Không dùng RAG hoặc structured lookup để bịa câu trả lời ngoài phạm vi."], "tags": sorted(set(case["tags"] + ["safe_ood"]))})
        answers.append(case)
    return answers


def _build_answers(
    retrieval: list[dict[str, Any]],
    docs_by_id: dict[str, dict[str, Any]],
    structured_index: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    answers = _rag_answers(retrieval, docs_by_id) + _structured_answers(structured_index) + _mixed_answers(retrieval, docs_by_id, structured_index) + _negative_answers()
    if len(answers) != COUNTS["answers"]:
        raise AssertionError(len(answers))
    actual = Counter(case["case_type"] for case in answers)
    if dict(actual) != ANSWER_TYPES:
        raise ValueError(f"answer distribution mismatch: {dict(actual)}")
    return answers


def _production_case(
    source: dict[str, Any],
    *,
    case_id: str,
    scenario: str,
    stream: bool,
    repeat_of: str | None = None,
    concurrency: int = 1,
) -> dict[str, Any]:
    case = {
        "id": case_id,
        "suite": "production",
        "scenario": scenario,
        "query": source["query"],
        "cohort": source["cohort"],
        "tags": sorted(set(source.get("tags") or []) | {"production", "architecture_v5"}),
        "expected_intent": source.get("expected_intent") or "query_plan",
        "expected_strategy": source.get("expected_strategy") or "query_plan_execution",
        "expected_path": source["expected_path"],
        "concurrency": concurrency,
        "stream": stream,
        "repeat_of": repeat_of,
        "duplicate_group": source.get("duplicate_group") or f"v5_source_{source['id']}",
        "near_duplicate_reviewed": True,
        "topic": source.get("topic") or "khac",
        "question_style": source.get("question_style") or "realistic",
        "cohort_sensitivity": source.get("cohort_sensitivity") or "single_cohort",
        "question_specificity": source.get("question_specificity") or "specific",
        "expected_answer_behavior": source.get("expected_answer_behavior") or "direct_answer",
        "eval_split": source.get("eval_split") or "realistic",
    }
    return case


def _select_by_cohort(
    cases: list[dict[str, Any]], counts: dict[str, int]
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for cohort, count in counts.items():
        pool = [case for case in cases if case.get("cohort") == cohort]
        if len(pool) < count:
            raise ValueError(f"Need {count} cases for cohort={cohort}, found {len(pool)}")
        selected.extend(pool[:count])
    return selected


def _build_production(
    retrieval: list[dict[str, Any]], deterministic: list[dict[str, Any]], answers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    cold_sources = _select_by_cohort(
        retrieval,
        {"general": 5, "K48-K49": 5, "K50": 5, "K51": 5},
    )
    for index, source in enumerate(cold_sources, 1):
        result.append(_production_case(source, case_id=f"v5_prod_cold_{index:02d}", scenario="cold_rag", stream=False))
    positive_sources = _select_by_cohort(
        [case for case in deterministic if case["case_type"] == "positive"],
        {"K48-K49": 4, "K50": 3, "K51": 3},
    )
    for index, source in enumerate(positive_sources, 1):
        result.append(_production_case(source, case_id=f"v5_prod_det_{index:02d}", scenario="deterministic", stream=False))
    warm_sources = [
        result[index]
        for index in (0, 5, 10, 15, 1, 6, 11, 16, 2, 7)
    ]
    for index, source in enumerate(warm_sources, 1):
        result.append(_production_case(source, case_id=f"v5_prod_warm_{index:02d}", scenario="warm_cache", stream=False, repeat_of=source["id"]))
    stream_sources = _select_by_cohort(
        [case for case in answers if case["case_type"] == "regulation_true_rag"],
        {"K48-K49": 3, "K50": 3, "K51": 2, "general": 2},
    )
    for index, source in enumerate(stream_sources, 1):
        result.append(_production_case(source, case_id=f"v5_prod_stream_{index:02d}", scenario="streaming", stream=True))
    burst_sources = _select_by_cohort(
        [
            case
            for case in answers
            if case["case_type"] in {"structured_answer", "mixed_answer"}
        ],
        {"K48-K49": 4, "K50": 3, "K51": 3},
    )
    for index, source in enumerate(burst_sources, 1):
        result.append(
            _production_case(
                source,
                case_id=f"v5_prod_burst_{index:02d}",
                scenario="burst",
                stream=False,
                concurrency=3 if index <= 5 else 5,
            )
        )
    if len(result) != COUNTS["production"]:
        raise AssertionError(len(result))
    return result


def _ragas_subset(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = (
        _select_by_cohort(
            [case for case in answers if case["case_type"] == "regulation_true_rag"],
            {"K48-K49": 8, "K50": 8, "K51": 7, "general": 7},
        )
        + _select_by_cohort(
            [case for case in answers if case["case_type"] == "structured_answer"],
            {"K48-K49": 5, "K50": 5, "K51": 5},
        )
        + _select_by_cohort(
            [case for case in answers if case["case_type"] == "mixed_answer"],
            {"K48-K49": 5, "K50": 5, "K51": 5},
        )
    )
    rows = [
        {
            "id": case["id"],
            "case_type": case["case_type"],
            "cohort": case["cohort"],
            "user_input": case["query"],
            "reference": case["ground_truth"],
            "response": None,
            "retrieved_contexts": [],
            "expected_citations": case.get("expected_citations") or [],
            "expected_structured_sources": case.get("expected_structured_sources") or [],
        }
        for case in selected
    ]
    return rows


def _human_audit(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = {
        "regulation_true_rag": 16,
        "structured_answer": 8,
        "mixed_answer": 6,
        "clarification": 3,
        "unanswerable": 3,
        "out_of_domain": 4,
    }
    selected: list[dict[str, Any]] = []
    for case_type, count in targets.items():
        pool = [case for case in answers if case["case_type"] == case_type]
        if case_type == "regulation_true_rag":
            selected.extend(
                _select_by_cohort(
                    pool,
                    {"K48-K49": 4, "K50": 4, "K51": 4, "general": 4},
                )
            )
        elif case_type == "structured_answer":
            selected.extend(
                _select_by_cohort(pool, {"K48-K49": 3, "K50": 3, "K51": 2})
            )
        elif case_type == "mixed_answer":
            selected.extend(
                _select_by_cohort(pool, {"K48-K49": 2, "K50": 2, "K51": 2})
            )
        else:
            selected.extend(pool[:count])
    return [
        {
            "id": case["id"],
            "case_type": case["case_type"],
            "query": case["query"],
            "cohort": case["cohort"],
            "human_verdict": None,
            "correctness": None,
            "faithfulness": None,
            "citation_correctness": None,
            "completeness": None,
            "notes": "",
            "repeat_for_consistency": ordinal < 5,
        }
        for ordinal, case in enumerate(selected)
    ]
def _char_ngrams(value: str, n: int = 3) -> Counter[str]:
    compact = f"  {normalize_query(value)}  "
    return Counter(compact[index : index + n] for index in range(max(0, len(compact) - n + 1)))


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    common = left.keys() & right.keys()
    numerator = sum(left[key] * right[key] for key in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _overlap_audit(
    datasets: dict[str, list[dict[str, Any]]], old: dict[str, Any]
) -> dict[str, Any]:
    new_rows = [
        (case["id"], case["query"], suite)
        for suite, cases in datasets.items()
        for case in cases
    ]
    old_items = list(old["queries"].items())
    old_vectors = [(normalized, _char_ngrams(info["query"]), info) for normalized, info in old_items]
    exact: list[dict[str, Any]] = []
    top_matches: list[dict[str, Any]] = []
    for case_id, query, suite in new_rows:
        normalized = normalize_query(query)
        if normalized in old["queries"]:
            exact.append({"id": case_id, "suite": suite, **old["queries"][normalized]})
        vector = _char_ngrams(query)
        best_score = -1.0
        best_info: dict[str, str] | None = None
        for _, old_vector, info in old_vectors:
            score = _cosine(vector, old_vector)
            if score > best_score:
                best_score = score
                best_info = info
        top_matches.append(
            {
                "id": case_id,
                "suite": suite,
                "query": query,
                "max_char_trigram_cosine": round(best_score, 6),
                "closest_old_query": (best_info or {}).get("query"),
                "closest_old_path": (best_info or {}).get("path"),
            }
        )
    top_matches.sort(key=lambda row: row["max_char_trigram_cosine"], reverse=True)
    retrieval_anchor_ids = {
        str(judgment["parent_section_id"])
        for case in datasets["retrieval"]
        for judgment in case.get("relevance_judgments") or []
    }
    primary_topic_keys = {
        _topic_key(source)
        for source_id in retrieval_anchor_ids
        if (source := DOCS_BY_ID_FOR_AUDIT.get(source_id)) is not None
    }
    topic_overlap = primary_topic_keys & old["anchor_topic_keys"]
    return {
        "contract": "frozen-holdout-overlap-audit-v1",
        "ok": not exact and not topic_overlap,
        "old_json_files_scanned": old["scanned_files"],
        "old_unique_queries": len(old["queries"]),
        "new_query_rows": len(new_rows),
        "exact_query_overlap_count": len(exact),
        "exact_query_overlaps": exact,
        "retrieval_anchor_id_overlap_count": len(retrieval_anchor_ids & old["anchor_ids"]),
        "retrieval_topic_group_overlap_count": len(topic_overlap),
        "max_lexical_similarity": top_matches[0]["max_char_trigram_cosine"] if top_matches else 0.0,
        "top_25_lexical_matches": top_matches[:25],
        "policy": (
            "Exact query overlap and retrieval topic-group overlap are forbidden. "
            "High lexical matches are disclosed for manual review, not silently discarded."
        ),
    }


DOCS_BY_ID_FOR_AUDIT: dict[str, dict[str, Any]] = {}


def _coverage(
    datasets: dict[str, list[dict[str, Any]]],
    ragas: list[dict[str, Any]],
    human: list[dict[str, Any]],
    overlap: dict[str, Any],
) -> dict[str, Any]:
    answers = datasets["answers"]
    retrieval = datasets["retrieval"]
    return {
        "contract": "architecture-v5-static-coverage-audit",
        "ok": overlap["ok"],
        "errors": [] if overlap["ok"] else ["old-set overlap detected"],
        "counts": {suite: len(cases) for suite, cases in datasets.items()},
        "deterministic_case_type_counts": dict(Counter(case["case_type"] for case in datasets["deterministic"])),
        "retrieval_cohort_counts": dict(Counter(case["cohort"] for case in retrieval)),
        "retrieval_eval_split_counts": dict(Counter(case["eval_split"] for case in retrieval)),
        "retrieval_unique_primary_sources": len({case["relevance_judgments"][0]["parent_section_id"] for case in retrieval}),
        "answer_case_type_counts": dict(Counter(case["case_type"] for case in answers)),
        "answer_cohort_counts": dict(Counter(case["cohort"] for case in answers)),
        "answer_path_counts": dict(Counter(case["expected_path"] for case in answers)),
        "answer_structured_lookup_counts": dict(Counter(case.get("lookup_group") for case in answers if case["case_type"] == "structured_answer")),
        "ragas_count": len(ragas),
        "ragas_case_type_counts": dict(Counter(case["case_type"] for case in ragas)),
        "human_audit_count": len(human),
        "human_audit_case_type_counts": dict(Counter(case["case_type"] for case in human)),
        "overlap_audit": overlap,
        "ground_truth_policy": "Derived from v32 parent documents and structured records before any system execution.",
    }


def _readme() -> str:
    return """# Architecture v5 unseen holdout

This bundle is the frozen, one-shot evaluation set for source commit `71e5ad5c`.
It replaces development-era headline metrics; older suites remain regression sets.

| Suite | Cases | Headline metrics |
|---|---:|---|
| Deterministic | 140 | exact path/tool/cohort/resolution accuracy |
| Retrieval | 160 | Hit@1/3/5, MRR, nDCG, observed cohort leakage |
| Generate + Judge | 150 | correctness, completeness, groundedness, citation correctness |
| Production | 60 | success rate, TTFT p50/p95, latency p50/p95, stream/cache contract |

The retrieval suite contains 120 realistic questions and 40 controlled stress
questions. The answer suite contains 101 realistic and 49 stress cases, spanning
72 regulation RAG, 30 structured, 18 mixed, 10 clarification, 10 unanswerable and
10 out-of-domain cases. Stress coverage includes missing diacritics, multi-intent
requests, ambiguous references, insufficient evidence and cohort comparisons.

The 60-case RAGAS set is a frozen subset of answerable answer cases. The 40-case
human template is also selected before generation. Both subsets are stratified by
cohort and answer path. Every automatic failure must be human-reviewed in addition
to those 40 cases.

## Anti-contamination policy

- Questions, expected paths and ground truth are frozen before execution.
- Retrieval primary topics are absent from every earlier tracked evaluation anchor.
- Exact normalized queries are checked across historical evaluation JSON files.
- Lexical nearest neighbors are reported for manual inspection.
- The system is evaluated once. Failures become regression cases for a later version;
  this holdout is not rerun after tuning and cannot be reused as a headline test set.

Report denominators with every percentage and distinguish automatic judge, RAGAS and
human-review metrics. `evaluated_system_commit` identifies the code under evaluation;
dataset hashes in `manifest.json` pin the immutable data contract.
"""


def build_bundle(target: Path, *, freeze: bool) -> dict[str, Any]:
    docs = load_json(DOCSTORE)
    docs_by_id = {str(item.get("_id") or ""): item for item in docs}
    global DOCS_BY_ID_FOR_AUDIT
    DOCS_BY_ID_FOR_AUDIT = docs_by_id
    old = _old_material(docs_by_id)
    structured_index = _structured_source_index(ROOT)
    retrieval = _build_retrieval(docs, old)
    deterministic = _build_deterministic()
    answers = _build_answers(retrieval, docs_by_id, structured_index)
    production = _build_production(retrieval, deterministic, answers)
    datasets = {
        "deterministic": deterministic,
        "retrieval": retrieval,
        "answers": answers,
        "production": production,
    }
    overlap = _overlap_audit(datasets, old)
    ragas = _ragas_subset(answers)
    human = _human_audit(answers)
    coverage = _coverage(datasets, ragas, human, overlap)
    if not coverage["ok"]:
        raise ValueError("Static overlap/coverage audit failed")

    target.mkdir(parents=True, exist_ok=True)
    filenames = {
        "deterministic": "deterministic_tool_cases.json",
        "retrieval": "retrieval_cases.json",
        "answers": "generated_answer_cases.json",
        "production": "production_cases.json",
    }
    for suite, cases in datasets.items():
        write_json(target / filenames[suite], cases)
    write_json(target / "ragas_subset.json", ragas)
    write_json(target / "human_audit_template.json", human)
    write_json(target / "overlap_audit.json", overlap)
    write_json(target / "coverage_report.json", coverage)

    build_manifest = load_json(BUILD_MANIFEST)
    storage_targets = build_manifest.get("storage_targets") or {}
    manifest = {
        "version": "architecture-v5.0-unseen-one-shot-holdout",
        "frozen": freeze,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluated_system_commit": EVALUATED_SYSTEM_COMMIT,
        "description": "Unseen, source-grounded one-shot evaluation frozen after v32 deployment.",
        "counts": {suite: len(cases) for suite, cases in datasets.items()},
        "dataset_hashes": {suite: stable_json_hash(cases) for suite, cases in datasets.items()},
        "auxiliary_hashes": {
            "ragas_subset": stable_json_hash(ragas),
            "human_audit_template": stable_json_hash(human),
            "overlap_audit": stable_json_hash(overlap),
            "coverage_report": stable_json_hash(coverage),
        },
        "docstore_hash": file_hash(DOCSTORE),
        "config_hashes": {name: file_hash(path) for name, path in CONFIG_PATHS.items()},
        "generation_provider": "gemini",
        "generation_model": GENERATION_MODEL,
        "router_provider": "groq",
        "router_model": "qwen/qwen3.6-27b",
        "judge_provider": "groq",
        "judge_model": JUDGE_MODEL,
        "headline_backend": "qdrant_cloud+mongodb",
        "strict_structured_sources": True,
        "strict_cohort_conflicts": True,
        "strict_query_duplicates": True,
        "holdout_policy": "single_run_no_post_tuning",
        "previous_suites_are_development_only": True,
        "source_build_id": build_manifest.get("build_id"),
        "source_qdrant_collection": storage_targets.get("qdrant_collection"),
        "source_mongo_collection": storage_targets.get("mongo_parent_collection"),
        "evaluation_contract": "unseen-one-shot-source-grounded-v5",
        "deterministic_contract": "query-plan-unseen-holdout-v5",
        "retrieval_contract": "regulation-rag-source-first-v3",
        "answer_contract": "answer-quality-unseen-holdout-v5",
        "deterministic_case_type_counts": DETERMINISTIC_TYPES,
        "deterministic_positive_lookup_counts": {group: 6 for group in POSITIVE_QUERIES},
        "retrieval_cohort_counts": RETRIEVAL_COHORTS,
        "retrieval_eval_split_counts": RETRIEVAL_SPLITS,
        "retrieval_forbidden_query_fragments": [
            "hệ thống cần tìm đúng điều nào",
            "nội dung chính trong sổ tay là gì",
            "hỏi về general",
        ],
        "max_parent_query_usage": 2,
        "answer_case_type_counts": ANSWER_TYPES,
        "answer_path_counts": dict(Counter(case["expected_path"] for case in answers)),
        "answer_eval_split_counts": dict(Counter(case["eval_split"] for case in answers)),
        "human_audit_required_n": 40,
        "human_audit_repeat_n": 5,
        "human_audit_plus_all_automatic_failures": True,
        "ragas_subset_n": 60,
        "overlap_policy": overlap["policy"],
    }
    write_json(target / "manifest.json", manifest)
    (target / "README.md").write_text(_readme(), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build frozen architecture v5 unseen holdout")
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    manifest = build_bundle(args.target, freeze=args.freeze)
    validation = validate_bundle(args.target, DOCSTORE, require_frozen=args.freeze, enforce_docstore_hash=True)
    output = {"manifest": manifest, "validation": validation}
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 1 if validation.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
