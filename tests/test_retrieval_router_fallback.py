from __future__ import annotations

from src.retrieval.core.retrieval_pipeline import _should_force_regulation_rag


def test_handbook_scoped_clarify_can_fallback_to_regulation_rag() -> None:
    assert _should_force_regulation_rag(
        "Em thuoc K50, trong so tay hoc bong quy dinh chinh xac la gi?",
        {
            "route": "clarify",
            "execution_mode": "regulation",
        },
        cohort="K50",
    )


def test_unresolved_reference_still_needs_clarification() -> None:
    assert not _should_force_regulation_rag(
        "Em thuoc K50, truong hop do trong so tay xu ly sao?",
        {
            "route": "clarify",
            "execution_mode": "regulation",
        },
        cohort="K50",
    )


def test_clear_out_of_domain_does_not_fallback_to_regulation_rag() -> None:
    assert not _should_force_regulation_rag(
        "Hom nay thoi tiet o TP HCM the nao?",
        {
            "route": "out_of_domain",
            "execution_mode": "regulation",
        },
        cohort=None,
    )
