from src.retrieval.core.office_lookup import find_grounded_catalog_hint


def test_catalog_hint_fails_closed_when_span_maps_to_multiple_tools() -> None:
    office = [{"unit_name": "Trạm A", "aliases": ["hỗ trợ thẻ"]}]
    services = [
        {
            "unit_name": "Trạm A",
            "service": "hỗ trợ thẻ",
            "aliases": [],
        }
    ]

    assert (
        find_grounded_catalog_hint(
            "đơn vị hỗ trợ thẻ",
            office,
            services,
        )
        is None
    )


def test_catalog_hint_keeps_unambiguous_exact_alias() -> None:
    office = [{"unit_name": "Phòng Đào tạo", "aliases": ["PĐT"]}]

    assert find_grounded_catalog_hint("email PĐT", office, []) == {
        "candidate_entity_type": "office",
        "matched_span": "PĐT",
        "catalog_record_id": "phong dao tao",
        "match_type": "exact_catalog_span",
    }
