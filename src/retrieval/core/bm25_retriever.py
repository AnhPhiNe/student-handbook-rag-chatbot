import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from src.common.cohort import is_cohort_applicable
from src.retrieval.core.acronym_registry import (
    DEFAULT_PROGRAM_DIRECTORY_PATH,
    DEFAULT_VOCABULARY_PATH,
    AcronymRegistry,
    build_acronym_registry,
    canonical_acronym,
)

try:
    import underthesea
except ModuleNotFoundError:
    underthesea = None

logger = logging.getLogger(__name__)


def _fold_text(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    value = "".join(
        character
        for character in unicodedata.normalize("NFD", value)
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def title_query_match_priority(query: str, chunk: dict[str, Any]) -> int:
    """Return a conservative lexical priority for an explicit section title."""

    metadata = chunk.get("metadata") or {}
    title = _fold_text(
        str(metadata.get("title") or metadata.get("source_section") or "")
    )
    query_text = _fold_text(query)
    # Single-token headings are too broad to use as lexical anchors.
    if len(title.split()) < 2:
        return 0
    return int(
        bool(title and re.search(rf"(?:^| )({re.escape(title)})(?: |$)", query_text))
    )


class BM25Retriever:
    """Index and score the local lexical corpus with BM25."""

    def __init__(
        self,
        *,
        vocabulary_path: str | Path | None = None,
        program_directory_path: str | Path | None = None,
    ):
        self.bm25_index = None
        self.chunks = []
        self.acronym_registry = build_acronym_registry(
            vocabulary_path=vocabulary_path or DEFAULT_VOCABULARY_PATH,
            program_directory_path=(
                program_directory_path or DEFAULT_PROGRAM_DIRECTORY_PATH
            ),
        )
        self.acronym_whitelist = set(self.acronym_registry.literal_acronyms)
        self._log_acronym_registry(self.acronym_registry)

        # Capture identifiers and document codes as indivisible tokens.
        self.literal_regex = re.compile(
            r"\b\d{4,}\b|\d+/[A-ZĐ\-]+|IELTS|TOEFL|B1|B2|Goethe-Zertifikat",
            re.IGNORECASE,
        )

    @staticmethod
    def _log_acronym_registry(registry: AcronymRegistry) -> None:
        logger.info(
            "Loaded %d BM25 acronym literals "
            "(%d explicit replacements, %d safe generated replacements, "
            "%d ambiguous generated).",
            len(registry.literal_acronyms),
            len(registry.explicit_replacements),
            len(registry.generated_replacements),
            len(registry.ambiguous_generated),
        )

    def _is_known_acronym_token(self, token: str) -> bool:
        canonical = canonical_acronym(token)
        if canonical in self.acronym_registry.explicit_literals:
            return True
        if canonical in self.acronym_registry.generated_replacements:
            return True
        return (
            canonical in self.acronym_registry.generated_literals
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
            canonical = canonical_acronym(word)
            if self._is_known_acronym_token(word):
                literals.append(canonical.lower())
                replacement = self.acronym_registry.replacement_for(word)
                if replacement:
                    remaining_words.extend(replacement.split())
            else:
                remaining_words.append(word)
        text_for_segmentation = " ".join(remaining_words)

        tokens.extend(literals)

        # Layer 2: Word Segmentation (underthesea)
        try:
            if underthesea is not None:
                segmented_words = underthesea.word_tokenize(
                    text_for_segmentation.lower()
                )
                tokens.extend([w.replace(" ", "_") for w in segmented_words])
            else:
                tokens.extend(text_for_segmentation.lower().split())

            # Bigrams of adjacent segmented syllables (fallback for bad segmentation)
            syllables = text_for_segmentation.lower().split()
            bigrams = [
                f"{syllables[i]}_{syllables[i + 1]}" for i in range(len(syllables) - 1)
            ]
            tokens.extend(bigrams)

        except Exception as e:
            logger.warning(f"Underthesea tokenization failed: {e}")
            # Absolute fallback
            tokens.extend(text_for_segmentation.lower().split())

        return [t for t in tokens if t.strip()]

    def build_bm25_index(self, chunks: list[dict[str, Any]]):
        """Build a BM25 retriever from normalized chunk records."""

        self.chunks = chunks
        corpus_tokens = [
            self._tokenize(self._index_text(chunk)) for chunk in self.chunks
        ]
        self.bm25_index = BM25Okapi(corpus_tokens)
        logger.info(f"BM25 index built with {len(self.chunks)} chunks.")

    @staticmethod
    def _index_text(chunk: dict[str, Any]) -> str:
        """Build a field-aware lexical document without changing result payloads."""

        metadata = chunk.get("metadata") or {}
        title = str(
            metadata.get("title") or metadata.get("source_section") or ""
        ).strip()
        article = str(metadata.get("article") or "").strip()
        document_title = str(metadata.get("document_title") or "").strip()
        content = str(chunk.get("content") or "")
        # Repeating the short section title gives an explicit article-topic match
        # more weight than incidental terms inside a long clause. Document title
        # disambiguates repeated headings across different regulations.
        fields = [title, title, title, article, document_title, content]
        return "\n".join(field for field in fields if field)

    def search_bm25(
        self, query: str, top_k: int = 24
    ) -> list[tuple[float, dict[str, Any]]]:
        """Return the highest-scoring lexical matches for a query."""

        if not self.bm25_index or not self.chunks:
            return []

        query_tokens = self._tokenize(query)
        scores = self.bm25_index.get_scores(query_tokens)

        # Pair scores with chunks
        scored_chunks = [
            (float(score), dict(chunk)) for score, chunk in zip(scores, self.chunks)
        ]

        # Filter zero scores and sort
        scored_chunks = [
            item
            for item in scored_chunks
            if item[0] > 0.0 or title_query_match_priority(query, item[1])
        ]
        scored_chunks.sort(
            key=lambda item: (
                title_query_match_priority(query, item[1]),
                item[0],
            ),
            reverse=True,
        )
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

            if expected_chunk_types and actual_chunk_type not in expected_chunk_types:
                continue
            if (
                expected_content_types
                and actual_content_type not in expected_content_types
            ):
                continue
            if expected_cohort and not is_cohort_applicable(chunk, expected_cohort):
                continue

            document = dict(chunk)
            document["metadata"] = metadata
            document["bm25_score"] = score
            results.append(document)
            if len(results) >= top_k:
                break
        return results
