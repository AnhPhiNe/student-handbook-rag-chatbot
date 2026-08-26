from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.common.cohort import admission_years_for_cohort, normalize_cohort


_AMENDMENT_NOTE_RE = re.compile(
    r"(?:^|\n)\s*(?P<note>"
    r"(?:\d+\s+)?(?:Điểm|Khoản|Điều|Nội dung)\s+này\b"
    r".{0,2600}?Cụ thể\s+như\s+sau\s*:\s*"
    r"[\u201c\"](?P<replacement>.{1,6000}?)[\u201d\"]"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)
_MIN_YEAR_RE = re.compile(
    r"áp\s+dụng\s+từ\s+(?:kh[oó][aá]\s+tuyển\s+sinh\s+)?năm\s+(\d{4})\s+trở\s+về\s+sau",
    flags=re.IGNORECASE,
)
_MAX_YEAR_RE = re.compile(
    r"(?:áp\s+dụng\s+)?(?:cho|đối\s+với)?\s*"
    r"(?:các\s+)?(?:kh[oó][aá]\s+tuyển\s+sinh\s+)?(?:từ\s+)?năm\s+"
    r"(\d{4})\s+trở\s+về\s+trước",
    flags=re.IGNORECASE,
)
_EXACT_YEAR_RE = re.compile(
    r"(?:áp\s+dụng\s+)?(?:cho|đối\s+với)\s+"
    r"(?:kh[oó][aá]\s+tuyển\s+sinh\s+)?năm\s+(\d{4})(?!\s+trở)",
    flags=re.IGNORECASE,
)
_AMENDMENT_CUE_RE = re.compile(
    r"(?:được|đã\s+được)\s+(?:sửa\s+đổi|bổ\s+sung)|sửa\s+đổi\s*,?\s*bổ\s+sung",
    flags=re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "anh",
    "bao",
    "bi",
    "cac",
    "can",
    "cho",
    "co",
    "cua",
    "em",
    "gi",
    "la",
    "mot",
    "nao",
    "nhung",
    "noi",
    "the",
    "thi",
    "thuoc",
    "toi",
    "va",
    "ve",
}


@dataclass(frozen=True)
class ApplicableAmendment:
    source_parent_id: str
    source_role: str
    source_title: str
    effective_rule: str
    replacement_text: str
    relevance_score: int
    source_document_id: str = ""
    source_locator: str = ""
    source_handbook_id: str = ""
    source_handbook_title: str = ""
    source_pages: tuple[int, ...] = ()


@lru_cache(maxsize=1)
def load_amendment_registry() -> tuple[dict[str, Any], ...]:
    path = Path(__file__).resolve().parents[2] / "data/processed/amendments/amendments.json"
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return ()
    return tuple(dict(item) for item in payload if isinstance(item, dict))


def strip_misattached_amendment_notes(
    content: str,
    *,
    source_parent_id: str,
    registry: tuple[dict[str, Any], ...] | None = None,
) -> str:
    """Remove footnotes whose authoritative target is another parent section."""

    records = registry if registry is not None else load_amendment_registry()
    targets_by_replacement = {
        _fold(str(record.get("replacement_text") or "")): str(
            record.get("target_parent_id") or ""
        )
        for record in records
        if record.get("replacement_text") and record.get("target_parent_id")
    }

    def replace(match: re.Match[str]) -> str:
        replacement = _fold(_clean_text(match.group("replacement")))
        target_parent_id = targets_by_replacement.get(replacement)
        if target_parent_id and target_parent_id != source_parent_id:
            return "\n"
        return match.group(0)

    return _AMENDMENT_NOTE_RE.sub(replace, content).strip()


def collect_applicable_amendments(
    retrieval_result: dict[str, Any],
    *,
    query: str,
    cohort: str | None,
    max_items: int = 4,
    max_replacement_chars: int = 5000,
    registry: tuple[dict[str, Any], ...] | None = None,
) -> list[ApplicableAmendment]:
    """Extract query-relevant amendments that apply to the requested cohort.

    Amendment footnotes may be physically attached to the following parent
    section after PDF extraction. Inspecting both primary and graph-related
    parents preserves those notes without changing citation/source IDs.
    """

    query_terms = _terms(query)
    requested_cohort = normalize_cohort(cohort)
    requested_years = admission_years_for_cohort(requested_cohort)
    candidates: list[ApplicableAmendment] = []
    seen_replacements: set[str] = set()
    records = registry if registry is not None else load_amendment_registry()
    registry_by_replacement = {
        _fold(str(record.get("replacement_text") or "")): record
        for record in records
        if record.get("replacement_text")
    }
    primary_items_by_parent_id = {
        str(
            (item.get("metadata") or {}).get("parent_section_id")
            or item.get("parent_section_id")
            or item.get("chunk_id")
            or ""
        ): item
        for item in retrieval_result.get("retrieved_items") or []
    }
    primary_parent_ids = set(primary_items_by_parent_id)

    # Curated registry records are authoritative. PDF extraction can omit a
    # closing quote at a page boundary, so requiring the footnote regex to
    # match would silently drop otherwise valid substantive amendments.
    for record in records:
        if str(record.get("importance") or "substantive") != "substantive":
            continue
        target_parent_id = str(record.get("target_parent_id") or "")
        if not target_parent_id or target_parent_id not in primary_parent_ids:
            continue
        record_cohort = normalize_cohort(str(record.get("cohort") or "") or None)
        if requested_cohort and record_cohort and record_cohort != requested_cohort:
            continue
        applies, effective_rule = _registry_applies_to_years(
            record.get("applicability"),
            requested_years,
        )
        if not applies:
            continue
        replacement = _clean_text(str(record.get("replacement_text") or ""))
        if not replacement:
            continue
        relevance_score = len(query_terms & _terms(replacement))
        if query_terms and relevance_score <= 0:
            continue
        replacement_key = _fold(replacement)
        seen_replacements.add(replacement_key)
        primary_item = primary_items_by_parent_id[target_parent_id]
        metadata = primary_item.get("metadata") or {}
        candidates.append(
            ApplicableAmendment(
                source_parent_id=target_parent_id,
                source_role="primary",
                source_title=str(
                    metadata.get("title")
                    or metadata.get("section_title")
                    or target_parent_id
                ),
                effective_rule=effective_rule,
                replacement_text=replacement[:max_replacement_chars].rstrip(),
                relevance_score=relevance_score,
                source_document_id=str(record.get("source_document_id") or ""),
                source_locator=str(record.get("source_locator") or ""),
                source_handbook_id=str(record.get("source_handbook_id") or ""),
                source_handbook_title=str(
                    record.get("source_handbook_title") or ""
                ),
                source_pages=_source_pages(record.get("source_pages")),
            )
        )

    for source_role, items in (
        ("primary", retrieval_result.get("retrieved_items") or []),
        ("related", retrieval_result.get("related_items") or []),
    ):
        for item in items:
            metadata = item.get("metadata") or {}
            item_cohort = normalize_cohort(
                str(metadata.get("cohort") or item.get("cohort") or "") or None
            )
            if requested_cohort and item_cohort and item_cohort != requested_cohort:
                continue

            content = str(item.get("content") or "")
            for match in _AMENDMENT_NOTE_RE.finditer(content):
                note = _clean_text(match.group("note"))
                replacement = _clean_text(match.group("replacement"))
                if not _AMENDMENT_CUE_RE.search(note):
                    continue

                applies, effective_rule = _applies_to_years(note, requested_years)
                if not applies:
                    continue

                relevance_score = len(query_terms & _terms(replacement))
                if query_terms and relevance_score <= 0:
                    continue

                replacement_key = _fold(replacement)
                if replacement_key in seen_replacements:
                    continue
                registry_record = registry_by_replacement.get(replacement_key)
                target_parent_id = str(
                    (registry_record or {}).get("target_parent_id") or ""
                )
                if target_parent_id:
                    # A graph-adjacent footnote can amend only its authoritative
                    # directly retrieved parent, never the section carrying it.
                    if target_parent_id not in primary_parent_ids:
                        continue
                seen_replacements.add(replacement_key)

                physical_parent_id = str(
                    metadata.get("parent_section_id")
                    or item.get("parent_section_id")
                    or item.get("chunk_id")
                    or ""
                )
                source_parent_id = target_parent_id or physical_parent_id
                source_title = str(
                    metadata.get("title")
                    or metadata.get("section_title")
                    or source_parent_id
                )
                candidates.append(
                    ApplicableAmendment(
                        source_parent_id=source_parent_id,
                        source_role=source_role,
                        source_title=source_title,
                        effective_rule=effective_rule,
                        replacement_text=replacement[:max_replacement_chars].rstrip(),
                        relevance_score=relevance_score,
                        source_document_id=str(
                            (registry_record or {}).get("source_document_id") or ""
                        ),
                        source_locator=str(
                            (registry_record or {}).get("source_locator") or ""
                        ),
                        source_handbook_id=str(
                            (registry_record or {}).get("source_handbook_id") or ""
                        ),
                        source_handbook_title=str(
                            (registry_record or {}).get("source_handbook_title") or ""
                        ),
                        source_pages=_source_pages(
                            (registry_record or {}).get("source_pages")
                        ),
                    )
                )

    candidates.sort(
        key=lambda amendment: (
            -amendment.relevance_score,
            amendment.source_role != "primary",
            amendment.source_parent_id,
        )
    )
    return candidates[: max(0, max_items)]


def _registry_applies_to_years(
    applicability: Any,
    years: tuple[int, ...],
) -> tuple[bool, str]:
    if not isinstance(applicability, dict):
        return True, "không nêu giới hạn khóa tuyển sinh"

    kind = str(applicability.get("kind") or "")
    try:
        year = int(applicability.get("year"))
    except (TypeError, ValueError):
        return False, "phạm vi hiệu lực không hợp lệ"

    if kind == "min_admission_year":
        return (
            bool(years) and all(item >= year for item in years),
            f"khóa tuyển sinh từ năm {year} trở về sau",
        )
    if kind == "max_admission_year":
        return (
            bool(years) and all(item <= year for item in years),
            f"khóa tuyển sinh đến năm {year}",
        )
    if kind == "exact_admission_year":
        return (
            bool(years) and all(item == year for item in years),
            f"khóa tuyển sinh năm {year}",
        )
    return False, "phạm vi hiệu lực không được hỗ trợ"


def _source_pages(value: Any) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    pages: list[int] = []
    for item in value:
        try:
            page = int(item)
        except (TypeError, ValueError):
            continue
        if page not in pages:
            pages.append(page)
    return tuple(pages)


def format_applicable_amendments(amendments: list[ApplicableAmendment]) -> str:
    if not amendments:
        return ""

    blocks = []
    for index, amendment in enumerate(amendments, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[AMENDMENT {index}]",
                    f"Nguồn: {amendment.source_title}",
                    f"Source ID: {amendment.source_parent_id}",
                    f"Phạm vi hiệu lực: {amendment.effective_rule}",
                    "Nội dung thay thế/bổ sung:",
                    amendment.replacement_text,
                ]
            )
        )
    return "APPLICABLE AMENDMENTS\n\n" + "\n\n---\n\n".join(blocks)


def _applies_to_years(note: str, years: tuple[int, ...]) -> tuple[bool, str]:
    min_year_match = _MIN_YEAR_RE.search(note)
    max_year_match = _MAX_YEAR_RE.search(note)
    exact_year_match = _EXACT_YEAR_RE.search(note)

    if min_year_match:
        min_year = int(min_year_match.group(1))
        return (
            bool(years) and all(year >= min_year for year in years),
            f"khóa tuyển sinh từ năm {min_year} trở về sau",
        )
    if max_year_match:
        max_year = int(max_year_match.group(1))
        return (
            bool(years) and all(year <= max_year for year in years),
            f"khóa tuyển sinh đến năm {max_year}",
        )
    if exact_year_match:
        exact_year = int(exact_year_match.group(1))
        return (
            bool(years) and all(year == exact_year for year in years),
            f"khóa tuyển sinh năm {exact_year}",
        )

    return True, "theo phạm vi của nguồn cùng cohort"


def _terms(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(_fold(value))
        if len(token) >= 2 and token not in _STOPWORDS
    }


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return without_marks.lower().replace("đ", "d")


def _clean_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", value)).strip()
