from __future__ import annotations

from src.common.cohort import (
    cohort_registry_digest,
    cohort_registry_version,
    extract_cohort_mentions,
    normalize_cohort,
)


def test_cohort_registry_is_versioned_and_digestible() -> None:
    assert cohort_registry_version() == 1
    assert len(cohort_registry_digest()) == 64


def test_registry_extraction_preserves_literal_span_and_source_order() -> None:
    mentions = extract_cohort_mentions("K 50 được hỏi trước, sau đó mới đến K51.")

    assert [(item.cohort, item.span) for item in mentions] == [
        ("K50", "K 50"),
        ("K51", "K51"),
    ]


def test_grouped_cohort_alias_is_one_non_overlapping_mention() -> None:
    mentions = extract_cohort_mentions("Quy định dành cho K48–K49.")

    assert [(item.cohort, item.span) for item in mentions] == [
        ("K48-K49", "K48–K49")
    ]


def test_unknown_cohort_fails_closed() -> None:
    assert normalize_cohort("K99") is None
