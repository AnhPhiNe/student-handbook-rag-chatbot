from src.retrieval.core.retrieval_planner import build_retrieval_plan


def test_retrieval_plan_preserves_scoped_content_types() -> None:
    plans = build_retrieval_plan(
        query="dia chi don vi mo ho",
        routing={
            "intent": "regulation_query",
            "target_chunk_types": ["office_directory"],
            "content_types": [
                "student_service_directory",
                "student_office_profile",
            ],
        },
        retrieval_query="dia chi don vi mo ho",
        detected_entities=[],
    )

    assert plans == [
        {
            "purpose": "regulation_query",
            "query": "dia chi don vi mo ho",
            "chunk_types": ["office_directory"],
            "content_types": [
                "student_service_directory",
                "student_office_profile",
            ],
            "top_k": 5,
        }
    ]
