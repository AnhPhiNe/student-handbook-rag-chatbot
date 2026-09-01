from __future__ import annotations

import os


DEFAULT_RETRIEVAL_MODE = "vector_primary_graph_supplement"
SUPPORTED_RETRIEVAL_MODES = {
    "full",
    "no_graph",
    "vector_only",
    DEFAULT_RETRIEVAL_MODE,
}
RETRIEVAL_ABLATION_MODES = SUPPORTED_RETRIEVAL_MODES - {DEFAULT_RETRIEVAL_MODE}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_retrieval_mode() -> str:
    """Resolve the runtime mode and keep evaluation ablations opt-in.

    ``STUDENT_RAG_EVAL_RETRIEVAL_MODE`` remains a compatibility alias for the
    evaluation harness. Production should use ``STUDENT_RAG_RETRIEVAL_MODE``.
    Any non-production mode additionally requires the explicit ablation guard.
    """

    mode = (
        os.environ.get("STUDENT_RAG_RETRIEVAL_MODE")
        or os.environ.get("STUDENT_RAG_EVAL_RETRIEVAL_MODE")
        or DEFAULT_RETRIEVAL_MODE
    ).strip().lower()
    if mode not in SUPPORTED_RETRIEVAL_MODES:
        raise ValueError(f"Unsupported retrieval mode={mode!r}")
    if mode in RETRIEVAL_ABLATION_MODES and not _env_bool(
        "STUDENT_RAG_ALLOW_RETRIEVAL_ABLATION"
    ):
        raise ValueError(
            f"Retrieval mode {mode!r} is evaluation-only; set "
            "STUDENT_RAG_ALLOW_RETRIEVAL_ABLATION=1 explicitly."
        )
    return mode
