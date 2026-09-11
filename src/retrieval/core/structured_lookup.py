import re
from functools import partial
from typing import Any, Optional

from src.common.cohort import is_validated_source_applicable, normalize_cohort
from src.common.text import fold_text


def extract_number(query: str) -> Optional[float]:
    """Extract the first numeric value from text."""

    match = re.search(r"\d+(?:[,.]\d+)?", query)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def extract_numbers_from_text(text: str) -> list[float]:
    """Extract all numeric values from text in source order."""

    matches = re.finditer(r"\d+(?:[,.]\d+)?", text)
    return [float(match.group(0).replace(",", ".")) for match in matches]


def _parse_scoring_operand(value: Any) -> float | None:
    """Parse one score, optionally followed by an explicit numeric scale."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    match = re.fullmatch(
        r"\s*([-+]?\d+(?:[,.]\d+)?)\s*(?:/\s*10(?:[,.]0+)?)?\s*",
        str(value or ""),
    )
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def find_table(tables: list[dict[str, Any]], table_id: str) -> Optional[dict[str, Any]]:
    """Find a normalized table by its identifier."""

    for table in tables:
        if table.get("table_id") == table_id:
            return table
    return None


normalize_text = partial(fold_text, keep="+")


def _metadata_from_tables(tables: list[dict[str, Any]]) -> dict[str, Any]:
    cohorts = {table.get("cohort") for table in tables if table.get("cohort")}
    document_ids = {
        table.get("document_id") for table in tables if table.get("document_id")
    }
    source_sections = {
        table.get("source_section") for table in tables if table.get("source_section")
    }
    display_rows: list[dict[str, Any]] = []
    include_table_context = len(tables) > 1
    for table in tables:
        for raw_row in table.get("rows") or []:
            if not isinstance(raw_row, dict):
                continue
            row = dict(raw_row)
            if include_table_context:
                row = {
                    "table_name": table.get("table_name"),
                    "applicability": table.get("applicability"),
                } | row
            display_rows.append(row)

    return {
        "cohort": next(iter(cohorts)) if len(cohorts) == 1 else None,
        "document_id": next(iter(document_ids)) if len(document_ids) == 1 else None,
        "source_section": next(iter(source_sections))
        if len(source_sections) == 1
        else "scoring_table",
        "content_type": "structured_lookup",
        "display_rows": display_rows,
    }


def _with_metadata(
    result: dict[str, Any],
    tables: list[dict[str, Any]],
) -> dict[str, Any]:
    return result | _metadata_from_tables(tables)


def _single_slot_value(value: Any) -> Any | None:
    """Return one explicit slot value, rejecting distinct list choices."""

    if not isinstance(value, list):
        return value
    values = [item for item in value if item is not None and str(item).strip()]
    if not values:
        return None
    normalized = {normalize_text(item) for item in values}
    return values[0] if len(normalized) == 1 else None


def in_range(value: float, range_text: str) -> bool:
    """Return whether a value satisfies optional lower and upper bounds."""

    text = range_text.lower().replace(",", ".").strip()
    nums = extract_numbers_from_text(text)

    if "trở lên" in text and len(nums) == 1:
        return value >= nums[0]

    # Handbook intervals may provide only an upper bound or both bounds.
    if "dưới" in text:
        if len(nums) == 1:
            return value < nums[0]
        if len(nums) >= 2:
            return nums[0] <= value < nums[1]

    if "từ" in text and "đến" in text and len(nums) >= 2:
        return nums[0] <= value <= nums[1]

    if "-" in text or "–" in text:
        if len(nums) >= 2:
            return nums[0] <= value <= nums[1]

    return False


def lookup_conduct_classification(
    query: str, tables: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Resolve a conduct score classification."""

    table = find_table(tables, "conduct_classification")
    if not table:
        return None

    # Map a conduct score to its deterministic classification.
    value = extract_number(query)
    if value is None:
        normalized_query = normalize_text(query)
        for row in table["rows"]:
            label = normalize_text(row.get("label"))
            if label and re.search(
                rf"(?<![a-z0-9]){re.escape(label)}(?![a-z0-9])",
                normalized_query,
            ):
                return {
                    "lookup_type": "conduct_classification",
                    "input_value": query,
                    "result": row,
                    "source_pages": table.get("source_pages", []),
                    "table_name": table.get("table_name"),
                } | _metadata_from_tables([table])
        return None

    for row in table["rows"]:
        if in_range(value, row["range"]):
            return {
                "lookup_type": "conduct_classification",
                "input_value": value,
                "result": row,
                "source_pages": table.get("source_pages", []),
                "table_name": table.get("table_name"),
            } | _metadata_from_tables([table])

    return None


def lookup_academic_classification(
    query: str, tables: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    # Map a four-point GPA to its academic classification.
    """Resolve a four-point GPA classification."""

    value = extract_number(query)
    if value is None:
        return None

    table = find_table(tables, "academic_classification")
    if not table:
        return None

    for row in table["rows"]:
        if in_range(value, row["range"]):
            return {
                "lookup_type": "academic_classification",
                "input_value": value,
                "result": row,
                "source_pages": table.get("source_pages", []),
                "table_name": table.get("table_name"),
            } | _metadata_from_tables([table])

    return None


def lookup_letter_grade(
    query: str, tables: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    # Map a letter grade through the deterministic four-point table.
    """Resolve the four-point value for a letter grade."""

    table = find_table(tables, "letter_to_grade_4")
    if not table:
        return None

    q = query.upper()

    # Match longer grades first so B+ is not consumed as B.
    rows = sorted(table["rows"], key=lambda x: len(x["letter_grade"]), reverse=True)

    for row in rows:
        grade = row["letter_grade"].upper()
        if _contains_letter_grade(q, grade):
            return {
                "lookup_type": "letter_to_grade_4",
                "input_value": grade,
                "result": row,
                "source_pages": table.get("source_pages", []),
                "table_name": table.get("table_name"),
            } | _metadata_from_tables([table])

    return None


def lookup_grade_10_to_letter(
    query: str,
    tables: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Resolve the letter grade for a ten-point score."""

    matching_tables = [
        table
        for table in tables
        if table.get("lookup_group") == "grade_10_to_letter"
        or "grade_10_to_letter" in str(table.get("table_id") or "")
    ]

    if not matching_tables:
        return None

    if len(matching_tables) == 1:
        table_name = matching_tables[0].get(
            "table_name",
            "Quy đổi thang điểm 10",
        )
    else:
        table_name = "Các bảng: " + " | ".join(
            table.get("table_name", "Bảng quy đổi") for table in matching_tables
        )

    return _with_metadata(
        {
            "lookup_type": "grade_10_to_letter",
            "input_value": query,
            "result": matching_tables,
            "source_pages": sorted(
                {
                    page
                    for table in matching_tables
                    for page in table.get("source_pages", [])
                }
            ),
            "table_name": table_name,
        },
        matching_tables,
    )


def _contains_letter_grade(text: str, grade: str) -> bool:
    # Letter grades containing plus signs do not work with word boundaries;
    # use lookarounds so a longer grade is not consumed as its base letter.
    normalized_text = normalize_text(text).upper()
    normalized_grade = normalize_text(grade).upper()
    pattern = rf"(?<![A-Z0-9]){re.escape(normalized_grade)}(?![A-Z0-9+])"
    return re.search(pattern, normalized_text) is not None


def scoring_lookup_from_reference(
    slots: dict[str, Any], table: dict[str, Any], cohort: str | None = None,
) -> Optional[dict[str, Any]]:
    """Resolve a scoring operation inside the one table the dispatcher selected.

    The resolvers below predate the canonical table registry and read English
    field names (score_10_range, letter_grade, score_4, range, label). This
    adapter renames the registry's Vietnamese columns to those names; the
    renamed rows are also the result schema the evaluator and the frontend
    read, so removing the adapter means migrating that schema end to end.
    Table selection and query meaning are never decided here.
    """
    if not is_validated_source_applicable(table, cohort):
        return None
    layouts = {
        "grade_scale": ("grade_10_to_letter", {
            "Loại": "status", "Thang điểm 10": "score_10_range", "Thang điểm chữ": "letter_grade"}),
        "pass_fail_ungraded": ("grade_10_to_letter", {
            "Kết quả": "status", "Thang điểm 10": "score_10_range", "Điểm chữ": "letter_grade"}),
        "letter_to_grade4": ("letter_to_grade_4", {
            "Thang điểm chữ": "letter_grade", "Thang điểm 4": "score_4"}),
        "academic_classification": ("academic_classification", {
            "Thang điểm 4": "range", "Xếp loại": "label"}),
        "conduct_classification": ("conduct_classification", {
            "Khung điểm": "range", "Xếp loại": "label"}),
    }
    layout = layouts.get(table.get("table_subtype"))
    if layout is None:
        return None
    operation, fields = layout
    rows = [{fields.get(key, key): value for key, value in row.items()}
            for row in table.get("rows", []) if isinstance(row, dict)]
    if operation == "letter_to_grade_4":
        for row in rows:
            try:
                row["score_4"] = float(str(row["score_4"]).replace(",", "."))
            except (KeyError, TypeError, ValueError):
                return None
    adapted = {**table, "table_id": operation, "lookup_group": operation, "rows": rows,
               "cohort": normalize_cohort(cohort) or table.get("cohort"),
               "source_section": table.get("source_parent_id") or table.get("source_section_id")}
    effective_slots = dict(slots)
    if table.get("table_subtype") == "pass_fail_ungraded" and slots.get("operation") == "pass_fail_ungraded":
        effective_slots["operation"] = "pass_threshold"
    resolved = structured_lookup_from_slots(effective_slots, [adapted], cohort=cohort)
    if resolved is None:
        return None
    # Replace the private operation identifier with the actual source identity.
    for item in resolved.get("items") or []:
        if isinstance(item, dict) and "table_id" in item:
            item["table_id"] = table.get("table_id")
    return {**resolved, "table_id": table.get("table_id"),
            "source_parent_id": table.get("source_parent_id") or table.get("source_section_id"),
            "source_cohort": table.get("source_cohort") or table.get("cohort")}


def structured_lookup_from_slots(
    slots: dict[str, Any],
    tables: list[dict[str, Any]],
    cohort: str | None = None,
) -> Optional[dict[str, Any]]:
    """Resolve a scoring request from typed slots without query keyword routing."""
    normalized_cohort = normalize_cohort(cohort)
    if normalized_cohort:
        tables = [table for table in tables if table.get("cohort") == normalized_cohort]

    course_scope_value = _single_slot_value(slots.get("course_scope"))
    if slots.get("course_scope") is not None and course_scope_value is None:
        return None
    course_scope = normalize_text(course_scope_value).replace(" ", "_")
    if course_scope:
        scoped_tables = [
            table
            for table in tables
            if normalize_text(table.get("course_scope")).replace(" ", "_")
            == course_scope
        ]
        # Legacy cohorts expose one generally applicable grade table without
        # course-scope metadata. Preserve that behavior; when scoped metadata
        # exists, however, an unmatched scope must not resolve another table.
        if scoped_tables or any(table.get("course_scope") for table in tables):
            tables = scoped_tables

    operation_value = _single_slot_value(slots.get("operation"))
    if operation_value is None or not str(operation_value).strip():
        # Operation is a planner-owned selector.  Never infer it from the
        # operand (for example, a letter grade or a value containing "qua
        # môn").
        return None
    # The normalizer has already validated operation against the registry enum.
    canonical = normalize_text(operation_value).replace(" ", "_")
    value = _single_slot_value(slots.get("score_or_grade"))

    if value is None:
        return None

    value_text = str(value).strip()

    # Map conduct scores to classifications.
    if canonical == "conduct_classification":
        return lookup_conduct_classification(value_text, tables)

    # Map letter grades to the four-point scale.
    if canonical == "letter_to_grade_4":
        return lookup_letter_grade(value_text, tables)

    # Map ten-point grades to letter grades.
    if canonical == "grade_10_to_letter":
        score = _parse_scoring_operand(value)
        if score is None:
            return lookup_grade_10_to_letter(value_text, tables)
        return _lookup_grade_10_value(score, tables)

    # Resolve course pass/fail threshold questions only when the planner
    # supplied that operation explicitly.  The operand may still be numeric
    # or a grade label; its meaning is not inferred from its text.
    if canonical == "pass_threshold":
        score = _parse_scoring_operand(value)
        if score is None:
            return lookup_grade_10_to_letter(value_text, tables)
        return _lookup_grade_10_value(score, tables)

    # Map GPA values to academic classifications.
    if canonical == "academic_classification":
        return lookup_academic_classification(value_text, tables)

    return None


def _lookup_grade_10_value(
    value: float, tables: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    matching_tables = [
        table
        for table in tables
        if table.get("lookup_group") == "grade_10_to_letter"
        or "grade_10_to_letter" in str(table.get("table_id") or "")
    ]
    matches: list[dict[str, Any]] = []
    for table in matching_tables:
        for row in table.get("rows") or []:
            if in_range(
                value, str(row.get("score_10_range") or row.get("range") or "")
            ):
                matches.append(
                    {
                        "table_id": table.get("table_id"),
                        "table_name": table.get("table_name"),
                        "applicability": table.get("applicability"),
                        "pass_threshold": table.get("pass_threshold"),
                        "row": row,
                    }
                )
    if not matches:
        return None
    return _with_metadata(
        {
            "lookup_type": "grade_10_to_letter",
            "input_value": value,
            "result": matches,
            "items": matches,
            "source_pages": sorted(
                {
                    page
                    for table in matching_tables
                    for page in table.get("source_pages", [])
                }
            ),
            "table_name": "Quy doi thang diem 10 sang diem chu",
        },
        matching_tables,
    )
