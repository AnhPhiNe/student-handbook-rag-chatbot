from typing import Any


def build_phase7_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    intent_count = {}
    strategy_count = {}

    for item in results:
        intent = item.get("intent")
        strategy = item.get("strategy")

        intent_count[intent] = intent_count.get(intent, 0) + 1
        strategy_count[strategy] = strategy_count.get(strategy, 0) + 1

    return {
        "phase": "phase_7_query_router_and_retrieval_strategy",
        "total_test_queries": len(results),
        "intent_count": intent_count,
        "strategy_count": strategy_count,
        "results": results,
        "status": "completed",
    }