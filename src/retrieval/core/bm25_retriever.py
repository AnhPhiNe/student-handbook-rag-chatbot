import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from src.common.cohort import VALID_COHORTS, is_cohort_applicable, normalize_cohort
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
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BM25_ARTIFACT_PATH = (
    _REPOSITORY_ROOT / "data" / "processed" / "retrieval" / "bm25_index.json"
)
SUPPORTED_BM25_ARTIFACT_VERSIONS = {
    "bm25-artifact-v1",
    "bm25-artifact-v2",
    "bm25-artifact-v2-title-index",
}
SUPPORTED_BM25_ARTIFACT_VERSION = "bm25-artifact-v1"
SUPPORTED_BM25_TOKENIZER_VERSION = "hcmue-bm25-tokenizer-v2"


def bm25_artifact_checksum(chunks: list[dict[str, Any]]) -> str:
    """Return the v1 artifact checksum for the serialized sparse corpus.

    The artifact is source data rather than a pickled ``BM25Okapi`` instance.
    Keeping the checksum over its ordered JSON chunk payload makes both its
    corpus and its source metadata part of the release contract.
    """

    serialized = json.dumps(chunks, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class BM25ArtifactError(RuntimeError):
    """Raised when the versioned sparse-retrieval artifact is not safe to serve."""


class BM25Retriever:
    def __init__(
        self,
        *,
        vocabulary_path: str | Path | None = None,
        program_directory_path: str | Path | None = None,
    ):
        self.bm25_index = None
        self.chunks: list[dict[str, Any]] = []
        self.artifact_metadata: dict[str, Any] | None = None
        self.readiness_error: str | None = None
        self.acronym_registry = build_acronym_registry(
            vocabulary_path=vocabulary_path or DEFAULT_VOCABULARY_PATH,
            program_directory_path=(
                program_directory_path or DEFAULT_PROGRAM_DIRECTORY_PATH
            ),
        )
        self.acronym_whitelist = set(self.acronym_registry.literal_acronyms)
        self._log_acronym_registry(self.acronym_registry)

        # Regex for capturing codes and numbers (e.g., 7480201, 23/QĐ-BGDĐT)
        self.literal_regex = re.compile(
            r'\b\d{4,}\b|\d+/[A-ZĐ\-]+|IELTS|TOEFL|B1|B2|Goethe-Zertifikat',
            re.IGNORECASE
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

    def build_bm25_index(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks = [dict(chunk) for chunk in chunks]
        corpus_tokens = [
            self._tokenize(str(chunk.get("content") or "")) for chunk in self.chunks
        ]
        self.bm25_index = BM25Okapi(corpus_tokens)
        self.readiness_error = None
        logger.info(f"BM25 index built with {len(self.chunks)} chunks.")

    def _mark_unready(self, reason: str) -> None:
        """Clear every serveable state after an artifact validation failure."""

        self.bm25_index = None
        self.chunks = []
        self.artifact_metadata = None
        self.readiness_error = reason

    @staticmethod
    def _artifact_validation_error(reason: str) -> BM25ArtifactError:
        return BM25ArtifactError(reason)

    @staticmethod
    def _validate_chunk_schema(chunk: dict[str, Any], index: int) -> None:
        metadata = chunk.get("metadata")
        chunk_id = str(chunk.get("chunk_id") or chunk.get("_id") or "").strip()
        content = str(chunk.get("content") or "").strip()
        if not chunk_id or not isinstance(metadata, dict):
            raise BM25ArtifactError(
                f"BM25 artifact chunk {index} lacks chunk_id or metadata"
            )
        if not content:
            raise BM25ArtifactError(f"BM25 artifact chunk {index} lacks content")
        if str(metadata.get("content_type") or "").strip() != "regulation_text":
            raise BM25ArtifactError(
                f"BM25 artifact chunk {index} is not regulation_text"
            )
        cohort = normalize_cohort(str(metadata.get("cohort") or ""))
        if cohort not in VALID_COHORTS:
            raise BM25ArtifactError(
                f"BM25 artifact chunk {index} has an unsupported cohort"
            )
        for field in ("parent_section_id", "document_id"):
            if not str(metadata.get(field) or "").strip():
                raise BM25ArtifactError(
                    f"BM25 artifact chunk {index} lacks metadata.{field}"
                )

    def load_artifact(
        self,
        path: str | Path = DEFAULT_BM25_ARTIFACT_PATH,
        *,
        expected_corpus_version: str,
    ) -> dict[str, Any]:
        """Load the pinned sparse corpus and reject version-mismatched inputs.

        The hybrid retriever must not silently build a different corpus in a
        background thread.  The artifact is a release input: its collection
        version, declared chunk count, tokenizer metadata, and chunk structure
        are validated before it becomes available to traffic.
        """

        configured_path = path if path != DEFAULT_BM25_ARTIFACT_PATH else (
            os.getenv("STUDENT_RAG_BM25_ARTIFACT_PATH") or DEFAULT_BM25_ARTIFACT_PATH
        )
        artifact_path = Path(configured_path)
        self._mark_unready("bm25_artifact_loading")
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._mark_unready(f"bm25_artifact_unreadable:{type(exc).__name__}")
            raise BM25ArtifactError(
                f"Cannot load BM25 artifact {artifact_path}: {type(exc).__name__}"
            ) from exc
        try:
            if not isinstance(payload, dict):
                raise self._artifact_validation_error("BM25 artifact root must be an object")
            chunks = payload.get("chunks")
            metadata = payload.get("metadata")
            if not isinstance(chunks, list) or not chunks:
                raise self._artifact_validation_error(
                    "BM25 artifact must contain non-empty chunks"
                )
            if not isinstance(metadata, dict):
                raise self._artifact_validation_error("BM25 artifact metadata is required")

            required_metadata = {
                "artifact_version",
                "checksum",
                "corpus_version",
                "tokenizer_version",
                "total_chunks",
            }
            missing = sorted(
                key
                for key in required_metadata
                if not str(metadata.get(key) or "").strip()
            )
            if missing:
                raise self._artifact_validation_error(
                    f"BM25 artifact missing metadata: {missing}"
                )
            if metadata["artifact_version"] not in SUPPORTED_BM25_ARTIFACT_VERSIONS:
                raise self._artifact_validation_error(
                    "Unsupported BM25 artifact version: "
                    f"{metadata['artifact_version']!r}"
                )
            if metadata["tokenizer_version"] != SUPPORTED_BM25_TOKENIZER_VERSION:
                raise self._artifact_validation_error(
                    "Unsupported BM25 tokenizer version: "
                    f"{metadata['tokenizer_version']!r}"
                )
            corpus_version = str(metadata["corpus_version"]).strip()
            if corpus_version != str(expected_corpus_version).strip():
                raise self._artifact_validation_error(
                    "BM25 corpus version does not match the active collection: "
                    f"artifact={corpus_version!r}, collection={expected_corpus_version!r}"
                )
            try:
                declared_total = int(metadata["total_chunks"])
            except (TypeError, ValueError) as exc:
                raise self._artifact_validation_error(
                    "BM25 artifact total_chunks must be an integer"
                ) from exc
            if declared_total != len(chunks):
                raise self._artifact_validation_error(
                    "BM25 artifact chunk count mismatch: "
                    f"declared={declared_total}, actual={len(chunks)}"
                )
            actual_checksum = bm25_artifact_checksum(chunks)
            expected_checksum = str(metadata["checksum"]).strip().lower()
            if actual_checksum != expected_checksum:
                raise self._artifact_validation_error(
                    "BM25 artifact checksum mismatch: "
                    f"expected={expected_checksum[:12]}, actual={actual_checksum[:12]}"
                )

            normalized_chunks: list[dict[str, Any]] = []
            for index, chunk in enumerate(chunks):
                if not isinstance(chunk, dict):
                    raise self._artifact_validation_error(
                        f"BM25 artifact chunk {index} is not an object"
                    )
                self._validate_chunk_schema(chunk, index)
                normalized_chunks.append(dict(chunk))

            self.build_bm25_index(normalized_chunks)
        except BM25ArtifactError as exc:
            self._mark_unready(f"bm25_artifact_invalid:{type(exc).__name__}")
            raise
        except Exception as exc:
            self._mark_unready(f"bm25_artifact_build_failed:{type(exc).__name__}")
            raise BM25ArtifactError(
                f"Cannot build BM25 artifact {artifact_path}: {type(exc).__name__}"
            ) from exc

        self.artifact_metadata = dict(metadata)
        logger.info(
            "BM25 artifact ready: corpus=%s chunks=%d checksum=%s",
            corpus_version,
            len(normalized_chunks),
            str(metadata["checksum"])[:12],
        )
        return dict(self.artifact_metadata)

    def is_ready(self) -> bool:
        return self.bm25_index is not None and bool(self.chunks)

    def readiness(self) -> dict[str, Any]:
        return {
            "ready": self.is_ready(),
            "chunk_count": len(self.chunks),
            "artifact": dict(self.artifact_metadata or {}),
            "error": self.readiness_error,
        }

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


# Global instance for legacy pipeline compat
_global_bm25_retriever = None

def get_bm25_retriever():
    global _global_bm25_retriever
    if _global_bm25_retriever is None:
        _global_bm25_retriever = BM25Retriever()
    return _global_bm25_retriever
