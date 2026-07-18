from __future__ import annotations

from src.retrieval.core.hybrid_pipeline import (
    select_graph_related_parent_candidates,
)


def test_graph_supplement_skips_primary_dedupes_and_caps() -> None:
    primary = ["P1", "P2", "P3", "P4", "P5"]
    expanded = [
        {"id": "P1", "depth": 0, "seed_source": "P1"},
        {"id": "R2", "depth": 2, "seed_source": "P1"},
        {"id": "R1", "depth": 1, "seed_source": "P3"},
        {"id": "R1", "depth": 2, "seed_source": "P1"},
        {"id": "R3", "depth": 1, "seed_source": "P1"},
        {"id": "R4", "depth": 1, "seed_source": "P2"},
        {"id": "R5", "depth": 2, "seed_source": "P1"},
        {"id": "R6", "depth": 2, "seed_source": "P1"},
    ]

    selected = select_graph_related_parent_candidates(
        primary,
        expanded,
        max_related_total=5,
    )

    assert [item["parent_id"] for item in selected] == [
        "R3",
        "R4",
        "R1",
        "R2",
        "R5",
    ]
    assert all(item["parent_id"] not in primary for item in selected)


def test_graph_supplement_prefers_lower_depth_then_primary_rank() -> None:
    selected = select_graph_related_parent_candidates(
        ["P1", "P2"],
        [
            {"id": "late-depth-one", "depth": 1, "seed_source": "P2"},
            {"id": "early-depth-two", "depth": 2, "seed_source": "P1"},
            {"id": "early-depth-one", "depth": 1, "seed_source": "P1"},
        ],
        max_related_total=3,
    )

    assert [item["parent_id"] for item in selected] == [
        "early-depth-one",
        "late-depth-one",
        "early-depth-two",
    ]
