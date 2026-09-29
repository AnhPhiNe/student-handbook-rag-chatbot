"""Directory selector contract: exact names first, validated LLM ids, no guessing on failure."""
from __future__ import annotations

from pathlib import Path

from src.retrieval.core.directory_selector import (
    SELECTOR_PROMPT_VERSION,
    DirectorySelector,
    exact_matches,
    render_prompt,
)
from src.retrieval.core.office_lookup import office_lookup
from src.retrieval.core.program_lookup import program_lookup
from tests.scripted_selector import ScriptedClient, scripted_selector

FIXTURE = Path(__file__).parent / "fixtures" / "directory_selector_prompt_v2.txt"

FACULTIES = [
    {"unit_name": "Khoa Tiếng Hàn Quốc", "aliases": ["Khoa Tiếng Hàn Quốc", "KTHQ"], "cohort": "K51",
     "content_type": "student_faculty_profile", "emails": ["khoatienghan@hcmue.edu.vn"]},
    {"unit_name": "Khoa Tiếng Nga", "aliases": ["Khoa Tiếng Nga", "KTN"], "cohort": "K51",
     "content_type": "student_faculty_profile"},
    {"unit_name": "Khoa Tiếng Nhật", "aliases": ["Khoa Tiếng Nhật", "KTN"], "cohort": "K51",
     "content_type": "student_faculty_profile"},
]
PROGRAMS = [
    {"program_name": "Vật lý học", "faculty_name": "Khoa Vật lý", "cohort": "K51"},
    {"program_name": "Sư phạm Vật lý", "faculty_name": "Khoa Vật lý", "cohort": "K51"},
    {"program_name": "Ngôn ngữ Anh", "faculty_name": "Khoa Tiếng Anh", "cohort": "K51"},
]


def _faculty(text: str, client: ScriptedClient) -> dict | None:
    return office_lookup(text, FACULTIES, candidate_text=text, lookup_type="faculty", cohort="K51",
                         selector=DirectorySelector(client))


def test_prompt_is_pinned_to_its_version() -> None:
    prompt, ids = render_prompt("faculty", "khoa Hàn", FACULTIES[:2])
    assert SELECTOR_PROMPT_VERSION == "directory-selector-v2-whole-question"
    assert list(ids) == ["S01", "S02"]
    assert prompt == FIXTURE.read_text(encoding="utf-8")


def test_exact_name_or_alias_needs_no_llm_call() -> None:
    client = ScriptedClient()
    result = _faculty("khoa tieng han quoc", client)
    assert result["result"][0]["unit_name"] == "Khoa Tiếng Hàn Quốc"
    assert result["selection_method"] == "catalog_exact"
    assert client.prompts == []


def test_alias_shared_by_two_units_is_not_exact() -> None:
    assert exact_matches("faculty", "KTN", FACULTIES) == []
    result = _faculty("KTN", ScriptedClient({"KTN": ("Khoa Tiếng Nga", "Khoa Tiếng Nhật")}))
    assert result["resolution_status"] == "ambiguous"
    assert set(result["candidate_units"]) == {"Khoa Tiếng Nga", "Khoa Tiếng Nhật"}


def test_llm_match_returns_the_catalog_record_not_model_text() -> None:
    client = ScriptedClient({"khoa Hàn": "Khoa Tiếng Hàn Quốc"})
    result = _faculty("khoa Hàn", client)
    assert result["result"][0]["emails"] == ["khoatienghan@hcmue.edu.vn"]
    assert result["selection"][0]["method"] == "llm_selector"
    assert len(client.prompts) == 1


def test_none_reply_finds_nothing() -> None:
    assert _faculty("khoa Y", ScriptedClient({})) is None


def test_malformed_reply_unknown_id_or_api_failure_asks_instead_of_guessing() -> None:
    for client in (
        ScriptedClient(raw="Khoa Tiếng Hàn Quốc"),
        ScriptedClient(raw='{"decision": "match", "ids": ["S99"]}'),
        ScriptedClient(raw='{"decision": "match", "ids": []}'),
        ScriptedClient(fail=True),
    ):
        result = _faculty("khoa Hàn", client)
        assert result["resolution_status"] == "unresolved"
        assert "result" not in result


def test_a_reply_after_the_echoed_format_is_still_read() -> None:
    reply = '{"type": "json_object"}\n{"decision": "match", "ids": ["S01"]}'
    result = _faculty("khoa Hàn", ScriptedClient(raw=reply))
    assert result["result"][0]["unit_name"] == "Khoa Tiếng Hàn Quốc"


def test_nothing_found_is_asked_again_with_thinking() -> None:
    fast, thinking = ScriptedClient({}), ScriptedClient({"khoa Hàn": "Khoa Tiếng Hàn Quốc"})
    result = office_lookup("khoa Hàn", FACULTIES, candidate_text="khoa Hàn", lookup_type="faculty",
                           cohort="K51", selector=DirectorySelector(fast, thinking))
    assert result["result"][0]["unit_name"] == "Khoa Tiếng Hàn Quốc"
    assert result["selection"][0]["method"] == "llm_selector_thinking"
    assert fast.prompts == thinking.prompts  # the same question, asked twice


def test_a_found_unit_is_not_asked_again() -> None:
    thinking = ScriptedClient({"khoa Hàn": "Khoa Tiếng Nga"})
    selector = DirectorySelector(ScriptedClient({"khoa Hàn": "Khoa Tiếng Hàn Quốc"}), thinking)
    result = office_lookup("khoa Hàn", FACULTIES, candidate_text="khoa Hàn", lookup_type="faculty",
                           cohort="K51", selector=selector)
    assert result["result"][0]["unit_name"] == "Khoa Tiếng Hàn Quốc"
    assert thinking.prompts == []


def test_a_failed_second_look_keeps_nothing_found() -> None:
    for thinking in (ScriptedClient(fail=True), ScriptedClient(raw="")):
        selector = DirectorySelector(ScriptedClient({}), thinking)
        assert office_lookup("khoa Y", FACULTIES, candidate_text="khoa Y", lookup_type="faculty",
                             cohort="K51", selector=selector) is None


def test_a_question_naming_two_units_selects_both() -> None:
    question = "Cho em email khoa Hàn và khoa Nga"
    result = _faculty(question, ScriptedClient({question: ["Khoa Tiếng Hàn Quốc", "Khoa Tiếng Nga"]}))
    assert [item["unit_name"] for item in result["result"]] == ["Khoa Tiếng Hàn Quốc", "Khoa Tiếng Nga"]


def test_each_listed_name_is_selected_on_its_own() -> None:
    result = office_lookup("", FACULTIES, candidate_text=["KTHQ", "khoa Nga"], lookup_type="faculty",
                           cohort="K51", selector=scripted_selector({"khoa Nga": "Khoa Tiếng Nga"}))
    assert [item["unit_name"] for item in result["result"]] == ["Khoa Tiếng Hàn Quốc", "Khoa Tiếng Nga"]


def test_program_selection_may_name_every_program_of_a_faculty() -> None:
    selector = scripted_selector({"khoa Vật lý": ["Vật lý học", "Sư phạm Vật lý"]})
    result = program_lookup(PROGRAMS, candidate_text="khoa Vật lý", cohort="K51", action="list",
                            scope="faculty", selector=selector)
    assert {item["program_name"] for item in result["result"]} == {"Vật lý học", "Sư phạm Vật lý"}


def test_program_ambiguity_asks_which_program() -> None:
    selector = scripted_selector({"vật lý": ("Vật lý học", "Sư phạm Vật lý")})
    result = program_lookup(PROGRAMS, candidate_text="vật lý", cohort="K51", action="resolve_faculty",
                            scope="school", selector=selector)
    assert result["needs_clarification"] is True
    assert set(result["candidate_programs"]) == {"Vật lý học", "Sư phạm Vật lý"}


def test_missing_program_is_reported_against_the_cohort_catalog_only() -> None:
    result = program_lookup(PROGRAMS, candidate_text="ngành Luật", cohort="K51", action="exists",
                            scope="school", selector=scripted_selector({}))
    assert result["exists"] is False
    assert "danh sách ngành đào tạo của khóa" in result["not_found_note"]


def test_undecided_program_is_never_reported_missing() -> None:
    result = program_lookup(PROGRAMS, candidate_text="ngành Luật", cohort="K51", action="exists",
                            scope="school", selector=scripted_selector(fail=True))
    assert "exists" not in result
    assert result["needs_clarification"] is True
