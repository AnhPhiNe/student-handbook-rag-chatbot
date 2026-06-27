from __future__ import annotations

import os
import secrets
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import Header, HTTPException

if TYPE_CHECKING:
    from src.services import AnswerService


ADMIN_API_KEY_ENV = "STUDENT_RAG_ADMIN_API_KEY"


def verify_admin_api_key(
    x_admin_api_key: str | None = Header(default=None, alias="X-Admin-API-Key"),
) -> None:
    """Xác minh khóa API quản trị viên (Admin API Key) được cung cấp.

    Hàm này kiểm tra xem khóa API quản trị viên được gửi trong tiêu đề HTTP
    có khớp với khóa API mong đợi được lưu trữ trong biến môi trường hay không.
    Nếu khóa không khớp hoặc không được cung cấp, nó sẽ trả về lỗi HTTP 403
    (Forbidden - Bị cấm), ngăn chặn truy cập trái phép.

    Args:
        x_admin_api_key: Khóa API quản trị viên được lấy từ tiêu đề HTTP
            'X-Admin-API-Key'. Đây là một chuỗi hoặc None nếu không được cung cấp.

    Raises:
        HTTPException: Nếu khóa API quản trị viên không được cung cấp hoặc
            không hợp lệ, một lỗi HTTP 403 sẽ được trả về, kèm theo thông báo
            rằng khóa API quản trị viên là bắt buộc.
    """
    expected_key = os.getenv(ADMIN_API_KEY_ENV, "").strip()
    if not expected_key or not x_admin_api_key:
        raise HTTPException(status_code=403, detail="Admin API key required")
    if not secrets.compare_digest(x_admin_api_key, expected_key):
        raise HTTPException(status_code=403, detail="Admin API key required")


@lru_cache(maxsize=1)
def get_answer_service() -> "AnswerService":
    """Tải và cung cấp một thể hiện (instance) của AnswerService.

    Hàm này được thiết kế để chỉ tạo một thể hiện của AnswerService duy nhất
    trong suốt quá trình chạy của ứng dụng API. Nó sử dụng bộ nhớ đệm (cache)
    để đảm bảo rằng AnswerService chỉ được khởi tạo một lần, giúp tiết kiệm
    tài nguyên và tăng hiệu suất bằng cách tránh tạo lại đối tượng nhiều lần.

    Returns:
        Một thể hiện của lớp AnswerService đã được khởi tạo. Thể hiện này
        sẽ được tái sử dụng cho các lần gọi hàm tiếp theo.
    """
    from src.services import AnswerService

    return AnswerService()