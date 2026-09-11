import json
from pathlib import Path

import pytest

from src.retrieval.core.structured_dispatcher import _reference_input_clarification
from src.retrieval.core.structured_dispatcher import resolve_structured_decision


@pytest.mark.parametrize("certificate", ["TOEIC", "ExampleCertificate"])
@pytest.mark.parametrize("slots,missing", [
    ({}, None),
    ({"score_or_level": "bậc 4", "speaking_score": "điểm Nói"}, None),
    ({"score_or_level": "bậc 3 và bậc 4"}, None),
    ({"speaking_score": "điểm Nói", "writing_score": "điểm Viết"}, None),
    ({"score_or_level": 650}, {"listening_score", "speaking_score", "writing_score"}),
    ({"speaking_score": 160}, {"listening_score", "writing_score"}),
    ({"speaking_score": "160,0"}, {"listening_score", "writing_score"}),
    ({"speaking_score": "160.0"}, {"listening_score", "writing_score"}),
    ({"speaking_score": 160, "listening_score": "điểm Nghe"}, {"listening_score", "writing_score"}),
    ({"speaking_score": "160 điểm", "listening_score": 400, "writing_score": "150"}, None),
])
def test_component_guard_distinguishes_requested_fields_from_scores(certificate, slots, missing):
    # Deliberately use three components: requirements must come from the row,
    # not a hard-coded TOEIC four-skill list.
    candidates = [{"rows": [{
        "certificate": certificate,
        "input_requirements": {
            "score_mode": "per_component",
            "required_components": ["listening", "speaking", "writing"],
            "component_slots": {
                name: {"slot": f"{name}_score", "label": name}
                for name in ("listening", "speaking", "writing")
            },
        },
    }]}]
    result = _reference_input_clarification(
        "foreign_language", candidates=candidates, cohort="K50",
        slots={"certificate_or_language": certificate, **slots},
    )
    if missing is None:
        assert result is None
    else:
        assert result["needs_clarification"] is True
        assert set(result["missing_slots"]) == missing


def test_scalar_certificate_has_no_component_requirement():
    assert _reference_input_clarification(
        "foreign_language", candidates=[{"rows": [{"certificate": "IELTS"}]}],
        cohort="K50", slots={"certificate_or_language": "IELTS", "score_or_level": 6.0},
    ) is None


@pytest.mark.parametrize("cohort", ["K48-K49", "K50", "K51"])
@pytest.mark.parametrize("slots,clarify", [
    ({"certificate_or_language": "TOEIC", "score_or_level": "bậc 4", "speaking_score": "điểm Nói"}, False),
    ({"certificate_or_language": "TOEIC", "score_or_level": "bậc 3 và bậc 4"}, False),
    ({"certificate_or_language": "TOEIC"}, False),
    ({"certificate_or_language": "TOEIC", "speaking_score": 160}, True),
    ({"certificate_or_language": "TOEIC", "listening_score": 400, "reading_score": 400,
      "speaking_score": 160, "writing_score": 150}, False),
    ({"certificate_or_language": "IELTS", "score_or_level": 6.0}, False),
])
def test_component_guard_with_runtime_catalog(cohort, slots, clarify):
    registry = json.loads(Path("data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    resolution = resolve_structured_decision(
        {"lookup_type": "foreign_language", "intent": "direct_value", "slots": slots},
        query="Tra bảng chứng chỉ", cohort=cohort, formula_rules=[],
        office_directory=[], student_service_directory=[], student_faculty_profiles=[],
        structured_tables_registry=registry, program_directory=[],
    )
    assert resolution is not None
    assert (resolution.result_kind == "clarification") is clarify
    if not clarify:
        assert resolution.result["cohort"] == cohort
        assert resolution.result.get("result")
