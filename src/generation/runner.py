import argparse
from pathlib import Path
from typing import Any

from src.common.env_loader import load_project_env

from .io_utils import save_json
from .answer_pipeline import DEFAULT_CONFIG_PATH, AnswerPipeline


SAMPLE_QUERIES = [
    "Điểm rèn luyện 85 là loại gì?",
    "Muốn tạm nghỉ học cần mẫu đơn nào?",
    "Email phòng CTCT-HSSV là gì?",
]


def main() -> None:
    load_project_env()

    parser = argparse.ArgumentParser(description="Run answer generation.")
    parser.add_argument("query", nargs="*", help="Optional query to answer.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Config YAML path.")
    args = parser.parse_args()

    pipeline = AnswerPipeline(config_path=args.config)
    queries = [" ".join(args.query)] if args.query else SAMPLE_QUERIES

    results: list[dict[str, Any]] = []
    for query in queries:
        try:
            result = pipeline.answer(query)
        except Exception as exc:
            result = _build_unhandled_error_result(query, exc)

        results.append(result)
        print("=" * 80)
        print("Query:", query)
        print("Status:", result.get("status"))
        print("LLM called:", result.get("llm_called"))
        print("Used cache:", result.get("used_cache"))
        if result.get("error_type"):
            print("Error:", result.get("error_type"), "-", result.get("error_message"))
        print("\nAnswer:")
        print(result.get("answer", ""))
        print()

    report = {
        "phase": "phase_8_answer_generation",
        "total_queries": len(results),
        "results": results,
        "status": "completed",
    }
    output_path = Path(pipeline.config["output"]["test_report"])
    save_json(report, output_path)
    print(f"Phase 8 completed. Report saved: {output_path}")


def _build_unhandled_error_result(query: str, exc: Exception) -> dict[str, Any]:
    return {
        "query": query,
        "answer": "Mình gặp lỗi ngoài dự kiến khi xử lý câu hỏi này.",
        "status": "fallback",
        "error_type": "unknown",
        "error_message": str(exc),
        "intent": None,
        "strategy": None,
        "retrieval_query": None,
        "citations": [],
        "citations_used": [],
        "structured_result": None,
        "tool_result": None,
        "llm_called": False,
        "used_cache": False,
        "context_used": "",
    }


if __name__ == "__main__":
    main()
