from __future__ import annotations

from pathlib import Path

from scripts.build_architecture_eval_v2 import (
    build_bundle,
    expand_general_relevance,
    migrate_deterministic,
)
from src.evaluation.dataset import file_hash, load_json, validate_bundle
from src.evaluation.suites import evaluate_deterministic_v2


ROOT = Path(__file__).resolve().parents[1]
LEGACY_BUNDLE = ROOT / "data" / "eval" / "final_holdout"
DOCSTORE = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"


def test_deterministic_migration_uses_query_plan_table_first_contract() -> None:
    legacy = load_json(LEGACY_BUNDLE / "deterministic_tool_cases.json")

    migrated = migrate_deterministic(legacy)

    assert len(migrated) == 120
    positive = next(case for case in migrated if case["case_type"] == "positive")
    negative = next(case for case in migrated if case["case_type"] == "hard_negative")
    ambiguous = next(case for case in migrated if case["case_type"] == "ambiguous")
    assert positive["expected_plan"]["allowed_modes"] == ["structured"]
    assert positive["expected_plan"]["lookup_types"]
    assert "expected_item_count" not in positive
    assert negative["expected_plan"]["allowed_modes"] == ["rag"]
    assert ambiguous["expected_plan"]["allowed_modes"] == ["clarify"]
    faculty_directory = next(case for case in migrated if case["id"] == "v9_det_071")
    compound_rag = next(case for case in migrated if case["id"] == "v9_det_090")
    table_first_duration = next(case for case in migrated if case["id"] == "v9_det_105")
    assert faculty_directory["expected_plan"]["lookup_types"] == ["program"]
    assert compound_rag["expected_plan"]["task_count"] == 2
    assert table_first_duration["legacy_case_type"] == "ambiguous"
    assert table_first_duration["case_type"] == "ambiguous"
    assert table_first_duration["evaluation_case_type"] == "positive"
    assert table_first_duration["expected_plan"]["lookup_types"] == ["study_duration"]


def test_architecture_v2_bundle_validates_against_current_build(tmp_path: Path) -> None:
    target = tmp_path / "architecture_v2"

    manifest = build_bundle(LEGACY_BUNDLE, target)
    result = validate_bundle(target, DOCSTORE)

    assert manifest["evaluation_contract"] == "query-plan-table-first-v2"
    assert manifest["docstore_hash"] == file_hash(DOCSTORE)
    assert manifest["source_qdrant_collection"] == "student_handbook_semantic_v31"
    assert manifest["source_mongo_collection"] == "parent_docs_v31"
    assert result["valid"], result["errors"]
    assert result["warnings"] == []


def test_deterministic_v2_scores_query_plan_and_full_table(monkeypatch) -> None:
    class FakePipeline:
        def _run_retrieval(self, query: str, *, cohort: str | None = None):
            assert query == "IELTS 5.5 tương đương bậc mấy?"
            assert cohort == "K51"
            return {
                "query_plan": {
                    "out_of_domain": False,
                    "tasks": [
                        {
                            "id": "t1",
                            "mode": "structured",
                            "lookup_type": "foreign_language",
                            "cohorts": ["K51"],
                        }
                    ],
                },
                "task_results": [{"task_id": "t1", "coverage": "covered"}],
                "structured_result": {
                    "lookup_type": "foreign_language",
                    "items": [
                        {
                            "certificate": "IELTS",
                            "equivalent_level_4": "5.5 - 6.5",
                        }
                    ],
                    "cohort": "K51",
                    "source_parent_id": "source-1",
                    "content_type": "structured_lookup",
                },
                "citations": [
                    {
                        "chunk_id": "source-1",
                        "cohort": "K51",
                        "chunk_type": "structured_lookup",
                    }
                ],
                "needs_llm_answer": True,
                "needs_clarification": False,
                "planner_fallback": None,
            }

    import src.generation.answer_pipeline as answer_pipeline

    monkeypatch.setattr(answer_pipeline, "AnswerPipeline", FakePipeline)
    report = evaluate_deterministic_v2(
        [
            {
                "id": "det-v2-1",
                "case_type": "positive",
                "query": "IELTS 5.5 tương đương bậc mấy?",
                "cohort": "K51",
                "expected_llm_called": True,
                "expected_citation_cohort": "K51",
                "expected_contains_any": ["5.5 - 6.5"],
                "expected_plan": {
                    "task_count": 1,
                    "allowed_modes": ["structured"],
                    "lookup_types": ["foreign_language"],
                    "cohorts": ["K51"],
                    "out_of_domain": False,
                    "needs_clarification": False,
                },
            }
        ]
    )

    assert report["evaluation_contract"] == "query-plan-table-first-v2"
    assert report["summary"]["accuracy"] == 1.0
    assert report["summary"]["table_first_evidence_accuracy"] == 1.0
    assert report["cases"][0]["passed"] is True


def test_general_relevance_expands_equivalent_cohort_editions() -> None:
    cases = [
        {
            "id": "general-1",
            "cohort": "general",
            "relevance_judgments": [
                {"parent_section_id": "K50_article", "grade": 2}
            ],
        }
    ]
    docstore = [
        {
            "_id": "K50_article",
            "metadata": {
                "document_title": "Quy chế đào tạo",
                "title": "Điều kiện tốt nghiệp",
                "cohort": "K50",
            },
        },
        {
            "_id": "K51_article",
            "metadata": {
                "document_title": "Quy chế đào tạo",
                "title": "Điều kiện tốt nghiệp",
                "cohort": "K51",
            },
        },
    ]

    expanded = expand_general_relevance(cases, docstore)

    assert expanded[0]["relevance_scope"] == "any_equivalent_cohort_edition"
    assert {
        item["parent_section_id"] for item in expanded[0]["relevance_judgments"]
    } == {"K50_article", "K51_article"}
