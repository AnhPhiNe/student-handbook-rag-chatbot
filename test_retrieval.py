import sys
import json
sys.stdout.reconfigure(encoding='utf-8')
from src.generation.answer_pipeline import AnswerPipeline
from src.common.env_loader import load_project_env
from src.generation.prompt_builder import build_answer_prompt
load_project_env()

pipeline = AnswerPipeline()
print("Running retrieval...")
retrieval_result, rewrite_result = pipeline._run_verified_retrieval(
    "mấy điểm thì qua môn vậy?", 
    pipeline.query_rewriter.rewrite("mấy điểm thì qua môn vậy?"), 
    cohort="K50-K51"
)

print("==== RETRIEVAL INTENT & STRATEGY ====")
print("Intent:", retrieval_result.get("intent"))
print("Strategy:", retrieval_result.get("strategy"))
print("Structured Result:", retrieval_result.get("structured_result"))
print("Has Context?", bool(retrieval_result.get("context_for_llm")))

prompt = build_answer_prompt(
    query="mấy điểm thì qua môn vậy?",
    retrieval_result=retrieval_result,
    selected_citations=None,
    cohort="K50-K51"
)
print("\n==== ACTUAL PROMPT ====")
print(prompt[:1000]) # Print first 1000 chars to check if the new instructions are there
print("=======================")

print("Calling LLM directly (Bypassing Cache)...")
llm_client = pipeline._get_llm_client()
llm_result = llm_client.generate(prompt)
print("LLM Output:")
print(llm_result.get('text'))
