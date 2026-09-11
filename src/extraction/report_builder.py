from typing import Any


def build_report(
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]],
    office_directory: list[dict[str, Any]],
    faculty_directory: list[dict[str, Any]],
    program_directory: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize extracted records and manual-review findings."""

    return {
        "tables_extracted": len(scoring_tables),
        "formula_rules_extracted": len(formula_rules),
        "office_records_extracted": len(office_directory),
        "faculty_records_extracted": len(faculty_directory),
        "program_records_extracted": len(program_directory),
        "items_need_manual_review": {
            "tables": [
                table["table_id"]
                for table in scoring_tables
                if table.get("review_status") == "needs_human_verified"
            ],
            "office_directory": [
                record["record_id"]
                for record in office_directory
                if record.get("needs_manual_review")
            ],
            "faculty_directory": [
                record["record_id"]
                for record in faculty_directory
                if record.get("needs_manual_review")
            ],
            "program_directory": [
                record["record_id"]
                for record in program_directory
                if record.get("needs_manual_review")
            ],
        },
    }
