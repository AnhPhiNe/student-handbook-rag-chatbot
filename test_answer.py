import asyncio
from src.generation.answer_pipeline import AnswerPipeline

async def main():
    print("Loading models...")
    answer_pipeline = AnswerPipeline()
    
    query = "bao nhiêu điểm thì mới được xem là qua môn"
    
    print(f"Generating answer...")
    output = answer_pipeline.process(query)
    
    print("\n" + "="*50)
    print("FINAL ANSWER:\n")
    print(output.get("final_answer"))
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
