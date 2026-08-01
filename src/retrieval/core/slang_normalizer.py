import re
from pathlib import Path
from typing import Any

import yaml

from src.retrieval.core.acronym_registry import (
    DEFAULT_PROGRAM_DIRECTORY_PATH,
    build_acronym_registry,
)


class SlangNormalizer:
    """
    Normalizes student slangs in retrieval queries using regex word boundaries.
    Applies 1-to-1 replacements for pure slangs (replace_slangs) and
    expansions (A -> A B) for ambiguous legal terms (expand_slangs).
    """

    def __init__(
        self,
        config_path: str | Path = "configs/hcmue_slang_dictionary.yaml",
        *,
        program_directory: list[dict[str, Any]] | None = None,
        program_directory_path: str | Path = DEFAULT_PROGRAM_DIRECTORY_PATH,
    ):
        self.replace_dict = {}
        self.expand_dict = {}
        self._load_config(config_path)

        self.acronym_registry = build_acronym_registry(
            vocabulary_path=config_path,
            program_directory_path=program_directory_path,
            program_directory=program_directory,
        )
        for acronym, replacement in self.acronym_registry.generated_replacements.items():
            self.replace_dict.setdefault(acronym.lower(), replacement.lower())

        # Build optimized regex patterns
        self.replace_pattern = self._build_regex(self.replace_dict.keys())
        self.expand_pattern = self._build_regex(self.expand_dict.keys())

    def _load_config(self, config_path: str | Path):
        path = Path(config_path)
        if not path.exists():
            return

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        for item in data.get("replace_slangs", []):
            match_str = str(item.get("match", "")).strip().lower()
            replace_str = str(item.get("replace_with", "")).strip().lower()
            if match_str and replace_str:
                self.replace_dict[match_str] = replace_str

        for item in data.get("expand_slangs", []):
            match_str = str(item.get("match", "")).strip().lower()
            expand_str = str(item.get("expand_with", "")).strip().lower()
            if match_str and expand_str:
                self.expand_dict[match_str] = expand_str

    def _build_regex(self, keys):
        if not keys:
            return None
        # Sort by length descending to match longer phrases first (e.g., "không đăng ký được môn" before "đăng ký")
        sorted_keys = sorted(keys, key=len, reverse=True)
        escaped_keys = [re.escape(k) for k in sorted_keys]
        pattern_str = r"\b(" + "|".join(escaped_keys) + r")\b"
        return re.compile(pattern_str, re.IGNORECASE | re.UNICODE)

    @staticmethod
    def _clean(query: str) -> str:
        return re.sub(r"\s+", " ", query).strip()

    def replace_for_router(self, query: str) -> str:
        """Apply only meaning-preserving replacements before routing."""
        if not query:
            return query

        normalized = query
        if self.replace_pattern:

            def replace_match(match):
                matched_text = match.group(1)
                replacement = self.replace_dict.get(matched_text.lower())
                return replacement if replacement else matched_text

            normalized = self.replace_pattern.sub(replace_match, normalized)

        return self._clean(normalized)

    def normalize_for_retrieval(self, query: str) -> str:
        """Apply canonical replacements first, then expand unmatched text."""
        if not query:
            return query

        normalized = query
        protected_replacements: dict[str, str] = {}

        # 1. Protect exact canonical replacements so shorter expansions inside
        # the same phrase cannot break high-confidence matches such as
        # "học bổng KKHT" before the generic "học bổng" expansion runs.
        if self.replace_pattern:

            def protect_replace_match(match):
                matched_text = match.group(1)
                replacement = self.replace_dict.get(matched_text.lower())
                if not replacement:
                    return matched_text
                placeholder = f"__SLANG_CANONICAL_{len(protected_replacements)}__"
                protected_replacements[placeholder] = replacement
                return placeholder

            normalized = self.replace_pattern.sub(protect_replace_match, normalized)

        # 2. Expand unmatched ambiguous phrases (A -> A + B).
        if self.expand_pattern:

            def expand_match(match):
                matched_text = match.group(1)
                replacement = self.expand_dict.get(matched_text.lower())
                if replacement:
                    # Keep original text but append the expansion
                    return f"{matched_text} {replacement}"
                return matched_text

            normalized = self.expand_pattern.sub(expand_match, normalized)

        # 3. Restore protected canonical phrases.
        for placeholder, replacement in protected_replacements.items():
            normalized = normalized.replace(placeholder, replacement)

        # 4. Final canonical pass for any replacement introduced through
        # fallback paths or expansion text.
        if self.replace_pattern:

            def replace_match(match):
                matched_text = match.group(1)
                replacement = self.replace_dict.get(matched_text.lower())
                return replacement if replacement else matched_text

            normalized = self.replace_pattern.sub(replace_match, normalized)

        return self._clean(normalized)

    def normalize(self, query: str) -> str:
        """Backward-compatible alias for full retrieval normalization."""
        return self.normalize_for_retrieval(query)
