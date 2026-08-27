from __future__ import annotations

from collections import Counter
from pathlib import Path

from scripts.build_architecture_eval_v3 import (
    FORBIDDEN_QUERY_FRAGMENTS,
    architecture_cases,
    build_bundle,
    rebuild_retrieval,
)
from src.evaluation.dataset import load_json, normalize_query, validate_bundle
from src.evaluation.suites import _retrieval_metrics_for_execution_units


ROOT = Path(__file__).resolve().parents[1]
LEGACY_BUNDLE = ROOT / "data" / "eval" / "final_holdout"
DOCSTORE = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"


def test_architecture_cases_cover_current_query_plan_scenarios() -> None:
    cases = architecture_cases()
    scenarios = Counter(case["architecture_scenario"] for case in cases)

    assert len(cases) == 24
    assert scenarios == {
        "multi_structured": 3,
        "structured_regulation": 7,
        "multi_regulation": 4,
        "multi_cohort": 4,
        "clarification": 2,
        "multi_entity_same_table": 2,
        "three_task_boundary": 1,
        "mixed_scope": 1,
    }
    assert any(case["expected_plan"]["task_count"] == 3 for case in cases)
    assert any(
        case["expected_plan"]["cohorts"] == ["K50", "K51"]
        and case["expected_plan"]["task_count"] == 1
        for case in cases
    )


def test_architecture_annotations_follow_table_first_registry_contract() -> None:
    cases = {case["id"]: case for case in architecture_cases()}

    assert cases["arch_det_003"]["expected_plan"]["allowed_modes"] == [
        "structured",
        "rag",
    ]
    assert cases["arch_det_003"]["expected_plan"]["lookup_types"] == ["program"]
    assert cases["arch_det_005"]["expected_plan"]["allowed_modes"] == [
        "structured",
        "rag",
    ]
    assert cases["arch_det_005"]["expected_plan"]["lookup_types"] == ["formula"]
    assert cases["arch_det_019"]["expected_plan"]["allowed_modes"] == ["structured"]
    assert cases["arch_det_019"]["expected_plan"]["lookup_types"] == [
        "foreign_language"
    ]
    assert cases["arch_det_019"]["expected_plan"]["needs_clarification"] is True


def test_end_to_end_general_retrieval_scores_top_k_per_cohort_unit() -> None:
    case = {
        "cohort": "general",
        "relevance_judgments": [
            {"cohort": "K50", "parent_section_id": "K50_expected", "grade": 2},
            {"cohort": "K51", "parent_section_id": "K51_expected", "grade": 2},
        ],
    }
    ranked_ids = [
        *(f"K48-K49_unrelated_{index}" for index in range(5)),
        "K50_expected",
        *(f"K50_unrelated_{index}" for index in range(4)),
        "K51_expected",
    ]
    grade_by_id = {"K50_expected": 2, "K51_expected": 2}

    end_to_end, metric_scope = _retrieval_metrics_for_execution_units(
        case=case,
        ranked_ids=ranked_ids,
        grade_by_id=grade_by_id,
        scope="end_to_end",
    )
    pure, pure_scope = _retrieval_metrics_for_execution_units(
        case=case,
        ranked_ids=ranked_ids,
        grade_by_id=grade_by_id,
        scope="pure",
    )

    assert metric_scope == "per_cohort_execution_unit"
    assert end_to_end["hit_at_1"] == 1.0
    assert pure_scope == "request_global"
    assert pure["hit_at_5"] == 0.0


def test_source_first_retrieval_is_regulation_only_and_natural() -> None:
    legacy = load_json(LEGACY_BUNDLE / "retrieval_cases.json")
    docstore = load_json(DOCSTORE)

    cases = rebuild_retrieval(legacy, docstore)
    docs_by_id = {str(item.get("_id") or ""): item for item in docstore}

    assert len(cases) == 180
    assert Counter(case["eval_split"] for case in cases) == {
        "realistic": 135,
        "stress": 45,
    }
    assert len({normalize_query(case["query"]) for case in cases}) == 180
    assert all(case["expected_path"] == "regulation_rag" for case in cases)
    assert all(case["case_type"] == "regulation_true_rag" for case in cases)
    assert all(
        (docs_by_id[judgment["parent_section_id"]].get("metadata") or {}).get(
            "content_type"
        )
        == "regulation_text"
        for case in cases
        for judgment in case["relevance_judgments"]
    )
    normalized_queries = [normalize_query(case["query"]) for case in cases]
    assert not any(
        normalize_query(fragment) in query
        for fragment in FORBIDDEN_QUERY_FRAGMENTS
        for query in normalized_queries
    )
    assert not any("ký túc xá" in case["query"].casefold() for case in cases)


def test_architecture_v3_bundle_validates_with_manifest_driven_counts(
    tmp_path: Path,
) -> None:
    target = tmp_path / "architecture_v3"

    manifest = build_bundle(LEGACY_BUNDLE, target)
    result = validate_bundle(target, DOCSTORE)

    assert manifest["counts"]["deterministic"] == 144
    assert manifest["counts"]["retrieval"] == 180
    assert manifest["retrieval_contract"] == "regulation-rag-source-first-v3"
    assert manifest["source_qdrant_collection"] == "student_handbook_semantic_v31"
    assert manifest["source_mongo_collection"] == "parent_docs_v31"
    assert result["valid"], result["errors"]
    assert result["warnings"] == []
