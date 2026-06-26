import sys
import os
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

from src.generation.answer_pipeline import AnswerPipeline

def main():
    pipeline = AnswerPipeline()
    query = sys.argv[1] if len(sys.argv) > 1 else "Cho mình xin số điện thoại Phòng Đào tạo"
    cohort = sys.argv[2] if len(sys.argv) > 2 else "K50-K51"
    
    print(f"Query: {query}")
    print(f"Cohort: {cohort}")
    try:
        res = pipeline._run_retrieval(query, cohort=cohort)
        for i, cit in enumerate(res.get("citations", [])):
            print(f"--- Chunk {i+1} ---")
            print(f"Title: {cit.get('title')}")
            print(f"Content: {str(cit.get('content') or '')[:150]}...")
            print(f"Score: {cit.get('score')}")
            print(f"Cohort: {cit.get('metadata', {}).get('cohort') if 'metadata' in cit else 'N/A'}")
            print(f"Pages: {cit.get('metadata', {}).get('source_pages') if 'metadata' in cit else cit.get('source_pages')}")
            print()
        print("Success")
    except Exception as e:
        import traceback
        print("EXCEPTION IN RETRIEVAL:")
        traceback.print_exc()

if __name__ == "__main__":
    main()
