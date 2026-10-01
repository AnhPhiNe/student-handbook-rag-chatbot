"""Check structured data against the handbook text it was extracted from, both ways.

Precision: every value a table cell or a directory field holds must occur in its
own source text (the handbook section a table was read from, the handbook entry a
directory record was read from), so no value is invented or mis-copied. A cell
is compared by its numbers when it has any, because the source writes "2,56 –
3,352" where a cell may hold "2.56-3.352"; otherwise by its words.

Recall: every value the source writes under a contact label (an address, a
website, an extension) must reach its field. This is the check that found the
four K48-K49 and K50 units whose address sat under "Phòng làm việc", a label
the extractor did not read.

It reads the committed artefacts and calls no model.

    python -m scripts.audit_extraction
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
DOCSTORE = ROOT / "data/processed/chunks/all_docstore_items.json"
TABLES = ROOT / "data/processed/tables/structured_tables_registry.json"
FORMULAS = ROOT / "data/processed/tables/formula_rules.json"
DIRECTORIES = ROOT / "data/processed/directories"

# Directory fields that hold values copied from the handbook entry.
CONTACT_FIELDS = ("emails", "phones", "internal_numbers", "websites", "office")
# Recall: a contact label in the source, and the field its value must reach.
LABELLED_VALUES = (
    (re.compile(r"(?:văn phòng làm việc|phòng làm việc|văn phòng ghi danh)\s*:?\s*\S", re.I), "office"),
    (re.compile(r"\bwebsite\s*:?\s*[a-z0-9]", re.I), "websites"),
    (re.compile(r"số (?:máy )?nội bộ\s*:?\s*\d", re.I), "internal_numbers"),
    (re.compile(r"\bemail\s*:?\s*[a-z0-9._-]+@", re.I), "emails"),
)


def fold(text: Any) -> str:
    """Case, accents kept; dashes, spaces and decimal commas made uniform."""

    text = unicodedata.normalize("NFC", str(text or "")).casefold()
    text = re.sub(r"[‐-―−]", "-", text)
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    return " ".join(text.split())


def numbers(text: Any) -> set[str]:
    """Numbers as written, without leading zeros or a trailing ".0", so "04" is "4"."""

    out = set()
    for raw in re.findall(r"\d+(?:\.\d+)?", fold(text)):
        value = raw.lstrip("0") or "0"
        value = value[:-2] if value.endswith(".0") else value
        out.add("0" + value if value.startswith(".") else value)
    return out


def words(text: Any) -> set[str]:
    return {w for w in re.findall(r"\w+", fold(text)) if len(w) > 1}


def _cell_is_in(value: Any, source: str, source_numbers: set[str], source_words: set[str]) -> bool:
    if not isinstance(value, str) or not value.strip():
        return True
    cell_numbers = numbers(value)
    if cell_numbers:
        return cell_numbers <= source_numbers
    return fold(value) in source or words(value) <= source_words


def table_findings() -> Iterator[dict[str, Any]]:
    docs = {str(d.get("_id")): d for d in json.loads(DOCSTORE.read_text(encoding="utf-8"))}
    for table in json.loads(TABLES.read_text(encoding="utf-8")):
        parent = docs.get(str(table.get("source_parent_id")))
        if parent is None:
            yield {"kind": "table_source_missing", "table": table.get("table_id")}
            continue
        source = fold(parent.get("content"))
        source_numbers, source_words = numbers(source), words(source)
        for index, row in enumerate(table.get("rows") or []):
            for column, value in (row.items() if isinstance(row, dict) else []):
                if not _cell_is_in(value, source, source_numbers, source_words):
                    yield {"kind": "cell_not_in_source", "table": table.get("table_id"),
                           "row": index, "column": column, "value": value}


def formula_findings() -> Iterator[dict[str, Any]]:
    # raw_excerpt stops at 1,500 characters, before the GPA formula itself, so
    # a rule is checked against the whole section it was read from.
    docs = {str(d.get("_id")): d for d in json.loads(DOCSTORE.read_text(encoding="utf-8"))}
    for rule in json.loads(FORMULAS.read_text(encoding="utf-8")):
        parent = docs.get(str(rule.get("source_parent_id")))
        source = fold((parent or {}).get("content") or rule.get("raw_excerpt"))
        for field in ("formula_text", "rounding"):
            value = rule.get(field)
            if value and not _cell_is_in(value, source, numbers(source), words(source)):
                yield {"kind": "formula_value_not_in_source", "rule": rule.get("rule_id"),
                       "cohort": rule.get("cohort"), "field": field, "value": value}


def _values(record: dict[str, Any], field: str) -> list[str]:
    value = record.get(field)
    return [str(v) for v in value] if isinstance(value, list) else ([str(value)] if value else [])


def directory_findings() -> Iterator[dict[str, Any]]:
    # Faculty and service records keep the handbook entry they were read from.
    for catalog in ("student_faculty_profiles", "student_service_directory"):
        for record in json.loads((DIRECTORIES / f"{catalog}.json").read_text(encoding="utf-8")):
            raw = str(record.get("raw_text") or "")
            source = fold(raw)
            source_numbers, source_words = numbers(source), words(source)
            name = record.get("unit_name") or record.get("faculty_name")
            for field in CONTACT_FIELDS:
                for value in _values(record, field):
                    # A multi-address value names its addresses ("Phòng làm việc: ...").
                    if not _cell_is_in(value, source, source_numbers, source_words):
                        yield {"kind": "field_value_not_in_source", "catalog": catalog,
                               "cohort": record.get("cohort"), "unit": name, "field": field, "value": value}
            for pattern, field in LABELLED_VALUES:
                if pattern.search(raw) and not record.get(field):
                    yield {"kind": "labelled_value_not_extracted", "catalog": catalog,
                           "cohort": record.get("cohort"), "unit": name, "field": field}


def audit() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    findings = [*table_findings(), *formula_findings(), *directory_findings()]
    summary = {"findings": len(findings),
               "by_kind": {k: sum(1 for f in findings if f["kind"] == k) for k in sorted({f["kind"] for f in findings})}}
    return summary, findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "data/eval/reports/extraction_audit")
    args = parser.parse_args()

    summary, findings = audit()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "audit.json").write_text(
        json.dumps({"summary": summary, "findings": findings}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for finding in findings[:40]:
        print(" ", json.dumps(finding, ensure_ascii=False)[:240])


if __name__ == "__main__":
    main()
