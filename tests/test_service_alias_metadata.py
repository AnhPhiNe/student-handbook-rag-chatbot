"""The directory catalogs carry only handbook services and curated unit names."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.retrieval.core.office_lookup import normalize_text, office_lookup
from src.retrieval.core.query_plan import normalize_query_plan
from tests.scripted_selector import scripted_selector


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY_DIR = ROOT / "data" / "processed" / "directories"


def _load_json(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, list)
    return value


@pytest.fixture(scope="module")
def services() -> list[dict[str, Any]]:
    return _load_json(DIRECTORY_DIR / "student_service_directory.json")


@pytest.fixture(scope="module")
def production_directory(services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror the student-service pool the dispatcher selects from."""
    return services


def test_services_are_handbook_text_without_guessed_aliases(services: list[dict[str, Any]]) -> None:
    # Keyword aliases and services the handbook does not list were removed on
    # 2026-09-28; the selector reads the service text itself.
    assert all(record["aliases"] == [] for record in services)
    assert not [record["service_id"] for record in services if "catalog_service" in record["service_id"]]
    assert not [record["service"] for record in services if "wifi" in normalize_text(record["service"])]


@pytest.mark.parametrize("catalog", ["student_office_profiles.json", "student_faculty_profiles.json"])
def test_unit_aliases_come_only_from_the_curated_list(catalog: str) -> None:
    curated = yaml.safe_load((ROOT / "configs/office_aliases.yaml").read_text(encoding="utf-8"))["unit_aliases"]
    allowed = {normalize_text(alias) for aliases in curated.values() for alias in aliases}
    for record in _load_json(DIRECTORY_DIR / catalog):
        # A campus unit also keeps its plain faculty name and campus forms.
        names = {normalize_text(record.get("faculty_name") or record["unit_name"])}
        extra = [alias for alias in record.get("aliases") or []
                 if normalize_text(alias) not in allowed | names
                 and not (record.get("campus") and normalize_text(record["faculty_name"]) in normalize_text(alias))]
        assert not extra, (record["unit_name"], extra)


def test_generic_service_phrase_stays_ambiguous_when_candidate_is_generic(
    production_directory: list[dict[str, Any]],
) -> None:
    # A generic phrase matches no single name exactly, so the selector
    # decides; its ambiguous reply becomes a clarification over both units.
    units = ("Phòng Khảo thí và Đảm bảo chất lượng", "Phòng Công tác chính trị và Học sinh, sinh viên")
    result = office_lookup(
        "Không cần giấy chứng nhận",
        production_directory,
        cohort="K51",
        candidate_text="giấy chứng nhận",
        lookup_type="student_service",
        selector=scripted_selector({"giấy chứng nhận": units}),
    )

    assert result is not None
    assert result["resolution_status"] == "ambiguous"
    assert set(result["candidate_units"]) == set(units)
    assert len(result["clarification_options"]) == 2


def _plan(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "context_mode": "standalone",
        "normalized_query": None,
        "standalone_query": None,
        "referenced_turns": [],
        "out_of_domain": False,
        "tasks": tasks,
    }


def test_compound_service_tasks_keep_local_aliases_across_cohorts(
    production_directory: list[dict[str, Any]],
) -> None:
    query = (
        "Muốn in giáo trình cho K48-K49 thì liên hệ đơn vị nào, "
        "còn xin giấy chứng nhận điểm K51 ở phòng nào?"
    )
    plan, errors = normalize_query_plan(
        _plan(
            [
                {
                    "id": "t1",
                    "question": "Muốn in giáo trình cho K48-K49 thì liên hệ đơn vị nào?",
                    "mode": "structured",
                    "intent": "contact",
                    "lookup_type": "student_service",
                    "slots": {"service": "in giáo trình", "requested_field": "unit"},
                    "slot_spans": {
                        "service": "in giáo trình",
                        "requested_field": "đơn vị",
                    },
                    "cohorts": ["K48-K49"],
                },
                {
                    "id": "t2",
                    "question": "Xin giấy chứng nhận điểm K51 ở phòng nào?",
                    "mode": "structured",
                    "intent": "contact",
                    "lookup_type": "student_service",
                    "slots": {
                        "service": "giấy chứng nhận điểm",
                        "requested_field": "unit",
                    },
                    "slot_spans": {
                        "service": "giấy chứng nhận điểm",
                        "requested_field": "phòng nào",
                    },
                    "cohorts": ["K51"],
                },
            ]
        ),
        query=query,
        selected_cohort="K48-K49",
    )

    assert errors == []
    assert [task["slots"]["service"] for task in plan["tasks"]] == [
        "in giáo trình",
        "giấy chứng nhận điểm",
    ]
    assert [task["cohorts"] for task in plan["tasks"]] == [
        ["K48-K49"],
        ["K51"],
    ]

    expected_units = [
        "Nhà xuất bản ĐHSP Thành phố Hồ Chí Minh",
        "Phòng Khảo thí và Đảm bảo chất lượng",
    ]
    # Each task is selected within its own cohort's catalog.
    selector = scripted_selector({"in giáo trình": "Nhà xuất bản ĐHSP Thành phố Hồ Chí Minh",
                                  "giấy chứng nhận điểm": "Phòng Khảo thí và Đảm bảo chất lượng"})
    for task, expected_unit in zip(plan["tasks"], expected_units, strict=True):
        task_cohort = task["cohorts"][0]
        result = office_lookup(
            task["question"],
            production_directory,
            cohort=task_cohort,
            candidate_text=task["slots"]["service"],
            lookup_type="student_service",
            selector=selector,
        )
        assert result is not None
        assert result["cohort"] == task_cohort
        assert result["result"][0]["unit_name"] == expected_unit
