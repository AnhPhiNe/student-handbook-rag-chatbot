# Hồ sơ duyệt architecture_v6_holdout

## Trạng thái

Đã chuẩn bị và được Codex phê duyệt theo ủy quyền của chủ dự án; **đã freeze nhưng chưa chạy hệ thống trên v6**. Không có điểm số v6 để đưa vào CV lúc này.

- Runtime dự kiến đánh giá: `b0560d1b06355737dd576ff8f01c4102c6fe7a8a`.
- Planner: Qwen 3.8-27B, reasoning low, native JSON Schema, strict=false.
- Composer: Gemini 3.1 Flash-Lite; Judge dự kiến: openai/gpt-oss-120b.
- Retrieval: vector_primary_graph_supplement, không reranker; collection student_handbook_semantic_v32.
- Không đổi prompt/runtime để phù hợp câu hỏi mới. Thay đổi evaluator chỉ phục vụ chấm/ghi nhận đúng bộ mới.

## Phân bố và cách chấm

| Bộ | Quy mô | Nội dung | Metric báo cáo |
| --- | ---: | --- | --- |
| Deterministic | 140 | 60 structured đơn, 28 compound, 24 ranh giới capability, 12 clarify, 8 thiếu dữ liệu, 8 ngoài phạm vi | Số đúng/tổng và % cho task/mode/slot, structured source/execution; tách lỗi route, slot, resolver. Tên deterministic chỉ contract được chấm, không có nghĩa LLM chạy lặp lại luôn giống nhau. |
| Retrieval | 160 | 96 semantic, 24 Điều đích danh, 24 dẫn chiếu graph, 16 nhiều nguồn | Hit@5, primary Hit@5, MRR, nDCG@5, độ phủ nhóm nguồn cần thiết, cohort leakage; tách subtype/cohort và số mẫu. |
| Generate + Judge | 150 | 72 RAG, 30 structured, 18 mixed, 10 clarify, 10 thiếu căn cứ, 10 OOD | Faithfulness, answer relevancy/correctness, citation/cohort và độ phủ các ý bắt buộc; báo riêng lỗi/thiếu judge và đối chiếu audit. |
| Production | 60 request / 50 câu | 20 cold RAG, 10 structured, 10 warm repeat, 10 stream, 10 burst | Availability, latency p50/p95, TTFT trên stream hợp lệ, cache hit và lỗi; HTTP thành công không đồng nghĩa nội dung đúng. |
| Audit | 40 chọn trước + mọi automatic failure | 16 RAG (4/phạm vi khóa), 8 structured, 6 mixed, 4 clarify, 3 thiếu căn cứ, 3 OOD | Đúng nội dung/phạm vi/nguồn, unsupported claim và phân loại lỗi. AI review không được gọi là human review độc lập nếu người dùng chưa thực sự kiểm tra. |

### Bao phủ và giới hạn

- Có cùng chủ đề nhưng khác output cần trả, biên điểm, câu nhiều ý, sai/thiếu thông tin, nguồn dẫn chiếu, cùng số Điều ở tài liệu khác và dữ liệu ngoài khả năng của Sổ tay.
- Retrieval: 120 câu thực tế, 40 câu nhiều ràng buộc. Generate: 117 thực tế, 33 stress. Stress không đồng nghĩa câu vô lý.
- Structured gồm ngoại ngữ, thời gian học, học bổng, điểm học tập và rèn luyện; directory gồm service, office, faculty, program. Công thức có trong compound, không có metric standalone formula riêng.
- Phân bố không cân bằng tuyệt đối theo khóa: deterministic K51/K50/K48–K49 = 111/18/11; answer = 92/31/19 và 8 general. K51 được ưu tiên; cần báo breakdown, không suy độ chính xác từng khóa từ điểm gộp.
- Bộ này đủ bao phủ các luồng chính để đánh giá phiên bản hiện tại; không tuyên bố kiểm thử mọi khả năng, bảo mật, tải lớn hay độ ổn định dài hạn.
- 24 câu graph-linked kiểm tra tìm đủ nguồn liên quan; không chứng minh graph là nguyên nhân tăng điểm nếu không có ablation.
- General question có gold theo từng cohort execution unit; không lấy nguồn của cohort khác làm đúng chỉ vì cùng số Điều.

## Trùng lặp với bộ cũ

- Inventory đọc được: 1675 câu lịch sử; 283 file, 0 lỗi đọc.
- Bộ hiện tại: 510 dòng trong 4 suite, 312 câu hỏi duy nhất; 0 dòng trùng câu lịch sử sau chuẩn hóa chữ hoa, dấu và khoảng trắng.
- Đã chạy kiểm tra lexical và semantic bằng mô hình multilingual cục bộ. Đây chỉ là công cụ gợi ý đối chiếu, không phải reranker của hệ thống và không chạy Planner/Composer.
- Đã thay 8 câu deterministic gần paraphrase (102/106/108/109/113/114/115/118) và câu retrieval019. ID giữ vị trí, nội dung đã thay trước freeze.
- **Vẫn có kiến thức/bảng/giá trị đã xuất hiện trong bộ cũ.** Tiêu chí đã thống nhất là câu hỏi, tình huống, biên hoặc tổ hợp mới trên cùng ba Sổ tay; không phải mọi fact đều mới.
- Câu cũ hỏi toàn Điều, câu mới hỏi một tình huống cụ thể có thể dùng cùng fact và được giữ với disclosure. Không chỉ đổi cohort hoặc đổi cách nói rồi tuyên bố kiến thức mới.
- Các suite cố ý dùng lại câu qua linked ID; 510 không phải 510 câu độc lập. 40 audit và 60 production cũng không phải holdout kiến thức độc lập.
- Không thể bảo đảm không trùng với hội thoại/file đã xóa hoặc câu lịch sử không còn trong workspace. Không công bố '0% semantic leakage'.

## Những điểm đã sửa trong giai đoạn chuẩn bị

- Đáp án directory ghi giá trị cụ thể, không chỉ 'đúng record'; phone Thư viện giữ đúng nhãn và số máy lẻ.
- Sửa chữ dính, gold clarification theo đúng thông tin thiếu; giữ điều kiện 'bị kỷ luật buộc thôi học' và 'danh hiệu sinh viên Giỏi' thay vì mở rộng nghĩa.
- Chọn audit/production theo nhóm trước khi có output, tránh chỉ lấy các câu đầu danh sách.
- Evaluator lấy đúng mẫu số, phân biệt report smoke/partial, giữ checkpoint gắn dataset/config, khử trùng source trước metric; không đổi kiến trúc trả lời.

## Quyết định duyệt

1. Phê duyệt có điều kiện để freeze và chạy đúng một lần; điều kiện chi tiết nằm trong `APPROVAL_REPORT_VI.md`.
2. Chạy lần lượt và báo cáo từng bộ trước khi qua bộ kế tiếp.
3. Không sửa hệ thống rồi chạy lại v6 để nâng điểm. Lỗi hệ thống chuyển regression; lỗi dataset/evaluator nếu phát hiện phải công khai, không âm thầm sửa đáp án sau khi thấy output.

## File

- CASEBOOK_VI.md: câu hỏi/đáp án rút gọn gộp theo query.
- deterministic_tool_cases.json, retrieval_cases.json, generated_answer_cases.json, production_cases.json: bộ chấm chi tiết.
- human_audit_template.json: 40 mẫu chọn trước, chưa có kết quả.
- manifest.json: cấu hình và hash đã freeze, `execution_approved=true`, nhưng `system_executed_on_dataset=false`.
- overlap_audit.json và historical_inventory.json: bằng chứng rà trùng; các lựa chọn cuối đang chờ người dùng phê duyệt.
