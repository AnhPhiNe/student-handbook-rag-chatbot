from __future__ import annotations

import os
from collections.abc import Mapping


def require_qdrant_collection_name(
    environ: Mapping[str, str] | None = None,
) -> str:
    """Return the explicitly configured Qdrant collection name.

    ``STUDENT_RAG_HYBRID_COLLECTION`` remains a supported compatibility alias,
    but there is deliberately no versioned fallback. A missing collection name
    must fail before retrieval can silently connect to stale data.
    """

    values = environ if environ is not None else os.environ
    name = (
        values.get("STUDENT_RAG_HYBRID_COLLECTION")
        or values.get("QDRANT_COLLECTION_NAME")
        or ""
    ).strip()
    if not name:
        raise RuntimeError(
            "QDRANT_COLLECTION_NAME (or STUDENT_RAG_HYBRID_COLLECTION) "
            "must be configured explicitly."
        )
    return name


def require_mongo_parent_collection_name(
    environ: Mapping[str, str] | None = None,
) -> str:
    """Return the explicitly configured MongoDB parent collection name."""

    values = environ if environ is not None else os.environ
    name = (values.get("MONGODB_PARENT_COLLECTION") or "").strip()
    if not name:
        raise RuntimeError("MONGODB_PARENT_COLLECTION must be configured explicitly.")
    return name
