# Bộ đánh giá chính thức v1 — chờ duyệt trước khi chạy

Đã soạn đủ bốn suite và rà gold offline. Chưa freeze dataset/evaluator, chưa gọi model, chưa chạy đánh giá trên local hoặc HF. Các self-test không phải metric chất lượng chatbot.

| Suite | Số case/request | Thông thường | Khó nhưng tự nhiên |
|---|---:|---:|---:|
| Deterministic | 135 | 108 | 27 |
| Retrieval | 155 | 124 | 31 |
| Generate + Judge | 150 | 120 | 30 |
| Production | 60 | 48 | 12 |

## Nội dung và gold

- Deterministic: routing/task, cohort, applicability, bảng/trường, kết quả duy nhất khi đủ điều kiện fact-lock. Có fixture chống bỏ task, tráo evidence và dùng kết quả khóa này cho khóa khác. Chấp nhận các cách phân rã tác vụ hợp lệ; N/A không được tính là pass.
- Retrieval: 155 câu từ 31 nhóm nội dung; nguồn bắt buộc, nguồn nền và nguồn tương đương được phân biệt. Có ngữ cảnh hội thoại, nhiều nguồn và nhiều khóa. Xem `RETRIEVAL_REVIEW.md`; không tuyên bố tìm hết mọi nguồn tương đương trong toàn corpus.
- Answer: 150 câu bao gồm một ý, nhiều ý, nhiều thực thể, structured–structured, regulation–regulation, regulation–structured, đa khóa, một ý trả lời được/một ý cần hỏi thêm, dữ liệu cá nhân/live và ngoài phạm vi. Không cố phủ mọi tổ hợp bằng stress test.
- Gold được đối chiếu parent và catalog: đã kiểm tra điều kiện/ngoại lệ, phạm vi khóa, chủ thể học tập/rèn luyện, các tổ hợp học bổng và trường ngoại ngữ được hỏi. Đây là kiểm tra trên nguồn đã xử lý, không phải kiểm định lại toàn bộ PDF/OCR.
- Với Answer, chấm tương đương ngữ nghĩa; không bắt lặp nguyên văn gold, mã nội bộ hoặc mọi trường của một hàng. Lexical assertion không phù hợp được ghi N/A; Judge và audit đánh giá ý trả lời, grounding và citation. Gold không được đưa vào evidence sinh câu trả lời.
- Phân bổ khóa gần cân bằng. Case đa khóa giữ riêng khóa của từng ý; allocation cohort chỉ phục vụ phân bố, không thay phạm vi thực của câu hỏi.

Review là **AI-assisted**, không phải human audit độc lập. Không kiểm tra overlap với bộ cũ theo quyết định của chủ dự án; bộ này là đánh giá hệ thống, không được mô tả là holdout nghiên cứu độc lập.

## Production 60: quy trình đã soạn

60 request đo vận hành gồm **40 câu riêng biệt** và các lần lặp có chủ đích:

1. 20 cold RAG và 10 structured request.
2. 10 warm-cache request lặp đúng query/cohort/history đã có.
3. 10 streaming request ghép với request sync trước đó.
4. 10 burst request: 5 ở concurrency 3, 5 ở concurrency 5.

Trước khi chạy phải xác minh HF đúng commit/build/corpus và trạng thái cache. Client ID mới không chứng minh cache lạnh. Ghi cache hit/miss thực tế; phân tách cold/warm và streaming có cache, không gọi toàn bộ TTFT là cold TTFT. Ghi nhận vi phạm cache protocol thay vì âm thầm chạy lại cho đẹp số.

Streaming so sánh ý nghĩa/contract, không bắt chuỗi đáp án giống hệt sync. Fallback và lỗi API chỉ được đo khi thực sự xuất hiện; nếu không xảy ra thì độ bao phủ fallback là **N/A**, không phải 100%. Không chủ động gây lỗi hoặc timeout trên HF trong bộ này. Burst nhỏ không chứng minh sức chịu tải ở quy mô lớn.

Fixture offline đã mô phỏng đủ 60 HTTP request, gồm 10 stream, cache, HTTP 429 và SSE error. Không có request thật tới HF trong self-test.

## Kiểm tra và thay đổi

- 100 self-test liên quan official suites, contract và runtime snapshot đã pass; Ruff trên các builder/test và evaluator đã pass.
- 92 runtime/artifact hashes khớp snapshot. Runtime vẫn là `7d9dc3ca87f124be1282c2f01d7a42983badbad2`, corpus v33, Gemini 3.1 Flash Lite, Composer v3.24.
- Thay đổi chỉ ở dữ liệu đánh giá, builder/tests/tài liệu và evaluator; không sửa Planner, Composer, resolver hoặc retrieval runtime.
- Chưa có metric chính thức, chưa commit/push/deploy trong lượt soạn này. Scaffolding stratification/30 mẫu cũ không còn là quy trình áp dụng.

## Sau khi chủ dự án duyệt

Freeze chung dataset, evaluator, rubric và hashes; kiểm tra manifest hoàn chỉnh trước khi chạy. Chạy Deterministic → Retrieval → Generate + Judge trên runtime đã freeze, tắt response/router cache. Báo riêng từng suite; audit mọi failure và 40 answer theo seed `20260906`.

Sau local evaluation mới push/deploy ứng viên, xác minh HF, chạy Production 60. Không sửa runtime vì điểm thấp; lỗi nghiêm trọng cần quyết định riêng. Cleanup bộ cũ và cập nhật metric README chỉ sau khi có kết quả và tag lưu lịch sử.
