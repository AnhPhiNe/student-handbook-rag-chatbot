# Planner v46 — sửa ranh giới hợp đồng, kiểm thử offline

Ngày: 26/09/2026. Chưa chạy model thật, chưa deploy, commit hoặc push.
Prompt: `structured-regulation-v46-contract-boundaries`.
Normalizer: `v29-planner-contract-boundaries`. Raw schema vẫn là QueryPlan v1.

Đợt này tiếp nối [audit v45](PLANNER_CONTRACT_AUDIT.md), không thay thế hay sửa
các số A/B đã lưu. Không đọc/chỉnh official_v3 hoặc gold. Không đổi HTTP API,
README, registry, dependency production hay cấu hình deployment trong đợt sửa này.
Các thay đổi local trước đó vẫn được giữ nguyên.

## Nguồn gốc đã đối chiếu qua Git

HEAD nền: `a8db95be58fb2c748bbcf016f0ac426ce8e900c1`.
Các mốc dưới đây là bằng chứng về sự hiện diện của cơ chế liên quan, không phải
khẳng định thời điểm đầu tiên người dùng gặp lỗi.

| Nhóm | Bằng chứng lịch sử |
|---|---|
| AUD-01, boolean | `b2fd2782c`, 26/08/2026, nhánh OOD dùng `bool(payload.get(...))` |
| AUD-02, cohort | `73fcae6a7`, 09/09/2026, ưu tiên cohort task và chỉ điền fallback khi trống; cơ chế này có mục đích bảo toàn scope từng task |
| AUD-03, history | `e13e941c`, 24/08/2026, prompt cắt 300 ký tự/lượt; đường grounding dùng content đầy đủ có từ trước đợt DeepSeek |
| AUD-04, đếm task | `7f1fc82b`, 03/09/2026, thêm marker count, repair và fallback cưỡng chế số task |
| AUD-05, nhiều trường | Ép requested_field thành chuỗi có trong lịch sử `35848e93`, 17/07/2026; v45 local mới làm rõ hướng dẫn dùng danh sách cho nhiều trường |

Không quy tất cả cho DeepSeek hay cho lần sửa prompt vừa qua. Đây là các lớp
quy tắc cũ/mới cần đồng bộ, và test tổng hợp kiểm tra một ranh giới trước đó chưa
được bao phủ đầy đủ.

## Hành vi đã chốt và thay đổi tối thiểu

### 1. Kiểu boolean: sai kiểu thì fallback có diagnostic

`out_of_domain` chấp nhận boolean thật, hoặc thiếu/null theo tolerance cũ.
Chuỗi `"false"`, `"true"`, số, array hay object không được chuyển bằng truthiness.
Normalizer trả safe RAG với `planner_fallback=invalid_plan_control` và
`invalid_out_of_domain_type`. Không đoán chuỗi sai kiểu có nghĩa gì.

Chưa gắn validator JSON Schema tổng quát vào runtime: các cơ chế phục hồi input
legacy/task-local vẫn được giữ. `jsonschema` chỉ là dependency kiểm thử từ audit.

### 2. Cohort: chỉ sửa trường hợp rõ ràng, không ghi đè toàn cục

Với plan **standalone, một raw task, đúng một khóa nêu trong query**, khóa trong
query là căn cứ cho task, kể cả khi model/UI ghi khóa khác. Sử dụng bản sao task,
không sửa raw payload dùng cho log.

Không áp dụng ghi đè này cho nhiều task, câu nhiều khóa hoặc follow-up. Các
trường hợp đó cần giữ task scope và lịch sử có thể có nhiều khóa. Đây không phải
bộ kiểm chứng ngữ nghĩa cohort hoàn chỉnh cho mọi cách diễn đạt, phủ định hay
tham chiếu ngầm; không tuyên bố đã giải quyết toàn bộ những trường hợp đó.

### 3. History: prompt và grounding dùng chung một view

`_visible_history_turns` tạo đúng 4 lượt cuối, tối đa 300 ký tự/lượt, giữ chỉ số
gốc trong cửa sổ. Lượt rỗng bị bỏ nhưng không đánh lại chỉ số.

Router truyền map content đã hiển thị cho normalizer ở cả initial và repair:

- Standalone/ambiguous: xóa standalone_query/referenced_turns không phù hợp và
  không dùng history để grounding.
- Follow-up: cần standalone_query có nội dung, danh sách chỉ số nguyên thực sự
  tồn tại trong view. Boolean không được coi là chỉ số integer; bỏ trùng chỉ số.
- Tham chiếu thiếu/sai: trả clarification, reason `invalid_history_reference`,
  không tiếp tục với câu rewrite chưa được xác thực tham chiếu.
- Grounding chỉ đọc các lượt đã tham chiếu, không đọc lượt khác hay phần sau ký
  tự 300 không xuất hiện trong prompt. Kiểm tra slot grounding cũ vẫn chạy sau đó.

Tham số `grounding_context` cũ vẫn dành cho caller offline đáng tin cậy nếu không
cung cấp `visible_history`; runtime router luôn truyền view. Cơ chế này không
chứng minh toàn bộ rewrite RAG trung thành về ngữ nghĩa — việc đó vẫn cần eval.

### 4. Count repair: giữ rà soát, bỏ cưỡng chế chỉ dựa vào số marker

Quy tắc được sửa đồng thời trong prompt và runtime:

> Xác định các target trong phạm vi trước; gộp theo logical-task rules và áp dụng
> giới hạn ba task. EXPLICIT_REQUEST_COUNT chỉ là tín hiệu rà soát bỏ sót.

Nếu số task lệch số marker, router vẫn gọi tối đa **một** lượt rà soát; feedback
yêu cầu kiểm tra đủ target trong phạm vi, không thêm task chỉ để khớp marker.
Không repair dựa trên count nếu plan đã OOD hoặc đã fallback có reason.

Sau repair, không chuyển cả plan thành safe RAG chỉ vì số lượng vẫn khác. Đây là
thay đổi hành vi có chủ ý: số lượng không phân biệt được bỏ sót thật với bỏ OOD
hoặc gộp hợp lệ. Test cũ đòi fallback vô điều kiện đã đổi kỳ vọng và ghi rõ giới
hạn này, không bị xóa lặng lẽ.

**Trade-off:** một model vẫn bỏ sót target sau repair có thể giữ plan thiếu.
Test count không chứng minh đủ ý, và lần trả lời thứ hai cũng không chứng minh
đủ ý. Giữ benchmark task coverage để đo rủi ro này ở lượt A/B sau. Không thêm
keyword thời tiết/danh bạ hay schema trường mới để chữa riêng fixture.

### 5. Nhiều trường liên hệ: giữ scalar hoặc list đúng kiểu

Directory resolver giữ requested_field scalar như trước; với list thì lưu bản
sao list thay vì chuỗi Python repr. Danh sách không tự đổi thành `all`.
Các consumer source được tìm theo literal `requested_field`: directory dùng làm
metadata; program có logic chọn action riêng nên không mở rộng program trong
đợt này. Prompt làm rõ “nhiều trường liên hệ”, không hứa mọi slot đều hỗ trợ list
xuyên suốt pipeline.

## Kiểm thử và giới hạn

Tám tình huống audit cũ đã được giữ assertion, làm chặt thêm một số assertion
(fallback reason, cohort cụ thể, không mutate raw plan), rồi bỏ marker xfail.
Không đổi gold hoặc thay câu hỏi để làm xanh test.

Thêm đối chứng: boolean hợp lệ/null và sai kiểu; query một/nhiều khóa; multi-task
khác scope; UI fallback; follow-up hợp lệ cả user/assistant; chỉ số âm, bool,
ngoài cửa sổ, lượt rỗng, chỉ số trùng; entity ở lượt không tham chiếu hoặc vùng bị
cắt; kiểm tra lại history trên repair; OOD thuần không bị ép task; gộp liên hệ
vẫn giữ đủ trường; scalar/list được giữ nguyên ở directory.

- Riêng `tests/test_planner_contract_audit.py`: **90 passed**, không xfail.
- Full backend suite lần cuối: **1.008 passed, 2 deprecation warnings**, không
  fail/xfail. Cảnh báo thuộc FastAPI/Starlette TestClient, không phải lỗi planner.
- Kiểm tra Ruff theo cấu hình CI, `pip check`, `git diff --check`: đạt.
- Không kiểm thử live Qwen/DeepSeek; không suy ra accuracy/latency mới.

Lần chạy full đầu tiên chặn mọi socket đã làm Windows asyncio/TestClient không
tạo được socket loopback (33 fail do harness, 973 pass). Chỉnh harness chỉ cho
phép IP loopback; vẫn chặn kết nối ra ngoài. Không sửa application code/test để
né lỗi harness. Lần tiếp theo đạt 1.006 test; hai test mới bổ sung được chạy riêng
trước lần xác nhận cuối đạt 1.008 test. Chỉ loopback nội bộ được cho phép để
Windows asyncio/TestClient hoạt động; kết nối ra ngoài bị chặn trong tiến trình test.

Prompt và normalizer đều đã tăng version, vốn có trong cache key nên không dùng
lại cache plan của phiên bản trước. Không xóa file cache của người dùng.

## Bước tiếp theo

Freeze đúng snapshot v46/v29 và giữ nguyên gold. Sau khi được duyệt chạy API,
chạy DeepSeek low smoke test rồi regression đầy đủ; so sánh Qwen trên cùng runtime.
Theo dõi riêng task coverage, follow-up clarification/fallback, JSON failures,
token usage và planner latency. V44 đạt 5/5 trước đây không phải kết quả của v46.
