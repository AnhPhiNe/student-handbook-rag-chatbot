# Rà prompt planner và chuẩn bị key OpenAI — 27/09/2026

## Phạm vi và kết luận

Rà source local, prompt thực sự được dựng, registry, schema và các test liên quan.
Không gọi inference, không đổi prompt/runtime/gold/production. Chỉ thêm biến
`OPENAI_API_KEY` trống vào `.env` (đã được Git ignore) và `.env.example`.
Không đưa key thật vào tài liệu hoặc Git. Model ID đã đối chiếu tài liệu chính
thức là `gpt-6-luna`; key chưa được kiểm chứng và quyền truy cập model chưa biết.

Prompt V48 đã quy định tương đối đầy đủ mode, task độc lập, cohort, history,
grounding, thang điểm, cách gộp/tách và JSON output. Không có bằng chứng trong
nội dung prompt/TOOLS được kiểm tra về chỉ dẫn riêng cho Qwen hoặc DeepSeek.
Tuy nhiên, chưa thể kết luận mọi model sẽ phân luồng đúng. Nên làm rõ một số
mô tả field dùng chung, không viết lại toàn bộ prompt hoặc đổi tên schema.

## 1. `unit` và `office`: đã có hướng dẫn, còn nhập nhằng ngôn ngữ

Bằng chứng: `configs/structured_lookup_registry.yaml`,
`tools.student_service.slot_schema.requested_field.description` phân biệt:

- `unit`: đơn vị phụ trách/hỗ trợ một việc.
- `office`: địa chỉ/vị trí; đơn vị đã nêu tên được hỏi ở đâu.
- Hỏi cả hai: mảng `[unit, office]` hoặc `all`.
- Không quyết định chỉ theo từ “phòng”.

`compact_registry_for_prompt()` giữ nguyên description trong TOOLS;
`AIRouter._build_plan_prompt()` đưa TOOLS vào request. Do đó đây không phải
hướng dẫn chỉ tồn tại trong YAML nhưng bị bỏ khi gọi model.

Report `DEEPSEEK_V48_NONE_LOW_SMOKE_20260926.md` ghi nhận `093/096` vẫn sai field.
Đó là bằng chứng lỗi chọn field trên lượt đã lưu, không chứng minh toàn bộ lỗi
do prompt, và cũng không chứng minh câu trả lời cuối sai vì deterministic run
không đánh giá composer. Không nên dùng hai câu đó làm ví dụ bắt buộc trong prompt.

Đề xuất chưa áp dụng: bổ sung câu giải thích theo loại đáp án cần trả:

> Chọn requested_field theo loại kết quả: tên đơn vị phụ trách → unit;
> địa chỉ/vị trí vật lý → office. “Phòng” có thể chỉ đơn vị hoặc căn phòng;
> dùng mục đích câu hỏi và history hợp lệ để phân biệt. Nếu cả hai cách hiểu
> vẫn có căn cứ mà không xác định được yêu cầu, áp dụng quy tắc clarify chung.

Không mặc định mọi câu có “ở đâu” là office, mọi “phòng nào” là unit, hoặc dùng
`all` để né việc xác định ý định. Việc chọn clarify cho một câu cụ thể cần được
kiểm tra với contract đã chốt, không tự nới gold.

## 2. Một từ `office` đang mang ba vai trò

| Vị trí | Ý nghĩa trong hệ thống |
| --- | --- |
| `lookup_type=office` | Tra catalog đơn vị/phòng ban |
| `slots.office` | Tên đơn vị đầu vào cần tìm |
| `slots.requested_field=office` | Địa chỉ/vị trí cần lấy ở đầu ra |

Trong registry, `office.slot_schema.office` hiện chỉ có type và verification_role,
không có description. `requested_field` có alias địa chỉ nhưng không giải thích
rõ sự khác nhau giữa tên slot và giá trị enum. Dispatcher dùng `slots.office`
làm candidate tìm đơn vị và truyền requested_field cho resolver: hai vai trò
thật sự khác nhau, không phải cách diễn đạt tùy ý.

Đề xuất chưa áp dụng:

- Thêm description cho `slots.office`: “Tên đơn vị/phòng ban đã được nêu,
  không phải địa chỉ, tầng hoặc số phòng.”
- Thêm description cho requested_field: “Trường đầu ra cần tra; office là
  địa chỉ/vị trí, services là danh sách dịch vụ của đơn vị.”

Đây là khoảng trống giải thích có thể kiểm chứng, nhưng chưa có thí nghiệm
chứng minh việc bổ sung sẽ cải thiện accuracy.

## 3. Các field gần nghĩa khác cần nhất quán

- `program.requested_field=faculty`: khoa phụ trách ngành;
  `lookup_type=faculty`: tra liên hệ một khoa đã nêu tên;
  `program.scope=faculty`: giới hạn danh sách ngành theo khoa.
  Enum của program hiện chưa có description cho các vai trò này.
- `student_service.slots.service`: dịch vụ đầu vào cần hỗ trợ;
  `office.requested_field=services`: danh sách dịch vụ đầu ra.
- Với `program.requested_field=email/phone/website/office`, cần nói rõ đây là
  liên hệ của khoa phụ trách ngành qua relationship, không phải một “email ngành”.
  `TOOLS.use` đã nói ngành kèm email khoa là một task, nhưng enum chưa giải thích
  đầy đủ các trường liên hệ còn lại.
- Prompt toàn cục liệt kê “trách nhiệm” trong nhóm RAG; ngay sau đó cho phép
  student_service tra đơn vị phụ trách. Registry phân biệt trách nhiệm theo quy
  chế với hỗ trợ vận hành. Có thể làm rõ ngay tại câu RAG thành “trách nhiệm theo
  quy chế/chính sách”, tránh model hiểu mọi câu hỏi ai phụ trách đều là RAG.
  Đây là nguy cơ diễn giải, chưa phải bằng chứng một lỗi runtime mới.

Các bổ sung nên nằm ở registry nơi sở hữu ngữ nghĩa field; không lặp lại nguyên
một bộ quy tắc trong system prompt. Không đổi tên field hoặc thêm heuristic sửa
output theo từ khóa chỉ để khiến regression pass.

## 4. OpenAI chưa được tích hợp; strict schema cần kiểm tra riêng

`ai_router.py` chỉ đăng ký provider `groq` và `deepseek`; constructor từ chối
provider khác. Nhánh dùng OpenAI SDK hiện gọi endpoint DeepSeek, không phải OpenAI.
Chỉ điền key hoặc thay model name sẽ không tạo được cấu hình Luna hợp lệ.

Schema nội bộ hiện cho phép `slots.additionalProperties=true` và dictionary
động ở `slot_spans`; response wrapper hiện là `strict=false`.
Vì thế không được chỉ đổi sang `strict=true` rồi khẳng định schema đã tương thích
OpenAI Structured Outputs. Tài liệu chính thức yêu cầu đóng các object bằng
`additionalProperties=false` cho Structured Outputs. JSON hợp lệ và đúng ý định
vẫn là hai vấn đề riêng; normalizer/validator phải tiếp tục kiểm tra ngữ nghĩa.

Tích hợp provider, lựa chọn JSON mode hay schema strict tương thích, timeout,
retry, usage và diagnostics là bước triển khai riêng. Chưa thực hiện trong lượt này.

## 5. Kiểm chứng và bước tiếp theo

Đã chạy ba file test liên quan: `test_ai_router_prompt.py`,
`test_scale_and_task_pairing_integration.py`,
`test_structured_grounding_and_field_coverage.py`: **134 passed, 17,40 giây**.
Chặn socket connect/connect_ex trong tiến trình test; không gọi inference.
Lượt đầu có 103 pass và 31 lỗi setup vì pytest không truy cập được thư mục tạm
mặc định; chạy lại toàn bộ ba file với basetemp riêng trong workspace thì pass.
Đây là tập test mục tiêu, không phải toàn bộ suite hoặc benchmark live.

Test prompt hiện có kiểm tra description được gửi tới Groq/DeepSeek, giữ field
đã xuất (không tự sửa bằng keyword), và fixture contact do người viết.
Các test đó không chứng minh Luna đã hiểu đúng; chưa có output Luna nào trong
đợt rà soát này.

Trước khi gọi API cần kiểm tra ít nhất các cặp đối chiếu: đơn vị phụ trách /
vị trí, một đơn vị đã nêu tên / một dịch vụ chưa biết đơn vị, đơn vị và vị trí
cùng câu, dịch vụ đầu vào / danh sách dịch vụ, ngành → liên hệ khoa / liên hệ
khoa trực tiếp; giữ cả câu diễn đạt mới ngoài hai regression cũ.
Giữ các test thang điểm, đa entity và cohort đã có. Không thay gold để hợp model.

## Nguồn chính thức

- [GPT-6 Luna, model ID và khả năng hỗ trợ](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [Structured Outputs, điều kiện schema](https://developers.openai.com/api/docs/guides/structured-outputs)

Các giới hạn schema trong tài liệu được đối chiếu với source; chưa được thử bằng
request thật và không phải kết luận model đã từ chối một request trong lượt này.
