from src.retrieval.core.citation_builder import build_citation_from_lookup
from src.retrieval.core.source_contract import (
    enrich_source_records_from_registry,
    normalize_source_ref,
)


def _table_source(
    *,
    document_id: str,
    cohort: str,
    table_id: str,
    source_pages: list[int],
) -> dict:
    return {
        "source_kind": "table",
        "document_id": document_id,
        "cohort": cohort,
        "table_id": table_id,
        "source_pages": source_pages,
    }


def test_rejects_page_only_source_without_document_identity():
    assert normalize_source_ref(
        {
            "source_kind": "table",
            "document_id": "",
            "source_pages": [23],
        }
    ) is None

    citations = build_citation_from_lookup(
        {
            "lookup_type": "scoring",
            "source_pages": [23],
            "result": {"label": "Giỏi"},
        }
    )

    assert citations == []


def test_invalid_canonical_sources_do_not_fallback_to_legacy_metadata():
    citations = build_citation_from_lookup(
        {
            "lookup_type": "scoring",
            "document_id": "handbook-k51",
            "source_parent_id": "K51_Dieu11",
            "source_pages": [23],
            "source_records": [{"source_kind": "table", "source_pages": [23]}],
            "result": {"label": "Giỏi"},
        }
    )

    assert citations == []


def test_registry_binding_uses_page_overlap_only_to_disambiguate_same_subtype():
    records = [
        _table_source(
            document_id="handbook-k51",
            cohort="K51",
            table_id="grade_scale",
            source_pages=[12],
        )
    ]
    registry = [
        {
            "table_id": "k51-foundation-grade-scale",
            "table_type": "scoring",
            "table_subtype": "grade_scale",
            "document_id": "handbook-k51",
            "cohort": "K51",
            "source_parent_id": "K51_Dieu10_Foundation",
            "source_pages": [10, 11, 12],
        },
        {
            "table_id": "k51-remaining-grade-scale",
            "table_type": "scoring",
            "table_subtype": "grade_scale",
            "document_id": "handbook-k51",
            "cohort": "K51",
            "source_parent_id": "K51_Dieu10_Remaining",
            "source_pages": [18, 19, 20],
        },
    ]

    enriched = enrich_source_records_from_registry(records, registry)
    citations = build_citation_from_lookup(
        {
            "lookup_type": "scoring",
            "table_name": "Thang diem",
            "result": {"letter_grade": "B"},
            "source_records": enriched,
        }
    )

    assert len(citations) == 1
    assert citations[0]["table_id"] == "k51-foundation-grade-scale"
    assert citations[0]["parent_section_id"] == "K51_Dieu10_Foundation"
    assert citations[0]["source_pages"] == [10, 11, 12]


def test_registry_subtype_fallback_accepts_unique_table_with_page_subset():
    records = [
        _table_source(
            document_id="handbook-k49",
            cohort="K48-K49",
            table_id="academic_classification",
            source_pages=[23],
        )
    ]
    registry = [
        {
            "table_id": "K48_49_Dieu11_academic_classification",
            "table_type": "scoring",
            "table_subtype": "academic_classification",
            "document_id": "handbook-k49",
            "cohort": "K48-K49",
            "source_parent_id": "K48-K49_Dieu11",
            "source_pages": [21, 22, 23],
        },
        {
            "table_id": "K48_49_Dieu11_letter_to_grade4",
            "table_type": "scoring",
            "table_subtype": "letter_to_grade4",
            "document_id": "handbook-k49",
            "cohort": "K48-K49",
            "source_parent_id": "K48-K49_Dieu11",
            "source_pages": [21, 22, 23],
        },
    ]

    enriched = enrich_source_records_from_registry(records, registry)

    assert enriched[0]["table_id"] == "K48_49_Dieu11_academic_classification"
    assert enriched[0]["parent_section_id"] == "K48-K49_Dieu11"
    assert enriched[0]["source_pages"] == [21, 22, 23]


def test_registry_binding_keeps_cohort_sources_isolated():
    records = [
        _table_source(
            document_id="handbook-k50",
            cohort="K50",
            table_id="academic_classification",
            source_pages=[21],
        ),
        _table_source(
            document_id="handbook-k51",
            cohort="K51",
            table_id="academic_classification",
            source_pages=[21],
        ),
    ]
    registry = [
        {
            "table_id": "K50_Dieu11_academic_classification",
            "table_subtype": "academic_classification",
            "document_id": "handbook-k50",
            "cohort": "K50",
            "source_parent_id": "K50_Dieu11",
            "source_pages": [19, 20, 21],
        },
        {
            "table_id": "K51_Dieu11_academic_classification",
            "table_subtype": "academic_classification",
            "document_id": "handbook-k51",
            "cohort": "K51",
            "source_parent_id": "K51_Dieu11",
            "source_pages": [19, 20, 21],
        },
    ]

    enriched = enrich_source_records_from_registry(records, registry)

    assert [record["document_id"] for record in enriched] == [
        "handbook-k50",
        "handbook-k51",
    ]
    assert [record["parent_section_id"] for record in enriched] == [
        "K50_Dieu11",
        "K51_Dieu11",
    ]
