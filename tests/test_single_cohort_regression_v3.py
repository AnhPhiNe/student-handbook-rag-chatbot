from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.apply_single_cohort_regression_v3_reviews import apply_reviews
from scripts.build_single_cohort_regression_v3 import build_bundle
from scripts.evaluate_single_cohort_regression_v3 import build_readiness_report
from scripts.evaluate_single_cohort_v2 import (
    _regression_v3_report_is_current_and_passing,
)
from src.evaluation.single_cohort_regression_v3 import (
    EXPECTED_COUNTS,
    ROOT,
    SUITE_FILES,
    archive_integrity,
    load_json,
    metric_cases,
    validate_bundle,
)


@pytest.fixture(scope="module")
def review_bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("regression-v3")
    build_bundle(root=ROOT, output=output)
    return output


def _case(bundle: Path, suite: str, case_id: str) -> dict:
    values = load_json(bundle / SUITE_FILES[suite])
    return next(value for value in values if value["id"] == case_id)


def test_frozen_archive_hashes_are_preserved() -> None:
    result = archive_integrity(ROOT)
    assert result["preserved"] is True
    assert result["actual"] == result["declared"]


def test_builder_keeps_all_460_cases_as_unapproved_proposals(
    review_bundle: Path,
) -> None:
    validation = validate_bundle(review_bundle, root=ROOT)
    assert validation.valid is True
    assert validation.release_ready is False
    assert validation.counts == EXPECTED_COUNTS
    assert validation.annotation_counts == {"review_required": 460}
    assert validation.lifecycle_counts == {
        "active": 401,
        "deferred_multi_cohort": 59,
    }


def test_general_scope_is_deferred_and_cannot_retrieve(review_bundle: Path) -> None:
    case = _case(review_bundle, "retrieval", "v9_ret_137")
    assert case["legacy_annotation"]["cohort"] == "general"
    assert case["lifecycle"] == "deferred_multi_cohort"
    assert case["expected_contract"] == {
        "outcome": "clarify",
        "effective_cohort": None,
        "retrieval_policy": "forbidden",
        "atomic_requests": [],
    }


def test_wrong_cohort_archive_gold_becomes_source_reviewed_no_match(
    review_bundle: Path,
) -> None:
    case = _case(review_bundle, "retrieval", "v9_ret_095")
    request = case["expected_contract"]["atomic_requests"][0]
    assert case["expected_contract"]["effective_cohort"] == "K51"
    assert request["expected_status"] == "no_match"
    assert request["evidence_sources"] == []
    assert "gold_source_not_applicable_to_effective_cohort" in case["annotation"][
        "reason_codes"
    ]


def test_current_registry_maps_faculty_program_listing_to_program_tool(
    review_bundle: Path,
) -> None:
    case = _case(review_bundle, "deterministic", "v9_det_075")
    request = case["expected_contract"]["atomic_requests"][0]
    assert request["tool_name"] == "program"
    assert request["source_contract"] == "directory_table"


def test_multi_operand_formula_is_decomposed_without_case_id_branch(
    review_bundle: Path,
) -> None:
    case = _case(review_bundle, "answers", "v9_ans_079")
    requests = case["expected_contract"]["atomic_requests"]
    assert [request["request_id"] for request in requests] == ["r1", "r2"]
    assert [request["typed_slots"]["formula_type"] for request in requests] == [
        "gpa_weighted_average",
        "scholarship_score",
    ]


def test_retired_cases_are_never_counted_as_metric_passes() -> None:
    cases = [
        {"id": "active", "lifecycle": "active"},
        {"id": "deferred", "lifecycle": "deferred_multi_cohort"},
        {"id": "retired", "lifecycle": "retired_invalid_gold"},
    ]
    assert [case["id"] for case in metric_cases(cases)] == ["active"]


def test_release_mode_fails_closed_before_review_and_freeze(
    review_bundle: Path,
) -> None:
    validation = validate_bundle(review_bundle, root=ROOT, require_frozen=True)
    assert validation.valid is False
    assert "release evaluation requires a frozen bundle" in validation.errors
    report = build_readiness_report(
        bundle_dir=review_bundle,
        root=ROOT,
        require_frozen=False,
    )
    assert report["passed"] is True
    assert report["bundle_validation"]["release_ready"] is False
    assert any("460 review proposals" in value for value in report["release_blockers"])
    assert _regression_v3_report_is_current_and_passing(report) is False


def test_approval_without_structured_source_audit_cannot_freeze(
    review_bundle: Path,
    tmp_path: Path,
) -> None:
    target = tmp_path / "bundle"
    target.mkdir()
    for path in review_bundle.iterdir():
        target.joinpath(path.name).write_bytes(path.read_bytes())
    decisions = load_json(target / "review_queue.json")
    for row in decisions:
        row["review_decision"] = "accept"
        row["reviewer"] = "test-reviewer"
        row["reviewed_at"] = "2026-08-21T00:00:00+00:00"
    decisions_path = target / "approved.json"
    decisions_path.write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="approved structured gold lacks source records"):
        apply_reviews(
            bundle_dir=target,
            decisions_path=decisions_path,
            freeze=True,
            root=ROOT,
        )
    unchanged = load_json(target / SUITE_FILES["deterministic"])
    assert all(case["annotation"]["state"] == "review_required" for case in unchanged)


def test_disabled_formula_is_proposed_as_no_match(review_bundle: Path) -> None:
    case = _case(review_bundle, "deterministic", "v9_det_094")
    request = case["expected_contract"]["atomic_requests"][0]
    assert request["typed_slots"] == {"formula_type": "scholarship_score"}
    assert request["expected_status"] == "no_match"
    assert request["expected_source_records"] == []
    assert "formula_source_disabled_or_rejected" in case["annotation"]["reason_codes"]
