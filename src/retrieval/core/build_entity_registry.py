import json
import re
import unicodedata
from pathlib import Path
from typing import Any


OFFICE_PATH = Path("data/processed/directories/office_directory.json")
FACULTY_PATH = Path("data/processed/directories/faculty_program_directory.json")
OUTPUT_PATH = Path("data/processed/entities/entity_registry.json")


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_name(name: str) -> str:
    name = re.sub(r"^\d+\.\s*", "", name).strip()
    name = name.replace("–", "-")
    return name


def fold_vietnamese(text: str) -> str:
    text = text.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    stripped = re.sub(r"[^\w\s-]", " ", stripped, flags=re.UNICODE)
    return re.sub(r"\s+", " ", stripped).strip()


def slugify(text: str) -> str:
    text = normalize_name(text).lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "_", text)
    return text.strip("_")


def make_basic_aliases(name: str) -> list[str]:
    clean = normalize_name(name)
    lower = clean.lower()
    aliases = {lower}

    aliases.add(lower.replace("–", "-"))
    aliases.add(lower.replace("-", " "))

    if "phòng" in lower:
        aliases.add(lower.replace("phòng ", ""))

    if "khoa" in lower:
        aliases.add(lower.replace("khoa ", ""))

    aliases.update(fold_vietnamese(alias) for alias in list(aliases))
    return sorted(a.strip() for a in aliases if a.strip())


def extract_program_names(raw_text: str) -> list[str]:
    program_names: list[str] = []
    lines = [line.strip() for line in raw_text.splitlines()]
    index = 0

    while index < len(lines):
        line = lines[index]
        if _is_program_heading(line):
            heading = _join_wrapped_program_heading(lines, index)
            program_name = _clean_program_heading(heading)
            if program_name:
                program_names.append(program_name)
        index += 1

    return list(dict.fromkeys(program_names))


def make_program_aliases(program_names: list[str]) -> list[str]:
    aliases: set[str] = set()

    for program_name in program_names:
        lower = program_name.lower()
        base = re.sub(r"\s*\([^)]*\)\s*", " ", lower)
        base = re.sub(r"\s+", " ", base).strip()
        if not base:
            continue

        variants = {
            base,
            f"ngành {base}",
            f"khoa {base}",
        }

        aliases.update(variants)
        aliases.update(fold_vietnamese(alias) for alias in variants)

    return sorted(alias for alias in aliases if _is_useful_alias(alias))


def _is_program_heading(line: str) -> bool:
    if not line:
        return False
    return line.startswith("NGÀNH ") or line.startswith(
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
    heading = re.sub(r"^NGÀNH\s+", "", heading.strip())
    heading = re.sub(r"\s+", " ", heading)
    return heading.title()


def _is_useful_alias(alias: str) -> bool:
    alias = alias.strip()
    if len(alias) < 4:
        return False
    return len(alias.split()) >= 2 or alias in {"cntt", "ktx", "ctsv", "hssv"}


def add_manual_aliases(entity: dict[str, Any]) -> dict[str, Any]:
    name = entity["canonical_name"].lower()
    aliases = set(entity["aliases"])

    if "công tác chính trị" in name:
        aliases.update(
            ["ctct", "hssv", "ctct-hssv", "phòng ctct", "phòng hssv", "ctsv"]
        )

    if "đào tạo" in name:
        aliases.update(["pdt", "phongdt", "phòng học vụ", "học vụ"])

    if "công nghệ thông tin" in name or "công nghệ - thông tin" in name:
        aliases.update(["cntt", "it", "khoa cntt", "khoa công nghệ thông tin"])

    if "ngữ văn" in name:
        aliases.update(
            [
                "ngành văn học",
                "khoa văn học",
                "văn học",
                "nganh van hoc",
                "khoa van hoc",
                "van hoc",
            ]
        )

    if "ký túc xá" in name:
        aliases.update(["ktx", "nội trú", "kí túc xá"])

    aliases.update(fold_vietnamese(alias) for alias in list(aliases))
    entity["aliases"] = sorted(aliases)
    return entity


def build_registry() -> list[dict[str, Any]]:
    office_records = load_json(OFFICE_PATH)
    faculty_records = load_json(FACULTY_PATH)

    entities = []

    for record in office_records:
        name = normalize_name(record["unit_name"])
        entity = {
            "entity_id": f"office_{slugify(name)}",
            "canonical_name": name,
            "entity_type": "office",
            "aliases": make_basic_aliases(name),
            "target_chunk_types": ["office_directory", "regulation"],
            "source_record_id": record.get("record_id"),
            "source_pages": record.get("source_pages", []),
        }
        entities.append(add_manual_aliases(entity))

    for record in faculty_records:
        name = normalize_name(record["faculty_or_unit_name"])
        program_names = extract_program_names(str(record.get("raw_text") or ""))
        aliases = set(make_basic_aliases(name))
        aliases.update(make_program_aliases(program_names))
        entity = {
            "entity_id": f"faculty_{slugify(name)}",
            "canonical_name": name,
            "entity_type": "faculty",
            "aliases": sorted(aliases),
            "program_names": program_names,
            "target_chunk_types": ["faculty_program_directory"],
            "source_record_id": record.get("record_id"),
            "source_pages": record.get("source_pages", []),
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
