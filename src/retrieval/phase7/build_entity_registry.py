import json
import re
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

    return sorted(a.strip() for a in aliases if a.strip())


def add_manual_aliases(entity: dict[str, Any]) -> dict[str, Any]:
    name = entity["canonical_name"].lower()
    aliases = set(entity["aliases"])

    if "công tác chính trị" in name:
        aliases.update(["ctct", "hssv", "ctct-hssv", "phòng ctct", "phòng hssv", "ctsv"])

    if "đào tạo" in name:
        aliases.update(["pdt", "phongdt", "phòng học vụ", "học vụ"])

    if "công nghệ thông tin" in name or "công nghệ - thông tin" in name:
        aliases.update(["cntt", "it", "khoa cntt", "khoa công nghệ thông tin"])

    if "ký túc xá" in name:
        aliases.update(["ktx", "nội trú", "kí túc xá"])

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
        entity = {
            "entity_id": f"faculty_{slugify(name)}",
            "canonical_name": name,
            "entity_type": "faculty",
            "aliases": make_basic_aliases(name),
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