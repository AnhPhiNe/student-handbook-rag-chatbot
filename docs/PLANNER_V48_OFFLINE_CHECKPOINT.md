# V48: giữ thang điểm và quan hệ entity–dữ kiện trước lượt API mới

Ngày kiểm chứng: 2026-09-26. Đây là checkpoint local/offline, **không phải**
release production hay kết quả chạy DeepSeek/Qwen với prompt mới.

## Phạm vi

- Prompt: `structured-regulation-v48-scale-task-pairing`.
- Normalizer: `v30-score-scale-grounding` (đổi version để không dùng cache plan cũ).
- Gold contract vẫn là `query-plan-grounded-outcome-v10`;
  evaluator vẫn là `r2-requested-field-coverage` từ sửa multi-field trước đó.
- Giữ interface `resolve_structured_task(...)`, JSON Schema, HTTP response,
  ý nghĩa `resolved_rows` và giới hạn ba task. Không thêm outcome/adapter/DAG.
- Không đổi README, cấu hình production, catalog nguồn, gold facts; không gọi
  API, commit hay push. Các thay đổi local có trước đợt này được giữ nguyên.

## 1. Chặn mất thang điểm

Lỗi trước sửa được tái hiện bằng plan giả lập: numeric slot `3.6`, span
`3,6/4`, query hỏi qua môn K50 vẫn khóa hàng của bảng hệ 10. Parser riêng đã
giữ được mẫu số, nhưng đường grounding chỉ tìm số trùng trong span nên bỏ qua
thang điểm; chỉ test parser không bắt được lỗi này.

`src/common/score.py::grounded_score` dùng parser Decimal chung và đối chiếu
**cụm số đầy đủ ở vị trí span trong nguồn**. Nó giữ mẫu số, không lấy mẫu số
làm operand, không lấy số khóa từ `K50`, và không tự chọn khi span rút gọn
khớp nhiều giá trị/thang điểm không nhất quán. NFC/casefold/khoảng trắng dùng
để đối chiếu văn bản; không suy diễn đơn vị hay đổi thang điểm.

- Normalizer và fact-lock validator kiểm span không bị cắt mất mẫu số từ
  QUERY/history được cung cấp. Hint điểm tùy chọn không hợp lệ được bỏ theo
  cơ chế warning/evidence-only hiện có, không sửa gold hoặc đoán lại operand.
- Dispatcher giữ thang điểm trong operand nội bộ trước khi tính cả hàng
  ứng viên và `resolved_result`; không sửa raw plan đã lưu.
- Scoring resolver đối chiếu thang đầu vào của bảng đã chọn: bảng đổi điểm
  chữ/đạt–không đạt dùng hệ 10, xếp loại học lực dùng hệ 4, rèn luyện dùng
  hệ 100. Cụm điểm có số nhưng parser không hiểu không được xử lý bằng cách
  lấy số đầu tiên. Các nhãn điểm chữ/xếp loại thuần văn bản giữ đường tra cũ.

| Slot/span/nguồn | Kết quả offline mong muốn và đã kiểm |
| --- | --- |
| `3.6`, span `3,6/4`, nguồn `3,6/4`, bảng hệ 10 | Evidence-only, không fact lock |
| `3.6`, span `3,6`, nguồn `3,6/4` | Bỏ hint điểm bị cắt thang; không fact lock |
| `4`, span `4`, nguồn `3,6/4` | Không coi mẫu số là điểm |
| `3,60/10`, span `3,6/10` | Giá trị/thang tương đương; có thể khóa khi scope/row duy nhất |
| `3.6`, span `3,6/10`, bảng hệ 10 | Có thể khóa sau các kiểm tra hiện có |
| `3.6`, span `3,6/10`, bảng xếp loại học lực hệ 4 | Không fact lock |
| K51 `graded` nhưng thiếu foundation/remaining, điểm hệ 10 hợp lệ | Giữ từng bảng và `resolved_rows`, không khóa toàn bộ |
| K51 điểm hệ 4 nhưng các bảng ứng viên là hệ 10 | Giữ bảng làm evidence; không phát sinh `resolved_rows` tính sai |

Việc không có fact lock không chứng minh câu trả lời LLM cuối cùng đúng.
Đợt này chưa gọi composer. Cách diễn đạt thang điểm tự nhiên ngoài ký hiệu
phân số mà parser chưa hỗ trợ không được tự chuyển đổi bằng heuristic.

## 2. Hướng dẫn gộp/tách trung lập model

System prompt chung yêu cầu:

- Chỉ gộp danh sách khi lookup hỗ trợ và không làm mất cặp entity–dữ kiện.
- Entity có giá trị riêng thì tách task; không lấy tích chéo các danh sách.
- Liên hệ qua relationship cần source duy nhất: mỗi source một task độc lập.
  Lookup danh sách trực tiếp không bị buộc tách theo quy tắc này.
- Một answer target trên hai cohort vẫn là một task với hai cohort. Trên ba
  task độc lập thì yêu cầu chọn phạm vi, không thực thi một phần.
- Không thêm thông tin không có căn cứ trong QUERY/history hợp lệ; cohort UI
  và chuẩn hóa alias đã xác nhận vẫn tuân quy tắc riêng hiện có.
- Người dùng nêu thang điểm thì giữ cả giá trị/thang trong `score_or_grade`
  và span nguyên văn; không rút thành số hay tự quy đổi.

Không thêm điều kiện riêng cho mã case, tên ngành, dịch vụ, Qwen hay DeepSeek.
Không thay đổi quy tắc tool/field của `096`.

Với query đại diện của budget test, history rỗng:

| Kiểu request | V47 tổng ký tự | V48 tổng ký tự | Ước tính input token V48 |
| --- | ---: | ---: | ---: |
| Native JSON Schema | 14.368 | 14.909 | 3.727 |
| JSON object/schema trong prompt | 14.280 | 14.821 | 3.705 |

Tăng 541 ký tự, khoảng 3,8%. Test ceiling là 15.200 ký tự/3.800 token ước
tính. Đây là ước tính từ số ký tự, **không phải** tokenizer/billing thực tế.
Không đổi output-token policy, timeout hoặc retry.

## 3. Kiểm thử đường xử lý

`tests/test_scale_and_task_pairing_integration.py` đưa **plan giả lập** qua
normalizer → executor/resolver thật → citation/evidence packet composer.
Catalog JSON hiện tại được đọc offline; router, retrieval và graph được
thay bằng stub local, không khởi tạo provider client hay embedding inference.

Đã kiểm:

- Numeric/string/list operand, dấu phẩy/chấm và độ chính xác thập phân;
  mất/thay mẫu số, lấy nhầm mẫu số, giá trị không khớp, task paraphrase hoặc
  history khiến span rút gọn không còn an toàn.
- Hai môn cùng bảng và khác bảng giữ điểm/hàng/table đúng từng task.
- Danh sách khoa trực tiếp giữ đủ entity trong một task.
- Structured–Structured, RAG–RAG và Structured–RAG giữ riêng evidence và
  `supports_task_ids` trong packet. RAG dùng nguồn giả lập, không đo chất
  lượng retrieval thật.
- So sánh K50/K51 vẫn một task, hai composition unit; citation và fact lock
  không trộn execution cohort. Các test source-merge hiện có vẫn pass.
- Program → faculty: source duy nhất, source nhiều mục, target thiếu/sai
  cohort, provenance source/target riêng; hai source tách thành hai task.
- Office → service một–nhiều trả danh sách; hơn ba source phải clarify trước
  lookup, không trả một phần.
- Test `018` qua executor thật và test `122` multi-field có trước vẫn pass.
  Bổ sung negative `122`: sai tool, sai đơn vị, sai email vẫn fail, bên cạnh
  mất email, email của record khác, sai cohort và evidence không gắn task.
- Bộ integrity hiện có vẫn kiểm 129 program và 239 service records, alias,
  cardinality và provenance; không sửa dữ liệu để làm test pass.

Toàn bộ **1.131 tests pass**, hai warning deprecation từ dependency.
`git diff --check` không phát hiện lỗi whitespace. Hash xác nhận V9/V10
compiled gold và hai report live lịch sử không đổi.

## 4. Kết quả replay: không phải lượt chạy model mới

Report mới: `data/eval/reports/deepseek_v10_v48_structured_replay_20260926/deterministic.json`.
Nó chạy lại **đúng 12 plan V46 đã lưu**, chỉ thực thi structured runtime hiện
tại; không gọi planner/composer, không chạy lại normalizer trên raw model
output, không dùng embedding, graph supplement hoặc parent enrichment.

| Phép đo | Kết quả | Diễn giải |
| --- | --- | --- |
| Smoke live V46 gốc | 9/12 | Giữ nguyên report lịch sử |
| R2 tái chấm cùng output/evidence smoke | 10/12 | `122` đổi do evaluator hiểu field array |
| R2 replay runtime và replay runtime V48 | 11/12 | `018` được sửa grounding; `096` vẫn fail |
| Tái chấm cùng output 135 case cũ bằng R2 | 123/135 | Không có case đổi pass/fail; không phải runtime mới |

Sửa mất thang điểm không làm tăng điểm của 12 plan này: các test đối kháng
mới kiểm một lỗi an toàn khác, không chỉnh đáp án benchmark để tăng metric.
Không dùng request-success/latency của replay CPU như số đo production.
Planner p95 mới chưa có; p95 smoke live V46 cũ vẫn khoảng 39,84 giây gồm retry.

Snapshot bổ sung:
`data/eval/development/prompt_v48_offline_snapshot.json` ghi version, số test,
budget đại diện và SHA-256 của 27 file/artifact liên quan. Đây không phải hash
của toàn repository hay freeze production. Manifest replay cũ chỉ hash catalog
và executor; sidecar bổ sung hash parser, validator, resolver, prompt và tests.

## Bước tiếp theo

Checkpoint offline đã đạt. Chỉ sau khi duyệt lượt inference/chi phí mới chạy
smoke với prompt V48, rồi benchmark đủ 135 case. Staging, gate accuracy/
request-success/latency và cấu hình rollback vẫn phải kiểm riêng trước canary.
Các test giả lập không chứng minh DeepSeek/Qwen sẽ xuất plan như hướng dẫn,
không chứng minh composer trả lời đúng hay hệ thống đã ổn định production.
