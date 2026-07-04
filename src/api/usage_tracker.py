from typing import Any
from datetime import datetime, timezone

class UsageTracker:
    """
    Sổ cái ghi nhận cấu trúc Pipeline RAG.
    Được sử dụng để chuyển số liệu token usage và độ trễ của từng model lên Langfuse.
    """
    def __init__(self):
        self._steps: list[dict[str, Any]] = []
        
    def record(self, step_name: str, model: str, input_tokens: int, output_tokens: int, 
               total_tokens: int, start_time: str, end_time: str, metadata: dict | None = None):
        self._steps.append({
            "step_name": step_name,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "start_time": start_time,
            "end_time": end_time,
            "metadata": metadata or {}
        })
        
    def get_steps(self) -> list[dict[str, Any]]:
        return self._steps
        
    def total_tokens(self) -> int:
        return sum(step["total_tokens"] for step in self._steps)
