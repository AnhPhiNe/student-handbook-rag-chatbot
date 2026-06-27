from pathlib import Path

from .directory_parser import (
    extract_faculty_program_directory,
    extract_office_directory,
    extract_reference_directory,
)
from .form_parser import extract_form_templates
from .formula_rules import extract_formula_rules
from .io_utils import load_json, load_yaml, save_json
from .procedure_parser import extract_procedures
from .report_builder import build_report
from .scoring_tables import build_scoring_tables
from .threshold_rules import extract_threshold_rules


CONFIG_PATH = Path("configs/extraction.yaml")


def main() -> None:
    config = load_yaml(CONFIG_PATH)

    pages = load_json(Path(config["input"]["pages"]))
    sections = load_json(Path(config["input"]["structured_sections"]))

    scoring_tables = build_scoring_tables()
    formula_rules = extract_formula_rules(sections)
    threshold_rules = extract_threshold_rules(sections)
    form_templates = extract_form_templates(pages)

    office_directory = extract_office_directory(pages)
    faculty_directory = extract_faculty_program_directory(pages)
    reference_directory = extract_reference_directory(pages)
    procedures = extract_procedures(pages)

    report = build_report(
        scoring_tables=scoring_tables,
        formula_rules=formula_rules,
        threshold_rules=threshold_rules,
        form_templates=form_templates,
        office_directory=office_directory,
        faculty_directory=faculty_directory,
        reference_directory=reference_directory,
        procedures=procedures,
    )

    save_json(scoring_tables, Path(config["output"]["scoring_tables"]))
    save_json(formula_rules, Path(config["output"]["formula_rules"]))
    save_json(threshold_rules, Path(config["output"]["threshold_rules"]))
    save_json(form_templates, Path(config["output"]["form_templates"]))
    save_json(office_directory, Path(config["output"]["office_directory"]))
    save_json(faculty_directory, Path(config["output"]["faculty_program_directory"]))
    save_json(reference_directory, Path(config["output"]["reference_directory"]))
    save_json(procedures, Path(config["output"]["procedures"]))
    save_json(report, Path(config["output"]["report"]))

    print("Structured extraction completed.")
    print(f"Scoring tables: {len(scoring_tables)}")
    print(f"Formula rules: {len(formula_rules)}")
    print(f"Threshold rules: {len(threshold_rules)}")
    print(f"Form templates: {len(form_templates)}")
    print(f"Office records: {len(office_directory)}")
    print(f"Faculty records: {len(faculty_directory)}")
    print(f"Reference records: {len(reference_directory)}")
    print(f"Procedures: {len(procedures)}")


if __name__ == "__main__":
    main()
