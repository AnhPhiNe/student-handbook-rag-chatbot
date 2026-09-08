# Official v1 — báo cáo ba bộ đánh giá và giới hạn

Ngày tổng hợp: 2026-09-08. Phạm vi: kết quả local đã chạy; không phải chứng nhận production hoặc benchmark tải.

## 1. Quy tắc công bố

- Giữ riêng Deterministic, Retrieval và Generate + Judge; không tạo điểm tổng.
- Các số dưới đây lấy từ lượt chạy đầy đủ đã chọn, không thay điểm bằng kết quả audit hoặc lượt chạy lại riêng.
- Audit là **AI-assisted**, không phải đánh giá độc lập của con người. Không công bố số cờ Judge như số lỗi thực tế đã được xác nhận.
- Đây là bộ đánh giá hệ thống trong quá trình phát triển, **không phải independent holdout**. Dataset/gold đã được chỉnh trong quá trình phát triển; xóa bộ cũ không làm mất ảnh hưởng đó. Baseline, ablation và review độc lập dành cho giai đoạn nghiên cứu tiếp theo.
- Báo cáo này chốt cách diễn giải kết quả hiện có; không tự đóng băng Git, gắn tag hoặc chứng nhận worktree sạch. Metadata lịch sử còn ghi `draft_current_worktree` được giữ nguyên.

## 2. Phiên bản được đo

| Thành phần | Danh tính |
| --- | --- |
| HEAD khi chạy | `2a293721ff7998ba5ace0d81ca194d10f67581f3` |
| Pipeline / Normalizer | `v73-planner-owned-structured-inputs` / `v26-planner-owned-semantics` |
| Planner | `qwen/qwen3.8-27b`; prompt `structured-regulation-v41-explicit-request-count` |
| Composer | `gemini-3.1-flash-lite`; prompt `student-handbook-answer-v3.24-grounded-table-context` |
| Judge | `openai/gpt-oss-120b` |
| Corpus build | `build-934f1caf384f99ad96e9` |
| Qdrant | `student_handbook_semantic_v33`, 3.121 points |
| MongoDB | `parent_docs_v33`, 462 parents |
| Retrieval mode | `vector_primary_graph_supplement`; reranker tắt |
| Quality cache | Router và response cache tắt |

HEAD không đủ để nhận diện dataset: Generate dùng gold đã chỉnh ở worktree. SHA-256 của ba file dữ liệu hiện tại:

```text
deterministic_tool_cases.json
151ad17b08f11a814fe10183c9297754ce9a85d202f1c81d6f4c74a542db5afd
retrieval_cases.json
8b0f474d1036fb9fa25f1e901e4562ff8c067f82384959d078747a0a08171026
generated_answer_cases.json
0bdefd8a4a541363e9ea9f43721169f965bd2d7227aa9003ac050f7faa5fc49e
```

Hash đầu vào theo từng lượt chạy (kể cả việc Deterministic còn ghi nhận bản
`generated_answer_cases.json` trước khi sửa câu 081) và hash các report/audit
được ghi trong [`RESULTS_PROVENANCE.json`](RESULTS_PROVENANCE.json). Manifest
này chỉ là sổ provenance; nó không biến report ignored thành artifact tracked,
không thay metric và không khẳng định report được chạy trên commit docs này.

## 3. Deterministic — 135 câu

**Đạt contract: 124/135 = 91,85%; còn 11 failure.** Đây là kiểm tra đường xử lý/execution, không phải tỷ lệ câu trả lời cuối đúng.

| Nhóm | Đạt / tổng |
| --- | --- |
| K48–K49 | 44/45 |
| K50 | 41/45 |
| K51 | 39/45 |
| Thông thường | 102/108 |
| Stress | 22/27 |
| Compound | 10/15 |
| Rèn luyện | 9/9 |
| Khoa | 5/6 |
| Ngoại ngữ | 10/11 |
| Công thức (tra cứu, không tính toán) | 6/6 |
| Thiếu đầu vào | 6/6 |
| Phòng ban | 9/9 |
| Ngoài phạm vi | 6/6 |
| Chính sách | 12/12 |
| Ngành/chương trình | 9/9 |
| Học bổng | 9/12 |
| Điểm/xếp loại | 16/17 |
| Dịch vụ sinh viên | 9/9 |
| Thời gian học | 8/8 |

Assertion kết quả tra xác định (`resolved_result`) đạt **44/50 = 88%**, chỉ tính 50 câu áp dụng contract. Assertion không áp dụng là N/A, không được mặc định pass. Không có Planner fallback hoặc lỗi API được ghi nhận trong lượt này.

Hậu tố ID của 11 failure: `014, 033, 049, 054, 057, 081, 113, 114, 117, 119, 122`; dùng ID đầy đủ trong artifact nguồn khi truy vết.

Nhóm nguyên nhân đã audit: chọn sai operation/route, bỏ dữ kiện rõ, biểu diễn slot/span không khớp schema, nhầm loại đơn vị và phụ thuộc giữa task. Một câu sai route trong suite này vẫn có thể trả lời hữu ích ở pipeline Generate; không quy tất cả thành lỗi Resolver.

## 4. Retrieval — 155 câu

Đây là **end-to-end retrieval**, có ảnh hưởng của routing và structured, không phải phép đo riêng dense retriever.

| Metric | Kết quả |
| --- | --- |
| Hit@1 | 120/155 = 77,42% |
| Hit@3 | 139/155 = 89,68% |
| Hit@5 | **141/155 = 90,97%** |
| MRR | 0,8333 |
| nDCG@5 | 0,8443 |
| Required-source recall@5, trung bình theo case | 0,9011 |
| Cohort leakage được ghi nhận | 0/155 |
| Content-type match | 148/155 = 95,48% |

**Gate tổng của evaluator: FAIL**, do content-type match thấp hơn ngưỡng 98%. Không công bố toàn bộ gate đạt chỉ vì Hit@5 vượt 90%.

| Nhóm cohort | n | MRR | nDCG@5 |
| --- | ---: | ---: | ---: |
| K48–K49 | 52 | 0,7965 | 0,8144 |
| K50 | 51 | 0,8301 | 0,8366 |
| K51 | 50 | 0,8683 | 0,8770 |
| General | 2 | 1,0000 | 1,0000 |

Hit@5 thông thường: 112/124 = 90,32%; stress: 29/31 = 93,55%.

Audit 17 câu gồm 14 câu trượt top 5 và 3 câu thiếu nguồn bắt buộc trong top 5 dù nguồn có ở vị trí 6. Kết quả diagnostic là lượt riêng, không thay lượt chính. Có lỗi chọn đường xử lý, nguồn đúng xếp thấp và khác biệt giữa directory trả đúng ý với gold yêu cầu nguồn regulation. Không có căn cứ quy mọi miss thành lỗi cần reranker.

Tên field `synthetic_leak_rate` hiện là proxy content-type mismatch, không chứng minh bảng đã rò vào embedding. Sáu case có danh sách retrieved items rỗng không đồng nghĩa cả pipeline thiếu evidence: structured evidence được lưu riêng. Không đổi tên hoặc sửa evaluator trong báo cáo này.

## 5. Generate + Judge — 150 câu

150 output và 150 Judge rows hợp lệ. Các metric chất lượng sau là **điểm trung bình trên thang 0–1**, không phải số câu đúng/tổng câu:

| Metric | Mean, n=150 |
| --- | ---: |
| Answer correctness | **0,9305** |
| Faithfulness | **0,9591** |
| Answer relevancy | 0,9543 |
| Citation correctness | 0,9355 |
| Context precision | 0,5815 |
| Context recall | 0,8845 |

Context precision còn thấp là tín hiệu về evidence dư/nhiễu theo rubric Judge; không bỏ metric này khỏi báo cáo. Không diễn giải trực tiếp nó thành tỷ lệ factual error.

| Phân nhóm | n | Mean correctness |
| --- | ---: | ---: |
| Thông thường | 120 | 0,9544 |
| Stress | 30 | 0,8350 |
| Expected regulation RAG | 77 | 0,9523 |
| Expected structured | 65 | 0,9077 |
| Expected mixed | 3 | 0,8000 |
| Expected clarify | 3 | 0,9500 |
| Expected out-of-domain | 2 | 1,0000 |

Theo nhóm phân bổ chạy (`allocation_cohort`): K48–K49 50 câu, mean 0,9624; K50 50 câu, 0,9166; K51 50 câu, 0,9126. Đây là nhóm phân bổ, không đồng nhất với nhãn cohort gốc của mọi câu; câu general được phân bổ vào nhóm chạy. Nhóm nhỏ như mixed/clarify không đủ để kết luận độ ổn định toàn capability.

### Trạng thái, độ trễ và audit

- `answered`: 141/150; `low_confidence`: 2; `api_error`: 3; `needs_clarification`: 2; `out_of_domain`: 2. Trạng thái answered không chứng minh câu đúng; clarify/OOD cũng không mặc định là thất bại.
- 147/150 không gặp lỗi API; không gọi con số đó là tỷ lệ trả lời đúng.
- Độ trễ pipeline local: mean 4,68 giây, p50 3,97 giây, p95 8,11 giây, max 23,92 giây. Không phải TTFT, không phải benchmark HF hoặc tải đồng thời.
- Composer token usage/cost: N/A trong artifact hiện có. Không suy ra chi phí từ số case.
- Judge gắn unsupported-claim flag **13/150**, critical flag **2/150**; có **22 câu** vào nhóm automatic failure. Đây là cờ tự động, không phải 22 lỗi thực tế đã xác nhận.
- Audit toàn bộ 22 câu và mẫu phân tầng 40 câu (seed `20260906`), trùng 4: **58 câu khác nhau**. Trong 36 câu chỉ thuộc mẫu: 32 không thấy lỗi đáng kể; 4 có thiếu ý/diễn đạt hoặc khác biệt phạm vi gold (`023, 128, 146, 150`). Không ngoại suy tỷ lệ này ra 150 vì mẫu audit có chủ đích gồm toàn bộ failure.
- Dựng lại packet Judge offline cho `009, 012, 054, 064, 080, 084, 098, 104` tìm thấy evidence hỗ trợ: có cơ sở xem các cờ unsupported này là false positive của Judge. Đây là kiểm chứng bằng evaluator/artifact hiện có, không phải gửi lại Judge; điểm gốc không thay đổi.
- `035`: ý chính phân biệt thôi học/bảo lưu có nguồn; khẳng định thêm không phải dự tuyển lại chưa được nguồn xác lập trực tiếp. Chưa chứng minh đó là phát biểu sai nguy hiểm.
- `069`: Planner chọn phạm vi học phần chỉ đạt/không đạt không tính GPA từ câu hỏi về môn chuyên ngành. Resolver đúng với bảng được giao, nhưng tính áp dụng chưa được xác lập. Câu trả lời có điều kiện không biến thành bằng chứng đã chọn đúng bảng; không loại failure gốc chỉ vì gold còn giả định về loại học phần.

### Kiểm chứng riêng ba lỗi API

`120–122` ghi nhận giới hạn tạm thời của provider trong lượt chính. Lượt kiểm chứng bổ sung đều answered và đối chiếu offline đạt **3/3**, không có API error/fallback: lần lượt 22,64; 3,61; 3,43 giây. Không gọi Judge, không trộn câu trả lời mới vào metric 150 câu, không xóa ba lỗi phục vụ của lượt chính.

Retry dùng model embedding cache offline đã xác minh tên/kích thước. Run gốc không ghi revision Hugging Face nên không tuyên bố chứng minh được revision lịch sử trùng tuyệt đối. Tên thư mục retry có `1402Z` nhưng timestamp chuẩn trong provenance là `2026-09-08T07:14:52.963735+00:00`; xem provenance, không suy thời gian UTC từ slug.

## 6. Limitation được ghi nhận

1. Planner vẫn có thể bỏ slot, chọn sai operation/route hoặc phạm vi áp dụng. Schema/enum hợp lệ không đảm bảo diễn giải đúng. Fact-lock đúng trên bảng được chọn không chứng minh chọn đúng bảng.
2. Phụ thuộc kết quả giữa task, nhiều thực thể và nhiều cohort chưa ổn định như câu một ý. Stress Generate thấp hơn nhóm thông thường; chưa có cơ sở khẳng định bao phủ mọi cách hỏi.
3. Retrieval có thể trả nguồn đúng ngoài top 5 hoặc evidence dư. Directory và nguồn điều khoản có thể trả cùng ý nhưng bị contract nguồn đánh giá khác; phải phân biệt với lỗi bỏ sót nội dung thật.
4. Composer vẫn có thể thiếu điều kiện/ý trả lời, thêm diễn giải vượt evidence hoặc tự mâu thuẫn. Full table + fact-lock không bảo đảm tuyệt đối chống hallucination.
5. Judge và matcher cũng có sai số. Cờ hallucination/critical của Judge không phải kết luận chuyên gia; chưa có human audit độc lập hoặc agreement giữa reviewer.
6. Provider throttling và độ trễ đuôi còn tồn tại. Retry3 thành công không chứng minh quota/key rotation đã tối ưu hoặc luôn sẵn sàng.
7. Bộ này phục vụ đánh giá hệ thống phát triển nội bộ, không chứng minh tổng quát ngoài Sổ tay/cohort đã hỗ trợ. Baseline, ablation, independent holdout và kiểm chứng độc lập chưa thực hiện.
8. Không chạy Production60 theo phạm vi mới. Chưa đo tải, TTFT trên HF, SLA hoặc khả năng scale. Deploy smoke và kiểm tra chịu lỗi vẫn phải thực hiện trước khi chốt bản beta.

## 7. Nguồn kết quả và bước chốt

Đường dẫn dưới đây tương đối với repository; giữ artifact/hash trước mọi cleanup, không xóa nguồn báo cáo này nếu chưa lưu provenance cần thiết.

```text
data/eval/reports/official_v1_deterministic_20260908T022556375610Z_2a293721/deterministic.json
data/eval/reports/official_v1_retrieval_20260908T030848974357Z_2a293721/retrieval_end_to_end_qdrant_vector_primary_graph_supplement_full.json
data/eval/reports/official_v1_generate_judge_20260908T054713Z_2a293721/final_summary.json
data/eval/reports/official_v1_generate_judge_20260908T054713Z_2a293721/answer_failure_findings_luna20260908.json
data/eval/reports/official_v1_generate_judge_20260908T054713Z_2a293721/answer_failure_decision_luna20260908.json
scratch/luna_answer_quality_audit_20260908.md
data/eval/reports/official_v1_generate_retry_quota3_20260908T1402Z_2a293721/retry_offline_review_luna20260908.json
```

Manifest hash/path tối thiểu để kiểm tra các nguồn trên: `data/eval/official_v1/RESULTS_PROVENANCE.json`.

**Chốt báo cáo không có nghĩa mọi gate đều pass hoặc đã release.** Không tự mở vòng sửa runtime vì điểm thấp. Bước còn lại: review/commit các thay đổi được duyệt, cập nhật README theo đúng số trên, push/deploy và smoke beta; ghi rõ limitation. Báo cáo này không tự thực hiện các bước đó.
