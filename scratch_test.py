import asyncio
import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

from src.generation.answer_pipeline import AnswerPipeline

async def main():
    pipeline = AnswerPipeline()
    query = "tui cần in bảng điểm thì đến đâu mới đúng"
    print(f"Query: {query}")
    
    response = pipeline.answer(query)
    retrieved_items = response.get("citations", [])
    
    print("\n--- RETRIEVED CHUNKS ---")
    for idx, item in enumerate(retrieved_items[:5]):
        print(f"[{idx}] Score: {item.get('score')} | Type: {item.get('chunk_type')} | Title: {item.get('title')}")
        print(f"Content:\n{item.get('content_preview', '')}\n")
        
    if response.get("error_message"):
        print(f"\n--- ERROR ---")
        print(response.get("error_message"))

    print("\n--- FINAL ANSWER ---")
    print(response.get("answer"))

if __name__ == "__main__":
    asyncio.run(main())
