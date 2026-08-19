from __future__ import annotations

import pytest

from scripts.judge_single_cohort_v2_answers import _validated_answer_targets


def test_judge_targets_only_generated_answers() -> None:
    cases = {
        "planned": {"id": "planned"},
        "planner-failed": {"id": "planner-failed"},
    }

    ids, answers = _validated_answer_targets(
        [{"id": "planned", "answer": "verified"}],
        cases,
        split="dev",
    )

    assert ids == ["planned"]
    assert set(answers) == {"planned"}


@pytest.mark.parametrize(
    "rows, error",
    [
        ([{"id": "case-1"}, {"id": "case-1"}], "duplicate"),
        ([{"id": "hidden-1"}], "outside dev"),
        ([{"answer": "missing id"}], "without an id"),
    ],
)
def test_judge_targets_fail_closed(rows, error) -> None:
    with pytest.raises(ValueError, match=error):
        _validated_answer_targets(rows, {"case-1": {"id": "case-1"}}, split="dev")
