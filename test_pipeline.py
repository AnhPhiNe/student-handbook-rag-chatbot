from src.api.deps import get_answer_service
service = get_answer_service()
try:
    for chunk in service.answer_stream("Mấy điểm thì qua môn", chat_history=[], cohort="K50-K51"):
        print(chunk)
except Exception as e:
    import traceback
    traceback.print_exc()
