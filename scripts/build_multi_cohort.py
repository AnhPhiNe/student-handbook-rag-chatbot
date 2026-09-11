import argparse
import os
import subprocess
import sys
from pathlib import Path
import json
import re
import shutil

from scripts.derive_foreign_language_policy import derive_foreign_language_policy
from src.common.cohort import COHORT_REGISTRY, DOCUMENT_ID_BY_COHORT
from src.common.io import load_json, save_json
from src.common.text import fold_text
from src.extraction.program_faculty_enricher import (
    enrich_program_faculty_names,
    load_program_overrides,
)


VALID_COHORTS = set(COHORT_REGISTRY)
LEGACY_COHORT_PREFIXES = ("K50-K51_",)
GENERATED_OUTPUT_DIRS = (
    Path("data/processed/chunks"),
    Path("data/processed/directories"),
    Path("data/processed/tables"),
    Path("data/processed/metadata"),
)


def get_cohort_from_filename(filename: str) -> str:
    normalized = Path(filename).stem.lower()
    normalized = normalized.replace("_", "-")

    if re.search(r"(?:khoa|k)-?48(?:-?49)?", normalized):
        return "K48-K49"

    if re.search(r"(?:khoa|k)-?49", normalized):
        return "K48-K49"

    if re.search(r"(?:khoa|k)-?50", normalized):
        return "K50"

    if re.search(r"(?:khoa|k)-?51", normalized):
        return "K51"

    raise ValueError(
        f"Không xác định được cohort từ tên PDF: {filename}"
    )


def run_pipeline_for_pdf(pdf_path: Path, cohort: str):
    print(f"\n{'='*50}\n--- RUNNING PIPELINE FOR {pdf_path.name} ({cohort}) ---\n{'='*50}")
    
    STEPS = [
        ("extract PDF pages", ["-m", "scripts.extract_pdf_pages"]),
        ("parse structured sections", ["-m", "scripts.parse_structure"]),
        ("extract structured data", ["-m", "scripts.extract_structured_data"]),
        ("build chunks", ["-m", "scripts.build_chunks"]),
    ]
    
    env = os.environ.copy()
    env["PDF_PATH"] = str(pdf_path)
    env["COHORT"] = cohort
    config_by_cohort = {
        "K48-K49": "configs/document_sections.yaml",
        "K50": "configs/document_sections_k50.yaml",
        "K51": "configs/document_sections_k51.yaml",
    }
    env["CONFIG_PATH"] = config_by_cohort.get(cohort, "configs/document_sections.yaml")
    
    for label, command in STEPS:
        print(f"\n==> {label} ({cohort})")
        subprocess.run([sys.executable, *command], env=env, check=True)


def merge_chunks(cohort_files, output_path):
    all_chunks = []
    for cohort, path in cohort_files.items():
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            chunks = json.load(f)
            for chunk in chunks:
                if "metadata" not in chunk:
                    chunk["metadata"] = {}
                chunk["metadata"]["cohort"] = cohort
                chunk["metadata"]["document_id"] = DOCUMENT_ID_BY_COHORT.get(cohort)
                chunk_id = str(chunk["chunk_id"])
                if not chunk_id.startswith(f"{cohort}_"):
                    chunk["chunk_id"] = f"{cohort}_{chunk_id}"
                if "parent_id" in chunk["metadata"]:
                    parent_id = str(chunk["metadata"]["parent_id"])
                    if not parent_id.startswith(f"{cohort}_"):
                        chunk["metadata"]["parent_id"] = f"{cohort}_{parent_id}"
                if "parent_section_id" in chunk["metadata"]:
                    parent_section_id = str(chunk["metadata"]["parent_section_id"])
                    if not parent_section_id.startswith(f"{cohort}_"):
                        chunk["metadata"]["parent_section_id"] = f"{cohort}_{parent_section_id}"
            all_chunks.extend(chunks)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)


def merge_docstore(cohort_files, output_path):
    all_docs = []
    for cohort, path in cohort_files.items():
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            docs = json.load(f)
            for doc in docs:
                if "metadata" not in doc:
                    doc["metadata"] = {}
                doc["metadata"]["cohort"] = cohort
                doc["metadata"]["document_id"] = DOCUMENT_ID_BY_COHORT.get(cohort)
                doc_id = str(doc["_id"])
                if not doc_id.startswith(f"{cohort}_"):
                    doc["_id"] = f"{cohort}_{doc_id}"
                if "chunk_id" in doc:
                    chunk_id = str(doc["chunk_id"])
                    if not chunk_id.startswith(f"{cohort}_"):
                        doc["chunk_id"] = f"{cohort}_{chunk_id}"
            all_docs.extend(docs)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_docs, f, ensure_ascii=False, indent=2)


def infer_content_type_from_output(path: Path) -> str:
    stem = path.stem
    if stem.endswith("s"):
        stem = stem[:-1]
    return stem


def merge_structured_data(cohort_files, output_path):
    all_items = []
    for cohort, path in cohort_files.items():
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            items = json.load(f)
            for index, item in enumerate(items, start=1):
                item["cohort"] = cohort
                item.setdefault("document_id", DOCUMENT_ID_BY_COHORT.get(cohort))
                item.setdefault("content_type", infer_content_type_from_output(output_path))
                item.setdefault("record_id", f"{cohort}_{path.stem}_{index}")
                if not str(item["record_id"]).startswith(f"{cohort}_"):
                    item["source_record_id"] = item["record_id"]
                    item["record_id"] = f"{cohort}_{item['record_id']}"
                # Keep references aligned with merge_docstore's namespace.
                parent_id = item.get("source_parent_id")
                if parent_id and not str(parent_id).startswith(f"{cohort}_"):
                    item["source_parent_id"] = f"{cohort}_{parent_id}"
            all_items.extend(items)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

def validate_structured_json(paths: list[Path]) -> None:
    issues = []

    for path in paths:
        if not path.exists():
            issues.append({
                "path": str(path),
                "issue": "missing_file",
            })
            continue

        with path.open("r", encoding="utf-8") as f:
            records = json.load(f)

        if not isinstance(records, list):
            issues.append({
                "path": str(path),
                "issue": "root_must_be_list",
            })
            continue

        seen_ids: set[str] = set()

        for index, record in enumerate(records):
            if not isinstance(record, dict):
                issues.append({
                    "path": str(path),
                    "index": index,
                    "issue": "record_must_be_object",
                })
                continue

            record_id = (
                record.get("record_id")
                or record.get("table_id")
                or record.get("rule_id")
            )
            cohort = record.get("cohort")
            document_id = record.get("document_id")

            if cohort not in VALID_COHORTS:
                issues.append({
                    "path": str(path),
                    "index": index,
                    "record_id": record_id,
                    "issue": "invalid_cohort",
                    "value": cohort,
                })

            if not document_id:
                issues.append({
                    "path": str(path),
                    "index": index,
                    "record_id": record_id,
                    "issue": "missing_document_id",
                })

            if not record_id:
                issues.append({
                    "path": str(path),
                    "index": index,
                    "issue": "missing_record_id",
                })
            elif str(record_id) in seen_ids:
                issues.append({
                    "path": str(path),
                    "index": index,
                    "record_id": record_id,
                    "issue": "duplicate_record_id",
                })
            else:
                seen_ids.add(str(record_id))

            if (
                "rows" in record
                and not isinstance(record["rows"], list)
            ):
                issues.append({
                    "path": str(path),
                    "record_id": record_id,
                    "issue": "rows_must_be_list",
                })

            if (
                "columns" in record
                and not isinstance(record["columns"], list)
            ):
                issues.append({
                    "path": str(path),
                    "record_id": record_id,
                    "issue": "columns_must_be_list",
                })

    if issues:
        raise RuntimeError(
            "Structured JSON validation failed:\n"
            + json.dumps(
                issues[:30],
                ensure_ascii=False,
                indent=2,
            )
        )


def merge_json_documents(cohort_files, output_path):
    documents = []
    for cohort, path in cohort_files.items():
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            document = json.load(f)
        document["cohort"] = cohort
        documents.append(document)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)


def validate_cohort_tags(paths: list[Path]) -> None:
    """Require every retrievable handbook record to use an allowed cohort key."""
    issues = []

    for path in paths:
        if not path.exists():
            issues.append({"path": str(path), "issue": "missing_file"})
            continue

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            if isinstance(data.get("chunks"), list):
                records = data["chunks"]
            elif isinstance(data.get("items"), list):
                records = data["items"]
            else:
                records = [data]
        elif isinstance(data, list):
            records = data
        else:
            continue

        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue

            metadata = record.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            cohort = record.get("cohort") or metadata.get("cohort")

            if cohort not in VALID_COHORTS:
                issues.append(
                    {
                        "path": str(path),
                        "index": index,
                        "id": record.get("chunk_id")
                        or record.get("_id")
                        or record.get("record_id"),
                        "cohort": cohort,
                    }
                )

    if issues:
        preview = json.dumps(issues[:20], ensure_ascii=False, indent=2)
        raise RuntimeError(
            "Cohort validation failed. "
            "Mọi record từ sổ tay phải có cohort K48-K49, K50 hoặc K51.\n"
            f"{preview}"
        )


def validate_retrieval_metadata(paths: list[Path]) -> None:
    issues = []

    for path in paths:
        seen_ids: set[str] = set()
        if not path.exists():
            issues.append({"path": str(path), "issue": "missing_file"})
            continue

        with path.open("r", encoding="utf-8") as f:
            records = json.load(f)

        if not isinstance(records, list):
            continue

        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue

            metadata = record.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}

            record_id = (
                record.get("chunk_id")
                or record.get("_id")
                or record.get("record_id")
            )
            if not record_id:
                issues.append({"path": str(path), "index": index, "issue": "missing_id"})
            elif str(record_id) in seen_ids:
                issues.append(
                    {
                        "path": str(path),
                        "index": index,
                        "id": record_id,
                        "issue": "duplicate_id",
                    }
                )
            else:
                seen_ids.add(str(record_id))

            cohort = record.get("cohort") or metadata.get("cohort")
            document_id = record.get("document_id") or metadata.get("document_id")
            content_type = (
                record.get("content_type")
                or metadata.get("content_type")
                or record.get("chunk_type")
            )

            if cohort not in VALID_COHORTS:
                issues.append(
                    {
                        "path": str(path),
                        "index": index,
                        "id": record_id,
                        "issue": "invalid_cohort",
                        "cohort": cohort,
                    }
                )
            if not document_id:
                issues.append(
                    {
                        "path": str(path),
                        "index": index,
                        "id": record_id,
                        "issue": "missing_document_id",
                    }
                )
            if not content_type:
                issues.append(
                    {
                        "path": str(path),
                        "index": index,
                        "id": record_id,
                        "issue": "missing_content_type",
                    }
                )

    if issues:
        preview = json.dumps(issues[:30], ensure_ascii=False, indent=2)
        raise RuntimeError(f"Retrieval metadata validation failed:\n{preview}")


def validate_program_directory(program_path: Path, overrides: dict) -> None:
    with program_path.open("r", encoding="utf-8") as f:
        programs = json.load(f)

    expected_counts = (
        (overrides.get("expected_counts") or {}).get("program_directory", {})
    )
    by_cohort: dict[str, list[dict]] = {}
    for program in programs:
        by_cohort.setdefault(str(program.get("cohort")), []).append(program)

    issues = []
    for cohort, expected_count in expected_counts.items():
        actual_count = len(by_cohort.get(cohort, []))
        if actual_count != int(expected_count):
            issues.append(
                {
                    "issue": "unexpected_program_count",
                    "cohort": cohort,
                    "expected": int(expected_count),
                    "actual": actual_count,
                }
            )

    k48_programs = {
        fold_text(program.get("program_name"))
        for program in by_cohort.get("K48-K49", [])
    }
    k50_programs = {
        fold_text(program.get("program_name"))
        for program in by_cohort.get("K50", [])
    }
    k50_additions = k50_programs - k48_programs
    if k48_programs - k50_programs:
        issues.append(
            {
                "issue": "unexpected_k48_only_programs",
                "actual": sorted(k48_programs - k50_programs),
            }
        )
    if k50_additions != {"du lich", "sinh hoc ung dung"}:
        issues.append(
            {
                "issue": "unexpected_k50_program_additions",
                "actual": sorted(k50_additions),
            }
        )

    k51_additions = {
        fold_text(program.get("program_name"))
        for program in by_cohort.get("K51", [])
    } - k50_programs
    if k51_additions != {"cong nghe giao duc", "toan ung dung"}:
        issues.append(
            {
                "issue": "unexpected_k51_program_additions",
                "actual": sorted(k51_additions),
            }
        )

    if issues:
        preview = json.dumps(issues, ensure_ascii=False, indent=2)
        raise RuntimeError(f"Program directory validation failed:\n{preview}")


def _content_type_map(audit_report):
    return {item["content_type"]: item for item in audit_report.get("content_types", [])}


def build_content_audit_diff(audit_reports):
    cohorts = list(audit_reports.keys())
    content_types = sorted(
        {
            item["content_type"]
            for report in audit_reports.values()
            for item in report.get("content_types", [])
        }
    )

    by_content_type = []
    for content_type in content_types:
        cohort_entries = {}
        for cohort, report in audit_reports.items():
            item = _content_type_map(report).get(content_type)
            if item is None:
                cohort_entries[cohort] = {
                    "exists": False,
                    "content_mode": None,
                    "page_count": 0,
                    "page_start": None,
                    "page_end": None,
                }
                continue

            cohort_entries[cohort] = {
                "exists": True,
                "content_mode": item.get("content_mode"),
                "page_count": item.get("page_count"),
                "page_start": item.get("page_start"),
                "page_end": item.get("page_end"),
                "needs_embedding": item.get("needs_embedding"),
                "needs_structured_lookup": item.get("needs_structured_lookup"),
            }

        by_content_type.append(
            {
                "content_type": content_type,
                "by_cohort": cohort_entries,
                "diff_notes": _build_content_type_notes(content_type, cohort_entries),
            }
        )

    return {
        "cohorts": cohorts,
        "documents": {
            cohort: {
                "document_id": report.get("document_id"),
                "file_name": report.get("file_name"),
                "total_pages": report.get("total_pages"),
                "content_mode_count": report.get("content_mode_count"),
            }
            for cohort, report in audit_reports.items()
        },
        "by_content_type": by_content_type,
    }


def _build_content_type_notes(content_type, cohort_entries):
    notes = []
    missing = [
        cohort for cohort, entry in cohort_entries.items() if not entry.get("exists")
    ]
    if missing:
        notes.append(f"Không có trong: {', '.join(missing)}")

    modes = {
        entry.get("content_mode")
        for entry in cohort_entries.values()
        if entry.get("content_mode")
    }
    if len(modes) > 1:
        notes.append("Khác chế độ xử lý giữa các khóa")

    page_ranges = {
        cohort: (entry.get("page_start"), entry.get("page_end"))
        for cohort, entry in cohort_entries.items()
        if entry.get("exists")
    }
    if len(set(page_ranges.values())) > 1:
        notes.append("Khác vị trí/phạm vi trang giữa các khóa")

    if content_type == "faculty_program_directory":
        notes.append("Cần tách faculty_directory và program_directory theo profile từng sổ tay")


    return notes


def enrich_merged_program_faculties(program_path, faculty_path, overrides):
    """Fill faculties that one cohort's handbook omits but another cohort states."""

    programs = enrich_program_faculty_names(
        load_json(program_path), load_json(faculty_path), overrides
    )
    save_json(programs, program_path)


def cleanup_legacy_cohort_artifacts() -> None:
    """Remove generated legacy-cohort artifacts before rebuilding."""
    removed = []
    for directory in GENERATED_OUTPUT_DIRS:
        if not directory.exists():
            continue
        for prefix in LEGACY_COHORT_PREFIXES:
            for path in directory.glob(f"{prefix}*.json"):
                path.unlink()
                removed.append(path)

    if removed:
        print("\nRemoved legacy cohort artifacts:")
        for path in removed:
            print(f"  - {path}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild all three handbook cohorts into one coherent snapshot."
    )
    parser.add_argument(
        "--qdrant-collection",
        default=os.environ.get("QDRANT_COLLECTION_NAME"),
        help="Explicit versioned Qdrant target recorded in the build manifest.",
    )
    parser.add_argument(
        "--mongo-collection",
        default=os.environ.get("MONGODB_PARENT_COLLECTION"),
        help="Explicit versioned MongoDB target recorded in the build manifest.",
    )
    args = parser.parse_args(argv)
    if not args.qdrant_collection or not args.mongo_collection:
        parser.error(
            "--qdrant-collection and --mongo-collection are required "
            "(or configure matching environment variables)."
        )
    return args


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    overrides = load_program_overrides()
    cleanup_legacy_cohort_artifacts()

    raw_dir = Path("data/raw")
    pdfs = sorted(raw_dir.glob("*.pdf"))

    if not pdfs:
        print("No PDFs found in data/raw!")
        return

    seen_cohorts: dict[str, Path] = {}

    for pdf in pdfs:
        cohort = get_cohort_from_filename(pdf.name)

        if cohort not in VALID_COHORTS:
            raise RuntimeError(
                f"Cohort không hợp lệ cho file {pdf.name}: {cohort}"
            )

        if cohort in seen_cohorts:
            raise RuntimeError(
                f"Phát hiện hai PDF cùng cohort {cohort}:\n"
                f"- {seen_cohorts[cohort]}\n"
                f"- {pdf}"
            )

        seen_cohorts[cohort] = pdf
        
    missing_cohorts = VALID_COHORTS - set(seen_cohorts)

    if missing_cohorts:
        raise RuntimeError(
            "Thiếu PDF của các cohort: "
            + ", ".join(sorted(missing_cohorts))
        )

    chunk_dir = Path("data/processed/chunks")
    
    semantic_outputs = {}
    structured_outputs = {}
    tool_outputs = {}
    all_chunk_outputs = {}
    regulation_chunk_outputs = {}
    docstore_outputs = {}
    formula_outputs = {}
    scoring_outputs = {}
    office_outputs = {}
    faculty_outputs = {}
    program_outputs = {}
    profile_outputs = {}
    audit_outputs = {}
    table_dir = Path("data/processed/tables")
    directory_dir = Path("data/processed/directories")
    metadata_dir = Path("data/processed/metadata")

    for pdf in pdfs:
        cohort = get_cohort_from_filename(pdf.name)
        run_pipeline_for_pdf(pdf, cohort)

        sem_dest = chunk_dir / f"{cohort}_semantic_chunks.json"
        struc_dest = chunk_dir / f"{cohort}_structured_lookup_chunks.json"
        tool_dest = chunk_dir / f"{cohort}_tool_rule_chunks.json"
        all_chunks_dest = chunk_dir / f"{cohort}_all_chunks.json"
        regulation_chunks_dest = chunk_dir / f"{cohort}_regulation_chunks.json"
        docstore_dest = chunk_dir / f"{cohort}_docstore_items.json"
        
        shutil.copy(chunk_dir / "semantic_chunks.json", sem_dest)
        shutil.copy(chunk_dir / "structured_lookup_chunks.json", struc_dest)
        shutil.copy(chunk_dir / "tool_rule_chunks.json", tool_dest)
        shutil.copy(chunk_dir / "all_chunks.json", all_chunks_dest)
        shutil.copy(chunk_dir / "regulation_chunks.json", regulation_chunks_dest)
        shutil.copy(chunk_dir / "docstore_items.json", docstore_dest)
        
        formula_dest = table_dir / f"{cohort}_formula_rules.json"
        scoring_dest = table_dir / f"{cohort}_scoring_tables.json"
        office_dest = directory_dir / f"{cohort}_office_directory.json"
        faculty_dest = directory_dir / f"{cohort}_faculty_directory.json"
        program_dest = directory_dir / f"{cohort}_program_directory.json"
        profile_dest = metadata_dir / f"{cohort}_document_profile.json"
        audit_dest = metadata_dir / f"{cohort}_content_audit_report.json"

        shutil.copy(table_dir / "formula_rules.json", formula_dest)
        shutil.copy(table_dir / "scoring_tables.json", scoring_dest)
        shutil.copy(directory_dir / "office_directory.json", office_dest)
        shutil.copy(directory_dir / "faculty_directory.json", faculty_dest)
        shutil.copy(directory_dir / "program_directory.json", program_dest)
        shutil.copy(metadata_dir / "document_profile.json", profile_dest)
        shutil.copy(metadata_dir / "content_audit_report.json", audit_dest)
        
        semantic_outputs[cohort] = sem_dest
        structured_outputs[cohort] = struc_dest
        tool_outputs[cohort] = tool_dest
        all_chunk_outputs[cohort] = all_chunks_dest
        regulation_chunk_outputs[cohort] = regulation_chunks_dest
        docstore_outputs[cohort] = docstore_dest
        formula_outputs[cohort] = formula_dest
        scoring_outputs[cohort] = scoring_dest
        office_outputs[cohort] = office_dest
        faculty_outputs[cohort] = faculty_dest
        program_outputs[cohort] = program_dest
        profile_outputs[cohort] = profile_dest
        audit_outputs[cohort] = audit_dest

    print(f"\n{'='*50}\n--- MERGING MULTI-COHORT CHUNKS ---\n{'='*50}")
    merge_chunks(semantic_outputs, chunk_dir / "semantic_chunks.json")
    merge_chunks(structured_outputs, chunk_dir / "structured_lookup_chunks.json")
    merge_chunks(tool_outputs, chunk_dir / "tool_rule_chunks.json")
    merge_chunks(all_chunk_outputs, chunk_dir / "all_chunks.json")
    merge_chunks(regulation_chunk_outputs, chunk_dir / "regulation_chunks.json")
    merge_docstore(docstore_outputs, chunk_dir / "all_docstore_items.json")
    
    for stale_path in (
        chunk_dir / "table_chunks.json",
        chunk_dir / "formula_chunks.json",
        chunk_dir / "directory_chunks.json",
    ):
        if stale_path.exists():
            stale_path.unlink()
        
    derived_policy_report = derive_foreign_language_policy(
        chunk_dir / "all_docstore_items.json",
        metadata_dir / "derived_foreign_language_policy_report.json",
    )
    print(
        "Annotated foreign-language policy sections: "
        f"{derived_policy_report['annotated_section_count']}"
    )
    
    print(f"\n{'='*50}\n--- MERGING STRUCTURED DATA ---\n{'='*50}")
    merge_structured_data(formula_outputs, table_dir / "formula_rules.json")
    merge_structured_data(scoring_outputs, table_dir / "scoring_tables.json")
    merge_structured_data(office_outputs, directory_dir / "office_directory.json")
    merge_structured_data(faculty_outputs, directory_dir / "faculty_directory.json")
    merge_structured_data(program_outputs, directory_dir / "program_directory.json")
    enrich_merged_program_faculties(
        directory_dir / "program_directory.json",
        directory_dir / "faculty_directory.json",
        overrides,
    )
    merge_json_documents(profile_outputs, metadata_dir / "document_profiles.json")
    merge_json_documents(audit_outputs, metadata_dir / "content_audit_reports.json")
    
    validate_structured_json(
        [
            table_dir / "scoring_tables.json",
            table_dir / "formula_rules.json",
            directory_dir / "office_directory.json",
            directory_dir / "faculty_directory.json",
            directory_dir / "program_directory.json",
        ]
    )

    audit_reports = {}
    for cohort, path in audit_outputs.items():
        with open(path, "r", encoding="utf-8") as f:
            audit_reports[cohort] = json.load(f)
    with open(
        metadata_dir / "content_audit_diff_report.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(build_content_audit_diff(audit_reports), f, ensure_ascii=False, indent=2)

    validate_cohort_tags(
        [
            chunk_dir / "all_chunks.json",
            chunk_dir / "semantic_chunks.json",
            chunk_dir / "structured_lookup_chunks.json",
            chunk_dir / "tool_rule_chunks.json",
            chunk_dir / "regulation_chunks.json",
            chunk_dir / "all_docstore_items.json",
            table_dir / "formula_rules.json",
            table_dir / "scoring_tables.json",
            directory_dir / "office_directory.json",
            directory_dir / "faculty_directory.json",
            directory_dir / "program_directory.json",
        ]
    )
    validate_retrieval_metadata(
        [
            chunk_dir / "all_chunks.json",
            chunk_dir / "semantic_chunks.json",
            chunk_dir / "structured_lookup_chunks.json",
            chunk_dir / "tool_rule_chunks.json",
            chunk_dir / "all_docstore_items.json",
            table_dir / "formula_rules.json",
            table_dir / "scoring_tables.json",
            directory_dir / "office_directory.json",
            directory_dir / "faculty_directory.json",
            directory_dir / "program_directory.json",
        ]
    )
    validate_program_directory(directory_dir / "program_directory.json", overrides)

    print(f"\n{'='*50}\n--- BUILDING STRUCTURED TABLE LAYER ---\n{'='*50}")
    subprocess.run(
        [sys.executable, "-m", "scripts.build_structured_table_layer"],
        check=True,
    )
    # This artifact is generated by the structured layer, not PDF extraction.
    validate_structured_json([table_dir / "foreign_language_equivalency_table.json"])

    print("\n--- BUILDING FULL PARENTS AND NARRATIVE-ONLY CHILDREN ---")
    subprocess.run(
        [sys.executable, "-m", "scripts.build_parent_child_artifacts", "--publish-artifacts"],
        check=True,
    )

    print(f"\n{'='*50}\n--- BUILDING CROSS-REFERENCE GRAPH ---\n{'='*50}")
    subprocess.run([sys.executable, "-m", "src.ingestion.graph_extractor"], check=True)

    print(f"\n{'='*50}\n--- WRITING BUILD MANIFEST ---\n{'='*50}")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.build_artifact_manifest",
            "--qdrant-collection",
            args.qdrant_collection,
            "--mongo-collection",
            args.mongo_collection,
        ],
        check=True,
    )

    print(f"\n{'='*50}\n--- RUNNING ARTIFACT INTEGRITY AUDITS ---\n{'='*50}")
    subprocess.run([sys.executable, "-m", "scripts.audit_table_quality"], check=True)
    subprocess.run([sys.executable, "-m", "scripts.check_deploy_artifacts"], check=True)

    if os.environ.get("PUSH_REMOTE", "").strip().lower() in {"1", "true", "yes", "on"}:
        print(f"\n{'='*50}\n--- PUSHING TO MONGODB & QDRANT CLOUD ---\n{'='*50}")
        publish_env = os.environ.copy()
        publish_env["QDRANT_COLLECTION_NAME"] = args.qdrant_collection
        publish_env["STUDENT_RAG_HYBRID_COLLECTION"] = args.qdrant_collection
        publish_env["MONGODB_PARENT_COLLECTION"] = args.mongo_collection
        subprocess.run(
            [sys.executable, "-m", "scripts.verify_remote_build", "--preflight"],
            check=True,
            env=publish_env,
        )
        subprocess.run(
            [sys.executable, "-m", "scripts.push_to_qdrant"],
            check=True,
            env=publish_env,
        )
        subprocess.run(
            [sys.executable, "-m", "scripts.push_to_mongo"],
            check=True,
            env=publish_env,
        )
        subprocess.run(
            [sys.executable, "-m", "scripts.verify_remote_build"],
            check=True,
            env=publish_env,
        )
    else:
        print("\nRemote push skipped. Set PUSH_REMOTE=1 to upload MongoDB/Qdrant.")

    print("\nMulti-cohort preprocessing completed successfully!")


if __name__ == "__main__":
    main()
