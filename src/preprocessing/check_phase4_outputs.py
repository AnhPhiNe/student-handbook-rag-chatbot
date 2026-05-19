import json
from pathlib import Path
from collections import Counter


FILES = {
    "report": Path("data/processed/metadata/phase4_processing_report.json"),
    "formulas": Path("data/processed/tables/formula_rules.json"),
    "forms": Path("data/processed/forms/form_templates.json"),
    "office": Path("data/processed/directories/office_directory.json"),
    "faculty": Path("data/processed/directories/faculty_program_directory.json"),
}


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    report = load(FILES["report"])
    formulas = load(FILES["formulas"])
    forms = load(FILES["forms"])
    office = load(FILES["office"])
    faculty = load(FILES["faculty"])

    print("===== REPORT =====")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    print("\n===== FORMULA IDS =====")
    print([item["rule_id"] for item in formulas])

    print("\n===== FORM NAMES =====")
    for form in forms:
        print("-", form["form_id"], "|", form["form_name"], "| pages:", form["source_pages"])

    print("\n===== OFFICE REVIEW COUNT =====")
    print(Counter(item.get("needs_manual_review") for item in office))

    print("\n===== FIRST 10 OFFICE RECORDS =====")
    for item in office[:10]:
        print("-", item["record_id"], "|", item["unit_name"], "| pages:", item["source_pages"])

    print("\n===== FACULTY REVIEW COUNT =====")
    print(Counter(item.get("needs_manual_review") for item in faculty))

    print("\n===== FIRST 10 FACULTY RECORDS =====")
    for item in faculty[:10]:
        print("-", item["record_id"], "|", item["faculty_or_unit_name"], "| pages:", item["source_pages"])


if __name__ == "__main__":
    main()