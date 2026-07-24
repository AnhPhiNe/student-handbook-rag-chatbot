import re
import yaml
from pathlib import Path


class SlangNormalizer:
    """
    Normalizes student slangs in retrieval queries using regex word boundaries.
    Applies 1-to-1 replacements for pure slangs (replace_slangs) and
    expansions (A -> A B) for ambiguous legal terms (expand_slangs).
    """

    def __init__(self, config_path: str = "configs/hcmue_slang_dictionary.yaml"):
        self.replace_dict = {}
        self.expand_dict = {}
        self._load_config(config_path)
        
        # Build optimized regex patterns
        self.replace_pattern = self._build_regex(self.replace_dict.keys())
        self.expand_pattern = self._build_regex(self.expand_dict.keys())

    def _load_config(self, config_path: str):
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

    def normalize(self, query: str) -> str:
        if not query:
            return query
            
        normalized = query

        # 1. Expand (A -> A + B)
        if self.expand_pattern:
            def expand_match(m):
                matched_text = m.group(1)
                replacement = self.expand_dict.get(matched_text.lower())
                if replacement:
                    # Keep original text but append the expansion
                    return f"{matched_text} {replacement}"
                return matched_text
            normalized = self.expand_pattern.sub(expand_match, normalized)

        # 2. Replace (A -> B)
        if self.replace_pattern:
            def replace_match(m):
                matched_text = m.group(1)
                replacement = self.replace_dict.get(matched_text.lower())
                return replacement if replacement else matched_text
            normalized = self.replace_pattern.sub(replace_match, normalized)
            
        # Clean up extra spaces
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized
