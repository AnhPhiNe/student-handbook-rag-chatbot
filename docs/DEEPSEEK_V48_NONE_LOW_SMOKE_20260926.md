# DeepSeek V48: smoke `none` và `low`, 26/09/2026

## Kết luận

Đã chạy đúng 36 lượt case-model được duyệt: 18 câu cho `none`, sau đó cùng
18 câu cho `low`. Không chạy full A/B 135 câu, composer/judge, staging hoặc
deploy. Không chỉnh prompt, runtime hay gold giữa hai lượt. Không commit/push.

`none` nhanh hơn trong lượt này; `low` pass thêm hai outcome về cách gộp task,
nhưng gặp timeout sau retry. **Chưa đủ cơ sở chọn cấu hình production.**
Đặc biệt `low` chưa đạt gate request success 99% và planner p95 20 giây.
Ngay cả 18/18 request success của `none` cũng chưa chứng minh mục tiêu vận
hành dài hạn. Đây là mẫu nhỏ, cố ý chọn các lỗi cũ, không phải accuracy toàn
bộ benchmark hay chất lượng câu trả lời cuối.

## 1. Danh tính và phạm vi

- Model/provider: `deepseek-flash` / DeepSeek; JSON object với cùng schema trong prompt.
- Prompt: `structured-regulation-v48-scale-task-pairing`.
- Normalizer: `v30-score-scale-grounding`.
- Contract: `query-plan-grounded-outcome-v10`; evaluator `r2-requested-field-coverage`.
- Timeout cấu hình: 20 giây mỗi request; tối đa một transient retry, cùng
  cơ chế repair hiện có. Planner latency đo toàn bộ lời gọi planner, gồm retry/chờ key.
- `omit_max_tokens=true` ở cả hai lượt; router cache tắt. Response cache không
  được dùng trong deterministic retrieval-only execution.
- Temperature gửi là 0 ở cả hai, nhưng không có tác dụng trong thinking mode.
- [Tài liệu DeepSeek](https://api-docs.deepseek.com/api/create-chat-completion/)
  ghi mặc định tối đa 8K cho non-thinking, 64K cho thinking khi không gửi
  `max_tokens`. Vì vậy đây là **so sánh cấu hình vận hành**, không cô lập riêng
  reasoning; giới hạn tối đa không phải số token thực tiêu thụ.
- Chạy tuần tự `none` trước `low`; ảnh hưởng thứ tự, cache phía provider và
  biến động dịch vụ chưa được kiểm soát bằng counterbalancing/lặp nhiều lượt.

12 case V10 được sao chép nguyên vẹn: `013/014/018/033/034/035/047/093/096/114/119/122`.
6 câu development mới được author/compile từ catalog trước inference:

| ID | Điều kiểm tra |
| --- | --- |
| `v48_dev_001` | Điểm `3,60/10` giữ cả giá trị và thang điểm |
| `v48_dev_002` | `3,6/4` không khóa kết quả theo bảng hệ 10 |
| `v48_dev_003` | Hai môn cùng bảng, mỗi môn có điểm riêng |
| `v48_dev_004` | Hai môn K51 có scope foundation/remaining riêng |
| `v48_dev_005` | Danh sách liên hệ trực tiếp của hai khoa |
| `v48_dev_006` | Một yêu cầu, hai cohort, một task với execution units riêng |

Authoring mới: `data/eval/deepseek_v48_smoke/deterministic_authoring.yaml`.
Compiled smoke: `data/eval/deepseek_v48_smoke/deterministic_tool_cases_v10.json`.
Không đổi authoring/compiled gold official V1/V10. Các development probes này
phát sinh từ test/prompt development, không được gọi là holdout độc lập.

## 2. Kiểm chứng trước/sau chạy

Toàn bộ **1.142 test pass**, hai dependency deprecation warnings. Có test
đưa 6 contract mới qua normalizer/resolver thật, và test xác nhận 12 case cũ
được sao chép đúng nguyên bản. `git diff --check` không có lỗi whitespace.

Chỉ bổ sung observability trước freeze: lưu finish reason, usage và optional
reasoning/cache token counters cho response thành công/repair/lỗi parse khi
bật planner diagnostics. Không lưu reasoning text, không đổi HTTP request,
public response, output-token policy, schema hay nội dung prompt.
Counters không có trong API response được xem là chưa biết, không suy là 0.

Freeze riêng: `data/eval/deepseek_v48_smoke/experiment_freeze.json`, hash 181
file runtime/config/corpus/gold/compiler liên quan. Runner kiểm hash và
planner settings trước inference. Hash trước/sau ở cả hai report vẫn khớp;
hai run snapshot có cùng map hash. Freeze này là danh tính thí nghiệm local,
không phải release production. Snapshot offline V48 cũ không bị viết lại;
router file thay đổi do diagnostics và test integration có thêm test smoke.

Một khởi động sandbox bị chặn ở retriever trước vòng chấm, chỉ có
`run_snapshot.json` trong thư mục `...20260926T151130Z`; đã dừng trước planner.
Hai lượt hoàn chỉnh dưới đây chạy sau khi cấp quyền mạng.

## 3. Kết quả live

| Phép đo | `none` | `low` |
| --- | ---: | ---: |
| Đã chạy / yêu cầu | 18/18 | 18/18 |
| Pass contract tổng, gồm lỗi vận hành | **13/18 (72,2%)** | **15/18 (83,3%)** |
| 12 case regression cũ | 7/12 | 9/12 |
| 6 câu development | 6/6 | 6/6 |
| Request success sau retry | 18/18 (100%) | 17/18 (94,4%) |
| Planner p50 | 2,24 giây | 10,18 giây |
| Planner p95, gồm retry | 4,16 giây | 42,86 giây |
| Planner request failures cuối | 0 | 1 |
| Execution/evaluator exceptions | 0/0 | 0/0 |
| Cross-cohort leak được ghi nhận | 0 | 0 |
| Request events trong diagnostics | 18 | 19 |
| Response có usage | 18 | 17 |
| Input tokens có báo cáo | 94.025 | 89.220 |
| Output tokens có báo cáo | 4.066 | 37.453 |
| Reasoning tokens có báo cáo | Không trả counter | 33.948 trên 17 response |
| Response có `finish_reason=length` | 0 | 0 |

Tổng 37 request events cho 36 lượt case-model: `047` của `low` có hai attempt
timeout, không có response/usage. Không chạy lại để thay thế kết quả fail.
Mọi response nhận được đều có `finish_reason=stop`; không có bằng chứng cắt
output trong các response quan sát được. Điều đó không chứng minh token
budget đã tối ưu, hoặc các request timeout đã dùng bao nhiêu token.

`semantic_accuracy` loại lỗi vận hành là 13/18 và 15/17; đây là metric phụ.
Headline vẫn 13/18 và 15/18, không loại timeout để làm đẹp kết quả tổng.
`047` low tốn 42,86 giây trong planner rồi RAG fallback; không quy fallback
do request timeout thành bằng chứng model hiểu sai câu hỏi. `122` low thành
công với một response nhưng toàn bộ planner tốn 20,67 giây; timeout cấu hình
20 giây không phải hard deadline cho toàn bộ planner.

Application router cache hits đều bằng 0. Provider prompt-cache hit tokens
là 84.864 (`none`) và 80.768 (`low`); đây là cache prefix phía DeepSeek, **không
phải** dùng lại plan hay né gọi API. Do đó không tuyên bố mọi lớp cache đều tắt.

Theo [giá off-peak](https://api-docs.deepseek.com/quick_start/pricing/) tại ngày
chạy (thứ Bảy), phần request có usage ước tính khoảng $0,00407 (`none`) và
$0,02398 (`low`). Chi phí hai request timeout chưa biết; không tính chúng là
miễn phí. Đây không phải hóa đơn hay trần USD. Output tokens đã gồm phần
reasoning được báo cáo; không cộng reasoning tokens lần thứ hai vào chi phí.

## 4. Phân tích fail, không đổi cách chấm sau khi xem output

| Case | `none` | `low` | Ý nghĩa bằng chứng |
| --- | --- | --- | --- |
| `033` | Fail | Pass | `none` tách TCF/DELF thành hai task đúng dữ kiện; outcome hiện đòi một task. `low` gộp đúng outcome. |
| `047` | Fail | Fail | `none` tách ba nhóm chương trình, các check dữ kiện/evidence pass nhưng task count fail. `low` timeout cả hai attempt, dùng fallback. Hai loại lỗi khác nhau. |
| `093` | Fail | Fail | Cả hai chọn student_service đúng nhưng requested_field=office; gold yêu cầu unit. |
| `096` | Fail | Fail | Cùng lỗi unit/office ở câu nhận bằng tốt nghiệp. |
| `122` | Fail | Pass | `none` dùng hai task student_service (unit và email), đúng record/email/cohort. Outcome một task fail count; decomposition khác được chấp nhận lại đòi office ở task thứ hai. `low` dùng một task với [unit,email], pass. |

Paired: 13 cùng pass, 2 chỉ low pass (`033/122`), không case chỉ none pass,
3 cùng fail (`047/093/096`). **Hai pass thêm chưa chứng minh thêm hai câu trả
lời đúng**: khác biệt quan sát được là decomposition theo contract, không
phải none lấy sai fact trong hai case đó. Không tính lại điểm, không thêm
accepted outcome dựa vào một raw output. Cần review policy gộp/tách và contract
theo nguyên tắc kiến trúc chung ở đợt riêng.

`093/096` tiếp tục là lỗi field theo contract đã chốt, dù có hướng dẫn chung.
Từ “phòng nào” còn nhập nhằng trong ngôn ngữ tự nhiên. Không kết luận toàn bộ
nguyên nhân chỉ do model, và chưa chứng minh câu trả lời composer sẽ sai:
composer không được gọi trong smoke này.

## 5. Kiểm safety/evidence bổ sung

Hai output live đều giữ nguyên `3,6/4` trong slot/span của probe sai thang.
Runtime trả evidence-only, không có `resolved_result` hoặc `resolved_rows`
tính toán sai. Dựng evidence packet offline từ output/citation đã lưu xác
nhận composer unit vẫn evidence-only và không có fact lock. Không gọi composer.
Các probe đa môn/scope/cohort và danh sách khoa đều pass contract ở cả hai.
Relation cases `114/119` cũng pass bằng program task và provenance theo V10.

## 6. Artifacts và bước tiếp theo

- None: `data/eval/reports/deepseek_v48_smoke_deterministic_20260926T151205Z/deterministic.json`.
- Low: `data/eval/reports/deepseek_v48_smoke_deterministic_20260926T151500Z/deterministic.json`.
- Paired summary, hashes, token coverage và safety review:
  `data/eval/reports/deepseek_v48_smoke_comparison_20260926/comparison.json`.

Nên review offline ranh giới unit/office và contract decomposition trước
quyết định đợt tiếp theo; không vá tên case, không đổi gold facts. Low cần
xử lý/kiểm chứng tail latency và request success, không mặc định tăng timeout
sẽ đạt gate. Bất kỳ chỉnh prompt/runtime/contract nào sau smoke đều phải có
version/snapshot mới, không viết lại kết quả này. Full A/B 270 lượt cần duyệt
riêng; staging, rollback và canary chưa thực hiện.
