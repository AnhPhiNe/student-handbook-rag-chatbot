# Phê duyệt architecture_v6_holdout

Ngày duyệt: 31/08/2026  
Phạm vi: câu hỏi, gold evidence, evaluator contract và cách công bố kết quả; **không bao gồm kết quả chạy hệ thống**.

## Quyết định

**PHÊ DUYỆT CÓ ĐIỀU KIỆN để freeze và chạy đúng một lần.**

Bộ v6 đủ rộng để đánh giá phiên bản hiện tại, không có dấu hiệu vá câu hỏi theo output của Qwen 3.8/Gemini và không cần tăng thêm số lượng. Không bổ sung RAGAS, reranker, LLM thứ ba, ablation hay stress tải lớn vào đợt này.

## Căn cứ phê duyệt

1. Bộ được xây offline và chưa đưa qua hệ thống đang đánh giá.
2. Có 140 deterministic, 160 retrieval, 150 answer-quality và 60 production request; 40 answer case được chọn audit trước khi có output.
3. 312 câu hỏi duy nhất trong 510 dòng liên kết giữa các suite; không có exact/accent-folded match với 1.675 câu lịch sử đọc được từ 283 file.
4. Đã rà semantic overlap để tìm paraphrase, thay các mục gần trùng rõ ràng; semantic score không bị dùng làm bằng chứng giả về tính mới.
5. Gold RAG chứa parent source, cohort, trích đoạn và fact; gold structured trỏ canonical record. Directory gold đã ghi giá trị cụ thể.
6. Validator chấp nhận đủ bốn suite, không lỗi/cảnh báo. Liên kết answer/production/audit và warm-cache repeat nhất quán.
7. Evaluator phân biệt full với smoke/partial, dùng đúng mẫu số, loại parent ID trùng trước metric và khóa resume theo dataset cùng run contract.

## Đánh giá overfitting

Không phát hiện overfitting nghiêm trọng:

- Không dùng output v6 để sửa câu, gold hoặc prompt.
- Không chỉ đổi cách nói của những lỗi development rồi gọi là test mới; các paraphrase rõ đã được thay.
- Structured có các hàng, ngưỡng biên và tổ hợp mới. Fact từng xuất hiện trước đây vẫn có thể tái sử dụng vì corpus/bảng hữu hạn; điều này được công bố, không che giấu.
- Retrieval trải trên semantic, Điều đích danh, dẫn chiếu và nhiều nguồn; không được chạy PhoRanker/reranker khác production.
- Một số atom cũ xuất hiện trong compound mới. Metric này đo composition generalization, không được mô tả là kiến thức hoàn toàn unseen.

## Đánh giá over-engineering

Không mở rộng thêm kiến trúc runtime. Những kiểm soát evaluator được giữ ở mức cần thiết:

- checkpoint sidecar chỉ khóa hash case, suite, settings và provenance/config đã khai báo;
- không hash toàn bộ môi trường/package/source lần thứ hai;
- không thêm semantic judge, post-processing câu trả lời hoặc protocol citation mới;
- production chỉ là kiểm tra bounded availability/latency/stream/cache, không biến thành load-testing framework.

Quy mô 140–160–150–60 là lớn hơn mức smoke nhưng hợp lý cho một lần benchmark CV. Tăng thêm sẽ tăng chi phí rà gold/judge nhiều hơn giá trị thông tin ở giai đoạn này.

## Hạn chế bắt buộc công bố

1. Đây là **new-question/scenario holdout trên cùng ba Sổ tay**, không phải unseen-document và không đảm bảo mọi fact chưa từng xuất hiện.
2. Deterministic và answer nghiêng về K51; phải báo breakdown khóa, không suy độ chính xác từng khóa chỉ từ điểm gộp.
3. Deterministic đo contract route/task/slot/resolution. Sai route là lỗi kiến trúc, nhưng không tự động chứng minh final answer sai.
4. Judge tự động được xem cùng deterministic checks và audit. Không dùng một điểm LLM judge duy nhất làm toàn bộ kết luận.
5. 24 graph-linked cases đo khả năng lấy đủ nguồn liên quan, không chứng minh graph tạo causal gain vì không làm ablation.
6. Production HTTP success không phải answer correctness. Chỉ báo availability, latency, TTFT, stream/cache contract và lỗi.
7. 40 case được Codex hỗ trợ đối chiếu nguồn theo ủy quyền của chủ dự án. Nếu chủ dự án không tự đọc lại, phải ghi **AI-assisted source audit**, không ghi independent human evaluation.
8. Kiểm tra overlap chỉ bao phủ lịch sử còn đọc được trong workspace; không tuyên bố `0% semantic leakage`.

## Quy tắc chạy và công bố

1. Freeze dataset/hash/commit trước lần gọi hệ thống đầu tiên.
2. Chạy lần lượt: deterministic → retrieval → generate/judge → production → audit; báo từng bộ trước khi sang bộ kế tiếp.
3. Không sửa runtime rồi chạy lại cùng v6 để nâng điểm. System failure chuyển regression cho phiên bản sau.
4. Nếu phát hiện lỗi gold/evaluator sau khi nhìn output, công bố case bị loại/sửa và lý do; không thay âm thầm.
5. Công bố tử số/mẫu số, missing/failed judge calls, confidence interval khi có và failure taxonomy.

## Kết luận

V6 được duyệt để đánh giá chính thức phiên bản runtime `b0560d1b06355737dd576ff8f01c4102c6fe7a8a`. Phê duyệt này không chứng nhận hệ thống đã đạt chất lượng; chất lượng chỉ được kết luận sau khi chạy và audit kết quả.
