from typing import Any


def build_report(
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]],
    threshold_rules: list[dict[str, Any]],
    office_directory: list[dict[str, Any]],
    faculty_directory: list[dict[str, Any]],
    program_directory: list[dict[str, Any]],
    reference_directory: list[dict[str, Any]],
    procedures: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "tables_extracted": len(scoring_tables),
        "formula_rules_extracted": len(formula_rules),
        "threshold_rules_extracted": len(threshold_rules),
        "threshold_priority_count": {
            "high": sum(1 for item in threshold_rules if item["priority"] == "high"),
            "medium": sum(
                1 for item in threshold_rules if item["priority"] == "medium"
            ),
            "low": sum(1 for item in threshold_rules if item["priority"] == "low"),
        },
        "office_records_extracted": len(office_directory),
        "faculty_records_extracted": len(faculty_directory),
        "program_records_extracted": len(program_directory),
        "reference_records_extracted": len(reference_directory),
        "procedures_extracted": len(procedures),
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
