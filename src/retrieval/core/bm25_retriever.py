import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from rank_bm25 import BM25Okapi

try:
    import underthesea
except ModuleNotFoundError:
    underthesea = None

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VOCABULARY_PATH = PROJECT_ROOT / "configs" / "hcmue_slang_dictionary.yaml"
DEFAULT_PROGRAM_DIRECTORY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "directories" / "program_directory.json"
)
FALLBACK_ACRONYMS = {
    "CNTT",
    "CTDT",
    "CVHT",
    "DKHP",
    "DRL",
    "GDQP",
    "GDQPAN",
    "GDTC",
    "GPA",
    "HB",
    "HBKKHT",
    "HP",
    "HSSV",
    "KQHT",
    "KQRL",
    "KTX",
    "MSSV",
    "SV",
}
ACRONYM_CONNECTORS = {"cua", "cho", "tai", "theo", "va", "ve", "voi"}
ORGANIZATION_PREFIXES = ("bo mon ", "chuyen nganh ", "khoa ", "nganh ")


def _ascii_upper(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.replace("Đ", "D").replace("đ", "d"))
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").upper()


def _canonical_acronym(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", _ascii_upper(value))


def _configured_acronyms(config_path: Path) -> set[str]:
    if not config_path.is_file():
        return set()

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    acronyms: set[str] = set()
    for item in payload.get("replace_slangs", []):
        match = str(item.get("match") or "").strip()
        if not match or match != match.upper() or not any(char.isalpha() for char in match):
            continue

        parts = re.findall(r"[A-ZĐ0-9]+", match)
        for part in parts:
            canonical = _canonical_acronym(part)
            if len(canonical) >= 2:
                acronyms.add(canonical)

        combined = _canonical_acronym(match)
        if len(combined) >= 2:
            acronyms.add(combined)
    return acronyms


def _name_acronyms(name: str) -> set[str]:
    without_parenthetical = re.sub(r"\([^)]*\)", " ", str(name or ""))
    normalized_name = re.sub(r"\s+", " ", without_parenthetical).strip()
    ascii_name = _ascii_upper(normalized_name).lower()
    for prefix in ORGANIZATION_PREFIXES:
        if ascii_name.startswith(prefix):
            normalized_name = normalized_name[len(prefix) :].strip()
            break

    initials = []
    for word in re.findall(r"[^\W_]+", normalized_name, flags=re.UNICODE):
        ascii_word = _ascii_upper(word)
        if ascii_word.lower() in ACRONYM_CONNECTORS:
            continue
        initials.append(ascii_word[0])

    acronym = "".join(initials)
    return {acronym} if 2 <= len(acronym) <= 12 else set()


def _directory_acronyms(directory_path: Path) -> set[str]:
    if not directory_path.is_file():
        return set()

    payload = json.loads(directory_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("program directory must contain a JSON list")

    acronyms: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        for field in ("program_name", "faculty_name"):
            acronyms.update(_name_acronyms(str(item.get(field) or "")))
    return acronyms


class BM25Retriever:
    def __init__(
        self,
        *,
        vocabulary_path: str | Path | None = None,
        program_directory_path: str | Path | None = None,
    ):
        self.bm25_index = None
        self.chunks = []
        self.acronym_whitelist = set()
        self.case_insensitive_acronyms = set()
        self.generated_acronyms = set()
        self._load_acronym_whitelist(
            Path(vocabulary_path) if vocabulary_path is not None else DEFAULT_VOCABULARY_PATH,
            (
                Path(program_directory_path)
                if program_directory_path is not None
                else DEFAULT_PROGRAM_DIRECTORY_PATH
            ),
        )

        # Regex for capturing codes and numbers (e.g., 7480201, 23/QĐ-BGDĐT)
        self.literal_regex = re.compile(
            r'\b\d{4,}\b|\d+/[A-ZĐ\-]+|IELTS|TOEFL|B1|B2|Goethe-Zertifikat',
            re.IGNORECASE
        )

    def _load_acronym_whitelist(
        self,
        vocabulary_path: Path,
        program_directory_path: Path,
    ) -> None:
        configured: set[str] = set()
        generated: set[str] = set()

        try:
            configured = _configured_acronyms(vocabulary_path)
        except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
            logger.warning("Could not load configured BM25 acronyms: %s", exc)

        try:
            generated = _directory_acronyms(program_directory_path)
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            logger.warning("Could not generate BM25 acronyms from program directory: %s", exc)

        self.case_insensitive_acronyms.update(FALLBACK_ACRONYMS)
        self.case_insensitive_acronyms.update(configured)
        self.generated_acronyms.update(generated)
        self.acronym_whitelist.update(self.case_insensitive_acronyms)
        self.acronym_whitelist.update(self.generated_acronyms)
        logger.info(
            "Loaded %d BM25 acronyms (%d configured, %d generated).",
            len(self.acronym_whitelist),
            len(configured),
            len(generated),
        )

    def _is_known_acronym_token(self, token: str) -> bool:
        canonical = _canonical_acronym(token)
        if canonical in self.case_insensitive_acronyms:
            return True
        return (
            canonical in self.generated_acronyms
            and any(char.isalpha() for char in token)
            and token == token.upper()
        )

    def _tokenize(self, text: str) -> list[str]:
        if not text:
            return []

        tokens = []
        # Layer 1: Literal Extraction
        # Find all literal matches and remove them from the text to be segmented
        literals = []
        
        def literal_replacer(match):
            lit = match.group(0)
            literals.append(lit.lower())
            return " "
            
        text_for_segmentation = self.literal_regex.sub(literal_replacer, text)
        
        # Also extract acronyms from whitelist
        remaining_words = []
        for word in text_for_segmentation.split():
            canonical = _canonical_acronym(word)
            if self._is_known_acronym_token(word):
                literals.append(canonical.lower())
            else:
                remaining_words.append(word)
        text_for_segmentation = " ".join(remaining_words)

        tokens.extend(literals)

        # Layer 2: Word Segmentation (underthesea)
        try:
            if underthesea is not None:
                segmented_words = underthesea.word_tokenize(text_for_segmentation.lower())
                tokens.extend([w.replace(" ", "_") for w in segmented_words])
            else:
                tokens.extend(text_for_segmentation.lower().split())
            
            # Bigrams of adjacent segmented syllables (fallback for bad segmentation)
            syllables = text_for_segmentation.lower().split()
            bigrams = [f"{syllables[i]}_{syllables[i+1]}" for i in range(len(syllables)-1)]
            tokens.extend(bigrams)
            
        except Exception as e:
             logger.warning(f"Underthesea tokenization failed: {e}")
             # Absolute fallback
             tokens.extend(text_for_segmentation.lower().split())

        return [t for t in tokens if t.strip()]

    def build_bm25_index(self, chunks: list[dict[str, Any]]):
        self.chunks = chunks
        corpus_tokens = [self._tokenize(str(chunk.get("content") or "")) for chunk in self.chunks]
        self.bm25_index = BM25Okapi(corpus_tokens)
        logger.info(f"BM25 index built with {len(self.chunks)} chunks.")

    def search_bm25(self, query: str, top_k: int = 24) -> list[tuple[float, dict[str, Any]]]:
        if not self.bm25_index or not self.chunks:
            return []

        query_tokens = self._tokenize(query)
        scores = self.bm25_index.get_scores(query_tokens)
        
        # Pair scores with chunks
        scored_chunks = [(float(score), dict(chunk)) for score, chunk in zip(scores, self.chunks)]
        
        # Filter zero scores and sort
        scored_chunks = [sc for sc in scored_chunks if sc[0] > 0.0]
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return scored_chunks[:top_k]

    def sparse_search(
        self,
        query: str,
        *,
        top_k: int = 24,
        chunk_types: list[str] | None = None,
        content_types: list[str] | None = None,
        cohort: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return filtered BM25 documents using the shared retriever interface."""
        if top_k <= 0:
            return []

        expected_chunk_types = {
            str(value).strip() for value in (chunk_types or []) if str(value).strip()
        }
        expected_content_types = {
            str(value).strip() for value in (content_types or []) if str(value).strip()
        }
        expected_cohort = str(cohort or "").strip()

        results: list[dict[str, Any]] = []
        for score, chunk in self.search_bm25(query, top_k=len(self.chunks)):
            metadata = dict(chunk.get("metadata") or {})
            actual_chunk_type = str(
                chunk.get("chunk_type") or metadata.get("chunk_type") or ""
            ).strip()
            actual_content_type = str(
                chunk.get("content_type") or metadata.get("content_type") or ""
            ).strip()
            actual_cohort = str(
                chunk.get("cohort") or metadata.get("cohort") or ""
            ).strip()

            if expected_chunk_types and actual_chunk_type not in expected_chunk_types:
                continue
            if (
                expected_content_types
                and actual_content_type not in expected_content_types
            ):
                continue
            if expected_cohort and actual_cohort != expected_cohort:
                continue

            document = dict(chunk)
            document["metadata"] = metadata
            document["bm25_score"] = score
            results.append(document)
            if len(results) >= top_k:
                break
        return results


# Global instance for legacy pipeline compat
_global_bm25_retriever = None

def get_bm25_retriever():
    global _global_bm25_retriever
    if _global_bm25_retriever is None:
        _global_bm25_retriever = BM25Retriever()
    return _global_bm25_retriever
