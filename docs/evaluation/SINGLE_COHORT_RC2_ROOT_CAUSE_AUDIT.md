# Single-Cohort RC2 — Root-Cause Audit

## Phạm vi và provenance

- Runtime candidate gốc: `fd2971fd3b5e281d32c2473265ebf03ef6374007`.
- Audit đầu vào: `dev_answer_external_llm_audit_fd2971fd.json`.
- Audit đã được project owner phê duyệt theo phương thức
  `llm_assisted_human_review`.
- Báo cáo này chỉ dùng case ID để truy vết evaluation. Runtime không chứa branch
  theo case ID, từ khóa đặc thù hoặc danh sách ngoại lệ theo câu hỏi.
- Không dùng reranker và không giảm retrieval pool Hit@5.

## Kết luận root cause

15 case cần chú ý gồm 3 incorrect abstention, 11 material answer defects và 1
critical cross-request defect. Các lỗi không xuất phát từ Planner hoặc retrieval
miss trong lần chạy này.

| Nhóm lỗi | Case | Root cause | Tầng sửa | Trạng thái |
|---|---|---|---|---|
| Incorrect abstention | `dev-robustness-09`, `dev-robustness-14`, `dev-single_structured-09` | RAG low-confidence guardrail chặn structured result đã `ok` và source-bound | Answer contract | Đã sửa và có sync/stream/cache regression tests |
| Cross-request claim leakage | `dev-two_regulations-10` | `REQUEST_RESULTS` dùng `r1/r2`, nhưng source header chỉ ghi index `0/1`; composer không nhận cùng một identity namespace | Context + composer contract | Đã sửa deterministic; cần live verification |
| Unsupported negative completeness | `dev-follow_up-04` | Composer suy “nguồn không nhắc” thành “không có ngoại lệ” | Composer prompt | Đã sửa invariant; cần live verification |
| Scope/condition overgeneralization | `dev-two_regulations-08`, `dev-mixed-01`, `dev-single_rag-01` | Điều kiện chỉ áp dụng cho một nhánh bị diễn đạt thành quyền chung | Composer context contract | Đã sửa invariant; cần live verification |
| Unsupported synthesis | `dev-follow_up-02`, `dev-single_rag-09`, `dev-two_regulations-02`, `dev-two_regulations-14`, `dev-two_regulations-15`, `dev-follow_up-03`, `dev-two_regulations-01` | Composer ghép chi tiết, con số hoặc thủ tục không được một source trực tiếp hỗ trợ đầy đủ | Composer prompt + answer validation gate | Prompt invariant đã sửa; cần live answer/judge để chứng minh |

## Ranh giới request mới

Mỗi atomic request được xuất rõ trong `REQUEST_EVIDENCE_SCOPE` với:

- `request_id`
- thứ tự
- loại request
- status
- cohort
- `query_span`

Mỗi PRIMARY SOURCE có cùng `Request ID` và một evidence-boundary rõ ràng. Index
chỉ còn là metadata thứ tự; nó không phải source of truth cho ownership. Đường
legacy không có `request_id` vẫn giữ header cũ để backward compatibility.

Composer được ràng buộc:

1. Chỉ dùng source có cùng `request_id` cho phần trả lời tương ứng.
2. Không chuyển điều kiện, thủ tục, số liệu hoặc kết luận giữa requests.
3. Không ghép nhiều mảnh đúng thành một quyền/kết luận mới nếu không source nào
   trực tiếp phát biểu toàn bộ claim.
4. Không suy kết luận phủ định tuyệt đối từ sự im lặng của nguồn.
5. Không mở rộng điều kiện của một nhánh thành quy tắc chung.

## Judge/evaluator separation

- `judge_false_positive`: evaluator defect, không phải production answer defect.
- `judge_false_negative`: answer vẫn được tính là material defect; judge miss không
  làm case đó pass.
- Judge packet phải giữ request-scoped citations. Việc tăng citation cap không
  được dùng để che lỗi composer.
- Release metric phải lấy verdict sau audit/judge reconciliation, đồng thời báo
  riêng raw judge metrics.

## Verification gates

Deterministic candidate hiện yêu cầu:

- Full pytest pass.
- Ruff pass.
- Structured source-bound result không bị RAG confidence chặn.
- Request ID trong request result, source header và evidence boundary phải khớp.
- Legacy request-index header vẫn tương thích.
- Response cache fingerprint đổi khi answer prompt/pipeline contract đổi.

Các sửa đổi prompt/context chỉ được công nhận hiệu quả sau khi chạy lại answer
stage trên dev và judge protocol đã pin. Không được dùng 60 hidden để kiểm tra bản
sửa này.

