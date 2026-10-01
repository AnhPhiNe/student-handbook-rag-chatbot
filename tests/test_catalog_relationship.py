"""Directory joins distinguish service rows from the unit providing them."""

import json
from pathlib import Path

import pytest

from src.retrieval.core.catalog_relationship import resolve_relationship
from src.retrieval.core.office_lookup import directory_result
from src.retrieval.core.structured_dispatcher import (
    _RELATIONSHIPS,
    resolve_structured_task,
)


@pytest.fixture(scope="module")
def directories():
    base = Path(__file__).resolve().parents[1] / "data/processed/directories"
    return {
        "office": json.loads((base / "student_office_profiles.json").read_text(encoding="utf-8")),
        "student_service": json.loads((base / "student_service_directory.json").read_text(encoding="utf-8")),
    }


@pytest.mark.parametrize("cohort", ["K48-K49", "K50", "K51"])
@pytest.mark.parametrize("unit,email", [
    ("Thư viện", "thuvien@hcmue.edu.vn"),
    ("Phòng Hợp tác Quốc tế", "phonghtqt@hcmue.edu.vn"),
])
def test_service_rows_for_one_unit_keep_requested_contacts(directories, cohort, unit, email):
    task = {
        "lookup_type": "student_service",
        "intent": "direct_value",
        "slots": {"requested_field": ["phone", "email"]},
        "slot_spans": {"service": unit},
    }
    resolution = resolve_structured_task(
        task, query=f"Cho em thông tin liên hệ của {unit}", cohort=cohort,
        formula_rules=[], office_directory=directories["office"],
        student_service_directory=directories["student_service"],
        student_faculty_profiles=[], structured_tables_registry=[],
        program_directory=[], directory_selector=None,
    )
    assert resolution.result_kind == "structured"
    assert not resolution.result.get("needs_clarification")
    rows = resolution.result["result"]
    assert len(rows) > 1
    assert {row["unit_name"] for row in rows} == {unit}
    assert all(email in row["emails"] and row["phones"] for row in rows)
    assert all(row["cohort"] == cohort for row in rows)


def _service(unit, service, cohort="K51"):
    return {
        "unit_name": unit, "service": service, "cohort": cohort,
        "content_type": "student_service_directory",
    }


def _join(services, offices):
    source = directory_result("liên hệ", services, cohort="K51")
    result = resolve_relationship(
        source, source_lookup="student_service", requested_field=["phone", "email"],
        cohort="K51", relationships=_RELATIONSHIPS,
        catalogs={"office": offices, "student_service": services},
    )
    return source, result


def test_service_rows_for_one_unit_can_join_missing_contacts():
    services = [_service("Phòng A", "Dịch vụ một"), _service("Phòng A", "Dịch vụ hai")]
    office = {
        "unit_name": "Phòng A", "cohort": "K51",
        "emails": ["office@example.test"], "phones": ["0123456789"],
        "content_type": "student_office_profile",
    }
    source, result = _join(services, [office])
    assert result["relationship_status"] == "resolved"
    assert result["result"]["targets"][0]["emails"] == ["office@example.test"]
    assert result["result"]["targets"][0]["phones"] == ["0123456789"]
    assert result["sub_lookups"][0] == source
    assert len(result["sub_lookups"][0]["result"]) == 2


@pytest.mark.parametrize("services", [
    [_service("Phòng A", "Một"), _service("Phòng B", "Hai")],
    [_service("Phòng A", "Một"), _service("Phòng A", "Hai", cohort="K50")],
    [_service("", "Một"), _service("", "Hai")],
])
def test_multiple_services_need_one_known_unit_and_cohort(services):
    _, result = _join(services, [])
    assert result["needs_clarification"] is True


@pytest.mark.parametrize("offices,expected", [
    ([{"unit_name": "Phòng A", "cohort": "K50"}], "target_unavailable"),
    ([{"unit_name": "Phòng A", "cohort": "K51", "emails": ["one@example.test"]},
      {"unit_name": "Phòng A", "cohort": "K51", "emails": ["two@example.test"]}], "clarification"),
])
def test_same_unit_services_still_validate_target_catalog(offices, expected):
    services = [_service("Phòng A", "Một"), _service("Phòng A", "Hai")]
    _, result = _join(services, offices)
    if expected == "clarification":
        assert result["needs_clarification"] is True
    else:
        assert result["relationship_status"] == expected
