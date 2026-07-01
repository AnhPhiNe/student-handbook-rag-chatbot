import os
import subprocess
import sys
from pathlib import Path
import json
import re
import shutil
import unicodedata
import yaml


VALID_COHORTS = {"K48-K49", "K50-K51"}
PROGRAM_OVERRIDES_PATH = Path("configs/program_overrides.yaml")
DOCUMENT_ID_BY_COHORT = {
    "K48-K49": "so_tay_sinh_vien_khoa_48",
    "K50-K51": "so_tay_sinh_vien_khoa_51",
}


def load_program_overrides(path: Path = PROGRAM_OVERRIDES_PATH) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_cohort_from_filename(filename: str) -> str:
    import re
    match = re.search(r"khoa-(\d+)", filename, re.IGNORECASE)
    if match:
        k = int(match.group(1))
        if k <= 49:
            return "K48-K49"
        else:
            return "K50-K51"
    return "UNKNOWN"


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
    if cohort == "K50-K51":
        env["CONFIG_PATH"] = "configs/document_sections_k50_k51.yaml"
    else:
        env["CONFIG_PATH"] = "configs/document_sections.yaml"
    
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
                chunk["chunk_id"] = f"{cohort}_{chunk['chunk_id']}"
                if "parent_id" in chunk["metadata"]:
                    chunk["metadata"]["parent_id"] = f"{cohort}_{chunk['metadata']['parent_id']}"
                if "parent_section_id" in chunk["metadata"]:
                    chunk["metadata"]["parent_section_id"] = (
                        f"{cohort}_{chunk['metadata']['parent_section_id']}"
                    )
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
                doc["cohort"] = cohort
                if "_id" in doc:
                    doc["_id"] = f"{cohort}_{doc['_id']}"
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
            all_items.extend(items)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)


def fold_text(value: str | None) -> str:
    text = str(value or "").lower().replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def derive_k48_programs_from_k50(
    merged_program_path: Path,
    k48_program_path: Path | None = None,
    overrides: dict | None = None,
) -> None:
    """Dùng danh sách ngành K50-K51 cho K48-K49, trừ các ngành không áp dụng."""
    if not merged_program_path.exists():
        return

    overrides = overrides or load_program_overrides()
    policy = (overrides.get("program_policy") or {}).get("K48-K49") or {}
    source_cohort = str(policy.get("source_cohort") or "K50-K51")
    exclusions = {fold_text(item) for item in policy.get("exclusions") or []}
    document_id = str(policy.get("document_id") or "so_tay_sinh_vien_khoa_48")
    derived_rule = str(policy.get("derived_rule") or "")
    review_status = str(policy.get("review_status") or "derived_from_source_policy")

    with merged_program_path.open("r", encoding="utf-8") as f:
        programs = json.load(f)

    k50_programs = [
        item
        for item in programs
        if item.get("cohort") == source_cohort
        and fold_text(item.get("program_name")) not in exclusions
    ]
    if not k50_programs:
        return

    derived_k48_programs = []
    for index, item in enumerate(k50_programs, start=1):
        derived = dict(item)
        derived["record_id"] = f"k48_derived_program_{index}"
        derived["cohort"] = "K48-K49"
        derived["document_id"] = document_id
        derived["derived_from_cohort"] = source_cohort
        derived["derived_rule"] = (
            "K48-K49 dùng danh sách ngành K50-K51, trừ Toán ứng dụng và Công nghệ Giáo dục"
        )
        derived["review_status"] = review_status
        derived["derived_rule"] = derived_rule
        derived_k48_programs.append(derived)

    rewritten = [
        item for item in programs if item.get("cohort") != "K48-K49"
    ] + derived_k48_programs
    rewritten.sort(key=lambda item: (str(item.get("cohort")), str(item.get("record_id"))))

    with merged_program_path.open("w", encoding="utf-8") as f:
        json.dump(rewritten, f, ensure_ascii=False, indent=2)

    if k48_program_path is not None:
        with k48_program_path.open("w", encoding="utf-8") as f:
            json.dump(derived_k48_programs, f, ensure_ascii=False, indent=2)


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
    """
    Kiểm tra mọi record dữ liệu truy vấn đều có cohort thuộc tập khóa hợp lệ.

    File manifest/cấu hình không đi qua hàm này. Với dữ liệu lấy từ sổ tay, pipeline
    không cho phép thiếu cohort hoặc dùng cohort chung như "all".
    """
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
            "Mọi record từ sổ tay phải có cohort K48-K49 hoặc K50-K51.\n"
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

    k48_policy = (overrides.get("program_policy") or {}).get("K48-K49") or {}
    k48_exclusions = {fold_text(item) for item in k48_policy.get("exclusions") or []}
    k48_program_names = {
        fold_text(program.get("program_name"))
        for program in by_cohort.get("K48-K49", [])
    }
    k50_program_names = {
        fold_text(program.get("program_name"))
        for program in by_cohort.get("K50-K51", [])
    }
    for program_name in k48_exclusions:
        if program_name in k48_program_names:
            issues.append(
                {
                    "issue": "excluded_program_present_in_k48",
                    "program_name": program_name,
                }
            )
        if program_name not in k50_program_names:
            issues.append(
                {
                    "issue": "expected_program_missing_in_k50",
                    "program_name": program_name,
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
    if content_type == "form_template":
        notes.append("Chỉ lưu metadata biểu mẫu, không embed toàn văn mẫu đơn")

    return notes


MANUAL_PROGRAM_FACULTY = {
    "cong nghe giao duc": "Khoa Công nghệ Thông tin",
    "cong nghe thong tin": "Khoa Công nghệ Thông tin",
    "dia ly hoc": "Khoa Địa lý",
    "du lich": "Khoa Địa lý",
    "giao duc chinh tri": "Khoa Giáo dục Chính trị",
    "giao duc cong dan": "Khoa Giáo dục Chính trị",
    "giao duc dac biet": "Khoa Giáo dục Đặc biệt",
    "giao duc hoc": "Khoa Khoa học Giáo dục",
    "giao duc mam non trinh do cao dang va dai hoc": "Khoa Giáo dục Mầm non",
    "giao duc quoc phong an ninh": "Khoa Giáo dục Quốc phòng",
    "giao duc the chat": "Khoa Giáo dục Thể chất",
    "giao duc tieu hoc": "Khoa Giáo dục Tiểu học",
    "hoa hoc": "Khoa Hóa học",
    "ngon ngu han quoc": "Khoa Tiếng Hàn Quốc",
    "ngon ngu nhat": "Khoa Tiếng Nhật",
    "quan ly giao duc": "Khoa Khoa học Giáo dục",
    "sinh hoc ung dung": "Khoa Sinh học",
    "su pham cong nghe": "Khoa Vật lý",
    "su pham dia ly": "Khoa Địa lý",
    "su pham lich su dia ly": "Khoa Địa lý",
    "su pham hoa hoc": "Khoa Hóa học",
    "su pham sinh hoc": "Khoa Sinh học",
    "su pham tin hoc": "Khoa Công nghệ Thông tin",
    "su pham toan hoc": "Khoa Toán – Tin học",
    "su pham toan hoc tieng viet va song ngu viet anh": "Khoa Toán – Tin học",
    "su pham vat ly": "Khoa Vật lý",
    "tam ly hoc": "Khoa Tâm lý học",
    "tam ly hoc giao duc": "Khoa Tâm lý học",
    "toan ung dung": "Khoa Toán – Tin học",
    "vat ly hoc": "Khoa Vật lý",
}


def fold_text(text):
    text = str(text or "").lower().replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_faculty_name(name):
    return re.sub(r"^\d+\.\s*", "", str(name or "")).strip()


def resolve_faculty_name(candidate, faculty_records):
    folded_candidate = fold_text(clean_faculty_name(candidate))
    for faculty in faculty_records:
        faculty_name = clean_faculty_name(faculty.get("faculty_or_unit_name"))
        if fold_text(faculty_name) == folded_candidate:
            return faculty_name
    return clean_faculty_name(candidate)


def enrich_program_faculty_names(program_path, faculty_path, overrides: dict | None = None):
    with open(program_path, "r", encoding="utf-8") as f:
        programs = json.load(f)
    with open(faculty_path, "r", encoding="utf-8") as f:
        faculties = json.load(f)
    overrides = overrides or load_program_overrides()
    program_faculty_overrides = {
        fold_text(key): value
        for key, value in (overrides.get("program_faculty_overrides") or {}).items()
    }

    known_by_program = {}
    for program in programs:
        faculty_name = program.get("faculty_name")
        if faculty_name:
            known_by_program.setdefault(
                fold_text(program.get("program_name")),
                clean_faculty_name(faculty_name),
            )

    for program in programs:
        if program.get("faculty_name"):
            continue
        program_key = fold_text(program.get("program_name"))
        candidate = known_by_program.get(program_key) or program_faculty_overrides.get(
            program_key
        )
        if not candidate:
            continue
        program["faculty_name"] = resolve_faculty_name(candidate, faculties)
        program["faculty_name_source"] = (
            "matched_existing_program"
            if program_key in known_by_program
            else "manual_program_faculty_rule"
        )

    with open(program_path, "w", encoding="utf-8") as f:
        json.dump(programs, f, ensure_ascii=False, indent=2)


def should_skip(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def main():
    overrides = load_program_overrides()
    raw_dir = Path("data/raw")
    pdfs = list(raw_dir.glob("*.pdf"))

    if not pdfs:
        print("No PDFs found in data/raw!")
        return

    chunk_dir = Path("data/processed/chunks")
    
    semantic_outputs = {}
    structured_outputs = {}
    tool_outputs = {}
    all_chunk_outputs = {}
    regulation_chunk_outputs = {}
    table_chunk_outputs = {}
    formula_chunk_outputs = {}
    form_chunk_outputs = {}
    directory_chunk_outputs = {}
    procedure_chunk_outputs = {}
    docstore_outputs = {}
    formula_outputs = {}
    threshold_outputs = {}
    scoring_outputs = {}
    form_outputs = {}
    office_outputs = {}
    faculty_outputs = {}
    program_outputs = {}
    reference_outputs = {}
    procedure_outputs = {}
    profile_outputs = {}
    audit_outputs = {}
    table_dir = Path("data/processed/tables")
    form_dir = Path("data/processed/forms")
    directory_dir = Path("data/processed/directories")
    procedure_dir = Path("data/processed/procedures")
    metadata_dir = Path("data/processed/metadata")

    for pdf in pdfs:
        cohort = get_cohort_from_filename(pdf.name)
        run_pipeline_for_pdf(pdf, cohort)

        sem_dest = chunk_dir / f"{cohort}_semantic_chunks.json"
        struc_dest = chunk_dir / f"{cohort}_structured_lookup_chunks.json"
        tool_dest = chunk_dir / f"{cohort}_tool_rule_chunks.json"
        all_chunks_dest = chunk_dir / f"{cohort}_all_chunks.json"
        regulation_chunks_dest = chunk_dir / f"{cohort}_regulation_chunks.json"
        table_chunks_dest = chunk_dir / f"{cohort}_table_chunks.json"
        formula_chunks_dest = chunk_dir / f"{cohort}_formula_chunks.json"
        form_chunks_dest = chunk_dir / f"{cohort}_form_chunks.json"
        directory_chunks_dest = chunk_dir / f"{cohort}_directory_chunks.json"
        procedure_chunks_dest = chunk_dir / f"{cohort}_procedure_chunks.json"
        docstore_dest = chunk_dir / f"{cohort}_docstore_items.json"
        
        shutil.copy(chunk_dir / "semantic_chunks.json", sem_dest)
        shutil.copy(chunk_dir / "structured_lookup_chunks.json", struc_dest)
        shutil.copy(chunk_dir / "tool_rule_chunks.json", tool_dest)
        shutil.copy(chunk_dir / "all_chunks.json", all_chunks_dest)
        shutil.copy(chunk_dir / "regulation_chunks.json", regulation_chunks_dest)
        shutil.copy(chunk_dir / "table_chunks.json", table_chunks_dest)
        shutil.copy(chunk_dir / "formula_chunks.json", formula_chunks_dest)
        shutil.copy(chunk_dir / "form_chunks.json", form_chunks_dest)
        shutil.copy(chunk_dir / "directory_chunks.json", directory_chunks_dest)
        shutil.copy(chunk_dir / "procedure_chunks.json", procedure_chunks_dest)
        shutil.copy(chunk_dir / "docstore_items.json", docstore_dest)
        
        formula_dest = table_dir / f"{cohort}_formula_rules.json"
        threshold_dest = table_dir / f"{cohort}_threshold_rules.json"
        scoring_dest = table_dir / f"{cohort}_scoring_tables.json"
        form_dest = form_dir / f"{cohort}_form_templates.json"
        office_dest = directory_dir / f"{cohort}_office_directory.json"
        faculty_dest = directory_dir / f"{cohort}_faculty_directory.json"
        program_dest = directory_dir / f"{cohort}_program_directory.json"
        reference_dest = directory_dir / f"{cohort}_reference_directory.json"
        procedure_dest = procedure_dir / f"{cohort}_procedures.json"
        profile_dest = metadata_dir / f"{cohort}_document_profile.json"
        audit_dest = metadata_dir / f"{cohort}_content_audit_report.json"

        shutil.copy(table_dir / "formula_rules.json", formula_dest)
        shutil.copy(table_dir / "threshold_rules.json", threshold_dest)
        shutil.copy(table_dir / "scoring_tables.json", scoring_dest)
        shutil.copy(form_dir / "form_templates.json", form_dest)
        shutil.copy(directory_dir / "office_directory.json", office_dest)
        shutil.copy(directory_dir / "faculty_directory.json", faculty_dest)
        shutil.copy(directory_dir / "program_directory.json", program_dest)
        shutil.copy(directory_dir / "reference_directory.json", reference_dest)
        shutil.copy(procedure_dir / "procedures.json", procedure_dest)
        shutil.copy(metadata_dir / "document_profile.json", profile_dest)
        shutil.copy(metadata_dir / "content_audit_report.json", audit_dest)
        
        semantic_outputs[cohort] = sem_dest
        structured_outputs[cohort] = struc_dest
        tool_outputs[cohort] = tool_dest
        all_chunk_outputs[cohort] = all_chunks_dest
        regulation_chunk_outputs[cohort] = regulation_chunks_dest
        table_chunk_outputs[cohort] = table_chunks_dest
        formula_chunk_outputs[cohort] = formula_chunks_dest
        form_chunk_outputs[cohort] = form_chunks_dest
        directory_chunk_outputs[cohort] = directory_chunks_dest
        procedure_chunk_outputs[cohort] = procedure_chunks_dest
        docstore_outputs[cohort] = docstore_dest
        formula_outputs[cohort] = formula_dest
        threshold_outputs[cohort] = threshold_dest
        scoring_outputs[cohort] = scoring_dest
        form_outputs[cohort] = form_dest
        office_outputs[cohort] = office_dest
        faculty_outputs[cohort] = faculty_dest
        program_outputs[cohort] = program_dest
        reference_outputs[cohort] = reference_dest
        procedure_outputs[cohort] = procedure_dest
        profile_outputs[cohort] = profile_dest
        audit_outputs[cohort] = audit_dest

    print(f"\n{'='*50}\n--- MERGING MULTI-COHORT CHUNKS ---\n{'='*50}")
    merge_chunks(semantic_outputs, chunk_dir / "semantic_chunks.json")
    merge_chunks(structured_outputs, chunk_dir / "structured_lookup_chunks.json")
    merge_chunks(tool_outputs, chunk_dir / "tool_rule_chunks.json")
    merge_chunks(all_chunk_outputs, chunk_dir / "all_chunks.json")
    merge_chunks(regulation_chunk_outputs, chunk_dir / "regulation_chunks.json")
    merge_chunks(table_chunk_outputs, chunk_dir / "table_chunks.json")
    merge_chunks(formula_chunk_outputs, chunk_dir / "formula_chunks.json")
    merge_chunks(form_chunk_outputs, chunk_dir / "form_chunks.json")
    merge_chunks(directory_chunk_outputs, chunk_dir / "directory_chunks.json")
    merge_chunks(procedure_chunk_outputs, chunk_dir / "procedure_chunks.json")
    merge_docstore(docstore_outputs, chunk_dir / "docstore_items.json")
    
    print(f"\n{'='*50}\n--- MERGING STRUCTURED DATA ---\n{'='*50}")
    merge_structured_data(formula_outputs, table_dir / "formula_rules.json")
    merge_structured_data(threshold_outputs, table_dir / "threshold_rules.json")
    merge_structured_data(scoring_outputs, table_dir / "scoring_tables.json")
    merge_structured_data(form_outputs, form_dir / "form_templates.json")
    merge_structured_data(office_outputs, directory_dir / "office_directory.json")
    merge_structured_data(faculty_outputs, directory_dir / "faculty_directory.json")
    merge_structured_data(program_outputs, directory_dir / "program_directory.json")
    enrich_program_faculty_names(
        directory_dir / "program_directory.json",
        directory_dir / "faculty_directory.json",
        overrides,
    )
    derive_k48_programs_from_k50(
        directory_dir / "program_directory.json",
        program_outputs.get("K48-K49"),
        overrides,
    )
    merge_structured_data(reference_outputs, directory_dir / "reference_directory.json")
    merge_structured_data(procedure_outputs, procedure_dir / "procedures.json")
    merge_json_documents(profile_outputs, metadata_dir / "document_profiles.json")
    merge_json_documents(audit_outputs, metadata_dir / "content_audit_reports.json")
    # Backward-compatible alias for old config keys and reports.
    shutil.copy(
        directory_dir / "faculty_directory.json",
        directory_dir / "faculty_program_directory.json",
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
            chunk_dir / "table_chunks.json",
            chunk_dir / "formula_chunks.json",
            chunk_dir / "form_chunks.json",
            chunk_dir / "directory_chunks.json",
            chunk_dir / "procedure_chunks.json",
            chunk_dir / "docstore_items.json",
            table_dir / "formula_rules.json",
            table_dir / "threshold_rules.json",
            table_dir / "scoring_tables.json",
            form_dir / "form_templates.json",
            directory_dir / "office_directory.json",
            directory_dir / "faculty_directory.json",
            directory_dir / "program_directory.json",
            directory_dir / "faculty_program_directory.json",
            directory_dir / "reference_directory.json",
            procedure_dir / "procedures.json",
        ]
    )
    validate_retrieval_metadata(
        [
            chunk_dir / "all_chunks.json",
            chunk_dir / "semantic_chunks.json",
            chunk_dir / "structured_lookup_chunks.json",
            chunk_dir / "tool_rule_chunks.json",
            chunk_dir / "docstore_items.json",
            table_dir / "formula_rules.json",
            table_dir / "threshold_rules.json",
            table_dir / "scoring_tables.json",
            form_dir / "form_templates.json",
            directory_dir / "office_directory.json",
            directory_dir / "faculty_directory.json",
            directory_dir / "program_directory.json",
            procedure_dir / "procedures.json",
        ]
    )
    validate_program_directory(directory_dir / "program_directory.json", overrides)

    print(f"\n{'='*50}\n--- BUILDING ENTITY REGISTRY ---\n{'='*50}")
    subprocess.run([sys.executable, "-m", "src.retrieval.core.build_entity_registry"], check=True)

    if should_skip("SKIP_VECTORSTORE"):
        print("\nSKIP_VECTORSTORE enabled; unified vector store build skipped.")
    else:
        print(f"\n{'='*50}\n--- BUILDING UNIFIED VECTOR STORE ---\n{'='*50}")
        subprocess.run([sys.executable, "-m", "scripts.build_vectorstore"], check=True)

    if should_skip("SKIP_REMOTE_PUSH"):
        print("\nSKIP_REMOTE_PUSH enabled; MongoDB/Qdrant upload skipped.")
    else:
        print(f"\n{'='*50}\n--- PUSHING TO MONGODB & QDRANT CLOUD ---\n{'='*50}")
        subprocess.run([sys.executable, "-m", "scripts.push_to_mongo"], check=True)
        subprocess.run([sys.executable, "-m", "scripts.migrate_to_qdrant"], check=True)

    print("\nMulti-cohort preprocessing completed successfully!")


if __name__ == "__main__":
    main()
