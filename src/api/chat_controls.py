from __future__ import annotations

import contextlib
import ipaddress
import math
import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque
from uuid import UUID

from fastapi import HTTPException, Request


DEFAULT_MAX_QUERY_CHARS = 1000
DEFAULT_RATE_LIMIT_PER_MINUTE = 5
DEFAULT_IP_RATE_LIMIT_PER_MINUTE = 120
DEFAULT_MAX_CONCURRENT_CHAT = 3
DEFAULT_MAX_QUEUE_SIZE = 10
DEFAULT_QUEUE_TIMEOUT_SECONDS = 15.0
CLIENT_ID_HEADER = "X-Client-ID"
TRUE_CLIENT_IP_HEADERS = (
    "CF-Connecting-IP",
    "X-Real-IP",
    "X-Forwarded-For",
)
_RATE_LIMIT_BUCKETS: dict[str, Deque[float]] = defaultdict(deque)
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_LAST_CLEANUP = 0.0
_CAPACITY_LOCK = threading.Lock()
_CAPACITY_LIMITER = None
_CAPACITY_SETTINGS: tuple[int, int, float] | None = None


class ChatCapacityError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class QueueTicket:
    def __init__(self, limiter: 'ChatCapacityLimiter', ticket_id: int):
        self.limiter = limiter
        self.ticket_id = ticket_id

    @property
    def position(self) -> int:
        return self.limiter.get_position(self.ticket_id)

    def try_acquire(self, timeout: float = 1.0) -> bool:
        return self.limiter.try_acquire(self.ticket_id, timeout)

    def leave_queue(self) -> None:
        self.limiter.remove_from_queue(self.ticket_id)


class ChatCapacityLimiter:
    def __init__(self, *, max_concurrent: int, max_queue_size: int) -> None:
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._active_count = 0
        self._queue: Deque[int] = deque()
        self._ticket_counter = 0

    def enter_queue(self) -> QueueTicket:
        with self._lock:
            if self._active_count >= self.max_concurrent and len(self._queue) >= self.max_queue_size:
                raise ChatCapacityError("queue_full")
            self._ticket_counter += 1
            ticket_id = self._ticket_counter
            self._queue.append(ticket_id)
            return QueueTicket(self, ticket_id)

    def get_position(self, ticket_id: int) -> int:
        with self._lock:
            try:
                # position 1 means you are next in line
                return self._queue.index(ticket_id) + 1
            except ValueError:
                return 0

    def try_acquire(self, ticket_id: int, timeout: float) -> bool:
        start = time.monotonic()
        with self._condition:
            while True:
                if self._queue and self._queue[0] == ticket_id and self._active_count < self.max_concurrent:
                    self._queue.popleft()
                    self._active_count += 1
                    return True
                
                remaining = timeout - (time.monotonic() - start)
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)

    def release(self) -> None:
        with self._condition:
            self._active_count = max(0, self._active_count - 1)
            self._condition.notify_all()

    def remove_from_queue(self, ticket_id: int) -> None:
        with self._lock:
            if ticket_id in self._queue:
                self._queue.remove(ticket_id)


def validate_chat_query(raw_query: str) -> str:
    """Kiểm tra và làm sạch chuỗi truy vấn (câu hỏi) từ người dùng.

    Hàm này đảm bảo rằng chuỗi truy vấn không rỗng và không vượt quá độ dài tối đa cho phép.
    Nếu truy vấn không hợp lệ, nó sẽ ném ra một lỗi HTTP.

    Args:
        raw_query (str): Chuỗi truy vấn thô (chưa được xử lý) từ người dùng.

    Returns:
        str: Chuỗi truy vấn đã được làm sạch và hợp lệ.

    Raises:
        HTTPException:
            - Nếu truy vấn rỗng (status_code=400).
            - Nếu truy vấn quá dài so với giới hạn cho phép (status_code=400).
    """
    query = raw_query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty")

    max_chars = max_query_chars()
    if len(query) > max_chars:
        raise HTTPException(
            status_code=400,
            detail=f"Query must be at most {max_chars} characters",
        )
    return query


def enforce_chat_rate_limit(request: Request) -> None:
    """Apply a per-browser limit plus a broader public-IP abuse guard."""
    client_limit = rate_limit_per_minute()
    ip_limit = ip_rate_limit_per_minute()
    if client_limit <= 0 and ip_limit <= 0:
        return

    client_host = _client_ip_for_rate_limit(request)
    client_id = _validated_client_id(request.headers.get(CLIENT_ID_HEADER))
    checks: list[tuple[str, int]] = []

    if client_id:
        if client_limit > 0:
            checks.append((f"client:{client_id}", client_limit))
        if ip_limit > 0:
            checks.append((f"ip:{client_host}", ip_limit))
    else:
        # Older or non-browser clients keep working without the custom header.
        fallback_limit = client_limit if client_limit > 0 else ip_limit
        if fallback_limit > 0:
            checks.append((f"ip:{client_host}", fallback_limit))

    now = time.monotonic()
    with _RATE_LIMIT_LOCK:
        _cleanup_rate_limit_buckets(now)
        retry_after = 0
        for key, limit in checks:
            bucket = _RATE_LIMIT_BUCKETS[key]
            while bucket and now - bucket[0] >= 60:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, math.ceil(60 - (now - bucket[0])))
                break

        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        for key, _ in checks:
            _RATE_LIMIT_BUCKETS[key].append(now)


def _validated_client_id(raw_value: str | None) -> str | None:
    """Accept only anonymous UUIDs so arbitrary headers cannot grow bucket keys."""
    if not raw_value:
        return None
    try:
        return str(UUID(raw_value.strip()))
    except (ValueError, AttributeError):
        return None


def _client_ip_for_rate_limit(request: Request) -> str:
    """Return a stable client IP, optionally trusting reverse proxy headers."""
    fallback = request.client.host if request.client else "unknown"
    if not _trust_proxy_headers():
        return fallback

    for header in TRUE_CLIENT_IP_HEADERS:
        raw_value = request.headers.get(header)
        if not raw_value:
            continue
        candidates = raw_value.split(",") if header == "X-Forwarded-For" else [raw_value]
        for candidate in candidates:
            value = candidate.strip()
            if _is_valid_ip(value):
                return value
    return fallback


def _trust_proxy_headers() -> bool:
    return os.getenv("STUDENT_RAG_TRUST_PROXY_HEADERS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _is_valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _cleanup_rate_limit_buckets(now: float) -> None:
    """Remove inactive sliding-window buckets once per minute."""
    global _RATE_LIMIT_LAST_CLEANUP
    if now - _RATE_LIMIT_LAST_CLEANUP < 60:
        return
    expired_keys = [
        key
        for key, bucket in _RATE_LIMIT_BUCKETS.items()
        if not bucket or now - bucket[-1] >= 60
    ]
    for key in expired_keys:
        _RATE_LIMIT_BUCKETS.pop(key, None)
    _RATE_LIMIT_LAST_CLEANUP = now


@contextlib.contextmanager
def chat_capacity_slot():
    """Context manager này giữ lại cho các hàm đồng bộ không cần streaming position. 
    Để stream position, hãy dùng limiter.enter_queue() trực tiếp."""
    settings = chat_capacity_settings()
    max_concurrent, _, timeout_seconds = settings
    if max_concurrent <= 0:
        yield
        return

    limiter = _chat_capacity_limiter(settings)
    ticket = limiter.enter_queue()
    try:
        if not ticket.try_acquire(timeout_seconds):
            raise ChatCapacityError("timeout")
        try:
            yield
        finally:
            limiter.release()
    finally:
        ticket.leave_queue()


def _chat_capacity_limiter(settings: tuple[int, int, float]) -> ChatCapacityLimiter:
    global _CAPACITY_LIMITER, _CAPACITY_SETTINGS
    max_concurrent, max_queue_size, _ = settings
    with _CAPACITY_LOCK:
        if _CAPACITY_LIMITER is None or _CAPACITY_SETTINGS != settings:
            _CAPACITY_LIMITER = ChatCapacityLimiter(
                max_concurrent=max_concurrent,
                max_queue_size=max_queue_size,
            )
            _CAPACITY_SETTINGS = settings
        return _CAPACITY_LIMITER


def chat_capacity_settings() -> tuple[int, int, float]:
    return (
        _env_int(
            "STUDENT_RAG_MAX_CONCURRENT_CHAT",
            DEFAULT_MAX_CONCURRENT_CHAT,
            minimum=0,
        ),
        _env_int(
            "STUDENT_RAG_MAX_QUEUE_SIZE",
            DEFAULT_MAX_QUEUE_SIZE,
            minimum=0,
        ),
        _env_float(
            "STUDENT_RAG_QUEUE_TIMEOUT_SECONDS",
            DEFAULT_QUEUE_TIMEOUT_SECONDS,
            minimum=0.0,
        ),
    )


def max_query_chars() -> int:
    """Lấy giá trị độ dài tối đa cho phép của một chuỗi truy vấn.

    Giá trị này được đọc từ biến môi trường có tên "STUDENT_RAG_MAX_QUERY_CHARS".
    Nếu biến môi trường không tồn tại hoặc không phải là số hợp lệ,
    hàm sẽ sử dụng giá trị mặc định. Giá trị trả về luôn là số dương.

    Returns:
        int: Số ký tự tối đa cho phép trong một truy vấn.
             Giá trị này luôn lớn hơn hoặc bằng 1.
    """
    raw_value = os.getenv("STUDENT_RAG_MAX_QUERY_CHARS", str(DEFAULT_MAX_QUERY_CHARS))
    try:
        value = int(raw_value)
    except ValueError:
        # Nếu giá trị trong biến môi trường không phải là số, dùng giá trị mặc định
        return DEFAULT_MAX_QUERY_CHARS
    return max(1, value)  # Đảm bảo giá trị trả về ít nhất là 1


def rate_limit_per_minute() -> int:
    """Lấy giá trị giới hạn số lượng yêu cầu mỗi phút.

    Giá trị này được đọc từ biến môi trường có tên "STUDENT_RAG_RATE_LIMIT_PER_MINUTE".
    Nếu biến môi trường không tồn tại hoặc không phải là số hợp lệ,
    hàm sẽ sử dụng giá trị mặc định. Giá trị trả về luôn là số không âm.

    Returns:
        int: Số lượng yêu cầu tối đa được phép trong một phút.
             Giá trị này luôn lớn hơn hoặc bằng 0.
    """
    raw_value = os.getenv(
        "STUDENT_RAG_RATE_LIMIT_PER_MINUTE",
        str(DEFAULT_RATE_LIMIT_PER_MINUTE),
    )
    try:
        value = int(raw_value)
    except ValueError:
        # Nếu giá trị trong biến môi trường không phải là số, dùng giá trị mặc định
        return DEFAULT_RATE_LIMIT_PER_MINUTE
    return max(0, value)  # Đảm bảo giá trị trả về ít nhất là 0


def ip_rate_limit_per_minute() -> int:
    """Return the broader public-IP abuse limit for identified browser clients."""
    return _env_int(
        "STUDENT_RAG_IP_RATE_LIMIT_PER_MINUTE",
        DEFAULT_IP_RATE_LIMIT_PER_MINUTE,
        minimum=0,
    )


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(minimum, value)


def _env_float(name: str, default: float, *, minimum: float) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError:
        return default
    return max(minimum, value)


def should_include_debug(include_debug: bool) -> bool:
    """Kiểm tra xem có nên hiển thị thông tin gỡ lỗi (debug) hay không.

    Quyết định này dựa trên hai yếu tố:
    1. Tham số `include_debug` được truyền vào hàm.
    2. Giá trị của biến môi trường "STUDENT_RAG_SHOW_DEBUG".

    Thông tin gỡ lỗi chỉ được hiển thị nếu cả `include_debug` là `True`
    VÀ biến môi trường "STUDENT_RAG_SHOW_DEBUG" được đặt thành một giá trị "true-ish"
    (ví dụ: "1", "true", "yes", "on", không phân biệt chữ hoa chữ thường).

    Args:
        include_debug (bool): Một giá trị boolean ban đầu cho biết có muốn hiển thị debug hay không.

    Returns:
        bool: `True` nếu nên hiển thị thông tin gỡ lỗi, ngược lại là `False`.
    """
    return include_debug and os.getenv("STUDENT_RAG_SHOW_DEBUG", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
