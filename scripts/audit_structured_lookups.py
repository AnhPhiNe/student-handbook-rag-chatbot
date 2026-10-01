"""Sweep every reference-table row and check the lookup pins that row, and no other.

For every cohort, table and row it builds the slots a planner would produce from
the row's own key value, resolves the task, and compares the row the answer
claims against the expected one. A value several rows share must not be pinned to
one of them. It runs offline against the committed tables and calls no model.

What this does NOT cover, measured rather than assumed: run against the code
before the five fixes of 2026-09-30, it reports no findings either, so it is
blind to them. Those bugs lived in matching the student's own words to a label or
code ("khác" read as "Khá", "N30" as "N3"), not in selecting a row from
well-formed slots. Their regression tests are in tests/test_scholarship_lookup.py
and tests/test_foreign_language_lookup.py. What this audit does establish is that
row selection itself is sound across every reference table and cohort.

    python -m scripts.audit_structured_lookups
    python -m scripts.audit_structured_lookups --lookup scoring
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "data/processed/tables/structured_tables_registry.json"
# One row is pinned by one key column; the audit reads the key from the row itself.
LETTER_COLUMN = "Thang điểm chữ"
RANGE_COLUMNS = ("Thang điểm 10", "Thang điểm 4", "Khung điểm")


def fold(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold().replace("đ", "d"))
    return " ".join(re.findall(r"[\w.,+-]+", "".join(c for c in text if unicodedata.category(c) != "Mn")))


def midpoint(text: str) -> str | None:
    """A value inside a range cell, so the query never repeats the range itself."""

    numbers = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", str(text or ""))]
    if not numbers:
        return None
    if len(numbers) == 1:
        lone = numbers[0]
        if re.search(r"dưới|nhỏ hơn|<", str(text), re.IGNORECASE):
            lone = max(0.0, lone - 0.5)
        elif re.search(r"trở lên|từ|>=", str(text), re.IGNORECASE):
            lone += 0.5
        return f"{lone:.1f}".replace(".", ",")
    low, high = min(numbers), max(numbers)
    return f"{(low + high) / 2:.1f}".replace(".", ",")


def probes(table: dict[str, Any]) -> Iterator[tuple[dict[str, Any], str, dict[str, Any], str | None]]:
    """Yield (row, lookup_type, slots, key_column) for each row this audit can address.

    `key_column` is the column whose exact value the probe used, or None when the
    probe is a value inside a range, which the table's disjoint ranges make unique.
    """

    subtype = str(table.get("table_subtype") or "")
    for row in table.get("rows") or []:
        if not isinstance(row, dict):
            continue
        if subtype == "letter_to_grade4" and row.get(LETTER_COLUMN):
            yield row, "scoring", {"operation": "letter_to_grade_4",
                                   "score_or_grade": str(row[LETTER_COLUMN])}, LETTER_COLUMN
        elif subtype in {"grade_scale", "pass_fail_ungraded", "academic_classification",
                         "conduct_classification"}:
            column = next((c for c in RANGE_COLUMNS if row.get(c)), None)
            value = midpoint(row.get(column)) if column else None
            if not value:
                continue
            operation = {"grade_scale": "grade_10_to_letter",
                         "pass_fail_ungraded": "pass_fail_ungraded",
                         "academic_classification": "academic_classification",
                         "conduct_classification": "conduct_classification"}[subtype]
            slots: dict[str, Any] = {"operation": operation, "score_or_grade": value}
            if subtype == "grade_scale":
                slots["course_scope"] = "foundation" if "foundation" in str(table.get("table_id")) else "remaining"
            yield row, "scoring", slots, None
        elif subtype == "scholarship_classification" and row.get("scholarship_level"):
            yield row, "scholarship_classification", {"aspect": "classification",
                                                      "score_or_label": str(row["scholarship_level"])}, "scholarship_level"
        elif subtype == "scholarship_amount" and row.get("scholarship_level"):
            yield row, "scholarship_classification", {"aspect": "amount",
                                                      "score_or_label": str(row["scholarship_level"])}, "scholarship_level"
        elif subtype == "foreign_language" and row.get("certificate"):
            for level, asked in (("equivalent_level_3", "bậc 3"), ("equivalent_level_4", "bậc 4")):
                if row.get(level):
                    yield row, "foreign_language", {"certificate_or_language": str(row["certificate"]),
                                                    "score_or_level": asked}, "certificate"


def answer_rows(resolution: Any) -> list[dict[str, Any]]:
    """The row or rows offered as the answer, unwrapped from the resolver envelope.

    The envelope renames columns and carries `display_rows`, the whole table; only
    the innermost `result` is what the answer claims.
    """
    if resolution is None:
        return []
    result = resolution.result or {}
    node = result.get("resolved_result")
    node = result.get("result") if node is None else node
    node = _unwrap(node)
    if isinstance(node, list):
        return [_clean(_unwrap(item)) for item in node if isinstance(_unwrap(item), dict)]
    if isinstance(node, dict):
        rows = node.get("rows")
        if isinstance(rows, list):
            return [_clean(_unwrap(row)) for row in rows if isinstance(_unwrap(row), dict)]
        return [_clean(node)]
    return []


def _unwrap(node: Any) -> Any:
    """Descend the envelope: the row sits under `result`, `row`, or both, and `result` may be a list."""

    for _ in range(4):
        if not isinstance(node, dict):
            return node
        nested = next((node[key] for key in ("result", "row")
                       if isinstance(node.get(key), (dict, list))), None)
        if nested is None:
            return node
        node = nested
    return node


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    """Drop the whole-table fields, so a comparison reads only the answer's own cells."""

    return {k: v for k, v in row.items() if k not in {"display_rows", "items", "rows"}}


def audit(lookup: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the sweep and return its summary and findings, without writing a report."""

    from src.retrieval.core.query_plan import QUERY_PLAN_SCHEMA_VERSION, normalize_query_plan
    from src.retrieval.core.structured_dispatcher import resolve_structured_task

    tables = json.loads(TABLES.read_text(encoding="utf-8"))
    findings, checked, ambiguous = [], 0, 0
    for table in tables:
        cohort = table.get("cohort")
        for row, lookup_type, slots, key_column in probes(table):
            if lookup and lookup_type != lookup:
                continue
            question = f"{table.get('table_name')} {' '.join(str(v) for v in slots.values())}"
            payload = {"schema_version": QUERY_PLAN_SCHEMA_VERSION, "context_mode": "standalone",
                       "out_of_domain": False,
                       "tasks": [{"id": "t1", "question": question, "mode": "structured",
                                  "lookup_type": lookup_type, "intent": "direct_value",
                                  "cohorts": [cohort], "slots": slots,
                                  "slot_spans": {k: str(v) for k, v in slots.items()}}]}
            plan, errors = normalize_query_plan(payload, query=question, selected_cohort=cohort)
            if errors:
                findings.append({"kind": "plan_rejected", "cohort": cohort, "table": table.get("table_id"),
                                 "slots": slots, "errors": errors[:2]})
                continue
            resolution = resolve_structured_task(
                plan["tasks"][0], query=question, cohort=cohort,
                formula_rules=[], office_directory=[], student_service_directory=[],
                student_faculty_profiles=[], structured_tables_registry=tables, program_directory=[])
            checked += 1
            got = answer_rows(resolution)
            status = getattr(resolution, "resolution_status", None)
            # Several rows may share the probed value (a scholarship level holds
            # several academic/conduct pairs). Then pinning one row would be the
            # error, and offering them all is right.
            siblings = [other for other in table.get("rows") or [] if isinstance(other, dict)
                        and key_column and fold(other.get(key_column)) == fold(row.get(key_column))]
            if len(siblings) > 1:
                ambiguous += 1
                if len(got) == 1 and status == "resolved":
                    findings.append({"kind": "pinned_despite_ambiguity", "cohort": cohort,
                                     "lookup": lookup_type, "table": table.get("table_id"),
                                     "slots": slots, "rows_sharing_the_value": len(siblings),
                                     "answer_row": got[0]})
                continue
            if len(got) != 1:
                findings.append({"kind": "not_pinned", "cohort": cohort, "lookup": lookup_type,
                                 "table": table.get("table_id"), "slots": slots,
                                 "status": status, "rows_returned": len(got)})
                continue
            expected = {fold(v) for v in row.values() if str(v).strip()}
            # Values that belong to a different row of this table and to no cell of
            # the expected one: if the answer shows any of them, it pinned the wrong row.
            others = {fold(v) for other in table.get("rows") or [] if isinstance(other, dict) and other is not row
                      for v in other.values() if str(v).strip()} - expected
            actual = {fold(v) for v in got[0].values() if str(v).strip()}
            if not expected & actual or actual & others:
                findings.append({"kind": "wrong_row", "cohort": cohort, "lookup": lookup_type,
                                 "table": table.get("table_id"), "slots": slots,
                                 "expected_row": row, "answer_row": got[0],
                                 "expected_values_matched": sorted(expected & actual),
                                 "other_row_values_shown": sorted(actual & others)})

    summary = {"probes_resolved": checked, "probes_with_a_unique_row": checked - ambiguous,
               "probes_where_several_rows_share_the_value": ambiguous, "findings": len(findings),
               "by_kind": {k: sum(1 for f in findings if f["kind"] == k) for k in {f["kind"] for f in findings}}}
    return summary, findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookup", help="Audit one lookup family only.")
    parser.add_argument("--out", type=Path, default=ROOT / "data/eval/reports/structured_lookup_audit")
    args = parser.parse_args()

    summary, findings = audit(args.lookup)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "audit.json").write_text(
        json.dumps({"summary": summary, "findings": findings}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for finding in findings[:12]:
        print(" ", json.dumps(finding, ensure_ascii=False)[:230])


if __name__ == "__main__":
    main()
