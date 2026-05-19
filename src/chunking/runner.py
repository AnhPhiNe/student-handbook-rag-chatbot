from pathlib import Path
from typing import Any

from .directory_chunker import build_directory_chunks
from .form_chunker import build_form_chunks
from .formula_chunker import build_formula_chunks
from .io_utils import load_json, load_yaml, save_json
from .procedure_chunker import build_procedure_chunks
from .regulation_chunker import build_regulation_chunks
from .report_builder import build_chunk_report
from .table_chunker import build_table_chunks
from .validator import validate_chunks


CONFIG_PATH = Path("configs/phase5_chunking.yaml")


def split_chunks_by_index_mode(
    chunks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    semantic = [chunk for chunk in chunks if chunk["index_mode"] == "semantic"]
    structured = [chunk for chunk in chunks if chunk["index_mode"] == "structured"]
    tool = [chunk for chunk in chunks if chunk["index_mode"] == "tool"]

    return semantic, structured, tool


def build_index_manifest(config: dict[str, Any]) -> dict[str, Any]:
    """
    Manifest này dùng để nhắc Phase 6:
    - Chỉ embed semantic_chunks.json
    - Không embed all_chunks.json
    - structured/tool xử lý riêng
    """
    return {
        "embedding_input": config["output"]["semantic_chunks"],
        "structured_lookup_input": config["output"]["structured_lookup_chunks"],
        "tool_rule_input": config["output"]["tool_rule_chunks"],
        "do_not_embed": [
            config["output"]["all_chunks"],
            config["output"]["structured_lookup_chunks"],
            config["output"]["tool_rule_chunks"],
        ],
        "note": (
            "Phase 6 must embed only semantic_chunks.json. "
            "Structured lookup chunks and tool rule chunks are handled separately."
        ),
    }


def main() -> None:
    config = load_yaml(CONFIG_PATH)

    structured_sections = load_json(Path(config["input"]["structured_sections"]))
    scoring_tables = load_json(Path(config["input"]["scoring_tables"]))
    formula_rules = load_json(Path(config["input"]["formula_rules"]))
    form_templates = load_json(Path(config["input"]["form_templates"]))
    office_directory = load_json(Path(config["input"]["office_directory"]))
    faculty_directory = load_json(Path(config["input"]["faculty_program_directory"]))
    reference_directory = load_json(Path(config["input"]["reference_directory"]))
    procedures = load_json(Path(config["input"]["procedures"]))

    regulation_config = config["chunking"]["regulation"]
    directory_config = config["chunking"]["directory_summary"]
    procedure_config = config["chunking"]["procedure_summary"]

    regulation_chunks = build_regulation_chunks(
        sections=structured_sections,
        max_tokens=regulation_config["max_tokens"],
        overlap_tokens=regulation_config["overlap_tokens"],
    )

    table_chunks = build_table_chunks(scoring_tables)
    formula_chunks = build_formula_chunks(formula_rules)
    form_chunks = build_form_chunks(form_templates)

    directory_chunks = build_directory_chunks(
        office_records=office_directory,
        faculty_records=faculty_directory,
        reference_records=reference_directory,
        directory_max_tokens=directory_config["max_tokens"],
    )

    procedure_chunks = build_procedure_chunks(
        procedures=procedures,
        max_tokens=procedure_config["max_tokens"],
    )

    all_chunks = (
        regulation_chunks
        + table_chunks
        + formula_chunks
        + form_chunks
        + directory_chunks
        + procedure_chunks
    )

    semantic_chunks, structured_lookup_chunks, tool_rule_chunks = split_chunks_by_index_mode(
        all_chunks
    )

    validation_issues = validate_chunks(all_chunks)

    report = build_chunk_report(
        regulation_chunks=regulation_chunks,
        table_chunks=table_chunks,
        formula_chunks=formula_chunks,
        form_chunks=form_chunks,
        directory_chunks=directory_chunks,
        procedure_chunks=procedure_chunks,
        all_chunks=all_chunks,
        validation_issues=validation_issues,
    )

    index_manifest = build_index_manifest(config)

    save_json(regulation_chunks, Path(config["output"]["regulation_chunks"]))
    save_json(table_chunks, Path(config["output"]["table_chunks"]))
    save_json(formula_chunks, Path(config["output"]["formula_chunks"]))
    save_json(form_chunks, Path(config["output"]["form_chunks"]))
    save_json(directory_chunks, Path(config["output"]["directory_chunks"]))
    save_json(procedure_chunks, Path(config["output"]["procedure_chunks"]))

    save_json(semantic_chunks, Path(config["output"]["semantic_chunks"]))
    save_json(structured_lookup_chunks, Path(config["output"]["structured_lookup_chunks"]))
    save_json(tool_rule_chunks, Path(config["output"]["tool_rule_chunks"]))
    save_json(all_chunks, Path(config["output"]["all_chunks"]))

    save_json(report, Path(config["output"]["report"]))
    save_json(index_manifest, Path(config["output"]["index_manifest"]))

    print("Phase 5 completed.")
    print(f"Total chunks: {len(all_chunks)}")
    print(f"Semantic chunks: {len(semantic_chunks)}")
    print(f"Structured lookup chunks: {len(structured_lookup_chunks)}")
    print(f"Tool rule chunks: {len(tool_rule_chunks)}")
    print(f"Validation issues: {len(validation_issues)}")
    print(f"Overlong chunks: {report.get('overlong_chunks_count', 0)}")
    print(f"Index manifest saved: {config['output']['index_manifest']}")


if __name__ == "__main__":
    main()