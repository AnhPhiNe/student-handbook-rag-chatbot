from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException, Request


DEFAULT_MAX_QUERY_CHARS = 500
DEFAULT_RATE_LIMIT_PER_MINUTE = 10
_RATE_LIMIT_BUCKETS: dict[str, Deque[float]] = defaultdict(deque)


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
    """Áp dụng giới hạn số lượng yêu cầu (rate limit) cho mỗi người dùng.

    Hàm này theo dõi số lượng yêu cầu mà một người dùng (được xác định bằng địa chỉ IP)
    gửi trong một khoảng thời gian nhất định (mặc định là 1 phút).
    Nếu người dùng gửi quá nhiều yêu cầu, họ sẽ bị chặn và nhận lỗi HTTP 429.

    Args:
        request (Request): Đối tượng yêu cầu HTTP từ FastAPI, chứa thông tin về người gửi
                           (ví dụ: địa chỉ IP của client).

    Returns:
        None: Hàm không trả về giá trị nào. Nếu giới hạn bị vượt quá, nó sẽ ném ra lỗi.

    Raises:
        HTTPException: Nếu người dùng vượt quá giới hạn số lượng yêu cầu (status_code=429).
    """
    limit = rate_limit_per_minute()
    if limit <= 0:  # Nếu giới hạn là 0 hoặc âm, tức là không áp dụng giới hạn
        return

    client_host = request.client.host if request.client else "unknown"
    now = time.monotonic()  # Lấy thời gian hiện tại
    bucket = _RATE_LIMIT_BUCKETS[client_host]  # Lấy "thùng" chứa các yêu cầu của client này

    # Xóa các yêu cầu đã cũ hơn 60 giây (1 phút) khỏi "thùng"
    while bucket and now - bucket[0] >= 60:
        bucket.popleft()

    # Nếu số lượng yêu cầu còn lại trong "thùng" đã đạt đến giới hạn
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Thêm thời gian của yêu cầu hiện tại vào "thùng"
    bucket.append(now)


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