"""Check that every answerable field of a structured tool is one the planner knows about.

The planner picks a tool from `configs/structured_lookup_registry.yaml` alone: it
reads the tool's description and slot descriptions, never the data. A column the
data holds but no description names is therefore unreachable in practice — the
planner routes the question to whichever tool does advertise the words the
student used. official_v4 lost two cases exactly this way: the scholarship table
holds `scholarship_score_range`, no description mentioned it, and "khoảng điểm
học bổng" went to the formula tool, which then computed a wrong range.

So each answerable field declares below the wording that must appear in its
tool's registry text (its description plus every slot description and span
alias) for the planner to know the field is there. The audit reads the registry
and reports a field whose wording is missing, a field this file does not
classify, which is what a new column looks like, and a classified field that has
left the data, which is what a stale description looks like.

    python -m scripts.audit_tool_descriptions
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/structured_lookup_registry.yaml"
TABLES = ROOT / "data/processed/tables/structured_tables_registry.json"
DIRECTORIES = {
    "office": "student_office_profiles",
    "faculty": "student_faculty_profiles",
    "program": "program_directory",
    "student_service": "student_service_directory",
}

# Bookkeeping every record carries; none of it is ever an answer.
PLUMBING = {
    "record_id", "cohort", "source_cohort", "applicable_cohorts", "applicability",
    "document_id", "document_ids", "source_section", "source_section_id", "source_pages",
    "content_type", "raw_text", "embedding_enabled", "retrieval_mode", "content_mode",
    "review_status", "source_parent_id", "data_category", "quality_status",
    "source_provenance", "source_record_id", "source_record_ids", "legacy_record_ids",
    "office_profile_id", "faculty_profile_id", "service_id", "service_ids",
    "source_service_ids", "extraction_method", "needs_manual_review",
    "program_name_source", "faculty_name_source", "raw_program_name", "aliases",
    "faculty_aliases", "summary", "unit",
    # Matching machinery on a foreign-language row (score_mode, entity_aliases),
    # read by the lookup and never shown as an answer.
    "input_requirements",
}

# Each answerable field maps to the wording its tool's registry text must contain,
# lowercased. The wording is what a student would use, because that is what the
# planner matches the question against.
ADVERTISED: dict[str, dict[str, str]] = {
    "foreign_language": {
        "certificate": "chứng chỉ",
        "language": "ngoại ngữ",
        "level_or_scale": "điểm ngoại ngữ",
        "equivalent_level_3": "bậc tương đương",
        "equivalent_level_4": "bậc tương đương",
    },
    "study_duration": {
        "Chương trình đào tạo": "loại chương trình",
        "Hình thức đào tạo": "hệ đào tạo",
        "Thời gian học tập chuẩn": "thời gian học chuẩn",
        "Thời gian học tập tối đa": "tối đa",
        "Quy tắc đối với sinh viên liên thông": "liên thông",
    },
    "scholarship_classification": {
        "scholarship_level": "loại",
        "label": "loại",
        "formula": "công thức",
        "multiplier": "hệ số",
        "tuition_basis": "căn cứ học phí",
        "academic_score_range": "điểm học tập",
        "conduct_score_condition": "rèn luyện",
        "academic_classification": "xếp loại học tập",
        "conduct_classification_condition": "học tập và rèn luyện",
        "scholarship_score_range": "điểm học bổng",
        "criterion": "điều kiện xét",
        "requirement": "điều kiện xét",
        "output": "công thức",
        "academic_score_scale": "thang điểm",
        "conduct_score_scale": "thang điểm",
    },
    "scoring": {
        "Thang điểm 10": "quy đổi điểm học phần",
        "Thang điểm 4": "quy đổi điểm học phần",
        "Thang điểm chữ": "quy đổi điểm học phần",
        "Điểm chữ": "điểm chữ",
        "Xếp loại": "xếp loại học lực",
        "Loại": "xếp loại học lực",
        "Khung điểm": "điểm rèn luyện",
        "Kết quả": "đạt",
        "Tính vào điểm trung bình học tập": "điểm trung bình",
    },
    "office": {
        "unit_name": "đơn vị",
        "phone": "điện thoại",
        "phones": "điện thoại",
        "internal_numbers": "nội bộ",
        "email": "email",
        "emails": "email",
        "office": "địa chỉ",
        "offices": "địa chỉ",
        "website": "website",
        "websites": "website",
        "services": "dịch vụ",
    },
    "faculty": {
        "unit_name": "khoa",
        "faculty_name": "khoa",
        "phones": "điện thoại",
        "internal_numbers": "nội bộ",
        "emails": "email",
        "office": "địa chỉ",
        "websites": "website",
    },
    "program": {
        "program_name": "ngành",
        "faculty_name": "khoa",
    },
    "student_service": {
        "service": "dịch vụ",
        "unit_name": "đơn vị",
        "phone": "điện thoại",
        "phones": "điện thoại",
        "internal_numbers": "nội bộ",
        "email": "email",
        "emails": "email",
        "office": "địa chỉ",
        "website": "website",
        "websites": "website",
    },
}


def fields_of_tools() -> dict[str, set[str]]:
    """Every field a tool could answer with, read from the data it actually reads."""

    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["tools"]
    tables = json.loads(TABLES.read_text(encoding="utf-8"))
    by_table_type: dict[str, set[str]] = defaultdict(set)
    for table in tables:
        for row in table.get("rows") or []:
            if isinstance(row, dict):
                by_table_type[str(table.get("table_type") or "")].update(row)

    found: dict[str, set[str]] = {}
    for tool, spec in registry.items():
        if spec.get("table_types"):
            found[tool] = {field for table_type in spec["table_types"]
                           for field in by_table_type.get(table_type, set())}
        elif tool in DIRECTORIES:
            records = json.loads((ROOT / f"data/processed/directories/{DIRECTORIES[tool]}.json")
                                 .read_text(encoding="utf-8"))
            found[tool] = {field for record in records for field in record}
    return {tool: fields - PLUMBING for tool, fields in found.items()}


def registry_text() -> dict[str, str]:
    """Everything the planner reads about a tool, lowercased: its description and its slots'."""

    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["tools"]
    text = {}
    for tool, spec in registry.items():
        parts = [str(spec.get("description") or "")]
        for slot_spec in (spec.get("slot_schema") or {}).values():
            parts.append(str(slot_spec.get("description") or ""))
            parts.extend(str(alias) for aliases in (slot_spec.get("span_aliases") or {}).values()
                         for alias in aliases)
        text[tool] = " ".join(parts).lower()
    return text


def audit() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return the summary and the fields the planner is not told about, or told about in vain."""

    found = fields_of_tools()
    described = registry_text()
    findings: list[dict[str, Any]] = []
    for tool, fields in sorted(found.items()):
        declared = ADVERTISED.get(tool, {})
        for field in sorted(fields - set(declared)):
            findings.append({"kind": "field_not_classified", "tool": tool, "field": field})
        for field in sorted(set(declared) - fields):
            findings.append({"kind": "classified_field_absent_from_data", "tool": tool,
                             "field": field, "wording": declared[field]})
        for field in sorted(fields & set(declared)):
            if declared[field] not in described.get(tool, ""):
                findings.append({"kind": "field_the_planner_is_not_told_about", "tool": tool,
                                 "field": field, "wording_missing": declared[field]})

    summary = {"tools": len(found), "answerable_fields": sum(len(f) for f in found.values()),
               "findings": len(findings),
               "by_kind": {kind: sum(1 for f in findings if f["kind"] == kind)
                           for kind in {f["kind"] for f in findings}}}
    return summary, findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "data/eval/reports/tool_description_audit")
    args = parser.parse_args()

    summary, findings = audit()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "audit.json").write_text(
        json.dumps({"summary": summary, "findings": findings}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for finding in findings:
        print(" ", json.dumps(finding, ensure_ascii=False))


if __name__ == "__main__":
    main()
