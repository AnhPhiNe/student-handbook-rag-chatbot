import asyncio
import os
import sys
import traceback
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

from src.generation.answer_pipeline import AnswerPipeline

async def main():
    pipeline = AnswerPipeline()
    query = "tui cần in bảng điểm thì đến đâu mới đúng"
    
    try:
        from src.generation.query_rewriter import QueryRewriteResult
        rewrite_result = QueryRewriteResult(
            original_query=query,
            effective_query=query,
            reason="test"
        )
        # Call the private method to see the exact exception
        res, _ = pipeline._run_verified_retrieval(query, rewrite_result)
        print("Success")
    except Exception as e:
        print("EXCEPTION IN RETRIEVAL:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
