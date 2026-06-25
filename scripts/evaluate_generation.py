from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.common.console import configure_utf8_stdio
from src.common.env_loader import load_project_env
from src.generation.answer_pipeline import DEFAULT_CONFIG_PATH, AnswerPipeline
from src.generation.groq_client import GroqClient

DEFAULT_CASES_PATH = Path("data/eval/generation_eval_cases.json")
DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/generation_eval_report.json")

JUDGE_PROMPT_TEMPLATE = """Bạn là giám khảo chuyên nghiệp đánh giá chất lượng câu trả lời của hệ thống RAG.
Dưới đây là Dữ liệu đầu vào:

[CÂU HỎI CỦA NGƯỜI DÙNG]
{query}

[NGỮ CẢNH TÌM ĐƯỢC BỞI HỆ THỐNG]
{context}

[CÂU TRẢ LỜI CỦA HỆ THỐNG]
{answer}

[ĐÁP ÁN CHUẨN]
{ground_truth}

Nhiệm vụ của bạn là chấm điểm từ 0.0 đến 1.0 cho 3 tiêu chí sau (trả về JSON). KHÔNG GIẢI THÍCH, CHỈ TRẢ VỀ JSON HỢP LỆ.
1. "faithfulness": Độ bám sát ngữ cảnh. Câu trả lời có hoàn toàn dựa trên [NGỮ CẢNH TÌM ĐƯỢC] không? Nếu có thông tin bịa đặt (hallucination) không có trong ngữ cảnh, trừ điểm. (1.0 = hoàn hảo, 0.0 = bịa hoàn toàn).
2. "relevancy": Độ liên quan. Câu trả lời có đúng trọng tâm [CÂU HỎI] không? Trả lời thừa không sao, nhưng nếu thiếu trọng tâm thì trừ điểm. (1.0 = đúng trọng tâm, 0.0 = hoàn toàn lạc đề).
3. "correctness": Độ chính xác. Nội dung của câu trả lời có khớp với [ĐÁP ÁN CHUẨN] không? (1.0 = hoàn toàn chính xác, 0.0 = sai lệch nội dung).

Định dạng trả về duy nhất (KHÔNG CÓ markdown blocks):
{{"faithfulness": 0.0, "relevancy": 0.0, "correctness": 0.0}}
"""

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")

def parse_judge_result(text: str) -> dict[str, float]:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    try:
        data = json.loads(text.strip())
        return {
            "faithfulness": float(data.get("faithfulness", 0.0)),
            "relevancy": float(data.get("relevancy", 0.0)),
            "correctness": float(data.get("correctness", 0.0)),
        }
    except Exception as e:
        print(f"Warning: Failed to parse judge output: {e}. Output was: {text}")
        return {"faithfulness": 0.0, "relevancy": 0.0, "correctness": 0.0}

def format_context(citations: list[dict[str, Any]]) -> str:
    parts = []
    for c in citations:
        parts.append(f"- Nguồn {c.get('chunk_id')}: {c.get('content')}")
    return "\n".join(parts)

def evaluate_case(case: dict[str, Any], pipeline: AnswerPipeline, judge: GroqClient) -> dict[str, Any]:
    query = str(case["query"])
    result = pipeline.answer(query)
    answer = str(result.get("answer") or "")
    
    # Get all context used for the answer
    citations = result.get("citations_used", [])
    context_str = format_context(citations)
    
    if not citations or not answer:
        # Failed to retrieve or answer
        return {
            "case_id": case.get("id"),
            "query": query,
            "status": result.get("status"),
            "error_type": result.get("error_type"),
            "metrics": {"faithfulness": 0.0, "relevancy": 0.0, "correctness": 0.0}
        }
        
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        query=query,
        context=context_str,
        answer=answer,
        ground_truth=case.get("ground_truth", "")
    )
    
    try:
        judge_res = judge.generate(prompt)
        if not judge_res.get("ok", False):
            print(f"Judge API Error: {judge_res.get('error_message')}")
            metrics = {"faithfulness": 0.0, "relevancy": 0.0, "correctness": 0.0}
            judge_raw_output = str(judge_res.get("error_message"))
        else:
            metrics = parse_judge_result(judge_res["text"])
            judge_raw_output = judge_res["text"]
    except Exception as e:
        print(f"Judge API Exception: {e}")
        metrics = {"faithfulness": 0.0, "relevancy": 0.0, "correctness": 0.0}
        judge_raw_output = str(e)
        
    return {
        "case_id": case.get("id"),
        "query": query,
        "status": result.get("status"),
        "intent": result.get("intent"),
        "metrics": metrics,
        "judge_raw_output": judge_raw_output
    }

def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    valid_cases = [r for r in results if r.get("status") == "answered"]
    
    if not valid_cases:
        return {"total_cases": len(results), "valid_cases": 0}
        
    faith_sum = sum(r["metrics"]["faithfulness"] for r in valid_cases)
    rel_sum = sum(r["metrics"]["relevancy"] for r in valid_cases)
    corr_sum = sum(r["metrics"]["correctness"] for r in valid_cases)
    
    return {
        "total_cases": len(results),
        "answered_cases": len(valid_cases),
        "faithfulness": round(faith_sum / len(valid_cases), 4),
        "relevancy": round(rel_sum / len(valid_cases), 4),
        "correctness": round(corr_sum / len(valid_cases), 4),
    }

from src.generation.gemini_client import GeminiClient
import time

def run_evaluation(config_path: Path, cases_path: Path) -> dict[str, Any]:
    load_project_env()
    cases = load_json(cases_path)
    
    # Sử dụng Gemini 3.1 Flash Lite siêu tốc độ
    generator = GeminiClient(model_name="gemini-3.1-flash-lite")
    pipeline = AnswerPipeline(config_path=config_path, llm_client=generator)
    pipeline.response_cache.enabled = False
    
    # Dùng Gemini 3.1 Flash Lite làm Giám khảo
    judge = GeminiClient(model_name="gemini-3.1-flash-lite", temperature=0.0)
    
    case_results = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] Evaluating query: {case['query'][:50]}...")
        result = evaluate_case(case, pipeline, judge)
        m = result["metrics"]
        print(f"   -> F:{m['faithfulness']:.2f} | R:{m['relevancy']:.2f} | C:{m['correctness']:.2f}")
        case_results.append(result)
        time.sleep(10) # Nghỉ 10 giây để đảm bảo 2 requests/câu không vượt quá 15 RPM
        
    summary = build_summary(case_results)
    return {
        "evaluation": "generation_quality_llm_judge",
        "config_path": str(config_path),
        "cases_path": str(cases_path),
        "pipeline_model": "llama-3.3-70b-versatile",
        "judge_model": "openai/gpt-oss-120b",
        "summary": summary,
        "cases": case_results,
    }

def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Evaluate generation quality using LLM-as-Judge.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--fail-under-faithfulness", type=float, default=None)
    args = parser.parse_args()

    report = run_evaluation(Path(args.config), Path(args.cases))
    save_json(report, Path(args.output))

    summary = report["summary"]
    print("\nGeneration Quality Evaluation (LLM-as-Judge)")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"Saved report: {args.output}")

    if args.fail_under_faithfulness is not None:
        val = summary.get("faithfulness", 0.0)
        if val < args.fail_under_faithfulness:
            print(f"Faithfulness {val} is below threshold {args.fail_under_faithfulness}")
            sys.exit(1)

if __name__ == "__main__":
    main()
