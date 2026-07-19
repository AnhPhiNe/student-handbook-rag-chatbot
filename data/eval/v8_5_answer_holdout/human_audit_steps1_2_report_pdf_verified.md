# Human Audit Bước 1–2 — Bản kiểm chứng trực tiếp 3 Sổ tay

> Phạm vi: 25 case trong `final_steps_guide.md`. Đây là **AI-assisted PDF-verified audit**; không phải đánh giá độc lập của một chuyên gia thứ ba.

## Nguồn đã đối chiếu

- `so_tay_K48_49.pdf` — K48-K49, SHA-256 `4bf7b510b66e6ed8ce60008d48efd05723f06899171cbf89e4494f4b277739db`
- `so_tay_K50.pdf` — K50, SHA-256 `bbae270b9821c71eeede660e3168c868bde07f458f07b648645c14584bdeb8b0`
- `so_tay_K51.pdf` — K51, SHA-256 `bab2e55fa964da302144aafa5675d0f5b2d8003254a5159e2d612a03f4beb4bd`

Ngoài câu hỏi, ground truth, required facts, câu trả lời Gemini, citations và điểm Judge, từng case đã được kiểm lại với Điều/Khoản trong PDF tương ứng.

## Bước 1 — Kết quả cập nhật

| Metric | Kết quả | Gate | Trạng thái |
|---|---:|---:|:---:|
| Human Correctness — 25 case (`human_score`) | **88,8%** | ≥85% | ✅ |
| Human Faithfulness — 19 regulation, tính đúng theo guide bằng `human_score` | **88,9%** | ≥90% | ❌ |
| Claim-level Faithfulness — kiểm trực tiếp PDF, metric bổ sung | **98,2%** | ≥90% | ✅ |
| Citation Correctness — 25 case | **94,6%** | ≥90% | ✅ |
| Critical False Pass | **0** | 0 | ✅ |
| Material Hallucination (`human_score < 0,3`) | **0/25 = 0,0%** | ≤5% | ✅ |
| Repeat MAE — 5 case | **0.04** | thấp | ⚠️ tạm thời |

**Điểm quan trọng:** template chỉ có một trường `human_score`, nên khi chạy script theo guide, cả Human Correctness và Human Faithfulness đều được suy ra từ cùng trường này. Vì vậy kết quả chính thức theo guide là **88,9% Human Faithfulness**, chưa đạt 90%. Metric claim-level 98,2% là phép kiểm bổ sung tách riêng mức độ được PDF hỗ trợ.

### Các case làm giảm điểm chính

- **v85_ans_049 — 0,40:** nguồn đúng là Điều 12 về CVHT/BCS trong quản lý ngoại trú, nhưng câu trả lời chuyển sang nhiệm vụ CVHT chung.
- **v85_ans_084 — 0,75:** các claim đều có nguồn nhưng trộn quy định K48/K50 với bản sửa đổi K51 mà không tách khóa.
- **v85_ans_099 — 0,40:** suy diễn từ tháng xét tốt nghiệp thành quyền lựa chọn tháng nhận bằng.
- **v85_ans_006, v85_ans_042, v85_ans_005:** đúng phần lớn nhưng thiếu ý chính hoặc mở rộng lệch trọng tâm.

## Bước 2 — Phân loại 21 case Judge chấm thấp nhất

| Phân loại | Số case | Tỷ lệ |
|---|---:|---:|
| Judge Error | **15** | **71,4%** |
| Elaboration / scope issue | **4** | **19,0%** |
| Lỗi retrieval / lệch trọng tâm, không hallucination | **1** | **4,8%** |
| True Hallucination | **1** | **4,8%** |

- **20/21 case (95,2%) không phải true hallucination.**
- Tuy nhiên, không nên gọi toàn bộ 20 case đó là hoàn hảo: 4 case có vấn đề scope/elaboration và 1 case là lỗi retrieval/trả lời lệch trọng tâm.
- **True Hallucination duy nhất: `v85_ans_099`.** Sổ tay K51 quy định đợt xét tốt nghiệp và thời hạn cấp bằng, không quy định sinh viên có hay không có quyền chọn tháng nhận bằng.
- Tỷ lệ **1/21 = 4,8%** chỉ áp dụng cho lát cắt low21; không được dùng làm hallucination rate của toàn bộ 100 case.

## Các lỗi dữ liệu/annotation phát hiện thêm

- **v85_ans_096:** bị gắn `unanswerable`, nhưng K50 Điều 14 trả lời trực tiếp cơ chế đổi điểm NCKH.
- **v85_ans_097:** metadata cohort không khớp query; quy định ngoại ngữ áp dụng được cho K51 nhưng được kiểm chứng qua văn bản liên khóa áp dụng từ tuyển sinh 2022.
- **v85_ans_092:** metadata/query có dấu hiệu lệch khóa; kết luận abstain vẫn đúng khi kiểm toàn văn K51.
- **v85_ans_084:** câu hỏi `general` nhưng answer cần tách rõ bản cũ và bản sửa đổi theo khóa.

## Kết luận sử dụng cho CV/README

Chưa nên ghi rằng dự án đã vượt toàn bộ CV-ready gate. Cách ghi an toàn hiện tại:

> PDF-verified audit trên 25 case đạt 88,8% overall human score, 94,6% citation correctness, 0 critical false-pass; direct claim-level faithfulness trên 19 regulation cases đạt 98,2%. Một true hallucination được phát hiện trong lát cắt 21 case khó nhất.

Sau khi sửa `v85_ans_049`, `v85_ans_084`, `v85_ans_099` và chạy lại, hãy thực hiện consistency check sau ít nhất 30 phút để chốt số liệu cuối.

## Bảng điểm 25 case

| Case | Nhóm | Overall | Faithfulness PDF | Citation | Phân loại |
|---|---|---:|---:|---:|---|
| v85_ans_006 | low21 | 0.80 | 0.95 | 1.00 | Elaboration / scope issue |
| v85_ans_008 | low21 | 1.00 | 1.00 | 1.00 | Judge Error |
| v85_ans_016 | low21 | 1.00 | 1.00 | 1.00 | Judge Error |
| v85_ans_019 | low21 | 0.90 | 1.00 | 1.00 | Judge Error |
| v85_ans_025 | low21 | 0.85 | 1.00 | 1.00 | Elaboration / scope issue |
| v85_ans_034 | low21 | 1.00 | 1.00 | 1.00 | Judge Error |
| v85_ans_036 | low21 | 1.00 | 1.00 | 1.00 | Judge Error |
| v85_ans_042 | low21 | 0.75 | 1.00 | 1.00 | Elaboration / scope issue |
| v85_ans_049 | low21 | 0.40 | 0.95 | 0.50 | Lỗi retrieval / lệch trọng tâm, không hallucination |
| v85_ans_052 | low21 | 1.00 | 1.00 | 1.00 | Judge Error |
| v85_ans_058 | low21 | 1.00 | 1.00 | 1.00 | Judge Error |
| v85_ans_059 | low21 | 1.00 | 1.00 | 1.00 | Judge Error |
| v85_ans_063 | low21 | 0.90 | 0.95 | 1.00 | Judge Error |
| v85_ans_065 | low21 | 0.80 | 0.95 | 1.00 | Judge Error |
| v85_ans_078 | low21 | 1.00 | 1.00 | 1.00 | Judge Error |
| v85_ans_084 | low21 | 0.75 | 0.85 | 0.80 | Elaboration / scope issue |
| v85_ans_092 | low21 | 0.95 | 1.00 | 0.90 | Judge Error |
| v85_ans_095 | low21 | 0.95 | 1.00 | 0.90 | Judge Error |
| v85_ans_096 | low21 | 1.00 | 1.00 | 1.00 | Judge Error |
| v85_ans_097 | low21 | 1.00 | 1.00 | 0.90 | Judge Error |
| v85_ans_099 | low21 | 0.40 | 0.50 | 0.70 | True Hallucination |
| v85_ans_004 | random4 | 1.00 | 1.00 | 1.00 | correct supported |
| v85_ans_005 | random4 | 0.75 | 1.00 | 1.00 | correct but partially relevant |
| v85_ans_045 | random4 | 1.00 | 1.00 | 0.95 | correct supported |
| v85_ans_090 | random4 | 1.00 | 1.00 | 1.00 | correct supported |