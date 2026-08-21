# Single-Cohort Regression v3 — Review Protocol

## Mục đích

`single_cohort_regression_v3` là bộ đánh giá theo Query Contract hiện tại. Bộ
`data/eval/final_holdout` chỉ là archive bất biến để truy xuất nguồn gốc; nhãn
cũ không còn là release gate và không được sửa.

Bundle proposal được sinh từ commit ghi trong `manifest.json`. Output của
Planner/executor hiện tại không được dùng để tạo gold. Mỗi case giữ nguyên
`origin.case_id`, query và toàn bộ `legacy_annotation` để reviewer đối chiếu.

## File cần review

- `data/eval/single_cohort_regression_v3/review_queue.json`: hàng đợi quyết định.
- `data/eval/single_cohort_regression_v3/migration_report.json`: tổng hợp lý do.
- `data/eval/single_cohort_regression_v3/*_cases.json`: proposal đầy đủ và nhãn cũ.
- `configs/structured_lookup_registry.yaml`: tool/source contract hiện hành.
- `data/processed/chunks/all_docstore_items.json`: nguồn RAG gốc.
- `data/processed/tables/*.json` và `data/processed/directories/*.json`: nguồn structured.

Không cần chỉnh hoặc gửi lại `data/eval/final_holdout` nếu chỉ review proposal;
hash archive đã được validator kiểm tra trực tiếp.

## Thứ tự review

1. Review các hàng có `gold_source_not_applicable_to_effective_cohort` hoặc
   `gold_parent_missing_from_current_docstore`. Không được giữ nguồn khác cohort.
2. Review `rag_gold_requires_source_review`. Chọn một trong hai:
   - bổ sung source-backed `evidence_sources` và đặt `expected_status=ok`; hoặc
   - xác nhận không có nguồn phù hợp và giữ `expected_status=no_match`.
3. Review `structured_source_binding_requires_adapter_audit` bằng adapter thật.
   Nếu status `ok`, proposal cuối phải có typed slots, expected result và
   `expected_source_records` gồm record/document/parent/pages/cohort/source type.
4. Review formula. K50/K51 `scholarship_score` đang bị source data đánh dấu
   `rejected_no_source_formula`, vì vậy proposal là `no_match`; không được phục
   hồi công thức chỉ vì runtime cũ từng trả được.
5. Review 59 `deferred_multi_cohort`: single-cohort phải clarify và không retrieval.
6. Review production duplicates qua `linked_contract_case_id`; không tạo gold mới
   từ kết quả cache/runtime.

## Cách điền quyết định

Mỗi hàng trong `review_queue.json` cần:

- `review_decision`: `accept`, `revise`, `defer_multi_cohort` hoặc
  `retire_invalid_gold`.
- `reviewer` và `reviewed_at` (ISO-8601).
- `review_notes` cho thay đổi quan trọng; bắt buộc khi retire.
- Với `revise`: thêm `replacement_contract`, và `replacement_lifecycle` nếu cần.

`retire_invalid_gold` không phải pass. Case retired luôn bị loại khỏi mẫu số và
được báo cáo riêng. Không retire chỉ vì hệ thống hiện tại fail case.

## Apply và freeze

Apply proposal để kiểm tra trước, chưa freeze:

```powershell
python scripts/apply_single_cohort_regression_v3_reviews.py `
  --decisions data/eval/single_cohort_regression_v3/review_queue.json
```

Chỉ sau khi mọi hàng đã có quyết định và structured/RAG source binding hợp lệ:

```powershell
python scripts/apply_single_cohort_regression_v3_reviews.py `
  --decisions data/eval/single_cohort_regression_v3/review_queue.json `
  --freeze
```

Freeze sẽ fail nếu còn review, sai source/cohort, structured `ok` không có source
record, RAG `ok` không có evidence, hoặc archive hash bị thay đổi.

Sau freeze mới được chạy full runtime evaluator và đưa report đó vào
`--regression-v3-report`. Readiness report không thể thỏa release gate.
