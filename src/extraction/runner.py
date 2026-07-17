import os
from pathlib import Path

from src.common.content_modes import apply_record_defaults

from .directory_parser import (
    extract_faculty_program_directory,
    extract_office_directory,
    extract_reference_directory,
)
from .audit_builder import build_content_audit
from .formula_rules import extract_formula_rules
from .io_utils import load_json, load_yaml, save_json
from .procedure_parser import extract_procedures
from .program_faculty_enricher import enrich_program_faculty_names
from .program_parser import extract_program_directory
from .report_builder import build_report
from .scoring_tables import build_scoring_tables
from .threshold_rules import extract_threshold_rules


CONFIG_PATH = Path("configs/extraction.yaml")

NON_EMBEDDED_CONTENT_TYPES = {
    "scoring_table",
    "formula_rule",
    "threshold_rule",
    "office_directory",
    "faculty_directory",
    "program_directory",
    "reference_directory",
    "procedure",
}

def main() -> None:
    config = load_yaml(CONFIG_PATH)

    pages = load_json(Path(config["input"]["pages"]))
    sections = load_json(Path(config["input"]["structured_sections"]))
    document_id = pages[0].get("document_id") if pages else None
    cohort = os.environ.get("COHORT")

    scoring_tables = build_scoring_tables()
    formula_rules = extract_formula_rules(sections)
    threshold_rules = extract_threshold_rules(sections)

    office_directory = extract_office_directory(pages)
    faculty_directory = extract_faculty_program_directory(pages)
    program_directory = extract_program_directory(pages)
    program_directory = enrich_program_faculty_names(
        program_directory,
        faculty_directory,
    )
    reference_directory = extract_reference_directory(pages)
    procedures = extract_procedures(pages)
    content_audit_report = build_content_audit(pages, sections)

    record_groups = [
        (scoring_tables, "scoring_table"),
        (formula_rules, "formula_rule"),
        (threshold_rules, "threshold_rule"),
        (office_directory, "office_directory"),
        (faculty_directory, "faculty_directory"),
        (program_directory, "program_directory"),
        (reference_directory, "reference_directory"),
        (procedures, "procedure"),
    ]
    
    for group, content_type in record_groups:
        for record in group:
            record.setdefault("content_type", content_type)

            if content_type in NON_EMBEDDED_CONTENT_TYPES:
                record.setdefault("embedding_enabled", False)

                if content_type == "procedure":
                    record.setdefault("retrieval_mode", "structured_lookup")
                else:
                    record.setdefault("retrieval_mode", "deterministic")
            else:
                record.setdefault("embedding_enabled", True)
                record.setdefault("retrieval_mode", "semantic")

            apply_record_defaults(
                record,
                document_id=document_id,
                cohort=cohort,
                source_section=(
                    record.get("source_section")
                    or record.get("article")
                    or record.get("section_title")
                    or record.get("title")
                    or content_type
                ),
            )

    report = build_report(
        scoring_tables=scoring_tables,
        formula_rules=formula_rules,
        threshold_rules=threshold_rules,
        office_directory=office_directory,
        faculty_directory=faculty_directory,
        program_directory=program_directory,
        reference_directory=reference_directory,
        procedures=procedures,
    )

    save_json(scoring_tables, Path(config["output"]["scoring_tables"]))
    save_json(formula_rules, Path(config["output"]["formula_rules"]))
    save_json(threshold_rules, Path(config["output"]["threshold_rules"]))
    save_json(office_directory, Path(config["output"]["office_directory"]))
    save_json(faculty_directory, Path(config["output"]["faculty_directory"]))
    save_json(program_directory, Path(config["output"]["program_directory"]))
    # Backward-compatible alias while retrieval/chunking migrates off the old name.
    save_json(faculty_directory, Path(config["output"]["faculty_program_directory"]))
    save_json(reference_directory, Path(config["output"]["reference_directory"]))
    save_json(procedures, Path(config["output"]["procedures"]))
    save_json(report, Path(config["output"]["report"]))
    save_json(content_audit_report, Path(config["output"]["content_audit_report"]))

    print("Structured extraction completed.")
    print(f"Scoring tables: {len(scoring_tables)}")
    print(f"Formula rules: {len(formula_rules)}")
    print(f"Threshold rules: {len(threshold_rules)}")
    print(f"Office records: {len(office_directory)}")
    print(f"Faculty records: {len(faculty_directory)}")
    print(f"Program records: {len(program_directory)}")
    print(f"Reference records: {len(reference_directory)}")
    print(f"Procedures: {len(procedures)}")


if __name__ == "__main__":
    main()
