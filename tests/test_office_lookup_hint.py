import src.retrieval.core.structured_routing as structured_routing_module
from src.retrieval.core.office_lookup import find_grounded_catalog_hint
from src.retrieval.core.structured_routing import find_grounded_registry_alias_hint


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

    hint = find_grounded_catalog_hint("email PĐT", office, [])

    assert hint is not None
    assert hint["candidate_entity_type"] == "office"
    assert hint["matched_span"] == "PĐT"
    assert hint["canonical_entity"] == "Phòng Đào tạo"
    assert hint["catalog_record_id"] == "phong dao tao"
    assert hint["match_type"] == "exact_catalog_span"
    assert hint["registry_name"] == "planner_registry"
    assert len(hint["registry_digest"]) == 64


def test_catalog_hint_resolves_registered_acronym_without_choosing_tool() -> None:
    hint = find_grounded_catalog_hint("don vi lo bhyt", [], [])

    assert hint is not None
    assert hint["matched_span"] == "bhyt"
    assert hint["canonical_entity"] == "bảo hiểm y tế"
    assert hint["candidate_entity_type"] == "student_service"
    assert hint["match_type"] == "exact_registry_alias"
    assert "tool_name" not in hint


def test_unknown_text_does_not_create_alias_hint() -> None:
    assert find_grounded_catalog_hint("đơn vị lo xyz-không-đăng-ký", [], []) is None


def test_registry_alias_hint_reports_ambiguous_provenance(monkeypatch) -> None:
    monkeypatch.setattr(
        structured_routing_module,
        "_slot_alias_index",
        lambda: {"student_service": {"dv": frozenset({"dịch vụ A", "dịch vụ B"})}},
    )
    registry = {
        "version": 1,
        "tools": {
            "directory": {
                "planner_capabilities": {
                    "input_entity_types": ["student_service"]
                },
                "slot_schema": {
                    "service": {"alias_entity_types": ["student_service"]}
                },
            }
        },
    }

    hint = find_grounded_registry_alias_hint("đơn vị DV", registry=registry)

    assert hint is not None
    assert hint["match_type"] == "ambiguous_registry_alias"
    assert hint["candidate_entities"] == ["dịch vụ A", "dịch vụ B"]
    assert hint["candidate_entity_types"] == ["student_service"]
    assert "canonical_entity" not in hint
    assert "tool_name" not in hint


def test_alias_hint_requires_registry_capability(monkeypatch) -> None:
    monkeypatch.setattr(
        structured_routing_module,
        "_slot_alias_index",
        lambda: {"student_service": {"dv": frozenset({"dịch vụ A"})}},
    )

    assert (
        find_grounded_registry_alias_hint(
            "đơn vị DV", registry={"version": 1, "tools": {}}
        )
        is None
    )


def test_alias_hint_ignores_identity_only_purpose_phrase(monkeypatch) -> None:
    monkeypatch.setattr(
        structured_routing_module,
        "_slot_alias_index",
        lambda: {"service": {"xac nhan": frozenset({"xác nhận"})}},
    )
    registry = {
        "version": 1,
        "tools": {
            "directory": {
                "planner_capabilities": {
                    "input_entity_types": ["student_service"]
                },
                "slot_schema": {
                    "service": {"alias_entity_types": ["service"]}
                },
            }
        },
    }

    assert (
        find_grounded_registry_alias_hint(
            "Tôi muốn xác nhận với cố vấn", registry=registry
        )
        is None
    )


def test_alias_hint_ignores_short_lexical_collision(monkeypatch) -> None:
    monkeypatch.setattr(
        structured_routing_module,
        "_slot_alias_index",
        lambda: {"faculty": {"ly": frozenset({"Khoa Vật lý"})}},
    )
    registry = {
        "version": 1,
        "tools": {
            "faculty": {
                "planner_capabilities": {"input_entity_types": ["faculty"]},
                "slot_schema": {
                    "faculty": {"alias_entity_types": ["faculty"]}
                },
            }
        },
    }

    assert (
        find_grounded_registry_alias_hint(
            "Cần thông tin trước thời hạn xử lý", registry=registry
        )
        is None
    )
