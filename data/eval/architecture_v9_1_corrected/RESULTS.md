# Architecture V9.1 — Corrected evaluation results

V9.1 là bản hiệu chỉnh phép đo trên đúng runtime và output đã đóng băng trước đó. Không có thay đổi nào đối với Planner, Composer, retrieval, database hoặc nội dung câu trả lời.

## Phạm vi

| Suite | Mẫu số | Nguồn output |
|---|---:|---|
| Deterministic | 135 | V9 deterministic run 3 |
| Retrieval | 155 | V9 retrieval run 1, loại 5 case sai contract |
| Generate + Judge | 141 | V9 generation/judge run 1, loại 9 case sai question–gold scope |
| Human audit | 40 | 37 mẫu hợp lệ cũ + 3 mẫu thay thế theo SHA256 cố định |

Production 60 được giữ trong bundle để truy xuất lịch sử nhưng không phải metric headline của V9.1.

## Deterministic

| Metric | Kết quả |
|---|---:|
| Pass | **124/135 (91,85%)** |
| Structured precision | 98,85% |
| Structured recall | 97,73% |
| Plan structure accuracy | 96,30% |
| Structured execution accuracy | 96,30% |
| Structured evidence accuracy | 96,59% |
| Structured row accuracy | 94,32% |
| Resolved-result accuracy | 41/46 (89,13%) |
| Cross-cohort leakage | **0%** |
| Planner fallback | **0%** |

11 case chưa đạt gồm 7 runtime-contract deviation và 4 case chỉ thiếu/sai fact-lock. Metric này không thay đổi so với V9 135-case vì evaluator correction không thay hành vi deterministic.

## Retrieval

Chế độ đo đúng production: `vector_primary_graph_supplement`, Qdrant `student_handbook_semantic_v32`, MongoDB `parent_docs_v32`, không reranker/PhoRanker.

| Metric | Kết quả |
|---|---:|
| Hit@1 | 134/155 (86,45%) |
| Hit@3 | 146/155 (94,19%) |
| Hit@5 | **149/155 (96,13%)** |
| MRR | **0,9085** |
| nDCG@5 | **0,8704** |
| Primary Hit@5 | 96,13% |
| Required-source Recall@5 | 91,29% |
| Cohort match | **100%** |
| Cohort leakage | **0%** |
| Realistic Hit@5 | 95,12% |
| Stress Hit@5 | 100% |

6/155 case là retrieval failure thật. Năm case bị loại được liệt kê trong `CORRECTION_AUDIT.md`; các câu đó không xác định duy nhất văn bản/target mà gold ngầm chọn.

## Generate + Judge

Các per-case Judge output của `openai/gpt-oss-120b` được replay nguyên trạng vì Judge prompt không đổi. Evaluator chỉ tính lại mẫu số và các metric deterministic phụ; Gemini không generate lại câu trả lời và Groq không judge lại.

| Metric | Kết quả |
|---|---:|
| Faithfulness | **90,79%** |
| Answer relevancy | **94,48%** |
| Answer correctness | **91,77%** |
| Context precision | 57,04% |
| Context recall | 81,96% |
| Citation correctness | **93,23%** |
| Abstention correctness | **95,74%** |
| Question-handling correctness | **97,16%** |
| Raw unsupported-claim flags | 16/141 (11,35%) |
| Human-adjudicated unsupported claims | **5/141 (3,55%)** |
| Critical runtime failure | 1 |

`numeric_accuracy` là `N/A (0 case)` vì V9/V8 không khai báo `numeric_assertions` độc lập. Không được dùng con số 82% cũ: metric cũ đã quét mọi số xuất hiện trong đoạn gold dài và tạo false negative.

Toàn bộ 21 automatic-risk case còn hợp lệ đã được audit: 11 Judge false positive, 6 runtime failure và 4 lỗi chất lượng nhỏ.

## Human audit

| Metric | Kết quả |
|---|---:|
| Hoàn tất | **40/40** |
| Điểm trung bình | **97,41%** |
| Human–Judge MAE | 0,0571 |
| Agreement trong sai số 0,15 | 87,50% |
| Critical false pass trong mẫu 40 | 0 |

Đây là single-reviewer audit; không báo Cohen's kappa hoặc inter-rater agreement.

## Gate và cách diễn giải

- Deterministic chưa qua gate cũ vì false-positive rate `2,13%` cao hơn ngưỡng `2,00%` đúng một case.
- Retrieval chưa qua gate cũ vì content-type match `96,13%` thấp hơn ngưỡng `98%`, dù Hit@5, MRR, nDCG@5 và cohort leakage đều đạt.
- Judge tự động chưa qua gate raw hallucination vì 11/16 cờ unsupported là false positive theo human audit. Sau adjudication, tỷ lệ còn lại là `3,55%`, dưới ngưỡng `5%`.
- Không hạ threshold hoặc sửa runtime để biến gate thành pass.

## Provenance

- Evaluated system commit: `7f1fc82bc0d6a02a10cc64f0a7726b3cc7a913a9`.
- Evaluation harness commit: `943d9b3805842ae764de7e3c893eceb1dbe96e7c`.
- Deterministic output SHA256: `5b721e90cba29129c77a28e33173ceef8aac471307e2fa7e899730fa61b952e0`.
- Retrieval output SHA256: `39f8a4f7e76bdace43a385aada2ca428b5fbb576cc91f2edfa70b02785fded4a`.
- Answer cache SHA256: `1ad9b9e535fcfab990e98d8f1b25e1e5f27b589009f294cbee59a496c959a01b`.
- Judge output SHA256: `6578831d64a241b6ed0168cae18761a1ee71db831c370558397cec4af90ef82f`.

V9.1 phù hợp làm báo cáo metric hiệu chỉnh cho CV với điều kiện luôn nêu đúng mẫu số. Vì đây là correction sau khi đã xem output, bài báo sau này nên dùng thêm một test set độc lập chưa từng được dùng để chẩn đoán hoặc loại case.
