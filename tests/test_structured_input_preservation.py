"""Regression tests for the structured execution contract, without model calls."""
import copy

from src.retrieval.core.query_plan import _merge_compatible_structured_tasks
from src.retrieval.core.structured_dispatcher import StructuredResolution
from src.generation.prompt_builder import build_authorized_evidence_packet


def test_distinct_values_operations_and_entities_are_not_erased():
    for slots in [
        [{"operation": "letter_to_grade_4", "score_or_grade": "C"},
         {"operation": "academic_classification", "score_or_grade": 2.83}],
        [{"faculty": "Khoa Tiếng Anh"}, {"faculty": "Khoa Tiếng Pháp"}],
        [{"score_or_grade": 2.1}, {"score_or_grade": 3.1}],
        [{"requested_field": "email"}, {"requested_field": ["email", "office"]}],
    ]:
        tasks = [{"id": f"t{i}", "mode": "structured", "lookup_type": "scoring",
                  "intent": "direct_value", "cohorts": ["K51"], "slots": slot}
                 for i, slot in enumerate(slots)]
        original = copy.deepcopy(tasks)
        assert _merge_compatible_structured_tasks(tasks) == original


def test_identical_slots_deduplicate_but_never_across_cohorts():
    first = {"id": "t1", "mode": "structured", "lookup_type": "scoring",
             "intent": "direct_value", "cohorts": ["K51"], "slots": {"score_or_grade": 3}}
    tasks = [first, {**first, "id": "t2"}, {**first, "id": "t3", "cohorts": ["K50"]}]
    assert len(_merge_compatible_structured_tasks(tasks)) == 2


def test_resolution_status_does_not_claim_whole_table_is_a_resolved_value():
    def resolution(result, kind="structured"):
        return StructuredResolution("scoring", "reference_table_lookup", kind, result, [])
    assert resolution({"rows": [{"label": "A"}]}).resolution_status == "evidence_only"
    assert resolution({"resolved_result": {"result": {"label": "A"}}}).resolution_status == "resolved"
    assert resolution({}, "clarification").resolution_status == "needs_clarification"


def test_packet_keeps_resolution_status_per_cohort():
    packet = build_authorized_evidence_packet(retrieval_result={
        "query_plan": {"tasks": [{"id": "t1", "mode": "structured", "question": "compare",
                                    "cohorts": ["K50", "K51"]}]},
        "task_results": [{"task_id": "t1", "coverage": "covered",
                          "resolution_by_cohort": {"K50": "resolved", "K51": "evidence_only"}}],
    }, query="compare", selected_citations=[], fallback_cohort="K51", max_context_chars=10000)
    text = str(packet)
    assert "evidence_only" in text and "resolved" in text
