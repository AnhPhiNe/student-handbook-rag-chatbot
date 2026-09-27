# V49: ngữ nghĩa field và OpenAI Luna — chuẩn bị offline

## Trạng thái

Chỉ sửa source local và kiểm thử offline. Không gọi inference, không xác minh
key/quyền truy cập model, không commit/push/deploy. Qwen vẫn là cấu hình mặc định
trong `configs/ai_router.yaml`. Prompt local dùng chung đã chuyển từ V48 sang V49;
production đang chạy không được thay đổi trong đợt này.

## Những gì thay đổi

Đã rà prompt tổng, TOOLS được dựng từ registry và schema. Giữ nguyên quy tắc task
độc lập, history, cohort, thang điểm, đa entity, structured/RAG/clarify và JSON.
Chỉ làm rõ những điểm có bằng chứng thiếu hoặc dễ nhập nhằng:

- RAG cho trách nhiệm **theo quy chế/chính sách**, không đồng nhất với tra đơn vị
  hỗ trợ một dịch vụ.
- `unit` là tên đơn vị, `requested_field=office` là vị trí; không chọn chỉ theo
  từ “phòng”, không dùng `all` để né xác định yêu cầu, clarify nếu mục đích vẫn mơ hồ.
- `slots.office` là tên đơn vị đầu vào, không phải địa chỉ đầu ra.
- `service` là dịch vụ đầu vào; `services` là danh sách dịch vụ đầu ra.
- Phân biệt catalog faculty, trường khoa phụ trách ngành, phạm vi liệt kê ngành
  theo khoa và thông tin liên hệ khoa được resolver nối từ ngành.
- `graded` không tự xác định foundation/remaining. Không suy thêm phạm vi.

Registry version 8; prompt `structured-regulation-v49-field-semantics`.
Không đổi gold, enum/HTTP schema, resolver, hay thêm luật sửa output theo keyword.
Không thêm ví dụ riêng cho case 093/096 hoặc tên model vào prompt.

## Tích hợp OpenAI

`provider=openai` sử dụng SDK có sẵn qua Responses API và endpoint OpenAI cố định.
Không gửi key OpenAI tới base URL DeepSeek hoặc giá trị OPENAI_BASE_URL còn sót.
Chỉ hỗ trợ model đã yêu cầu `gpt-6-luna` trong đợt này; cấu hình model Groq còn sót
bị chặn trước request.

- JSON mode: `text.format.type=json_object`, schema nội bộ nằm trong prompt;
  normalizer và validator vẫn quyết định contract. **Không phải strict schema.**
- Không gửi temperature hoặc tham số max_tokens kiểu Chat Completions.
- Gửi reasoning effort và `max_output_tokens`; tắt lưu Responses bằng `store=false`.
- SDK retry=0; dùng retry/key pool sẵn có của router, tránh nhân số retry.
- Ánh xạ input/output/total token, reasoning/cache counters vào diagnostics;
  không lưu reasoning hoặc refusal text.
- Response incomplete, refusal hoặc failed không trở thành plan thực thi, ngay
  cả khi đoạn JSON nhận được parse được; đi vào fallback và diagnostics sẵn có.
- Cache key thêm provider, reasoning, response format và cấu hình token budget
  để không tái dùng plan của một cấu hình khác. Cấu hình Luna thử nghiệm tắt cache.

Không sửa schema nội bộ thành strict chỉ để tích hợp provider mới. Khi cần strict
schema, phải thiết kế và kiểm thử tương thích riêng, không chỉ bật strict=true.

## Cấu hình thử nghiệm (chưa được gọi API)

`configs/experiments/ai_router_openai_luna.yaml`:

| Thuộc tính | Giá trị |
| --- | --- |
| Model / reasoning | gpt-6-luna / low |
| Response format | JSON object |
| Output budget / hard cap | 8192 / 8192 |
| Timeout | 20 giây mỗi attempt |
| Transient retries | Tối đa 1 theo router |
| Local throttle | 30 request/phút/key; không phải hạn mức tài khoản được xác minh |
| Router cache | Tắt; state key pool tách khỏi Groq/DeepSeek |

Output budget là cấu hình khởi điểm chưa tối ưu bằng thực nghiệm, không phải trần
chi phí USD. Một retry hoặc semantic repair có thể phát sinh thêm request;
planner tổng thời gian có thể vượt 20 giây. Không tuyên bố latency/accuracy live.

## Cách chuẩn bị cấu hình — không tự chạy eval

Điền `OPENAI_API_KEY` trong `.env` local, không gửi key qua chat. Có thể cấu hình
terminal PowerShell cho lượt đánh giá riêng sau khi duyệt chi phí:

```powershell
$env:STUDENT_RAG_ROUTER_CONFIG = 'configs/experiments/ai_router_openai_luna.yaml'
$env:STUDENT_RAG_ROUTER_MODEL = 'gpt-6-luna'
$env:STUDENT_RAG_ROUTER_REASONING_EFFORT = 'low'
$env:STUDENT_RAG_ROUTER_RESPONSE_FORMAT = 'json_object'
$env:STUDENT_RAG_ROUTER_MAX_OUTPUT_TOKENS = '8192'
$env:STUDENT_RAG_ROUTER_HARD_MAX_OUTPUT_TOKENS = '8192'
$env:STUDENT_RAG_ROUTER_REQUEST_TIMEOUT_SECONDS = '20'
$env:STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED = 'false'
$env:STUDENT_RAG_DISABLE_ROUTER_CACHE = 'true'
```

Các dòng này chỉ đặt biến terminal, không gọi API. Chúng ghi đè các giá trị Qwen
có thể còn trong `.env`; không ghi lại `.env` hoặc cấu hình production.
Mở terminal mới khi muốn bỏ các override của terminal thử nghiệm.

## Kiểm chứng và giới hạn

Toàn bộ `tests`: **1.167 pass, 2 dependency deprecation warnings, 33,33 giây**.
Kết nối ra ngoài bị chặn trong tiến trình test; chỉ cho loopback để socketpair
nội bộ Windows/asyncio hoạt động. Lượt chặn mọi socket ban đầu có 33 lỗi API test
do socketpair bị chặn và 1.134 pass; không phải lỗi HTTP từ provider. Sau điều chỉnh
test harness, chạy lại toàn bộ suite đạt kết quả trên. Lỗi cú pháp YAML trong lúc
soạn description đã được sửa trước lượt test mục tiêu đạt 180 pass.

Test mới mock provider và dùng SDK thật qua `httpx.MockTransport`, không qua mạng:
request none/low, schema trong prompt, usage, retry/timeout, auth/rate-limit/server
error classification, output rỗng/hỏng/cắt dở/refusal, semantic repair, cấu hình,
cache identity và mô tả TOOLS của cả ba provider. Các fixture ngữ nghĩa và regression
thang điểm/đa entity vẫn phải pass; chúng không thay thế đánh giá output model thật.

Ngân sách độ dài test tăng từ 15.200 lên 17.000 ký tự (ước lượng 4.250 token),
phù hợp cho phép tăng độ dài để rõ nghĩa của người dùng. Đây không phải tokenizer
hoặc token tính tiền. System prompt đo được 8.198 ký tự, TOOLS 6.122 và schema
JSON compact 1.411, chưa tính query/history động.

Snapshot/hash V48 và các report cũ được giữ nguyên. V49 là thay đổi prompt nên
không dùng lại freeze V48 để chứng nhận thí nghiệm mới. Snapshot chuẩn bị V49 không
phải quyền chạy API, không phải release, và không chứng minh hiệu quả model.

Bước sau: duyệt số lượt/ngân sách, smoke có các cặp who/where và service/services
bên cạnh 18 case cũ; giữ prompt/gold cố định giữa các model. Chỉ sau đó xét full
benchmark, staging có composer và canary. Chưa phê duyệt bất kỳ bước live nào ở đây.

## Tài liệu đối chiếu

- [GPT-6 Luna: model ID và reasoning](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [Responses JSON mode và giới hạn strict schema](https://developers.openai.com/api/docs/guides/structured-outputs)

Theo OpenAI Docs, JSON mode không đảm bảo tuân thủ schema. Khả năng truy cập và
chất lượng trên tài khoản thật vẫn cần xác minh ở lượt gọi API được duyệt riêng.
