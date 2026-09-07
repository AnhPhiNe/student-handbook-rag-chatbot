"""Offline regressions for source-backed student-service aliases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.retrieval.core.office_lookup import normalize_text, office_lookup
from src.retrieval.core.query_plan import normalize_query_plan


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY_DIR = ROOT / "data" / "processed" / "directories"
COHORTS = ("K48-K49", "K50", "K51")

EXPECTED_UNITS = {
    "giấy chứng nhận điểm": {
        cohort: "Phòng Khảo thí và Đảm bảo chất lượng" for cohort in COHORTS
    },
    "chứng nhận điểm": {
        cohort: "Phòng Khảo thí và Đảm bảo chất lượng" for cohort in COHORTS
    },
    "in ấn giáo trình": {
        "K48-K49": "Nhà xuất bản ĐHSP Thành phố Hồ Chí Minh",
        "K50": "Nhà xuất bản ĐHSP Thành phố Hồ Chí Minh",
        "K51": "Nhà xuất bản Đại học Sư phạm Thành phố Hồ Chí Minh",
    },
    "in giáo trình": {
        "K48-K49": "Nhà xuất bản ĐHSP Thành phố Hồ Chí Minh",
        "K50": "Nhà xuất bản ĐHSP Thành phố Hồ Chí Minh",
        "K51": "Nhà xuất bản Đại học Sư phạm Thành phố Hồ Chí Minh",
    },
}

SOURCE_PHRASE = {
    "giấy chứng nhận điểm": "giấy chứng nhận điểm",
    "chứng nhận điểm": "giấy chứng nhận điểm",
    "in ấn giáo trình": "in ấn giáo trình",
    "in giáo trình": "in ấn giáo trình",
}


def _load_json(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, list)
    return value


@pytest.fixture(scope="module")
def services() -> list[dict[str, Any]]:
    return _load_json(DIRECTORY_DIR / "student_service_directory.json")


@pytest.fixture(scope="module")
def office_profiles() -> list[dict[str, Any]]:
    return _load_json(DIRECTORY_DIR / "student_office_profiles.json")


@pytest.fixture(scope="module")
def production_directory(
    services: list[dict[str, Any]], office_profiles: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Mirror the student-service production pool used by the dispatcher."""
    return services + office_profiles


@pytest.mark.parametrize("alias", sorted(EXPECTED_UNITS))
def test_aliases_are_source_bound_to_one_service_per_cohort(
    services: list[dict[str, Any]], alias: str
) -> None:
    expected_by_cohort = EXPECTED_UNITS[alias]
    for cohort, expected_unit in expected_by_cohort.items():
        matches = [
            record
            for record in services
            if record.get("cohort") == cohort and alias in (record.get("aliases") or [])
        ]
        assert len(matches) == 1
        record = matches[0]
        assert record["unit"] == expected_unit
        assert normalize_text(SOURCE_PHRASE[alias]) in normalize_text(
            record.get("service")
        )

    # A short alias must not be emitted on any other unit or responsibility.
    assert all(
        alias not in (record.get("aliases") or [])
        or record.get("unit") == expected_by_cohort.get(record.get("cohort"))
        for record in services
    )


@pytest.mark.parametrize("alias", sorted(EXPECTED_UNITS))
def test_office_profiles_keep_service_alias_binding(
    office_profiles: list[dict[str, Any]], alias: str
) -> None:
    expected_by_cohort = EXPECTED_UNITS[alias]
    for cohort, expected_unit in expected_by_cohort.items():
        matches = [
            profile
            for profile in office_profiles
            if profile.get("cohort") == cohort
            and alias in (profile.get("aliases") or [])
        ]
        assert len(matches) == 1
        assert matches[0]["unit"] == expected_unit
        assert any(
            normalize_text(SOURCE_PHRASE[alias]) in normalize_text(service)
            for service in matches[0].get("services") or []
        )


@pytest.mark.parametrize(
    ("cohort", "candidate_text", "query", "expected_unit"),
    [
        (
            "K48-K49",
            "in giáo trình",
            "Muốn in giáo trình thì liên hệ đơn vị nào?",
            "Nhà xuất bản ĐHSP Thành phố Hồ Chí Minh",
        ),
        (
            "K50",
            "IN GIAO TRINH",
            "MUỐN IN GIAO TRINH THÌ LIÊN HỆ ĐƠN VỊ NÀO?",
            "Nhà xuất bản ĐHSP Thành phố Hồ Chí Minh",
        ),
        (
            "K51",
            "GIẤY CHỨNG NHẬN ĐIỂM",
            "Xin GIẤY CHỨNG NHẬN ĐIỂM ở phòng nào?",
            "Phòng Khảo thí và Đảm bảo chất lượng",
        ),
        (
            "K50",
            "chung nhan diem",
            "Xin chung nhan diem o phong nao?",
            "Phòng Khảo thí và Đảm bảo chất lượng",
        ),
    ],
)
def test_service_alias_lookup_accepts_natural_case_and_accent_variants(
    production_directory: list[dict[str, Any]],
    cohort: str,
    candidate_text: str,
    query: str,
    expected_unit: str,
) -> None:
    result = office_lookup(
        query,
        production_directory,
        cohort=cohort,
        candidate_text=candidate_text,
        require_confident_match=True,
        min_confidence=0.62,
    )

    assert result is not None
    assert result["cohort"] == cohort
    assert result["selection_method"] == "catalog_exact"
    assert result["result"][0]["unit_name"] == expected_unit
    assert result["result"][0]["cohort"] == cohort


def test_generic_service_phrase_stays_ambiguous_when_candidate_is_generic(
    production_directory: list[dict[str, Any]],
) -> None:
    # This deliberately exercises only the existing ambiguity contract; the
    # matcher does not claim to interpret negation semantics.
    result = office_lookup(
        "Không cần giấy chứng nhận",
        production_directory,
        cohort="K51",
        candidate_text="giấy chứng nhận",
        require_confident_match=True,
        min_confidence=0.62,
    )

    assert result is not None
    assert result["resolution_status"] == "ambiguous"
    assert result["clarification_options"]


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
    for task, expected_unit in zip(plan["tasks"], expected_units, strict=True):
        task_cohort = task["cohorts"][0]
        result = office_lookup(
            task["question"],
            production_directory,
            cohort=task_cohort,
            candidate_text=task["slots"]["service"],
            require_confident_match=True,
            min_confidence=0.62,
        )
        assert result is not None
        assert result["cohort"] == task_cohort
        assert result["result"][0]["unit_name"] == expected_unit
