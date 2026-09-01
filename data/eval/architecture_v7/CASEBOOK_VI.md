# Architecture V7 — Draft review casebook

> V7 is mutable and has not been run against the system. Source targets, distributions, graph links and overlap were reviewed and approved for a draft execution on 2026-09-01.

## Distribution

- `deterministic`: 140 cases; realistic=95, stress=45
- `retrieval`: 160 cases; realistic=108, stress=52
- `answers`: 150 cases; realistic=102, stress=48
- `production`: 60 cases; realistic=40, stress=20

### Deterministic theo case type

| Nhóm | Số case |
|---|---:|
| `single_structured` | 60 |
| `compound` | 28 |
| `capability_boundary` | 24 |
| `missing_or_ambiguous` | 12 |
| `out_of_domain` | 8 |
| `unsupported_in_domain` | 8 |

### Deterministic structured theo capability

| Nhóm | Số case |
|---|---:|
| `program` | 8 |
| `scoring` | 8 |
| `conduct` | 6 |
| `faculty` | 6 |
| `foreign_language` | 6 |
| `office` | 6 |
| `scholarship_classification` | 6 |
| `student_service` | 6 |
| `study_duration` | 6 |
| `formula` | 2 |

### Retrieval theo subtype

| Nhóm | Số case |
|---|---:|
| `semantic` | 68 |
| `exact_article` | 30 |
| `graph_linked` | 20 |
| `multi_source` | 20 |
| `multi_cohort_equivalent` | 12 |
| `typo_no_diacritics` | 10 |

### Generate + Judge theo case type

| Nhóm | Số case |
|---|---:|
| `regulation_true_rag` | 90 |
| `structured_answer` | 30 |
| `mixed_answer` | 10 |
| `clarification` | 8 |
| `out_of_domain` | 6 |
| `unanswerable` | 6 |

### Production theo scenario

| Nhóm | Số case |
|---|---:|
| `cold_rag` | 20 |
| `burst` | 10 |
| `streaming` | 10 |
| `structured` | 10 |
| `warm_cache` | 10 |

## Overlap review

- Exact historical matches: 0
- Cases flagged at token Jaccard >= 0.72: 0
- Flags are review signals; do not edit gold merely to lower similarity.

## Deterministic contract

- Each case declares one or more `accepted_outcomes`.
- Task order, task IDs and undeclared optional slots are not scored.
- Mode/lookup/slot keys are constrained only when architecturally material.
- Planner-level and task-level clarification can both be valid.
- Live/private requests accept safe unavailable, clarification or out-of-domain handling without fabricated evidence.

## Mẫu đại diện để review nhanh

Các bảng dưới đây là lát cắt cố định theo từng nhóm, không phải kết quả chạy hệ thống.

### Deterministic

| ID | Nhóm | Cohort | Câu hỏi |
|---|---|---|---|
| `v7_det_061` | `capability_boundary` | `K51` | Theo Điều 13 dành cho K51, nội dung về tổ chức thực hiện được quy định thế nào? |
| `v7_det_062` | `capability_boundary` | `K50` | Theo Điều 8 dành cho K50, nội dung về ứng xử với người học được quy định thế nào? |
| `v7_det_085` | `compound` | `K48-K49` | IELTS trong bảng tham chiếu của khóa em có hai khoảng tương đương nào. Đồng thời, điểm trung bình 0,95 được bảng học lực K48–K49 xếp mức nào? |
| `v7_det_086` | `compound` | `K50` | Chỉ xem bảng: HSK bậc 3 và bậc 4 tương ứng cấp nào. Đồng thời, điểm học phần 7,7 của K50 nằm ở hàng điểm chữ nào? |
| `v7_det_113` | `missing_or_ambiguous` | `K51` | Em học K50 nhưng năm tuyển sinh em lại ghi 2025; tra bảng thời gian chính quy giúp em. |
| `v7_det_114` | `missing_or_ambiguous` | `K51` | TOEIC bốn kỹ năng của em thiếu điểm Viết, vậy đã kết luận được bậc chưa? |
| `v7_det_133` | `out_of_domain` | `general` | Viết hàm JavaScript đảo ngược một chuỗi. |
| `v7_det_134` | `out_of_domain` | `general` | Gợi ý thực đơn ăn tối ít dầu mỡ cho gia đình. |
| `v7_det_001` | `single_structured` | `K51` | Trong bảng K51, TOEFL iBT được ghi các khoảng nào cho bậc 3 và bậc 4? |
| `v7_det_002` | `single_structured` | `K50` | Tra giúp em riêng dòng TOEFL ITP: hai cột bậc 3 và bậc 4 ghi gì? |
| `v7_det_125` | `unsupported_in_domain` | `K51` | Hồ sơ công nhận ngoại ngữ em gửi sáng nay đã được duyệt chưa? |
| `v7_det_126` | `unsupported_in_domain` | `K51` | Tiền học bổng kỳ này đã vào đúng tài khoản cá nhân của em chưa? |

### Retrieval

| ID | Subtype | Cohort | Câu hỏi | Gold chính |
|---|---|---|---|---|
| `v7_ret_013` | `exact_article` | `K50` | Điều 8 của quy định quy tắc ứng xử áp dụng cho K50 quy định gì về ứng xử với người học? | K50_QuyDinhQuyTacUngXu_Chuong2_Dieu8 |
| `v7_ret_014` | `exact_article` | `K50` | Điều 1 của quy định cố vấn học tập áp dụng cho K50 quy định gì về phạm vi và đối tượng áp dụng? | K50_QuyDinhCongTacCoVanHocTap_Chuong1_Dieu1 |
| `v7_ret_121` | `graph_linked` | `K51` | Ở K51, đánh giá và tính điểm học phần có dẫn chiếu điểm học phần không đạt phải đăng ký học lại theo quy định tại Điều 4; cần đọc thêm nội dung nào từ điều được dẫn chiếu? | K51_QuyCheDaoTao_Chuong3_Dieu10 |
| `v7_ret_122` | `graph_linked` | `K50` | Ở K50, trình tự, thủ tục và hồ sơ xét kỷ luật có dẫn chiếu Điều 37; cần đọc thêm nội dung nào từ điều được dẫn chiếu? | K50_QuyCheCongTacSinhVien_Chuong6_Dieu35 |
| `v7_ret_001` | `multi_cohort_equivalent` | `general` | Trong Sổ tay sinh viên, phạm vi điều chỉnh và đối tượng áp dụng được văn bản trong Sổ tay quy định như thế nào? | K48-K49_K48_49_QuyCheDaoTao_Chuong1_Dieu1, K50_QuyCheDaoTao_Chuong1_Dieu1, K51_QuyCheDaoTao_Chuong1_Dieu1 |
| `v7_ret_002` | `multi_cohort_equivalent` | `general` | Trong Sổ tay sinh viên, trách nhiệm của các đơn vị liên quan được quy chế rèn luyện quy định như thế nào? | K48-K49_K48_49_QuyCheDanhGiaKetQuaRenLuyen_Chuong5_Dieu16, K50_QuyCheDanhGiaKetQuaRenLuyen_Chuong5_Dieu16, K51_QuyCheDa… |
| `v7_ret_141` | `multi_source` | `K48-K49` | Em thuộc K48-K49 và cần biết hai nội dung: (1) học bổng; (2) khen thưởng và xử lý vi phạm. Mỗi nội dung có những điểm chính nào? | K48-K49_K48_49_QuyCheCongTacSinhVien_Chuong5_Dieu27, K48-K49_K48_49_QuyDinhNghienCuuKhoaHocSinhVien_Chuong4_Dieu15 |
| `v7_ret_142` | `multi_source` | `K50` | Em thuộc K50 và cần biết hai nội dung: (1) phòng hợp tác quốc tế; (2) hiệu lực thi hành. Mỗi nội dung có những điểm chính nào? | K50_QuyCheCongTacSinhVien_Chuong4_Dieu16, K50_QuyCheCongTacSinhVien_Chuong7_Dieu40 |
| `v7_ret_043` | `semantic` | `K48-K49` | Em thuộc K48-K49; cho em hỏi công tác quản lý sinh viên được quy chế công tác sinh viên quy định thế nào? | K48-K49_K48_49_QuyCheCongTacSinhVien_Chuong2_Dieu5 |
| `v7_ret_044` | `semantic` | `K48-K49` | Với K48-K49, nội dung chính của Điều 6 về hỗ trợ và dịch vụ sinh viên là gì? | K48-K49_K48_49_QuyCheCongTacSinhVien_Chuong2_Dieu6 |
| `v7_ret_111` | `typo_no_diacritics` | `K48-K49` | Em hoc K48-K49, cho em hoi quy dinh ve ieu khoan thi hanh trong quy che ren luyen. | K48-K49_K48_49_QuyCheDanhGiaKetQuaRenLuyen_Chuong5_Dieu18 |
| `v7_ret_112` | `typo_no_diacritics` | `K48-K49` | Em hoc K48-K49, cho em hoi quy dinh ve co van hoc tap trong quy che cong tac sinh vien. | K48-K49_K48_49_QuyCheCongTacSinhVien_Chuong4_Dieu24 |

### Generate + Judge

| ID | Nhóm | Cohort | Câu hỏi |
|---|---|---|---|
| `v7_ans_clarify_001` | `clarification` | `K51` | Em học K50 nhưng năm tuyển sinh em lại ghi 2025; tra bảng thời gian chính quy giúp em. |
| `v7_ans_clarify_002` | `clarification` | `K51` | TOEIC bốn kỹ năng của em thiếu điểm Viết, vậy đã kết luận được bậc chưa? |
| `v7_ans_mixed_001` | `mixed_answer` | `K48-K49` | IELTS trong bảng tham chiếu của khóa em có hai khoảng tương đương nào; ngoài ra theo Điều 6 dành cho K48-K49, nội dung về đánh giá về ý thức và kết quả tham gia các hoạt động chín… |
| `v7_ans_mixed_002` | `mixed_answer` | `K51` | K51 vừa làm vừa học: bảng ghi cả mốc chuẩn lẫn mốc tối đa thế nào; ngoài ra theo Điều 2 dành cho K51, nội dung về mục đích công tác cố vấn học tập được quy định thế nào? |
| `v7_ans_ood_001` | `out_of_domain` | `general` | Viết hàm JavaScript đảo ngược một chuỗi. |
| `v7_ans_ood_002` | `out_of_domain` | `general` | Gợi ý thực đơn ăn tối ít dầu mỡ cho gia đình. |
| `v7_ans_rag_001` | `regulation_true_rag` | `K48-K49` | Em thuộc K48-K49; cho em hỏi công tác quản lý sinh viên được quy chế công tác sinh viên quy định thế nào? |
| `v7_ans_rag_002` | `regulation_true_rag` | `K48-K49` | Với K48-K49, nội dung chính của Điều 6 về hỗ trợ và dịch vụ sinh viên là gì? |
| `v7_ans_struct_001` | `structured_answer` | `K51` | Trong bảng K51, TOEFL iBT được ghi các khoảng nào cho bậc 3 và bậc 4? |
| `v7_ans_struct_002` | `structured_answer` | `K50` | Tra giúp em riêng dòng TOEFL ITP: hai cột bậc 3 và bậc 4 ghi gì? |
| `v7_ans_unanswerable_001` | `unanswerable` | `K51` | Hồ sơ công nhận ngoại ngữ em gửi sáng nay đã được duyệt chưa? |
| `v7_ans_unanswerable_002` | `unanswerable` | `K51` | Tiền học bổng kỳ này đã vào đúng tài khoản cá nhân của em chưa? |

### Production

| ID | Scenario | Cohort | Path | Câu hỏi |
|---|---|---|---|---|
| `v7_prod_burst_01` | `burst` | `K51` | `regulation_rag` | Với K51, nội dung chính của Điều 33 về trình tự và thủ tục xét khen thưởng đối với cá nhân và tập thể lớp có thành tích xuất sắc là gì? |
| `v7_prod_burst_02` | `burst` | `K50` | `regulation_rag` | Sinh viên K50 cần lưu ý gì trong quy định về xác định nhu cầu đào tạo, giao nhiệm vụ, đặt hàng hoặc đấu thầu? |
| `v7_prod_cold_rag_01` | `cold_rag` | `K48-K49` | `regulation_rag` | Em thuộc K48-K49; cho em hỏi công tác quản lý sinh viên được quy chế công tác sinh viên quy định thế nào? |
| `v7_prod_cold_rag_02` | `cold_rag` | `K48-K49` | `regulation_rag` | Với K48-K49, nội dung chính của Điều 6 về hỗ trợ và dịch vụ sinh viên là gì? |
| `v7_prod_streaming_01` | `streaming` | `K48-K49` | `regulation_rag` | Sinh viên K48-K49 cần lưu ý gì trong quy định về thu hồi chi phí bồi hoàn? |
| `v7_prod_streaming_02` | `streaming` | `K48-K49` | `regulation_rag` | Em thuộc K48-K49; cho em hỏi xây dựng kế hoạch hoạt động nghiên cứu khoa học của sinh viên được quy định nghiên cứu khoa học quy định thế nào? |
| `v7_prod_structured_01` | `structured` | `K51` | `structured` | Trong bảng K51, TOEFL iBT được ghi các khoảng nào cho bậc 3 và bậc 4? |
| `v7_prod_structured_02` | `structured` | `K50` | `structured` | Tra giúp em riêng dòng TOEFL ITP: hai cột bậc 3 và bậc 4 ghi gì? |
| `v7_prod_warm_cache_01` | `warm_cache` | `K48-K49` | `regulation_rag` | Em thuộc K48-K49; cho em hỏi công tác quản lý sinh viên được quy chế công tác sinh viên quy định thế nào? |
| `v7_prod_warm_cache_02` | `warm_cache` | `K48-K49` | `regulation_rag` | Với K48-K49, nội dung chính của Điều 6 về hỗ trợ và dịch vụ sinh viên là gì? |

## Owner review checklist

1. Review every overlap-flagged case.
2. Spot-check at least 20 structured records and all 20 graph cases against artifacts.
3. Review all multi-source and mixed cases for independent answer targets.
4. Review all clarification/unanswerable cases for realistic user intent.
5. Only after approval, run with `--allow-draft-dataset`; results remain draft and not CV headline metrics.
