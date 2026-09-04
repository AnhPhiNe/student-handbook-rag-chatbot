import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VOCABULARY_PATH = PROJECT_ROOT / "configs" / "hcmue_slang_dictionary.yaml"
DEFAULT_PROGRAM_DIRECTORY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "directories" / "program_directory.json"
)

_CONNECTORS = {"cua", "cho", "tai", "theo", "va", "ve", "voi"}
_ORGANIZATION_PREFIXES = ("bo mon ", "chuyen nganh ", "khoa ", "nganh ")


def ascii_upper(value: str) -> str:
    """Fold text to uppercase ASCII for stable acronym matching."""

    normalized = unicodedata.normalize(
        "NFD",
        value.replace("Đ", "D").replace("đ", "d"),
    )
    return "".join(
        character for character in normalized if unicodedata.category(character) != "Mn"
    ).upper()


def canonical_acronym(value: str) -> str:
    """Normalize an acronym token to its canonical form."""

    return re.sub(r"[^A-Z0-9]", "", ascii_upper(value))


def normalize_entity_name(value: str) -> str:
    """Normalize an entity name for alias matching."""

    without_parenthetical = re.sub(r"\([^)]*\)", " ", str(value or ""))
    normalized = re.sub(r"\s+", " ", without_parenthetical).strip()
    ascii_name = ascii_upper(normalized).lower()
    for prefix in _ORGANIZATION_PREFIXES:
        if ascii_name.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
            break
    return normalized


def acronym_for_name(value: str) -> str | None:
    """Derive an acronym from a normalized multi-word entity name."""

    normalized = normalize_entity_name(value)
    initials: list[str] = []
    for word in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE):
        ascii_word = ascii_upper(word)
        if not ascii_word or ascii_word.lower() in _CONNECTORS:
            continue
        initials.append(ascii_word[0])

    acronym = "".join(initials)
    return acronym if 2 <= len(acronym) <= 12 else None


@dataclass(frozen=True)
class AcronymRegistry:
    """Resolve canonical entities from explicit and derived acronyms."""

    explicit_replacements: dict[str, str]
    generated_replacements: dict[str, str]
    ambiguous_generated: dict[str, tuple[str, ...]]
    explicit_literals: frozenset[str]
    generated_literals: frozenset[str]

    @property
    def literal_acronyms(self) -> frozenset[str]:
        """Return acronyms that should remain indivisible lexical tokens."""

        return self.explicit_literals | self.generated_literals

    def replacement_for(self, token: str) -> str | None:
        """Return the canonical expansion for an acronym token."""

        key = canonical_acronym(token)
        return self.explicit_replacements.get(key) or self.generated_replacements.get(
            key
        )


def _load_vocabulary(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        return {}
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _load_program_directory(directory_path: Path) -> list[dict[str, Any]]:
    if not directory_path.is_file():
        return []
    payload = json.loads(directory_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("program directory must contain a JSON list")
    return [item for item in payload if isinstance(item, dict)]


def _explicit_acronyms(
    vocabulary: dict[str, Any],
) -> tuple[dict[str, str], set[str]]:
    replacements: dict[str, str] = {}
    literals: set[str] = set()

    for item in vocabulary.get("replace_slangs", []):
        if not isinstance(item, dict):
            continue
        match = str(item.get("match") or "").strip()
        replacement = str(item.get("replace_with") or "").strip()
        if (
            not match
            or not replacement
            or match != match.upper()
            or not any(character.isalpha() for character in match)
        ):
            continue

        parts = re.findall(r"[A-ZĐ0-9]+", match)
        for part in parts:
            canonical = canonical_acronym(part)
            if len(canonical) >= 2:
                literals.add(canonical)

        combined = canonical_acronym(match)
        if len(combined) >= 2:
            literals.add(combined)
            replacements[combined] = replacement

    return replacements, literals


def _generated_acronyms(
    program_directory: list[dict[str, Any]],
    *,
    explicit_replacements: dict[str, str],
) -> tuple[dict[str, str], dict[str, tuple[str, ...]], set[str]]:
    candidates: dict[str, dict[str, str]] = {}
    literals: set[str] = set()

    for item in program_directory:
        for field in ("program_name", "faculty_name"):
            entity_name = normalize_entity_name(str(item.get(field) or ""))
            acronym = acronym_for_name(entity_name)
            if not acronym or not entity_name:
                continue
            literals.add(acronym)
            candidates.setdefault(acronym, {})[entity_name.casefold()] = entity_name

    replacements: dict[str, str] = {}
    ambiguous: dict[str, tuple[str, ...]] = {}
    for acronym, names_by_key in candidates.items():
        if acronym in explicit_replacements:
            continue
        names = tuple(sorted(names_by_key.values()))
        if len(acronym) < 3:
            continue
        if len(names) == 1:
            replacements[acronym] = names[0]
        else:
            ambiguous[acronym] = names

    return replacements, ambiguous, literals


def build_acronym_registry(
    *,
    vocabulary_path: str | Path = DEFAULT_VOCABULARY_PATH,
    program_directory_path: str | Path = DEFAULT_PROGRAM_DIRECTORY_PATH,
    program_directory: list[dict[str, Any]] | None = None,
) -> AcronymRegistry:
    """Build the shared acronym registry from project resources."""

    vocabulary = _load_vocabulary(Path(vocabulary_path))
    explicit_replacements, explicit_literals = _explicit_acronyms(vocabulary)
    directory = (
        program_directory
        if program_directory is not None
        else _load_program_directory(Path(program_directory_path))
    )
    generated_replacements, ambiguous, generated_literals = _generated_acronyms(
        directory,
        explicit_replacements=explicit_replacements,
    )
    return AcronymRegistry(
        explicit_replacements=explicit_replacements,
        generated_replacements=generated_replacements,
        ambiguous_generated=ambiguous,
        explicit_literals=frozenset(explicit_literals),
        generated_literals=frozenset(generated_literals),
    )
