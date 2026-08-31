# Kiểm tra chuẩn bị v6 — 31/08/2026

- `validate_bundle(..., require_frozen=False)`: hợp lệ, không lỗi/cảnh báo; đủ 140/160/150/60.
- Kiểm tra unit toàn dự án bằng pytest: **449 passed**, 18,21 giây. Đây không phải 449 câu v6 và không phải metric chất lượng câu trả lời.
- Ruff cho evaluator và test mới: đạt.
- `git diff --check`: đạt; Git chỉ cảnh báo chuyển LF/CRLF trên Windows.
- Rà trùng trên 1.675 câu lịch sử đọc từ 283 file: không trùng exact sau chuẩn hóa; semantic chỉ dùng rà soát, không chứng minh không trùng ý nghĩa.
- Liên kết production → answer, mẫu audit và warm-cache repeat: không phát hiện lỗi liên kết; 40 audit ID duy nhất, 50 câu production duy nhất.
- Chưa chạy Planner/Composer/retrieval trên dataset v6; chưa gọi Generate, Judge hoặc production suite.
- Các chỉnh sửa tracked chỉ ở evaluator/test. Runtime Planner, Composer, retrieval, database và UI không đổi trong giai đoạn này.
- Dataset đã được phê duyệt theo ủy quyền và freeze; chưa commit và chưa chạy. Hash chính thức nằm trong manifest của bundle frozen.

## Điểm cần hiểu trước khi duyệt

Không có bộ hữu hạn nào bảo đảm kiểm tra mọi lỗi. Bộ v6 bao phủ các luồng chính, có mẫu thực tế và stress, nhưng vẫn dùng lại kiến thức trên cùng ba Sổ tay. Điểm số sau này phải nêu đúng phạm vi này, tử số/mẫu số và giới hạn.

Lựa chọn câu hỏi/gold được AI hỗ trợ đối chiếu nguồn theo ủy quyền của chủ dự án. Không ghi là independent human review.

Một số câu clarification mới kiểm tra thiếu dữ kiện để kết luận cá nhân (ví dụ thiếu điểm Viết TOEIC, thiếu trọng số tín chỉ, thiếu ngày chứng chỉ). Khi duyệt cần phân biệt: không đủ để kết luận cuối không có nghĩa không thể cung cấp bảng hoặc chính sách tham khảo. Nếu cách chấm route quá chặt thì điều chỉnh gold trước freeze, không đợi xem output mới thay tiêu chí.
