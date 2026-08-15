from typing import Any

class UsageTracker:
    """
    Sổ cái ghi nhận cấu trúc Pipeline RAG.
    Được sử dụng để chuyển số liệu token usage và độ trễ của từng model lên LangSmith.
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
        return sum(int(step.get("total_tokens") or 0) for step in self._steps)

    def get_total_usage(self) -> dict[str, int]:
        input_tokens = sum(int(step.get("input_tokens") or 0) for step in self._steps)
        output_tokens = sum(int(step.get("output_tokens") or 0) for step in self._steps)
        total_tokens = sum(int(step.get("total_tokens") or 0) for step in self._steps)
        if total_tokens == 0 and (input_tokens > 0 or output_tokens > 0):
            total_tokens = input_tokens + output_tokens
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
