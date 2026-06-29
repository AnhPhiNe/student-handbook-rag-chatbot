import json
import re
import unicodedata
from pathlib import Path
from typing import Any


OFFICE_PATH = Path("data/processed/directories/office_directory.json")
FACULTY_PATH = Path("data/processed/directories/faculty_directory.json")
PROGRAM_PATH = Path("data/processed/directories/program_directory.json")
OUTPUT_PATH = Path("data/processed/entities/entity_registry.json")


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_name(name: str) -> str:
    name = re.sub(r"^\d+\.\s*", "", str(name)).strip()
    name = name.replace("–", "-")
    return re.sub(r"\s+", " ", name)


def fold_vietnamese(text: str) -> str:
    text = str(text).lower().replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    text = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def slugify(text: str) -> str:
    text = fold_vietnamese(normalize_name(text))
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", "_", text).strip("_")


def make_basic_aliases(name: str) -> list[str]:
    clean = normalize_name(name)
    lower = clean.lower()
    aliases = {
        lower,
        lower.replace("–", "-"),
        lower.replace("-", " "),
        fold_vietnamese(lower),
        fold_vietnamese(lower.replace("-", " ")),
    }

    if "phòng" in lower:
        aliases.add(lower.replace("phòng ", ""))
    if "khoa" in lower:
        aliases.add(lower.replace("khoa ", ""))

    aliases.update(fold_vietnamese(alias) for alias in list(aliases))
    return sorted(alias for alias in aliases if _is_useful_alias(alias))


def extract_program_names(raw_text: str) -> list[str]:
    program_names: list[str] = []
    lines = [line.strip() for line in str(raw_text).splitlines()]

    for index, line in enumerate(lines):
        if not _is_program_heading(line):
            continue
        heading = _join_wrapped_program_heading(lines, index)
        program_name = _clean_program_heading(heading)
        if program_name:
            program_names.append(program_name)

    return list(dict.fromkeys(program_names))


def make_program_aliases(program_names: list[str]) -> list[str]:
    aliases: set[str] = set()

    for program_name in program_names:
        lower = normalize_name(program_name).lower()
        base = re.sub(r"\s*\([^)]*\)\s*", " ", lower)
        base = re.sub(r"\s+", " ", base).strip()
        if not base:
            continue

        variants = {
            base,
            f"ngành {base}",
            f"khoa {base}",
            fold_vietnamese(base),
            f"nganh {fold_vietnamese(base)}",
            f"khoa {fold_vietnamese(base)}",
        }
        aliases.update(variants)

    return sorted(alias for alias in aliases if _is_useful_alias(alias))


def _is_program_heading(line: str) -> bool:
    if not line:
        return False
    upper = line.upper()
    return upper.startswith("NGÀNH ") or upper.startswith(
        "TIẾNG VIỆT VÀ VĂN HÓA VIỆT NAM"
    )


def _join_wrapped_program_heading(lines: list[str], index: int) -> str:
    heading = lines[index].strip()
    next_index = index + 1

    if heading.count("(") > heading.count(")") and next_index < len(lines):
        continuation = lines[next_index].strip()
        if continuation and not continuation.endswith(":"):
            heading = f"{heading} {continuation}"

    return heading


def _clean_program_heading(heading: str) -> str:
    heading = re.sub(r"^NGÀNH\s+", "", heading.strip(), flags=re.IGNORECASE)
    heading = re.sub(r"\s+", " ", heading)
    return heading.title()


def _is_useful_alias(alias: str) -> bool:
    alias = alias.strip()
    if len(alias) < 3:
        return False
    return len(alias.split()) >= 2 or alias in {"cntt", "it", "ktx", "ctsv", "hssv"}


def add_manual_aliases(entity: dict[str, Any]) -> dict[str, Any]:
    name = fold_vietnamese(entity["canonical_name"])
    aliases = set(entity["aliases"])

    if "cong tac chinh tri" in name or "hoc sinh sinh vien" in name:
        aliases.update(
            [
                "ctct",
                "hssv",
                "ctct-hssv",
                "phòng ctct",
                "phòng hssv",
                "phong ctct",
                "phong hssv",
                "ctsv",
            ]
        )

    if "dao tao" in name:
        aliases.update(["pdt", "phongdt", "phòng học vụ", "phong hoc vu", "học vụ", "hoc vu"])

    if "cong nghe thong tin" in name:
        entity_type = entity.get("entity_type")
        if entity_type == "office":
            aliases.update(
                [
                    "phòng cntt",
                    "phong cntt",
                    "phòng công nghệ thông tin",
                    "phong cong nghe thong tin",
                ]
            )
        elif entity_type == "faculty":
            aliases.update(["cntt", "it", "khoa cntt", "khoa công nghệ thông tin"])
        elif entity_type == "program":
            aliases.update(["cntt", "it", "ngành cntt", "ngành công nghệ thông tin"])

    if "ngu van" in name:
        aliases.update(["ngành văn học", "nganh van hoc", "văn học", "van hoc"])

    if "ky tuc xa" in name:
        aliases.update(["ktx", "nội trú", "noi tru", "kí túc xá", "ki tuc xa"])

    aliases.update(fold_vietnamese(alias) for alias in list(aliases))
    entity["aliases"] = sorted(alias for alias in aliases if _is_useful_alias(alias))
    return entity


def _entity_id(prefix: str, record: dict[str, Any], name: str) -> str:
    cohort = record.get("cohort") or "all"
    return f"{prefix}_{slugify(cohort)}_{slugify(name)}"


def build_registry() -> list[dict[str, Any]]:
    office_records = load_json(OFFICE_PATH)
    faculty_records = load_json(FACULTY_PATH)
    program_records = load_json(PROGRAM_PATH) if PROGRAM_PATH.exists() else []

    entities = []

    for record in office_records:
        name = normalize_name(record["unit_name"])
        entity = {
            "entity_id": _entity_id("office", record, name),
            "canonical_name": name,
            "entity_type": "office",
            "aliases": make_basic_aliases(name),
            "target_chunk_types": ["office_directory", "regulation"],
            "source_record_id": record.get("record_id"),
            "source_pages": record.get("source_pages", []),
            "cohort": record.get("cohort"),
        }
        entities.append(add_manual_aliases(entity))

    for record in faculty_records:
        name = normalize_name(record["faculty_or_unit_name"])
        program_names = extract_program_names(str(record.get("raw_text") or ""))
        aliases = set(make_basic_aliases(name))
        aliases.update(make_program_aliases(program_names))
        entity = {
            "entity_id": _entity_id("faculty", record, name),
            "canonical_name": name,
            "entity_type": "faculty",
            "aliases": sorted(aliases),
            "program_names": program_names,
            "target_chunk_types": ["faculty_directory", "program_directory"],
            "source_record_id": record.get("record_id"),
            "source_pages": record.get("source_pages", []),
            "cohort": record.get("cohort"),
        }
        entities.append(add_manual_aliases(entity))

    for record in program_records:
        name = normalize_name(record["program_name"])
        aliases = set(make_basic_aliases(name))
        aliases.update(make_program_aliases([name]))
        entity = {
            "entity_id": _entity_id("program", record, name),
            "canonical_name": name,
            "entity_type": "program",
            "aliases": sorted(aliases),
            "faculty_name": record.get("faculty_name"),
            "target_chunk_types": ["program_directory"],
            "source_record_id": record.get("record_id"),
            "source_pages": record.get("source_pages", []),
            "cohort": record.get("cohort"),
        }
        entities.append(add_manual_aliases(entity))

    return entities


def main() -> None:
    registry = build_registry()
    save_json(registry, OUTPUT_PATH)

    print("Entity registry created.")
    print(f"Entities: {len(registry)}")
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
