from typing import Any


def build_retrieval_plan(
    query: str,
    routing: dict[str, Any],
    retrieval_query: str,
    detected_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    intent = routing["intent"]
    target_chunk_types = routing.get("target_chunk_types", [])

    if intent != "mixed_query":
        return [
            {
                "purpose": intent,
                "query": retrieval_query,
                "chunk_types": target_chunk_types,
                "top_k": 5,
            }
        ]

    plans = []

    q = query.lower()

    if any(k in q for k in ["mẫu đơn", "đơn", "biểu mẫu", "giấy xác nhận"]):
        plans.append(
            {
                "purpose": "form",
                "query": retrieval_query,
                "chunk_types": ["form"],
                "top_k": 2,
            }
        )

    if any(k in q for k in ["điều kiện", "quy định", "thủ tục", "cần đáp ứng"]):
        plans.append(
            {
                "purpose": "regulation",
                "query": retrieval_query,
                "chunk_types": ["regulation"],
                "top_k": 3,
            }
        )

    if any(k in q for k in ["ktx", "ký túc xá", "nội trú", "tiêu chí", "xét"]):
        plans.append(
            {
                "purpose": "procedure",
                "query": retrieval_query,
                "chunk_types": ["procedure"],
                "top_k": 3,
            }
        )

    if any(k in q for k in ["liên hệ", "phòng nào", "email", "số điện thoại", "địa chỉ"]):
        plans.append(
            {
                "purpose": "office",
                "query": retrieval_query,
                "chunk_types": ["office_directory"],
                "top_k": 2,
            }
        )

    if not plans:
        plans.append(
            {
                "purpose": "mixed_default",
                "query": retrieval_query,
                "chunk_types": target_chunk_types,
                "top_k": 5,
            }
        )

    return plans


def merge_plan_results(results_by_plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = []
    seen_ids = set()

    for plan_result in results_by_plan:
        purpose = plan_result["purpose"]

        for item in plan_result["results"]:
            chunk_id = item["chunk_id"]

            if chunk_id in seen_ids:
                continue

            new_item = dict(item)
            new_item["retrieval_purpose"] = purpose
            merged.append(new_item)
            seen_ids.add(chunk_id)

    return merged