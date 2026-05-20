import argparse
import time
from pathlib import Path
from typing import Any

from src.common.console import configure_utf8_stdio
from src.common.env_loader import load_project_env

from .io_utils import save_json
from .phase8_pipeline import DEFAULT_CONFIG_PATH, Phase8AnswerPipeline


TEST_QUERIES = [
    "Học vụ liên hệ ai?",
    "CNTT ở đâu?",
    "Giấy tờ sinh viên làm ở đâu?",
    "Học bổng hỏi ai?",
    "Phòng CNTT ở đâu?",
    "Khoa CNTT ở đâu?",
    "Có thể học vượt để ra trường sớm không?",
    "Có giới hạn số lần học lại một môn không?",
    "Muốn tạm nghỉ học cần mẫu đơn nào?",
    "Điểm rèn luyện 85 là loại gì?",
    "Tính điểm học bổng nếu GPA 3.2 và rèn luyện 90",
    "Email phòng CTCT-HSSV là gì?",
    "Điều kiện xét học bổng khuyến khích học tập là gì?",
    "Đơn xin vào KTX cần thông tin gì?",
    "Form xin xác nhận sinh viên nằm ở trang nào?",
    "GPA 3.4 là loại học lực gì?",
    "Điểm B+ quy đổi sang thang điểm 4 là bao nhiêu?",
    "Khoa Công nghệ thông tin có ngành nào?",
    "Khoa Tiếng Anh có những ngành nào?",
    "Quy trình vào ký túc xá như thế nào?",
    "Thủ tục xét học bổng gồm những bước nào?",
    "Học vụ",
    "Giấy tờ",
    "Liên hệ ai?",
]

EXPECTED_RESULTS = {
    "Học vụ liên hệ ai?": {
        "status": "needs_clarification",
        "llm_called": False,
        "clarification_needed": True,
    },
    "CNTT ở đâu?": {
        "status": "needs_clarification",
        "llm_called": False,
        "clarification_needed": True,
    },
    "Giấy tờ sinh viên làm ở đâu?": {
        "status": "needs_clarification",
        "llm_called": False,
        "clarification_needed": True,
    },
    "Học bổng hỏi ai?": {
        "status": "needs_clarification",
        "llm_called": False,
        "clarification_needed": True,
    },
    "Phòng CNTT ở đâu?": {
        "intent": "office_query",
        "clarification_needed": False,
    },
    "Khoa CNTT ở đâu?": {
        "intent": "faculty_query",
        "clarification_needed": False,
    },
    "Có thể học vượt để ra trường sớm không?": {
        "clarification_needed": False,
    },
    "Có giới hạn số lần học lại một môn không?": {
        "clarification_needed": False,
    },
    "Muốn tạm nghỉ học cần mẫu đơn nào?": {
        "clarification_needed": False,
    },
    "Điểm rèn luyện 85 là loại gì?": {
        "clarification_needed": False,
    },
}


def main() -> None:
    configure_utf8_stdio()
    load_project_env()

    parser = argparse.ArgumentParser(description="Run robust Phase 8 batch test.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Config YAML path.")
    parser.add_argument("--limit", type=int, default=10, help="Max queries to run by default.")
    parser.add_argument("--all", action="store_true", help="Run all bundled test queries.")
    args = parser.parse_args()

    pipeline = Phase8AnswerPipeline(config_path=args.config)
    queries = TEST_QUERIES if args.all else TEST_QUERIES[: max(0, args.limit)]
    output_path = Path(pipeline.config["output"]["test_report"])

    results: list[dict[str, Any]] = []
    validation_errors: list[str] = []
    for query in queries:
        print("=" * 80)
        print("Query:", query)
        try:
            result = pipeline.answer(query)
        except Exception as exc:
            result = _build_unhandled_error_result(query, exc)

        validation_errors.extend(_validate_expected_result(query, result))
        results.append(result)
        save_json(_build_report(results, validation_errors), output_path)

        print(
            "Status:",
            result.get("status"),
            "| llm_called:",
            result.get("llm_called"),
            "| used_cache:",
            result.get("used_cache"),
        )
        print(result.get("answer", ""))
        for error in _validate_expected_result(query, result):
            print("Validation:", error)

        if result.get("llm_called"):
            time.sleep(float(pipeline.config.get("llm", {}).get("request_sleep_seconds", 2)))

    save_json(_build_report(results, validation_errors), output_path)
    print(f"\nPhase 8 batch test completed. Report saved: {output_path}")
    if validation_errors:
        print("\nValidation errors:")
        for error in validation_errors:
            print("-", error)
        raise SystemExit(1)


def _build_report(
    results: list[dict[str, Any]],
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    validation_errors = validation_errors or []
    summary = {
        "total_queries": len(results),
        "answered_count": sum(1 for result in results if result.get("status") == "answered"),
        "needs_clarification_count": sum(
            1 for result in results if result.get("status") == "needs_clarification"
        ),
        "fallback_count": sum(
            1
            for result in results
            if result.get("status") in {"fallback", "api_error", "retrieval_error", "low_confidence"}
        ),
        "api_error_count": sum(1 for result in results if result.get("status") == "api_error"),
        "cache_hit_count": sum(1 for result in results if result.get("used_cache") is True),
        "llm_call_count": sum(1 for result in results if result.get("llm_called") is True),
        "low_confidence_count": sum(1 for result in results if result.get("status") == "low_confidence"),
        "retrieval_error_count": sum(1 for result in results if result.get("status") == "retrieval_error"),
        "validation_error_count": len(validation_errors),
    }
    return {
        "phase": "phase_8_answer_generation_batch_test",
        "summary": summary,
        "total_queries": summary["total_queries"],
        "answered_count": summary["answered_count"],
        "fallback_count": summary["fallback_count"],
        "api_error_count": summary["api_error_count"],
        "cache_hit_count": summary["cache_hit_count"],
        "llm_call_count": summary["llm_call_count"],
        "validation_errors": validation_errors,
        "results": results,
        "status": "failed" if validation_errors else "completed",
    }


def _validate_expected_result(query: str, result: dict[str, Any]) -> list[str]:
    expected = EXPECTED_RESULTS.get(query)
    if not expected:
        return []

    errors: list[str] = []
    for field, expected_value in expected.items():
        actual_value = result.get(field)
        if actual_value != expected_value:
            errors.append(
                f"{query}: expected {field}={expected_value!r}, got {actual_value!r}"
            )
    return errors


def _build_unhandled_error_result(query: str, exc: Exception) -> dict[str, Any]:
    return {
        "query": query,
        "answer": "Mình gặp lỗi ngoài dự kiến khi xử lý câu hỏi này, nhưng batch test vẫn tiếp tục chạy.",
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
        "clarification_needed": False,
        "context_used": "",
    }


if __name__ == "__main__":
    main()
