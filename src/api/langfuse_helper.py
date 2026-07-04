import os
import uuid
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger("student_handbook_rag.api.langfuse_helper")

def push_trace_to_langfuse(
    trace_id: str, 
    name: str, 
    session_id: str | None, 
    input_text: str | Any, 
    output_text: str | Any, 
    metadata: dict | None = None,
    latency_ms: float | None = None,
    model: str | None = None,
    usage: dict | None = None,
    tags: list[str] | None = None,
    tracker: Any = None,
):
    """
    Gửi thông tin Trace + Generation lên Langfuse qua API Ingestion.
    Chạy trong thread riêng để không block luồng SSE.
    
    Args:
        trace_id: ID duy nhất của trace
        name: Tên trace (vd: "Chat (Stream)")
        session_id: Cohort / session
        input_text: Câu hỏi của user
        output_text: Câu trả lời của bot
        metadata: Thông tin bổ sung (intent, strategy, status...)
        latency_ms: Thời gian phản hồi (ms)
        model: Tên model LLM đã dùng (vd: "gemini-2.0-flash")
        usage: Token usage dict {"input": N, "output": N, "total": N}
        tags: Danh sách tags
    """
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
    
    if not public_key or not secret_key:
        logger.warning("LANGFUSE credentials not configured. Skipping trace log.")
        return
        
    url = f"{host.rstrip('/')}/api/public/ingestion"
    auth = (public_key, secret_key)
    
    now = datetime.now(timezone.utc)
    end_time = now.isoformat()
    
    if latency_ms:
        start_time = (now - timedelta(milliseconds=latency_ms)).isoformat()
    else:
        start_time = end_time
    
    generation_id = str(uuid.uuid4())
    meta = metadata or {}
    
    # Build trace tags
    trace_tags = tags or []
    if meta.get("intent"):
        trace_tags.append(f"intent:{meta['intent']}")
    if meta.get("strategy"):
        trace_tags.append(f"strategy:{meta['strategy']}")
    
    # Detect model from metadata or use default
    used_model = model or meta.get("model") or "llama-3.3-70b-versatile"
    
    # Build usage info for cost calculation
    usage_body = {}
    if usage:
        usage_body = {
            "input": usage.get("input", 0),
            "output": usage.get("output", 0),
            "total": usage.get("total", 0),
            "unit": "TOKENS"
        }
    
    batch = [
        {
            "id": trace_id,
            "type": "trace-create",
            "timestamp": end_time,
            "body": {
                "id": trace_id,
                "name": name,
                "sessionId": session_id,
                "input": input_text,
                "output": output_text,
                "metadata": meta,
                "tags": trace_tags,
            }
        }
    ]
    
    if tracker and hasattr(tracker, "get_steps"):
        print(f"[Langfuse] tracker has {len(tracker.get_steps())} steps: {[s.get('step_name') for s in tracker.get_steps()]}")
    else:
        print(f"[Langfuse] tracker is None or has no get_steps. tracker={tracker}")
    
    if tracker and hasattr(tracker, "get_steps") and tracker.get_steps():
        for step in tracker.get_steps():
            step_id = str(uuid.uuid4())
            step_usage = {
                "input": step.get("input_tokens", 0),
                "output": step.get("output_tokens", 0),
                "total": step.get("total_tokens", 0),
                "unit": "TOKENS"
            }
            batch.append({
                "id": step_id,
                "type": "generation-create",
                "timestamp": step.get("end_time") or end_time,
                "body": {
                    "id": step_id,
                    "traceId": trace_id,
                    "name": step.get("step_name", "Unknown Step"),
                    "startTime": step.get("start_time") or start_time,
                    "endTime": step.get("end_time") or end_time,
                    "model": step.get("model") or "unknown",
                    "input": "[Tracker Generation]",
                    "output": "[Tracker Generation]",
                    "metadata": step.get("metadata", {}),
                    "usage": step_usage
                }
            })
    else:
        generation_id = str(uuid.uuid4())
        batch.append({
            "id": generation_id,
            "type": "generation-create",
            "timestamp": end_time,
            "body": {
                "id": generation_id,
                "traceId": trace_id,
                "name": "LLM Generation",
                "startTime": start_time,
                "endTime": end_time,
                "model": used_model,
                "input": input_text,
                "output": output_text,
                "metadata": meta,
                **({"usage": usage_body} if usage_body else {})
            }
        })
        
    payload = {"batch": batch}
    try:
        with httpx.Client() as client:
            resp = client.post(url, json=payload, auth=auth, timeout=5.0)
            logger.info(f"Langfuse push_trace result: {resp.status_code}")
            
            if resp.status_code == 207:
                print(f"[Langfuse] push_trace {trace_id}: 207 Multi-Status. Details: {resp.text}")
            else:
                print(f"[Langfuse] push_trace {trace_id}: {resp.status_code}")
                
            if resp.status_code not in (200, 201, 207):
                logger.warning(f"Langfuse API error: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.warning(f"Failed to push trace to Langfuse: {e}")
        print(f"[Langfuse] push_trace FAILED: {e}")
