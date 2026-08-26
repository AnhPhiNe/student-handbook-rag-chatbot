# Product regression

Đây là tập **development/product regression**, không phải benchmark hoặc holdout.
Có thể chạy lại sau mỗi thay đổi tổng quát. Không dùng LLM judge, frozen manifest hay
candidate workflow.

## Chạy

Kiểm tra schema mà không gọi backend/LLM:

```powershell
.\.venv\Scripts\python.exe scripts\run_product_regression.py --dry-run
```

Chạy toàn bộ pipeline thật (mặc định tắt response cache):

```powershell
.\.venv\Scripts\python.exe scripts\run_product_regression.py
```

Chạy một vài case khi phát triển:

```powershell
.\.venv\Scripts\python.exe scripts\run_product_regression.py --case product_009 --case product_023
```

Report được ghi vào `data/eval/reports/product_regression.json`; thư mục report được
Git ignore để tránh commit raw output có thể chứa dữ liệu runtime.

## Human review

Mỗi case trong report có khối `human_review`. Reviewer đọc câu trả lời và mở nguồn
trích dẫn/bảng hiển thị, sau đó điền:

- `decision`: `pass` hoặc `fail`.
- `tasks_complete`: không bỏ yêu cầu chính.
- `grounded`: không có claim quan trọng ngoài evidence.
- `citations_correct`: mọi phần được trả lời có nguồn đúng.
- `cohort_correct`: không trộn K48-K49/K50/K51 hoặc applicability.
- `abstention_correct`: phần thiếu căn cứ biết từ chối/yêu cầu làm rõ.
- `runtime_stable`: không crash hoặc timeout bất thường.
- `severity`: `none`, `minor`, `major`, `critical`.
- `notes`: ghi ngắn nguyên nhân quan sát được.

Mục tiêu sản phẩm: ít nhất 90% pass và không có critical failure. Với 30 case,
ngưỡng 90% tương ứng tối thiểu 27/30.

