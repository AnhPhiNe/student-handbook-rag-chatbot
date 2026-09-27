# Kiểm chứng độc lập hợp đồng JSON của planner

> Báo cáo lịch sử cho v45 trước khi sửa. Các kết quả `xfail` và vị trí dòng bên
> dưới ghi nhận trạng thái lúc audit, không phải trạng thái mới nhất. Đợt sửa
> tiếp theo được ghi tại [PLANNER_V46_CONTRACT_FIXES.md](PLANNER_V46_CONTRACT_FIXES.md);
> các test tái hiện đã được chuyển thành regression không có marker xfail.

Ngày: 26/09/2026. Phạm vi: working tree hiện tại, prompt
`structured-regulation-v45-shared-json-contract`, normalizer
`v28-resolver-owned-directory-fallback`, registry version 7, QueryPlan v1.
HEAD nền: `a8db95be58fb2c748bbcf016f0ac426ce8e900c1`; kết luận áp dụng cho
working tree có các thay đổi local v44/v45, không phải riêng commit HEAD.

## Kết luận

**Không lấy output Qwen làm chuẩn.** Schema thuộc dự án, không thuộc nhà cung cấp.
Cấu trúc cơ bản, danh sách tool/cohort, mô tả tool trong prompt và các nhánh thực
thi hiện tại khớp nhau ở những điểm đã kiểm tra. Tuy nhiên, schema không phải
toàn bộ đặc tả nghiệp vụ, và backend chưa thực thi mọi ràng buộc đã viết trong
prompt/schema.

Hướng đề xuất: **xử lý các điểm lệch ngoài prompt trước**, kèm chỉnh nhỏ quy tắc
ưu tiên chung nếu cần. Không có bằng chứng trong đợt này để kết luận prompt
overfit Qwen, hay để hứa DeepSeek sẽ tăng accuracy sau khi sửa.

Không thay runtime, prompt, schema, registry, gold, production, README hoặc báo
cáo A/B cũ trong đợt audit này. Không chạy inference, commit hay push. Chỉ thêm
test, báo cáo và dependency **development-only** `jsonschema==4.25.1`.

## Cách kiểm chứng

- Dùng knowledge graph để tìm định nghĩa, rồi đối chiếu source local hiện tại.
- Dùng `Draft202012Validator` kiểm tra tính hợp lệ của schema và các payload tổng
  hợp. Đây là validator chuẩn dùng trong test, **chưa được gắn vào runtime**.
- Kiểm tra cả required fields, kiểu dữ liệu, enum, thuộc tính lạ, và payload hợp
  schema nhưng sai nghiệp vụ; chạy qua normalizer/validator thực của dự án.
- Fake completion để kiểm tra đường `AIRouter.plan` mà không gọi model. Không
  dùng key thật; cache/state file bị tắt trong fixture mới.
- Kiểm tra nhánh executor và dispatcher bằng spy, không gọi retrieval/catalog
  service. Kiểm tra dispatch không chứng minh câu trả lời hay dữ liệu đúng.
- Không đọc hoặc sử dụng official_v3 để thiết kế test. Các câu tổng hợp là
  development fixtures, không phải hold-out hay benchmark accuracy mới.

## Ba lớp khác nhau

1. **Raw JSON schema** — cấu trúc output model: tên field, kiểu, enum, giới hạn
   task thô; `query_plan.py:166`.
2. **Hợp đồng nghiệp vụ** — ý nghĩa mode/tool/intent/slot, grounding và history;
   prompt, registry và `structured_routing.py` cùng tham gia.
3. **Plan đã chuẩn hóa và thực thi** — có thêm metadata runtime, loại bỏ/sửa
   input không an toàn, rồi chạy từng task/cohort; `normalize_query_plan` và
   `PlanExecutor`. Không dùng nguyên raw schema để validate toàn bộ normalized
   plan vì normalized plan có thêm field runtime hợp lệ.

Hai transport không tương đương về mức cưỡng chế: native request gửi
`json_schema` với `strict=False`, còn JSON-object request chỉ nhận schema qua
prompt. Việc hai nơi dùng chung schema không chứng minh hai provider cưỡng chế
nó giống nhau. Đợt audit này không kiểm chứng hành vi provider thực tế.

## Đối chiếu field

| Field | Schema / prompt | Normalizer / executor | Đánh giá |
|---|---|---|---|
| `schema_version` | enum `v1` | Normalizer luôn xuất version hiện tại | Đúng version đầu ra; không đồng nghĩa input sai version bị từ chối |
| `context_mode` | standalone/follow_up/ambiguous | Chọn query hiệu lực; ambiguous chuyển sang clarify nếu cần | Thiếu kiểm tra chéo history — AUD-03 |
| `normalized_query` | string/null; prompt chỉ sửa nhẹ | Có fallback query gốc; standalone một task dùng question gốc | Độ trung thành về ngữ nghĩa vẫn cần eval |
| `standalone_query`, `referenced_turns` | Rewrite và các chỉ số history đã dùng | Lọc chỉ số âm/sai kiểu; không kiểm tra chỉ số có tồn tại | AUD-03 |
| `out_of_domain` | boolean/null; prompt yêu cầu boolean | Dùng `bool(value)`; OOD bỏ tasks, trừ domain-signal rescue | Sai kiểu có thể đổi route — AUD-01 |
| `tasks` | 0–12 raw tasks | Merge trước, tối đa 3 logical tasks; quá giới hạn clarify | Tolerance có chủ ý, không tự nó là lỗi |
| `id` | string; prompt t1/t2/t3 | Runtime đánh lại ID tuần tự | Khớp nhờ chuẩn hóa |
| `question` | string; prompt tự đủ nghĩa | RAG query hoặc structured resolver query | Cần eval ngữ nghĩa, không thể chứng minh bằng schema |
| `mode` | structured/rag/clarify | Executor có nhánh tương ứng | Khớp trong test |
| `intent`, `lookup_type` | intent string; tool enum từ registry | Validate/default intent theo tool; tool lạ chuyển clarify | Schema cố ý rộng hơn validator nghiệp vụ |
| `slots`, `slot_spans` | Open object; span string/list | Kiểm tra khai báo, type, value, grounding theo vai trò | Bảo vệ các ca đã test; xem thêm AUD-03/AUD-05 |
| `cohorts` | Enum khóa hợp lệ, prompt QUERY > history > UI | Lọc khóa không hỗ trợ; điền fallback khi mảng rỗng | Hợp lệ không đồng nghĩa đúng câu hỏi — AUD-02 |
| `clarification_question` | string/null, prompt theo mode | Clarify có câu hỏi mặc định; structured có thể giữ câu hỏi | Runtime rộng hơn quy tắc sinh output hiện tại |

Không phải mọi sai biệt trong bảng đều là bug: `intent` sai có thể được đưa về
default, task IDs được đánh lại, task RAG được xóa lookup/slots, optional slot
không đáng tin có thể bị bỏ. Đây là cơ chế phục hồi, không nên xóa chỉ để schema
và runtime giống nhau tuyệt đối.

## Đối chiếu toàn bộ tool hiện có

| Tool | Intents được kiểm tra | Nhánh dispatcher |
|---|---|---|
| foreign_language | direct_value, list_items | reference table + foreign-language resolver |
| study_duration | direct_value, list_items | reference table + study-duration resolver |
| scholarship_classification | direct_value, list_items | reference table + scholarship resolver |
| scoring | direct_value, list_items | reference table + scoring resolver |
| student_service | direct_value, contact | directory / office_lookup |
| office | contact | directory / office_lookup |
| faculty | contact | directory / office_lookup |
| program | direct_value, list_items, exists | program_lookup |
| formula | formula | formula_lookup |

16 ví dụ hợp lệ độc lập đi qua schema, normalizer và validator slot. Test
dispatcher kiểm tra cả 9 tool có nhánh xử lý; resolver được fake để cô lập hợp
đồng. Không tuyên bố đã vét cạn mọi tổ hợp enum, danh sách, nguồn dữ liệu hay
ý nghĩa câu hỏi. Với reference tables, empty optional slots là yêu cầu bảng
tổng quan hợp lệ; việc chọn hàng chính xác là trách nhiệm kiểm chứng khác.

## Các phát hiện tái hiện được

### AUD-01 — P1: boolean sai kiểu có thể làm đổi route

- Quy tắc: phần OUTPUT yêu cầu boolean thật; schema không chấp nhận `"false"`.
- Vị trí: `ai_router.py:775` parse rồi normalize; `query_plan.py:367–373` dùng
  `bool(payload.get("out_of_domain"))`.
- Fixture: plan tra email Phòng Đào tạo có `out_of_domain="false"`.
- Kết quả: validator schema từ chối, nhưng đường router với fake completion
  chuyển nó thành OOD và bỏ task; câu hỏi này không kích hoạt domain-signal rescue.
- Nguyên nhân đã chứng minh: chuyển kiểu theo truthiness thay vì kiểm tra boolean.
- Đề xuất: kiểm tra kiểu trường điều khiển trước khi routing; giá trị sai đi vào
  lỗi contract/fallback có diagnostic, không được biến thành quyết định OOD.
  Không mặc định bật strict validation toàn bộ raw payload: runtime đang có
  chủ đích hỗ trợ một số input thiếu/legacy và task thô để phục hồi.
- Test mở: `test_string_false_must_not_silently_become_out_of_domain`.

### AUD-02 — P1: khóa hợp lệ nhưng sai yêu cầu vẫn qua normalizer

- Quy tắc: phần COHORT ưu tiên khóa trong QUERY, UI chỉ là fallback.
- Vị trí: `query_plan.py:496–526`; fallback cohort chỉ áp dụng khi `cohorts` rỗng.
  `plan_executor.py:204` thực thi theo cohorts đã có trên task.
- Fixture: query `K50 được bảo lưu thế nào?`, raw task `cohorts=["K51"]`, UI K51.
- Kết quả: hợp schema, không báo lỗi, task vẫn K51.
- Nguyên nhân đã chứng minh: kiểm tra khóa được hỗ trợ, chưa đối chiếu với ràng
  buộc khóa được nêu rõ trong query. Kiểm tra provenance của nguồn không sửa
  được việc đã chọn sai khóa ngay từ đầu.
- Đề xuất: kiểm tra xung đột khóa cho trường hợp rõ ràng một target/một khóa;
  chọn khóa tường minh hoặc clarify. Không ghi đè toàn cục cho câu nhiều task,
  so sánh nhiều khóa, hoặc task có phạm vi khác nhau. Cần các negative controls đó.
- Test mở: `test_wrong_task_cohort_cannot_silently_override_explicit_query`.

### AUD-03 — P1: history hiển thị và history dùng để grounding không đồng nhất

- Quy tắc: standalone không dùng history; follow_up chỉ dùng các lượt hiển thị,
  và phải khai báo đúng `referenced_turns`.
- Vị trí: `ai_router.py:989` chỉ đưa 300 ký tự/lượt trong 4 lượt cuối vào prompt;
  `ai_router.py:779` dùng toàn bộ content của 4 lượt đó làm grounding, không phụ
  thuộc context mode hoặc referenced turns. `query_plan.py:408` chỉ lọc kiểu/âm.
- Fixtures: referenced_turns=[999] khi history rỗng (standalone và follow_up);
  entity chỉ có trong history nhưng mode standalone; entity sau ký tự 300 khi
  mode follow_up.
- Kết quả: tham chiếu 999 được giữ; slot của hai fixture entity vẫn được nhận là
  grounded và task vẫn structured, dù vi phạm quy tắc được đưa cho model.
- Nguyên nhân đã chứng minh: hai cách dựng history khác nhau và thiếu kiểm tra chéo.
- Đề xuất: dùng chung biểu diễn history đã hiển thị, giữ nguyên chỉ số; standalone
  không cấp history cho grounding; follow_up kiểm tra chỉ số tồn tại, sử dụng
  đúng các lượt được tham chiếu. Kiểm thử history rỗng, lượt rỗng, lượt bị cắt,
  nhiều lượt/role và những trường hợp follow-up hợp lệ trước khi áp dụng.
- Bốn test mở nằm trong `test_unseen_history_reference_is_rejected_or_cleared`
  và `test_grounding_cannot_use_forbidden_or_invisible_history`.

### AUD-04 — P1: đếm task xung đột với bỏ phần ngoài phạm vi

- Quy tắc: phần NGỮ CẢNH yêu cầu đủ EXPLICIT_REQUEST_COUNT; OUTPUT yêu cầu bỏ phần
  ngoài phạm vi khi query trộn trong/ngoài phạm vi.
- Vị trí: `_explicit_request_count`, phần repair trong `ai_router.py:805–890`.
- Fixture: thứ nhất hỏi email Phòng Đào tạo, thứ hai hỏi thời tiết. Fake model
  trả đúng một task tra email, bỏ thời tiết theo quy tắc OUTPUT.
- Kết quả: router yêu cầu repair thành 2 task; khi fake model vẫn giữ 1 task,
  router chuyển toàn bộ sang `planner_task_count_mismatch` safe RAG.
- Nguyên nhân đã chứng minh: số marker không phân biệt target trong phạm vi.
- Đề xuất: chốt thứ tự ưu tiên rồi đồng bộ repair, không chỉ thêm câu vào prompt.
  Nội dung đề xuất: “Xác định target trong phạm vi trước; chỉ các target đó chịu
  quy tắc đủ task và tối đa 3. Marker đánh số là tín hiệu kiểm tra, không tự
  chứng minh số task phải thực thi.” Phần repair phải có đủ thông tin về target
  bị loại hoặc không được cưỡng ép bằng tổng marker. Không thêm keyword thời tiết
  vào heuristic để chữa riêng fixture này.
- Test mở: `test_mixed_domain_keeps_only_in_domain_target_without_count_fallback`.

### AUD-05 — P2: hỗ trợ list ở validator chưa đồng nhất với requested_field downstream

- Quy tắc mới v45 mô tả danh sách cùng kiểu cho entity hoặc nhiều trường.
- Vị trí: `structured_routing.py:361` chấp nhận list string;
  `structured_dispatcher.py` nhánh directory chuyển requested_field bằng `str(...)`.
- Fixture: office + requested_field=["email", "phone"], grounding đầy đủ.
- Kết quả: schema và normalizer chấp nhận; resolver ghi requested_field thành
  chuỗi Python `"['email', 'phone']"`, không còn là danh sách hoặc enum scalar.
- Ảnh hưởng đã chứng minh chỉ là metadata không đồng nhất. Test không chứng minh
  composer trả lời sai: record đầy đủ và task.question vẫn được giữ.
- Đề xuất: rà consumer rồi chọn một biểu diễn thống nhất. Trước mắt không quảng
  bá mọi slot/list đều được hỗ trợ xuyên suốt chỉ vì validator chấp nhận list.
  Không đổi thành `all` mặc định vì có thể làm rộng yêu cầu ban đầu.
- Test mở: `test_multiple_requested_fields_keep_machine_readable_structure`.

## Những điểm không kết luận là lỗi

- 12 raw tasks và 3 normalized tasks: có bước merge và clarify rõ ràng; test 4
  target riêng biệt trả một clarify task. Không cần đổi schema chỉ vì hai số khác nhau.
- Open slots / intent string: validator nghiệp vụ kiểm tra riêng. Test missing
  required slot, sai type, sai enum, slot lạ và entity không grounded đều không
  đi tiếp dưới dạng structured task không hợp lệ.
- Danh sách tool và cohort được sinh từ registry; không thấy tool đang khai báo
  nhưng thiếu nhánh dispatcher trong cấu hình hiện tại.
- `reading_intent` cố ý không cần literal grounding như `result_input`/entity.
  Prompt nghiêm hơn về span không đồng nghĩa validator phải áp dụng cùng luật
  literal cho mọi selector ngữ nghĩa.
- Các vấn đề trên được tái hiện bằng input tổng hợp, không phải phân tích tần suất
  từ production hoặc bằng chứng giải thích các lỗi A/B Qwen/DeepSeek đã lưu.

## Test và cách đọc kết quả

File: `tests/test_planner_contract_audit.py`.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_planner_contract_audit.py -q -rx -p no:cacheprovider
```

Kết quả riêng audit: **50 passed, 8 xfailed**. Tám `xfail(strict=True)` là các
assertion về hành vi mong muốn hiện chưa đạt, không phải tám test đã sửa xong.
Khi sửa runtime tương ứng, bỏ marker xfail và giữ assertion làm regression.
Không được trình bày suite này thành “mọi kiểm tra đều đạt”.

Các test hiện có được chạy kèm: planner_json_contract, planner_operational_failures,
ai_router_prompt, query_plan, evaluation_contracts. Tổng lần chạy cuối:
**250 passed, 8 xfailed**. Ruff, `git diff --check` và `pip check` đạt.
Chưa chạy toàn bộ repository suite hay live model evaluation.

## Thứ tự công việc đề xuất, chưa áp dụng

1. Chốt validation tối thiểu cho kiểu trường điều khiển và quy tắc khóa tường minh.
2. Đồng bộ history view/grounding và kiểm tra referenced_turns.
3. Chốt ưu tiên in-domain targets rồi sửa cả prompt lẫn count repair.
4. Thu hẹp hoặc hoàn thiện hợp đồng list theo từng slot/consumer.
5. Chạy lại test; chỉ khi các invariant đã rõ mới freeze snapshot để A/B hai model.

Không cần viết lại toàn bộ JSON Schema hoặc tạo benchmark mới cho đợt sửa này.
Nếu thay runtime phải tăng version normalizer/cache tương ứng. A/B sau đó cần
ghi rõ prompt, schema, runtime, transport, token policy và reasoning của mỗi model.
