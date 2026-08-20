from __future__ import annotations

from typing import Any

import pytest

from src.common.cohort import normalize_cohort
from src.retrieval.core.query_context import (
    select_effective_query,
    validated_correction_provenance,
)
from src.retrieval.core.structured_routing import (
    MAX_LOOKUP_REQUESTS,
    reject_invalid_plan,
    normalize_router_decision,
    validate_router_decision,
)


def _request(
    *,
    request_kind: str,
    intent: str,
    query_span: str,
    lookup_type: str | None = None,
    slots: dict[str, Any] | None = None,
    slot_spans: dict[str, Any] | None = None,
    cohort_refs: list[str] | Any | None = None,
) -> dict[str, Any]:
    return {
        "request_kind": request_kind,
        "lookup_type": lookup_type,
        "intent": intent,
        "query_span": query_span,
        "slots": slots or {},
        "slot_spans": slot_spans or {},
        "cohort_refs": [] if cohort_refs is None else cohort_refs,
    }


def _normalize(
    query: str,
    requests: list[Any] | Any,
    *,
    selected_cohort: str | None = "K50",
    cohort: str | None = "K50",
    cohorts: list[str] | None = None,
) -> dict[str, Any]:
    return normalize_router_decision(
        {
            "context_mode": "standalone",
            "context_confidence": "high",
            "normalized_query": query,
            "normalization_confidence": "high",
            "corrections": [],
            "standalone_query": None,
            "referenced_turns": [],
            "route": "rag",
            "cohort": cohort,
            "cohorts": cohorts if cohorts is not None else ([cohort] if cohort else []),
            "is_multi_cohort": bool(cohorts and len(cohorts) > 1),
            "lookup_requests": requests,
            "clarification_question": None,
        },
        query=query,
        selected_cohort=selected_cohort,
    )


def _errors(
    decision: dict[str, Any],
    query: str,
    *,
    selected_cohort: str | None = "K50",
) -> list[str]:
    handling = select_effective_query(
        query,
        decision,
        selected_cohort=selected_cohort,
    )
    return validate_router_decision(
        decision,
        query=query,
        selected_cohort=selected_cohort,
        grounding_context=handling.effective_query,
        validated_corrections=validated_correction_provenance(
            decision, handling
        ),
    )


def test_follow_up_query_span_must_stay_in_current_user_query() -> None:
    query = "Nội dung đó có ngoại lệ nào?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="rag",
                intent="consequence_or_exception",
                query_span="quy định học lại",
                cohort_refs=["K50"],
            )
        ],
    )

    errors = validate_router_decision(
        decision,
        query=query,
        selected_cohort="K50",
        grounding_context="K50 quy định học lại có ngoại lệ nào?",
    )

    assert "request:0:ungrounded_query_span" in errors


@pytest.mark.parametrize("lookup_type", ["null", "policy", "procedure"])
def test_rag_lookup_type_representation_is_canonicalized_when_unambiguous(
    lookup_type: str,
) -> None:
    query = "K50 quy định học lại thực hiện thế nào?"
    intent = "policy" if lookup_type in {"null", "policy"} else "procedure"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="rag",
                lookup_type=lookup_type,
                intent=intent,
                query_span="quy định học lại thực hiện thế nào",
                cohort_refs=["K50"],
            )
        ],
    )

    request = decision["lookup_requests"][0]
    assert request["lookup_type"] is None
    assert request["schema_corrections"]
    assert _errors(decision, query) == []


def test_rag_request_with_structured_tool_remains_invalid() -> None:
    query = "K50 quy định IELTS thế nào?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="rag",
                lookup_type="foreign_language",
                intent="policy",
                query_span="quy định IELTS",
                cohort_refs=["K50"],
            )
        ],
    )

    assert decision["lookup_requests"][0]["lookup_type"] == "foreign_language"
    assert "request:0:rag_request_has_lookup_type" in _errors(decision, query)


def test_legacy_top_level_decision_becomes_one_request() -> None:
    query = "K50 IELTS 6.0 tương đương bậc mấy?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "foreign_language",
            "cohort": "K50",
            "slots": {
                "certificate_or_language": "IELTS",
                "score_or_level": "6.0",
            },
            "slot_spans": {
                "certificate_or_language": "IELTS",
                "score_or_level": "6.0",
            },
        },
        query=query,
        selected_cohort="K50",
    )

    assert decision["request_plan_provided"] is False
    assert len(decision["lookup_requests"]) == 1
    assert decision["lookup_requests"][0]["query_span"].startswith(query[:-1])
    assert _errors(decision, query) == []


def test_two_structured_domains_keep_slots_isolated() -> None:
    query = "IELTS 6.0 tương đương bậc mấy và GPA 3.4 xếp loại gì?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span="IELTS 6.0 tương đương bậc mấy",
                slots={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "6.0",
                },
                slot_spans={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "6.0",
                },
            ),
            _request(
                request_kind="structured",
                lookup_type="scoring",
                intent="direct_value",
                query_span="GPA 3.4 xếp loại gì",
                slots={
                    "operation": "academic_classification",
                    "score_or_grade": 3.4,
                },
                slot_spans={"score_or_grade": "3.4"},
            ),
        ],
    )

    assert decision["route"] == "rag"
    assert decision["execution_mode"] == "mixed"
    assert decision["intent"] == "multi_request"
    assert [item["lookup_type"] for item in decision["lookup_requests"]] == [
        "foreign_language",
        "scoring",
    ]
    assert decision["lookup_requests"][0]["slots"]["score_or_level"] == "6.0"
    assert decision["lookup_requests"][1]["slots"]["score_or_grade"] == 3.4
    assert _errors(decision, query) == []


def test_registry_canonicalizes_typed_and_named_slot_values() -> None:
    query = "k51 ielts 6.0 và GPA 3.4 xếp loại học lực"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span="ielts 6.0",
                slots={
                    "certificate_or_language": "ielts",
                    "score_or_level": "6.0",
                },
                slot_spans={
                    "certificate_or_language": "ielts",
                    "score_or_level": "6.0",
                },
            ),
            _request(
                request_kind="structured",
                lookup_type="scoring",
                intent="direct_value",
                query_span="GPA 3.4 xếp loại học lực",
                slots={
                    "operation": "academic_classification",
                    "score_or_grade": "3.4",
                },
                slot_spans={"score_or_grade": "3.4"},
            ),
        ],
        selected_cohort="K51",
        cohort="K51",
    )

    first, second = decision["lookup_requests"]
    assert first["slots"]["certificate_or_language"] == "IELTS"
    assert first["slots"]["score_or_level"] == "6.0"
    assert second["slots"]["score_or_grade"] == 3.4
    assert _errors(decision, query, selected_cohort="K51") == []


@pytest.mark.parametrize("value", ["NULL", "null", "None", "N/A", "unresolved"])
def test_null_like_cohort_sentinels_are_not_real_cohorts(value: str) -> None:
    assert normalize_cohort(value) is None


def test_non_scalar_cohort_fails_closed() -> None:
    assert normalize_cohort({"evidence_span": "K51"}) is None


def test_object_cohort_ref_is_invalid_instead_of_crashing() -> None:
    query = "Quy định đăng ký học phần thế nào?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="rag",
                intent="procedure",
                query_span=query,
                cohort_refs=[{"turn_id": 0, "evidence_span": "K50"}],
            )
        ],
    )

    request = decision["lookup_requests"][0]
    assert request["cohort_refs"] == ["K50"]
    assert request["invalid_cohort_refs_payload"] is True
    assert "request:0:invalid_cohort_refs" in _errors(decision, query)


def test_validated_local_correction_can_ground_canonical_slot_value() -> None:
    query = "IELST 6.0 đổi bậc"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span=query,
                slots={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "6.0",
                },
                slot_spans={
                    "certificate_or_language": "IELST",
                    "score_or_level": "6.0",
                },
                cohort_refs=["K50"],
            )
        ],
    )
    decision["corrections"] = [
        {"original_span": "IELST", "normalized_span": "IELTS"}
    ]
    decision["normalized_query"] = "IELTS 6.0 đổi bậc"

    assert _errors(decision, query) == []


def test_unvalidated_content_substitution_cannot_ground_slot_value() -> None:
    query = "TOEFL 60 đổi bậc"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span=query,
                slots={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "60",
                },
                slot_spans={
                    "certificate_or_language": "TOEFL",
                    "score_or_level": "60",
                },
                cohort_refs=["K50"],
            )
        ],
    )
    decision["corrections"] = [
        {"original_span": "TOEFL", "normalized_span": "IELTS"}
    ]
    decision["normalized_query"] = "IELTS 60 đổi bậc"

    assert "request:0:slot_value_mismatch:certificate_or_language" in _errors(
        decision, query
    )


def test_correction_is_ignored_when_normalization_falls_back_to_raw() -> None:
    query = "IELST 6.0 đổi bậc"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span=query,
                slots={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "6.0",
                },
                slot_spans={
                    "certificate_or_language": "IELST",
                    "score_or_level": "6.0",
                },
                cohort_refs=["K50"],
            )
        ],
    )
    decision["corrections"] = [
        {"original_span": "not in query", "normalized_span": "IELTS"}
    ]
    decision["normalized_query"] = "IELTS 6.0 đổi bậc"

    assert "request:0:slot_value_mismatch:certificate_or_language" in _errors(
        decision, query
    )


def test_unused_correction_cannot_ground_slot_when_normalized_query_is_unchanged() -> None:
    query = "TOEFL 60 đổi bậc"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span=query,
                slots={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "60",
                },
                slot_spans={
                    "certificate_or_language": "TOEFL",
                    "score_or_level": "60",
                },
                cohort_refs=["K50"],
            )
        ],
    )
    decision["corrections"] = [
        {"original_span": "TOEFL", "normalized_span": "IELTS"}
    ]

    assert "request:0:slot_value_mismatch:certificate_or_language" in _errors(
        decision, query
    )


@pytest.mark.parametrize(
    ("query", "lookup_type", "intent", "slot_name", "value", "span", "expected"),
    [
        (
            "mail pdt",
            "office",
            "contact",
            "office",
            "Phòng Đào tạo",
            "pdt",
            "Phòng Đào tạo",
        ),
        (
            "web khoa cntt",
            "faculty",
            "contact",
            "faculty",
            "khoa cntt",
            "khoa cntt",
            "Khoa Công nghệ Thông tin",
        ),
        (
            "đơn vị hỗ trợ bhyt",
            "student_service",
            "contact",
            "service",
            "bhyt",
            "bhyt",
            "bảo hiểm y tế",
        ),
        (
            "nganh cntt thuộc khoa nào",
            "program",
            "direct_value",
            "program_or_faculty",
            "nganh cntt",
            "nganh cntt",
            "Công nghệ Thông tin",
        ),
    ],
)
def test_registry_canonicalizes_exact_declared_aliases(
    query: str,
    lookup_type: str,
    intent: str,
    slot_name: str,
    value: str,
    span: str,
    expected: str,
) -> None:
    fixed_slots = {
        "requested_field": "unit" if lookup_type == "student_service" else "website"
    }
    if lookup_type == "program":
        fixed_slots = {"requested_field": "faculty"}
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type=lookup_type,
                intent=intent,
                query_span=query,
                slots={slot_name: value, **fixed_slots},
                slot_spans={slot_name: span},
            )
        ],
        selected_cohort="K51",
        cohort="K51",
    )
    request = decision["lookup_requests"][0]
    assert request["slots"][slot_name] == expected
    assert _errors(decision, query, selected_cohort="K51") == []


def test_registry_preserves_distinct_toefl_certificate_types() -> None:
    query = "K51 TOEFL iBT 60 tương đương bậc nào"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span="TOEFL iBT 60",
                slots={
                    "certificate_or_language": "toefl ibt",
                    "score_or_level": "60",
                },
                slot_spans={
                    "certificate_or_language": "TOEFL iBT",
                    "score_or_level": "60",
                },
            )
        ],
        selected_cohort="K51",
        cohort="K51",
    )
    request = decision["lookup_requests"][0]
    assert request["slots"]["certificate_or_language"] == "TOEFL iBT"
    assert _errors(decision, query, selected_cohort="K51") == []


def test_slot_offsets_are_valid_provenance_within_query_span() -> None:
    query = "k51 ielts 6.0 tuong duong bac may"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span=query,
                slots={
                    "certificate_or_language": "ielts",
                    "score_or_level": "6.0",
                },
                slot_spans={
                    "certificate_or_language": {"start": 4, "end": 9},
                    "score_or_level": {"start": 10, "end": 13},
                },
            )
        ],
        selected_cohort="K51",
        cohort="K51",
    )

    assert _errors(decision, query, selected_cohort="K51") == []


def test_raw_query_and_grounded_follow_up_both_validate_request_spans() -> None:
    raw_query = "Nội dung đó có ngoại lệ nào?"
    standalone = "K51 quy định bảo lưu có ngoại lệ nào?"
    decision = _normalize(
        raw_query,
        [
            _request(
                request_kind="rag",
                intent="consequence_or_exception",
                query_span="Nội dung đó có ngoại lệ nào",
                cohort_refs=["K51"],
            )
        ],
        selected_cohort="K51",
        cohort="K51",
    )

    assert validate_router_decision(
        decision,
        query=raw_query,
        grounding_context=standalone,
        selected_cohort="K51",
    ) == []


def test_two_regulations_become_two_rag_requests() -> None:
    query = "Điều kiện cảnh báo học vụ và thủ tục xin bảo lưu là gì?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="rag",
                intent="policy",
                query_span="Điều kiện cảnh báo học vụ",
            ),
            _request(
                request_kind="rag",
                intent="procedure",
                query_span="thủ tục xin bảo lưu",
            ),
        ],
    )

    assert len(decision["lookup_requests"]) == 2
    assert all(item["request_kind"] == "rag" for item in decision["lookup_requests"])
    assert _errors(decision, query) == []


def test_same_tool_can_appear_in_two_requests() -> None:
    query = "GPA 3.4 xếp loại gì, còn GPA 2.7 xếp loại gì?"
    requests = []
    for span, score in (
        ("GPA 3.4 xếp loại gì", 3.4),
        ("GPA 2.7 xếp loại gì", 2.7),
    ):
        requests.append(
            _request(
                request_kind="structured",
                lookup_type="scoring",
                intent="direct_value",
                query_span=span,
                slots={
                    "operation": "academic_classification",
                    "score_or_grade": score,
                },
                slot_spans={"score_or_grade": str(score)},
            )
        )

    decision = _normalize(query, requests)

    assert [item["lookup_type"] for item in decision["lookup_requests"]] == [
        "scoring",
        "scoring",
    ]
    assert _errors(decision, query) == []


def test_multiple_entities_in_one_domain_stay_in_one_request() -> None:
    query = "IELTS 5.5 và 6.0 tương đương các bậc nào?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span=query,
                slots={
                    "certificate_or_language": "IELTS",
                    "score_or_level": ["5.5", "6.0"],
                },
                slot_spans={
                    "certificate_or_language": "IELTS",
                    "score_or_level": ["5.5", "6.0"],
                },
            )
        ],
    )

    assert len(decision["lookup_requests"]) == 1
    assert _errors(decision, query) == []


def test_ungrounded_query_span_is_rejected() -> None:
    query = "IELTS 6.0 tương đương bậc mấy?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="rag",
                intent="policy",
                query_span="điều kiện tốt nghiệp",
            )
        ],
    )

    assert "request:0:ungrounded_query_span" in _errors(decision, query)


def test_slot_cannot_be_grounded_by_another_request() -> None:
    query = "IELTS 6.0 tương đương bậc mấy và GPA 3.4 xếp loại gì?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span="IELTS 6.0 tương đương bậc mấy",
                slots={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "3.4",
                },
                slot_spans={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "3.4",
                },
            )
        ],
    )

    assert "request:0:ungrounded_slot:score_or_level" in _errors(decision, query)


@pytest.mark.parametrize(
    ("slots", "slot_spans", "expected_error"),
    [
        (
            {"certificate_or_language": "TOEFL", "score_or_level": "6.0"},
            {"certificate_or_language": "IELTS", "score_or_level": "6.0"},
            "request:0:slot_value_mismatch:certificate_or_language",
        ),
        (
            {"certificate_or_language": "IELTS", "score_or_level": "3.4"},
            {"certificate_or_language": "IELTS", "score_or_level": "6.0"},
            "request:0:slot_value_mismatch:score_or_level",
        ),
    ],
)
def test_free_form_slot_value_must_match_its_grounded_span(
    slots: dict[str, Any],
    slot_spans: dict[str, Any],
    expected_error: str,
) -> None:
    query = "IELTS 6.0 tương đương bậc mấy?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span=query,
                slots=slots,
                slot_spans=slot_spans,
            )
        ],
    )

    assert expected_error in _errors(decision, query)


@pytest.mark.parametrize(
    ("lookup_request", "expected_error"),
    [
        (
            _request(
                request_kind="structured",
                lookup_type="unknown_tool",
                intent="direct_value",
                query_span="IELTS 6.0",
            ),
            "request:0:unknown_lookup_type",
        ),
        (
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="calculate",
                query_span="IELTS 6.0",
                slots={"invented": "6.0"},
                slot_spans={"invented": "6.0"},
            ),
            "request:0:unsupported_intent",
        ),
        (
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="list_items",
                query_span="IELTS 6.0",
                slots={"invented": "6.0"},
                slot_spans={"invented": "6.0"},
            ),
            "request:0:unknown_slot:invented",
        ),
    ],
)
def test_unknown_contract_values_are_rejected(
    lookup_request: dict[str, Any],
    expected_error: str,
) -> None:
    query = "IELTS 6.0"
    decision = _normalize(query, [lookup_request])

    assert expected_error in _errors(decision, query)


def test_request_cohorts_may_inherit_selected_cohort() -> None:
    query = "IELTS 6.0 tương đương bậc mấy?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span=query,
                slots={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "6.0",
                },
                slot_spans={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "6.0",
                },
            )
        ],
    )

    assert decision["lookup_requests"][0]["cohort_refs"] == ["K50"]
    assert _errors(decision, query) == []


@pytest.mark.parametrize("cohort_refs", [["K51"], ["K99"], "K51"])
def test_ungrounded_or_malformed_request_cohorts_are_rejected(
    cohort_refs: Any,
) -> None:
    query = "IELTS 6.0 tương đương bậc mấy?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="foreign_language",
                intent="direct_value",
                query_span=query,
                slots={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "6.0",
                },
                slot_spans={
                    "certificate_or_language": "IELTS",
                    "score_or_level": "6.0",
                },
                cohort_refs=cohort_refs,
            )
        ],
    )

    errors = _errors(decision, query)
    assert any("cohort" in error for error in errors)


def test_request_limit_is_enforced() -> None:
    query = "Quy định học vụ là gì?"
    requests = [
        _request(request_kind="rag", intent="policy", query_span=query)
        for _ in range(MAX_LOOKUP_REQUESTS + 1)
    ]
    decision = _normalize(query, requests)

    assert "too_many_lookup_requests" in _errors(decision, query)


@pytest.mark.parametrize("requests", [[], "invalid", ["invalid"]])
def test_empty_or_malformed_explicit_request_plan_is_rejected(requests: Any) -> None:
    query = "Điều kiện tốt nghiệp là gì?"
    decision = _normalize(query, requests)
    errors = _errors(decision, query)

    assert errors
    assert "missing_lookup_requests" in errors or "request:0:invalid_payload" in errors


def test_invalid_plan_clarifies_without_a_whole_query_rag_request() -> None:
    query = "IELTS 6.0 tương đương bậc mấy và điều kiện tốt nghiệp là gì?"
    decision = _normalize(
        query,
        [
            _request(
                request_kind="structured",
                lookup_type="unknown_tool",
                intent="direct_value",
                query_span="IELTS 6.0 tương đương bậc mấy",
            )
        ],
    )
    errors = _errors(decision, query)
    fallback = reject_invalid_plan(decision, errors, query=query)

    assert fallback["route"] == "clarify"
    assert fallback["execution_mode"] == "regulation"
    assert fallback["lookup_requests"] == []
    assert fallback["retrieval_executed"] is False
    assert fallback["retrieval_query"] is None
    assert _errors(fallback, query) == []
