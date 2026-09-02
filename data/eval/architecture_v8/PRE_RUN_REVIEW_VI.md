# Biên bản duyệt trước khi chạy Architecture V8

Ngày duyệt: 2026-09-03  
Trạng thái: **Đạt điều kiện đóng băng và chạy chính thức**

## Phạm vi đã duyệt

- Runtime được đánh giá: `09b1d3da5206f8b16a7f6c10e34793c813ff4d30`.
- Evaluator: `f8161ff827c396931c164ab8b26f0b1cc64b071f`.
- Deterministic: 140 case.
- Retrieval: 160 case.
- Generate + Judge: 150 case.
- Production: 60 request, gồm 50 query duy nhất và 10 lượt lặp có chủ đích để đo cache.
- Dữ liệu vẫn ghi `system_executed_on_dataset=false`; chưa có query V8 nào được gửi vào runtime trước khi đóng băng.

## Kết quả kiểm tra contract

- Validator profile `full`: hợp lệ, không có error hoặc warning.
- Evaluator contract tests: 41/41 đạt.
- Các assertion không áp dụng được ghi `N/A` và không được tính thành pass.
- Structured case có thể kiểm tra source, row/field và `resolved_result` khi gold khai báo.
- Directory record trực tiếp được nhận diện là evidence hợp lệ; không bị ép phải có hình dạng bảng.
- Retrieval khóa mode `vector_primary_graph_supplement`, không dùng reranker/PhoRanker.
- Qdrant khóa tại `student_handbook_semantic_v32`; MongoDB khóa tại `parent_docs_v32`.

## Duyệt câu hỏi và gold

- Tỷ lệ mục tiêu realistic/stress được giữ ở 80/20 cho Retrieval và Generate + Judge; stress case vẫn là yêu cầu có thể hiểu được, không cố tình đánh đố.
- Gold được dựng từ structured artifact hoặc nguồn Sổ tay trước khi chạy hệ thống, không lấy từ output của runtime.
- Đã kiểm tra lại các trường hợp structured theo hàng/giá trị, cohort, directory identity, compound task, clarification, unanswerable và out-of-domain.
- Đã sửa các lỗi biên soạn phát hiện trước freeze: mất chữ `đ` khi tạo câu không dấu, ghép hai nguồn cùng tiêu đề thành câu hỏi trùng ý, placeholder rỗng và mẫu câu lặp từ.

## Chính sách overlap

- So với 2.082 câu lịch sử: **0 câu trùng exact sau chuẩn hóa**.
- Giữa các suite V8: **0 câu trùng exact ngoài quan hệ lặp cache đã khai báo**.
- Có 12 tín hiệu lexical và 134 tín hiệu semantic từ ngưỡng 0,90; đây là tín hiệu review, không phải điều kiện loại vì corpus và capability hữu hạn.
- Bảy cặp có cosine từ 0,95 trở lên đã được kiểm tra: đều là cách diễn đạt mới của cùng chủ đề/Điều hoặc lượt production cache có chủ đích, không phải sao chép nguyên câu.
- V8 được phép kiểm tra lại cùng năng lực và cùng nguồn như các bộ cũ; chỉ cấm sao chép nguyên câu hoặc đưa failure cũ sang bằng cách đổi hời hợt một con số.

## Quy tắc sau khi chạy

- Mỗi suite chỉ chạy một lần trên đúng runtime/config đã khóa và dùng output mới.
- Chỉ chạy lại khi chứng minh lượt trước không hợp lệ do hạ tầng hoặc cấu hình; phải ghi rõ lý do.
- Không sửa runtime, câu hỏi hoặc gold rồi chạy lại V8 để nâng điểm.
- Failure được phân loại, đưa sang regression cho phiên bản kế tiếp và không làm thay đổi metric V8 chính thức.
- Báo kết quả từng suite trước khi chuyển sang suite tiếp theo; không gộp thành một điểm tổng.
