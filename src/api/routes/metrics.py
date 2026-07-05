import os
import time
from typing import Any
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

# Khởi tạo kết nối Redis tĩnh để tái sử dụng
_redis_client = None

def get_redis_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
        
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis
            _redis_client = redis.from_url(redis_url, decode_responses=True)
            # Kiểm tra kết nối nhanh
            _redis_client.ping()
        except Exception as e:
            print(f"[Metrics] Redis connection failed: {e}")
            _redis_client = False # False means connection failed/disabled, avoid retrying
    else:
        _redis_client = False
        
    return _redis_client

@router.get("/active-users")
async def get_active_users(session_id: str = Query(None, description="Unique session ID of the client")) -> dict[str, Any]:
    """
    Đếm số lượng người dùng đang truy cập hệ thống thời gian thực sử dụng Redis Set.
    Mỗi session_id sẽ được lưu vào một Redis Set và tự động hết hạn sau 5 phút.
    """
    r = get_redis_client()
    
    if not r:
        # Fallback nếu không có Redis (ví dụ chạy local không docker)
        return {"active_users": 1, "status": "fallback"}
        
    TTL_SECONDS = 300  # 5 phút
    ZSET_KEY = "system:active_users_zset"
    
    try:
        current_time = int(time.time())
        
        # Nếu có session ID, thêm/cập nhật vào Sorted Set với score là thời gian hiện tại
        if session_id:
            r.zadd(ZSET_KEY, {session_id: current_time})
            
        # Dọn dẹp (xóa) những session có score (timestamp) cũ hơn 5 phút trước
        r.zremrangebyscore(ZSET_KEY, "-inf", current_time - TTL_SECONDS)
        
        # Lấy tổng số lượng session còn sống
        active_count = r.zcard(ZSET_KEY)
        
        # Cập nhật thời gian sống của bản thân cái ZSET để tránh tồn đọng mãi mãi nếu không ai gọi
        r.expire(ZSET_KEY, TTL_SECONDS * 2)
        
        return {"active_users": active_count, "status": "ok"}
            
    except Exception as e:
        print(f"[Metrics] Error tracking active users: {e}")
        return {"active_users": 1, "status": "error"}
