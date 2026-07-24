from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Đại diện cho một yêu cầu trò chuyện từ người dùng.

    Lớp này định nghĩa cấu trúc dữ liệu cho một yêu cầu trò chuyện, bao gồm câu hỏi
    của người dùng, các tùy chọn bổ sung như lịch sử trò chuyện và cờ gỡ lỗi.

    Attributes:
        query (str): Câu hỏi chính mà người dùng muốn hỏi. Đây là nội dung chính của yêu cầu.
        include_debug (bool): Nếu là `True`, yêu cầu sẽ bao gồm thông tin gỡ lỗi trong phản hồi.
            Mặc định là `False`.
        chat_history (list[dict[str, str]] | None): Một danh sách các tin nhắn trước đó
            trong cuộc trò chuyện. Mỗi tin nhắn là một từ điển có thể chứa khóa như 'role' và 'content'.
            Mặc định là `None` nếu không có lịch sử trò chuyện.
        cohort (str | None): Một chuỗi định danh nhóm người dùng, thường được sử dụng
            cho các thử nghiệm A/B hoặc phân tích. Mặc định là `None`.
    """

    query: str
    include_debug: bool = False
    chat_history: list[dict[str, str]] | None = None
    cohort: str | None = None


class ChatResponse(BaseModel):
    """Đại diện cho phản hồi từ hệ thống trò chuyện.

    Lớp này định nghĩa cấu trúc dữ liệu cho câu trả lời mà hệ thống gửi lại
    sau khi xử lý một yêu cầu trò chuyện, bao gồm câu trả lời, trạng thái và
    các thông tin bổ sung khác.

    Attributes:
        answer (str): Câu trả lời chính được tạo ra bởi hệ thống.
        status (str): Trạng thái của yêu cầu, ví dụ: "success" (thành công) hoặc "error" (lỗi).
        effective_query (str | None): Câu hỏi thực tế đã được xử lý bởi hệ thống,
            có thể khác với `query` gốc nếu có quá trình viết lại câu hỏi. Mặc định là `None`.
        query_rewrite (dict[str, Any] | None): Thông tin chi tiết về quá trình viết lại câu hỏi,
            nếu có. Mặc định là `None`.
        query_handling (dict[str, Any] | None): Quyết định chuẩn hóa hoặc nối ngữ cảnh
            đã được Router kiểm tra trước khi truy vấn.
        request_id (str | None): Một ID duy nhất cho mỗi yêu cầu, giúp theo dõi. Mặc định là `None`.
        run_id (str | None): Một ID duy nhất cho mỗi lần chạy xử lý nội bộ. Mặc định là `None`.
        latency_ms (float | None): Thời gian xử lý yêu cầu tính bằng mili giây. Mặc định là `None`.
    """

    answer: str
    status: str
    effective_query: str | None = None
    query_handling: dict[str, Any] | None = None
    query_rewrite: dict[str, Any] | None = None
    request_id: str | None = None
    run_id: str | None = None
    latency_ms: float | None = None
    intent: str | None = None
    strategy: str | None = None
    citations: list[dict[str, Any]] | None = None
    citations_used: list[dict[str, Any]] | None = None
    llm_called: bool = False
    used_cache: bool = False
    clarification_needed: bool = False
    error_type: str | None = None
    error_message: str | None = None
    debug: dict[str, Any] | None = None


class ChatFeedbackRequest(BaseModel):
    """Đại diện cho một yêu cầu phản hồi (feedback) từ người dùng về một cuộc trò chuyện.

    Lớp này được sử dụng để thu thập đánh giá và bình luận của người dùng về chất lượng
    của một câu trả lời cụ thể từ hệ thống trò chuyện.

    Attributes:
        run_id (str): ID của lần chạy xử lý mà người dùng đang cung cấp phản hồi.
            Điều này giúp liên kết phản hồi với một phiên trò chuyện cụ thể.
        score (float): Điểm đánh giá của người dùng cho câu trả lời, thường là một giá trị số
            (ví dụ: từ 1 đến 5).
        comment (str | None): Bình luận chi tiết của người dùng về câu trả lời. Mặc định là `None`.
        citations_used (list[dict[str, Any]]): Danh sách các nguồn tham khảo (trích dẫn)
            đã được sử dụng trong câu trả lời. Mặc định là một danh sách rỗng.
        clarification_needed (bool): Nếu là `True`, người dùng cảm thấy cần làm rõ thêm
            về câu trả lời. Mặc định là `False`.
        intent (str | None): Mục đích hoặc ý định của câu hỏi gốc của người dùng. Mặc định là `None`.
        strategy (str | None): Chiến lược mà hệ thống đã sử dụng để tạo ra câu trả lời. Mặc định là `None`.
        llm_called (bool): Nếu là `True`, có nghĩa là một mô hình ngôn ngữ lớn (LLM) đã được
            gọi để tạo ra câu trả lời. Mặc định là `False`.
        used_cache (bool): Nếu là `True`, câu trả lời đã được lấy từ bộ nhớ đệm thay vì
            tạo mới. Mặc định là `False`.
        error_type (str | None): Loại lỗi xảy ra (nếu có) trong quá trình tạo câu trả lời. Mặc định là `None`.
        error_message (str | None): Thông báo lỗi chi tiết (nếu có). Mặc định là `None`.
        debug (dict[str, Any] | None): Thông tin gỡ lỗi bổ sung liên quan đến phản hồi. Mặc định là `None`.
    """

    run_id: str
    score: float
    comment: str | None = None
    citations_used: list[dict[str, Any]] = Field(default_factory=list)
    clarification_needed: bool = False
    intent: str | None = None
    strategy: str | None = None
    llm_called: bool = False
    used_cache: bool = False
    error_type: str | None = None
    error_message: str | None = None
    debug: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Đại diện cho phản hồi về trạng thái sức khỏe của một dịch vụ.

    Lớp này được sử dụng để kiểm tra xem một dịch vụ có đang hoạt động bình thường không,
    cung cấp thông tin về trạng thái, tên dịch vụ và phiên bản.

    Attributes:
        status (str): Trạng thái sức khỏe của dịch vụ, ví dụ: "ok" (ổn định) hoặc "unhealthy" (không ổn định).
        service (str): Tên của dịch vụ đang được kiểm tra.
        version (str): Phiên bản hiện tại của dịch vụ.
    """

    status: str
    service: str
    version: str


class ArtifactStatus(BaseModel):
    """Đại diện cho trạng thái của một tài nguyên (artifact) cụ thể.

    Lớp này mô tả thông tin về một tài nguyên riêng lẻ, chẳng hạn như một mô hình
    học máy hoặc một tập dữ liệu, bao gồm đường dẫn, sự tồn tại và loại của nó.

    Attributes:
        path (str): Đường dẫn đến vị trí của tài nguyên.
        exists (bool): Nếu là `True`, tài nguyên được tìm thấy và tồn tại.
        kind (str): Loại của tài nguyên, ví dụ: "model" (mô hình), "data" (dữ liệu), "config" (cấu hình).
    """

    path: str
    exists: bool
    kind: str


class ArtifactHealthResponse(BaseModel):
    """Đại diện cho phản hồi về trạng thái sức khỏe của các tài nguyên cần thiết.

    Lớp này tổng hợp trạng thái sức khỏe của nhiều tài nguyên quan trọng mà một dịch vụ
    phụ thuộc vào, giúp kiểm tra xem tất cả các thành phần cần thiết có sẵn và hoạt động không.

    Attributes:
        status (str): Trạng thái sức khỏe tổng thể của các tài nguyên, ví dụ: "ok" hoặc "degraded" (suy giảm).
        required_artifacts (list[ArtifactStatus]): Một danh sách các đối tượng `ArtifactStatus`,
            mỗi đối tượng mô tả trạng thái của một tài nguyên cần thiết.
    """

    status: str
    required_artifacts: list[ArtifactStatus]
