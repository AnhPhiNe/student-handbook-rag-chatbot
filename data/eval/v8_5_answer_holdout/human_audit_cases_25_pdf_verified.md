# 25 Case Audit — PDF Verified

## v85_ans_006 — elaboration
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K48-K49
- **Human score:** 0.80
- **Faithfulness PDF:** 0.95
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em thuộc K48-K49, Sinh viên cần hiểu thế nào về hiệu lực thi hành thì em cần thực hiện hoặc đáp ứng những gì?
- **Ground truth:** Quy chế này có hiệu lực thi hành kể từ ngày ký và áp dụng đối với các khóa tuyển sinh sau ngày Quy chế có hiệu lực. Các khoá tuyển sinh trước khi Quy chế có hiệu lực được thực hiện theo Quyết định số 2045/QĐ-ĐHSP ngày 05/9/2016 của Hiệu trưởng Trường Đại học Sư phạm Thành phố Hồ Chí Minh về việc ban hành Quy chế Đào tạo đại học và cao đẳng hệ chính quy theo hệ thống tín chỉ và Quyết định 3672/QĐ-ĐHSP ngày 20/12/2018 của Hiệu trưởng Trường Đại học Sư phạm Thành phố Hồ Chí Minh về việc ban hành Quy chế Đào tạo hệ vừa làm vừa học theo hệ thống tín chỉ. Đối với những vấn đề phát sinh ngoài Quy chế này, Hiệu trưởng quyết định phương án giải quyết.
- **Kết luận kiểm PDF:** Đối chiếu K48-K49 Điều 24: câu trả lời nêu đúng các hiệu lực được dẫn, nhưng bỏ hai quyết định chuyển tiếp 2045/QĐ-ĐHSP và 3672/QĐ-ĐHSP — hai ý chính trong ground truth.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K48_49.pdf` — Hiệu lực thi hành; trang [63, 64]
  - `so_tay_K48_49.pdf` — Hiệu lực thi hành; trang [32, 33, 34]
  - `so_tay_K48_49.pdf` — Điều khoản thi hành; trang [101, 102]
  - `so_tay_K48_49.pdf` — Hiệu lực và trách nhiệm thi hành; trang [117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128]
  - `so_tay_K48_49.pdf` — Điều khoản thi hành; trang [81]
- **Judge:** {"faithfulness": 0.1, "answer_relevancy": 0.2, "answer_correctness": 0.2, "context_precision": 0.5, "context_recall": 0.9, "citation_correctness": 0.8, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Contains incorrect regulations; unsupported claims despite some correct facts"}
- **Câu trả lời Gemini:**

Đối với sinh viên khóa K48-K49 (nhập học năm 2022/2023), hiệu lực thi hành của các quy định trong Sổ tay sinh viên được xác định cụ thể theo từng văn bản như sau:

1. **Quy chế đào tạo trình độ đại học:** Quy chế ban hành kèm theo Quyết định số 989/QĐ-ĐHSP ngày 29/3/2022 có hiệu lực kể từ ngày ký và áp dụng đối với các khóa tuyển sinh sau ngày Quy chế có hiệu lực [2].
2. **Quy chế công tác sinh viên:** Quy chế có hiệu lực kể từ ngày ký, thay thế cho Quy chế ban hành kèm theo Quyết định số 132/QĐ-ĐHSP ngày 13/01/2014 [1].
3. **Quy chế đánh giá kết quả rèn luyện:** Quy chế có hiệu lực kể từ ngày ký, thay thế cho Quy định ban hành kèm theo Quyết định số 133/QĐ-ĐHSP ngày 13/01/2014 [5].
4. **Quy định về hoạt động nghiên cứu khoa học:** Quyết định có hiệu lực kể từ ngày ký, thay thế cho Quyết định số 1673/ĐHSP-KHCN&MT-TCKH ngày 11/9/2012 [3].
5. **Chính sách hỗ trợ học phí và chi phí sinh hoạt:** Nghị định quy định về chính sách này có hiệu lực từ ngày 15/11/2020 và áp dụng bắt đầu từ khóa tuyển sinh năm học 2021 – 2022 [4].

**Lưu ý chung:**
* Đối với các vấn đề phát sinh ngoài quy định, Hiệu trưởng là người xem xét và quyết định phương án giải quyết [1, 2, 3, 5].
* Trong trường hợp cần thiết, Hiệu trưởng có thẩm quyền quyết định sửa đổi, bổ sung các quy định để phù hợp với tình hình thực tế [1, 2].

---
## v85_ans_008 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K48-K49
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em thuộc K48-K49, Em chưa rõ học liên thông đối với người có văn bằng khác được quy định cụ thể như thế nào?
- **Ground truth:** Học liên thông đối với người có văn bằng khác 1. Người đã tốt nghiệp các trình độ đào tạo của giáo dục nghề nghiệp được dự tuyển và học liên thông lên trình độ đại học theo đề án tuyển sinh và thông báo tuyển sinh hằng năm của Trường. Người đã tốt nghiệp đại học được dự tuyển và học liên thông để nhận thêm một bằng tốt nghiệp đại học của một ngành đào tạo khác theo đề án tuyển sinh và thông báo tuyển sinh hằng năm của Trường.
- **Kết luận kiểm PDF:** Đối chiếu K48-K49: đối tượng học liên thông, thời gian học, học bổng và phạm vi hỗ trợ học phí đều có trong các Điều được dẫn.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K48_49.pdf` — Học liên thông đối với người có văn bằng khác; trang [31]
  - `so_tay_K48_49.pdf` — Chương trình đào tạo và thời gian học tập; trang [11, 12, 13]
  - `so_tay_K48_49.pdf` — Học bổng; trang [51, 52]
  - `so_tay_K48_49.pdf` — Liên kết đào tạo; trang [14]
  - `so_tay_K48_49.pdf` — Phạm vi điều chỉnh và đối tượng áp dụng; trang [106, 107]
- **Judge:** {"faithfulness": 0.3, "answer_relevancy": 0.95, "answer_correctness": 0.9, "context_precision": 0.8, "context_recall": 0.5, "citation_correctness": 0.9, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Correct core fact but includes unsupported eligibility claim"}
- **Câu trả lời Gemini:**

Đối với sinh viên khóa K48-K49, quy định về học liên thông tại Trường Đại học Sư phạm Thành phố Hồ Chí Minh được thực hiện theo các nội dung sau:

**1. Đối tượng và hình thức dự tuyển**
*   Người đã tốt nghiệp các trình độ đào tạo của giáo dục nghề nghiệp hoặc đã tốt nghiệp đại học được dự tuyển và học liên thông theo đề án tuyển sinh và thông báo tuyển sinh hằng năm của Trường.
*   Người học liên thông thực hiện chương trình đào tạo (CTĐT) và đăng ký học tập theo kế hoạch chung như các sinh viên khác cùng hình thức đào tạo.
*   Sinh viên được miễn trừ các học phần tương ứng với khối lượng học tập đã tích lũy dựa trên cơ sở công nhận và chuyển đổi tín chỉ theo quy định hiện hành.

**2. Thời gian học tập chuẩn và tối đa**
Thời gian học tập phụ thuộc vào hình thức đào tạo và trình độ đào tạo trước đó:

*   **Đối với hình thức đào tạo chính quy:**
    *   Liên thông từ trình độ cao đẳng lên đại học: Chuẩn 1,5 năm; Tối đa 3 năm.
    *   Liên thông từ trình độ trung cấp lên đại học: Chuẩn 2,5 năm; Tối đa 5 năm.
    *   Liên thông đại học đối với người đã có một bằng đại học: Chuẩn 2 năm; Tối đa 4 năm.

*   **Đối với hình thức đào tạo vừa làm vừa học:**
    *   Liên thông từ trình độ cao đẳng lên đại học: Chuẩn 2 năm; Tối đa 4 năm.
    *   Liên thông từ trình độ trung cấp lên đại học: Chuẩn 3 năm; Tối đa 6 năm.
    *   Liên thông đại học đối với người đã có một bằng đại học: Chuẩn 2,5 năm; Tối đa 5 năm.

**3. Lưu ý về học bổng**
Sinh viên hệ liên thông không được xét cấp Học bổng khuyến khích học tập (HBKKHT), vốn chỉ áp dụng cho sinh viên hệ chính quy đang học tập tại Trường.

**4. Chính sách hỗ trợ học phí**
Theo quy định tại Nghị định về chính sách hỗ trợ tiền đóng học phí, chi phí sinh hoạt đối với sinh viên sư phạm, chính sách này áp dụng cho sinh viên học liên thông chính quy các ngành đào tạo giáo viên (đối với văn bằng thứ 2 yêu cầu kết quả học lực văn bằng thứ 1 đạt loại giỏi).

---
## v85_ans_016 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K50
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em thuộc K50, Trong sổ tay các hành vi sinh viên không được làm nội dung chính trong sổ tay là gì?
- **Ground truth:** Các hành vi sinh viên không được làm 1. Xúc phạm nhân phẩm, danh dự, xâm phạm thân thể giảng viên, viên chức, nhân viên, sinh viên Trường và người khác. Gian lận trong học tập, kiểm tra, thi cử như: quay cóp, mang tài liệu vào phòng thi, xin điểm;
- **Kết luận kiểm PDF:** Đối chiếu K50 Điều 10: câu trả lời bao quát đúng 10 nhóm hành vi sinh viên không được làm.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K50.pdf` — Các hành vi sinh viên không được làm; trang [63, 64]
  - `so_tay_K50.pdf` — Tổ chức đăng ký học tập; trang [15, 16]
  - `so_tay_K50.pdf` — Đánh giá kết quả học tập theo học kỳ, năm học; trang [19, 20, 21]
  - `so_tay_K50.pdf` — Công tác sinh viên; trang [56, 57]
  - `so_tay_K50.pdf` — Trách nhiệm; trang [86, 87]
- **Judge:** {"faithfulness": 0.2, "answer_relevancy": 0.9, "answer_correctness": 0.85, "context_precision": 0.2, "context_recall": 0.2, "citation_correctness": 0.7, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Answer includes many unsupported items; citations not backed by context"}
- **Câu trả lời Gemini:**

Theo quy định tại Điều 10, Chương III của "Quy chế công tác sinh viên" trong Sổ tay sinh viên K50, sinh viên không được thực hiện các hành vi sau:

1. Xúc phạm nhân phẩm, danh dự, xâm phạm thân thể giảng viên, viên chức, nhân viên, sinh viên Trường và người khác.
2. Gian lận trong học tập, kiểm tra, thi cử (quay cóp, mang tài liệu vào phòng thi, xin điểm; học, thi, thực tập hộ hoặc nhờ người khác làm hộ; sao chép, nhờ hoặc làm hộ tiểu luận, đồ án, khóa luận; tổ chức hoặc tham gia tổ chức thi hộ...).
3. Sản xuất, buôn bán, vận chuyển, phát hành, tàng trữ, sử dụng hoặc lôi kéo người khác sử dụng vũ khí, chất nổ, ma túy, các loại dược phẩm, hóa chất cấm; các tài liệu, ấn phẩm, thông tin phản động, đồi trụy và các tài liệu cấm khác; tổ chức, tham gia, truyền bá các hoạt động mê tín dị đoan, hoạt động tôn giáo trong Trường và các hành vi vi phạm đạo đức khác.
4. Hút thuốc, uống rượu, bia trong trường học; say rượu, bia khi đến lớp. Bôi xóa, viết vẽ lên bàn, tường trong phòng học và khuôn viên Trường; làm hư hại tài sản, trang thiết bị của Trường.
5. Tổ chức hoặc tham gia tụ tập đông người, biểu tình, khiếu kiện trái pháp luật; tham gia tệ nạn xã hội, gây rối an ninh, trật tự an toàn trong Trường và ngoài xã hội.
6. Tổ chức hoặc tham gia đua xe hoặc cổ vũ đua xe trái phép.
7. Tổ chức hoặc tham gia đánh bạc dưới mọi hình thức.
8. Thành lập, tham gia các hoạt động mang tính chất chính trị trái pháp luật; tổ chức, tham gia các hoạt động tập thể mang danh nghĩa của Trường khi chưa được Hiệu trưởng cho phép.
9. Đăng tải, bình luận, chia sẻ bài viết, hình ảnh có nội dung dung tục, phản cảm, bạo lực, đồi trụy, xâm phạm an ninh quốc gia, chống phá Đảng và Nhà nước, xuyên tạc, vu khống, xúc phạm uy tín của tổ chức, danh dự và nhân phẩm của cá nhân trên không gian mạng.
10. Tổ chức hoặc tham gia các hoạt động vi phạm pháp luật khác.

---
## v85_ans_019 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K50
- **Human score:** 0.90
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em thuộc K50, Cho em hỏi hiệu trưởng có những điều kiện và mốc nào cần lưu ý?
- **Ground truth:** Chỉ đạo, tổ chức quản lý các hoạt động về công tác sinh viên; bố trí các nguồn lực nhằm bảo đảm thực hiện tốt các nội dung công tác sinh viên. Tổ chức chỉ đạo việc thực hiện các chủ trương, đường lối của Đảng, chính sách, pháp luật của Nhà nước, các quy chế, quy định của Bộ SỔ TAY SINH VIÊN KHÓA 50 Giáo dục và Đào tạo trong công tác sinh viên, bảo đảm công bằng, công khai, minh bạch và dân chủ.
- **Kết luận kiểm PDF:** Đối chiếu K50: nhiệm vụ Hiệu trưởng, đối thoại hằng năm, khen thưởng–kỷ luật và mốc xét tốt nghiệp đều có căn cứ; câu trả lời chỉ hơi rộng.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K50.pdf` — Hiệu lực thi hành; trang [84, 85]
  - `so_tay_K50.pdf` — Hiệu trưởng; trang [64, 65]
  - `so_tay_K50.pdf` — Hội đồng Khen thưởng và Kỷ luật sinh viên; trang [82, 83]
  - `so_tay_K50.pdf` — Hiệu lực thi hành; trang [30, 31, 32]
  - `so_tay_K50.pdf` — Công nhận tốt nghiệp và cấp bằng tốt nghiệp; trang [23, 24, 25]
- **Judge:** {"faithfulness": 0.3, "answer_relevancy": 0.8, "answer_correctness": 0.6, "context_precision": 0.4, "context_recall": 0.9, "citation_correctness": 1.0, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Relevant but many unsupported details, low faithfulness"}
- **Câu trả lời Gemini:**

Đối với sinh viên khóa K50, các quy định và mốc thời gian liên quan đến Hiệu trưởng trong công tác sinh viên và đào tạo được quy định như sau:

**1. Các nhiệm vụ và quyền hạn của Hiệu trưởng:**
*   **Quản lý chung:** Chỉ đạo, tổ chức quản lý công tác sinh viên; đảm bảo thực hiện các chủ trương, chính sách, quy chế của Bộ Giáo dục và Đào tạo; đưa công tác sinh viên vào nề nếp và bảo đảm quyền, nghĩa vụ của sinh viên.
*   **Đối thoại:** Hằng năm, Hiệu trưởng tổ chức đối thoại với sinh viên để giải thích chủ trương, chính sách, cung cấp thông tin và giải quyết kịp thời các thắc mắc, tâm tư, nguyện vọng của sinh viên.
*   **Khen thưởng và Kỷ luật:** Hiệu trưởng là người ra quyết định khen thưởng hoặc kỷ luật sinh viên dựa trên sự tư vấn của Hội đồng Khen thưởng và Kỷ luật sinh viên. Hiệu trưởng (hoặc Phó Hiệu trưởng phụ trách) giữ vai trò Chủ tịch Hội đồng này.
*   **Quyết định khác:** Hiệu trưởng có thẩm quyền quyết định các vấn đề phát sinh ngoài quy chế, sửa đổi/bổ sung quy định khi cần thiết, và quyết định sự tham gia của sinh viên đại diện cho Trường khi có yêu cầu từ các cấp, ngành.

**2. Mốc thời gian liên quan đến Hiệu trưởng trong xét tốt nghiệp:**
*   **Công nhận tốt nghiệp và cấp bằng:** Hiệu trưởng ký quyết định công nhận tốt nghiệp và cấp bằng trong thời hạn **03 tháng** tính từ thời điểm sinh viên đáp ứng đầy đủ điều kiện tốt nghiệp và hoàn thành nghĩa vụ với Trường.
*   **Đợt xét tốt nghiệp bổ sung:** Ngoài các đợt xét tốt nghiệp chính thức (tháng 5, 8, 10 đối với hệ chính quy), Hiệu trưởng sẽ căn cứ vào điều kiện cụ thể của từng năm học để quyết định các đợt xét tốt nghiệp bổ sung.

*

---
## v85_ans_025 — elaboration
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K50
- **Human score:** 0.85
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em thuộc K50, Cho em hỏi nhiệm vụ của sinh viên có những điều kiện và mốc nào cần lưu ý?
- **Ground truth:** Chấp hành chủ trương, đường lối của Đảng, chính sách, pháp luật của Nhà nước và các quy chế, quy định, nội quy của Trường. Học tập, rèn luyện theo chương trình, kế hoạch giáo dục, đào tạo của Trường; chủ động, tích cực tự học, nghiên cứu, sáng tạo và rèn luyện đạo đức, lối sống.
- **Kết luận kiểm PDF:** Đối chiếu K50 Điều 7 và các Điều liên quan: các nhiệm vụ/mốc nêu ra có nguồn, nhưng thiếu nghĩa vụ báo cáo kịp thời hành vi tiêu cực, gian lận.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K50.pdf` — Tín chỉ và học phần; trang [8, 9]
  - `so_tay_K50.pdf` — Nhiệm vụ của sinh viên; trang [60, 61]
  - `so_tay_K50.pdf` — Lớp sinh viên; trang [69, 70, 71]
  - `so_tay_K50.pdf` — Nghỉ học tạm thời, tạm dừng tiến độ học tập và tiếp nhận sinh viên trở lại học; trang [75, 76, 77]
  - `so_tay_K50.pdf` — Trách nhiệm; trang [86, 87]
- **Judge:** {"faithfulness": 0.3, "answer_relevancy": 0.9, "answer_correctness": 0.6, "context_precision": 0.4, "context_recall": 0.8, "citation_correctness": 0.8, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Missing reporting duty; many unsupported duties."}
- **Câu trả lời Gemini:**

Đối với sinh viên khóa K50, nhiệm vụ và các mốc thời gian thực hiện quy định cụ thể như sau:

### 1. Nhiệm vụ của sinh viên
Theo Quy chế công tác sinh viên, sinh viên có các nhiệm vụ chính sau:
*   Chấp hành chủ trương, đường lối của Đảng, chính sách, pháp luật của Nhà nước và các quy chế, quy định, nội quy của Trường.
*   Học tập, rèn luyện theo chương trình, kế hoạch đào tạo; chủ động, tích cực tự học, nghiên cứu, sáng tạo và rèn luyện đạo đức, lối sống.
*   Tôn trọng giảng viên, viên chức, nhân viên; đoàn kết, giúp đỡ lẫn nhau và thực hiện nếp sống văn hóa trong trường học.
*   Giữ gìn, bảo vệ tài sản của Trường và phát huy truyền thống của Trường.
*   Thực hiện đầy đủ quy định về khám sức khỏe khi nhập học và khám sức khỏe định kỳ.
*   Đóng học phí, bảo hiểm y tế đầy đủ và đúng thời hạn.
*   Tham gia phòng, chống tiêu cực, gian lận trong học tập, thi cử; tham gia đảm bảo an ninh, trật tự, an toàn giao thông, phòng chống tội phạm, tệ nạn xã hội.
*   Tham gia lao động công ích, hoạt động tình nguyện, xã hội phù hợp với năng lực và sức khỏe.

### 2. Các mốc thời gian cần lưu ý
Trong quá trình học tập, sinh viên cần lưu ý các mốc thời gian quan trọng đối với một số thủ tục hành chính:

*   **Nghỉ học tạm thời:**
    *   Hồ sơ phải được gửi **trước khi thi học kỳ 04 tuần**.
    *   Điều kiện: Sinh viên phải hoàn thành ít nhất một học kỳ và không nợ học phí tại thời điểm làm hồ sơ.
*   **Thủ tục xin học lại:**
    *   Sinh viên phải hoàn tất thủ tục xin học lại **trước thời điểm đăng ký học phần** (của học kỳ muốn trở lại học) ít nhất **02 tuần**.
*   **Hoạt động lớp:**
    *   Cố vấn học tập tổ chức họp lớp định kỳ **02 lần/học kỳ** để tư vấn kế hoạch học tập và đánh giá kết quả rèn luyện.
    *   Ban cán sự lớp báo cáo tình hình học tập, rèn luyện của lớp cho Cố vấn học tập định kỳ **hằng tháng**.

*Lưu ý: Các quy định về học tập chi tiết (như tín chỉ, học phần) được thực hiện theo Quy chế đào tạo trình độ đại học tại Trường.*

---
## v85_ans_034 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K51
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em thuộc K51, Em chưa rõ hội đồng đánh giá kết quả rèn luyện của sinh viên được quy định cụ thể như thế nào?
- **Ground truth:** Hội đồng đánh giá kết quả rèn luyện của sinh viên Mỗi học kỳ, Hiệu trưởng ban hành Quyết định thành lập Hội đồng đánh giá kết quả rèn luyện sinh viên và tự giải thể khi hoàn thành nhiệm vụ. Hội đồng cấp Trường 94 SỔ TAY SINH VIÊN KHÓA 51 a) Thẩm quyền thành lập: Hiệu trưởng; Thành phần Hội đồng cấp Trường bao gồm: – Chủ tịch Hội đồng: Hiệu trưởng hoặc Phó Hiệu trưởng được ủy quyền;
- **Kết luận kiểm PDF:** Đối chiếu K51 Điều 12: thành phần, nhiệm vụ của Hội đồng cấp Trường/cấp cơ sở và việc tự giải thể đều đúng.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K51.pdf` — Hội đồng đánh giá kết quả rèn luyện của sinh viên; trang [93, 94, 95]
  - `so_tay_K51.pdf` — Quy trình đánh giá kết quả rèn luyện sinh viên; trang [92, 93]
  - `so_tay_K51.pdf` — Nguyên tắc đánh giá kết quả rèn luyện của sinh viên; trang [88]
  - `so_tay_K51.pdf` — Thời gian đánh giá kết quả rèn luyện; trang [95]
  - `so_tay_K51.pdf` — Nội dung đánh giá và thang điểm; trang [88, 89]
- **Judge:** {"faithfulness": 0.45, "answer_relevancy": 0.9, "answer_correctness": 0.7, "context_precision": 0.6, "context_recall": 0.95, "citation_correctness": 0.9, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Core facts correct, extra details unsupported"}
- **Câu trả lời Gemini:**

Theo quy định tại Sổ tay sinh viên K51, việc tổ chức đánh giá kết quả rèn luyện được thực hiện thông qua Hội đồng đánh giá kết quả rèn luyện sinh viên ở hai cấp, được Hiệu trưởng ban hành quyết định thành lập mỗi học kỳ:

**1. Hội đồng cấp Trường**
*   **Thẩm quyền thành lập:** Hiệu trưởng.
*   **Thành phần:**
    *   Chủ tịch: Hiệu trưởng hoặc Phó Hiệu trưởng được ủy quyền.
    *   Phó Chủ tịch: Trưởng Phòng CTCT&HSSV.
    *   Ủy viên thường trực: Phó Trưởng Phòng CTCT&HSSV.
    *   Các ủy viên: Bí thư Đoàn Thanh niên, Chủ tịch Hội Sinh viên Trường, đại diện lãnh đạo các khoa, phân hiệu, phòng có liên quan.
    *   Ủy viên thư ký: Chuyên viên phụ trách công tác điểm rèn luyện sinh viên.
*   **Nhiệm vụ:** Tư vấn cho Hiệu trưởng xem xét, công nhận kết quả rèn luyện của từng sinh viên; xem xét, đánh giá kết quả rèn luyện của từng khoa, phân hiệu dựa trên đề nghị của Trưởng đơn vị.

**2. Hội đồng cấp cơ sở (Khoa và Phân hiệu)**
*   **Thẩm quyền thành lập:** Trưởng khoa hoặc Giám đốc phân hiệu.
*   **Thành phần:**
    *   Chủ tịch: Trưởng/Phó Trưởng khoa hoặc Giám đốc/Phó Giám đốc phân hiệu.
    *   Các ủy viên:
        *   Tại khoa: Giáo vụ khoa, Cố vấn học tập (CVHT), đại diện BCH Đoàn khoa, đại diện BCH Liên Chi hội Sinh viên khoa.
        *   Tại phân hiệu: Tổ trưởng tổ Đào tạo – Khảo thí – Công tác sinh viên, Trưởng/Phó Trưởng khoa có sinh viên đào tạo tại phân hiệu, CVHT các lớp, đại diện BCH Đoàn phân hiệu, đại diện BCH Liên Chi hội Sinh viên phân hiệu (và các thành phần khác nếu cần).
*   **Nhiệm vụ:** Giúp Trưởng đơn vị xem xét, đánh giá chính xác, công bằng, công khai và dân chủ kết quả rèn luyện của sinh viên trong đơn vị; tổng hợp kết quả từ CVHT các lớp để trình Hội đồng cấp Trường.

Hội đồng sẽ tự giải thể sau khi hoàn thành nhiệm vụ mỗi học kỳ.

*

---
## v85_ans_036 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K51
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em thuộc K51, Nhờ giải thích giúp em lớp học phần áp dụng cho sinh viên ra sao?
- **Ground truth:** Lớp học phần bao gồm những sinh viên đăng ký cùng học một học phần. Lớp học phần được tổ chức theo thời gian học một học phần, để được theo dõi, quản lý về học tập và kỷ luật của sinh viên trong giờ học. Đại diện lớp học phần sẽ do giảng viên phụ trách lớp học phần chỉ định và có trách nhiệm báo cáo việc chấp hành nội quy, quy định, quy chế của sinh viên với khoa, phân hiệu.
- **Kết luận kiểm PDF:** Đối chiếu K51: định nghĩa lớp học phần, điều kiện mở lớp, buổi học đầu tiên và quy định cải thiện điểm đều có nguồn.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K51.pdf` — Lớp học phần; trang [69]
  - `so_tay_K51.pdf` — Đánh giá kết quả học tập theo học kỳ, năm học; trang [19, 20, 21]
  - `so_tay_K51.pdf` — Quy định về việc thôi học, chuyển trường, chuyển ngành, buộc thôi học; trang [75, 76]
  - `so_tay_K51.pdf` — Tổ chức giảng dạy và học tập; trang [13, 14, 15]
  - `so_tay_K51.pdf` — Chính sách miễn, giảm học phí và hỗ trợ chi phí, phương tiện đồ dùng học tập, cấp học bổng đối với sinh viên khuyết tật, sinh viên người dân tộc thiểu số; trang [73]
- **Judge:** {"faithfulness": 0.35, "answer_relevancy": 0.92, "answer_correctness": 0.78, "context_precision": 0.45, "context_recall": 0.92, "citation_correctness": 0.9, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Extra details lack source support"}
- **Câu trả lời Gemini:**

Đối với sinh viên khóa K51, quy định về lớp học phần được thực hiện như sau:

**1. Định nghĩa và tổ chức:**
*   Lớp học phần bao gồm những sinh viên đăng ký cùng học một học phần, được tổ chức theo thời gian học của học phần đó để theo dõi, quản lý về học tập và kỷ luật trong giờ học.
*   Mỗi học phần được tổ chức thành các lớp học phần dựa theo thời khóa biểu chung của Trường và có mã số riêng.
*   Đại diện lớp học phần do giảng viên phụ trách lớp chỉ định, có trách nhiệm báo cáo việc chấp hành nội quy, quy định, quy chế của sinh viên với khoa hoặc phân hiệu.

**2. Điều kiện tổ chức lớp:**
*   Trưởng phòng Đào tạo sẽ trình Hiệu trưởng quyết định số lượng sinh viên tối thiểu cho mỗi lớp học phần tùy theo điều kiện cụ thể của từng học kỳ.
*   Nếu số lượng sinh viên đăng ký ít hơn quy định, lớp học phần đó sẽ không được tổ chức. Trong trường hợp này, sinh viên phải đăng ký chuyển sang học ở các lớp học phần khác mà Trường có tổ chức để đảm bảo đủ số tín chỉ quy định trong học kỳ.

**3. Lưu ý về học tập:**
*   Trong buổi học đầu tiên, giảng viên sẽ phổ biến đề cương chi tiết và các quy định liên quan đến học phần.
*   Đối với sinh viên K51, nếu đã có điểm học phần đạt, sinh viên được đăng ký học lại chính học phần đó để cải thiện điểm. Điểm đánh giá cao nhất trong những điểm đã đạt sẽ là điểm chính thức của học phần.

*

---
## v85_ans_042 — elaboration
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / general
- **Human score:** 0.75
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Sinh viên cần hiểu thế nào về chương trình đào tạo và thời gian học tập thì em cần thực hiện hoặc đáp ứng những gì?
- **Ground truth:** Chương trình đào tạo và thời gian học tập 1. CTĐT là một hệ thống các hoạt động giáo dục, đào tạo được thiết kế và tổ chức thực hiện nhằm đạt được mục tiêu đào tạo. CTĐT bao gồm mục tiêu, chuẩn đầu ra, khối lượng kiến thức, cấu trúc, nội dung, phương pháp và hình thức đánh giá đối với môn học, ngành học, trình độ đào tạo phù hợp với chuẩn nghề nghiệp và Khung trình độ quốc gia Việt Nam.
- **Kết luận kiểm PDF:** Đối chiếu K51 và K48-K49 Điều 3: các claim đều có nguồn, nhưng câu trả lời bỏ định nghĩa CTĐT và một số mốc định lượng mà câu hỏi/ground truth nhấn mạnh.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K51.pdf` — Chương trình đào tạo và thời gian học tập; trang [9, 10, 11]
  - `so_tay_K48_49.pdf` — Chương trình đào tạo và thời gian học tập; trang [11, 12, 13]
  - `so_tay_K51.pdf` — Lớp học phần; trang [69]
  - `so_tay_K50.pdf` — Lớp học phần; trang [71]
- **Judge:** {"faithfulness": 0.3, "answer_relevancy": 0.8, "answer_correctness": 0.2, "context_precision": 0.8, "context_recall": 0.2, "citation_correctness": 0.7, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Answer misses definition, cites time tables, includes unsupported claims"}
- **Câu trả lời Gemini:**

Chào bạn, về yêu cầu và điều kiện đối với chương trình đào tạo (CTĐT) và thời gian học tập, Sổ tay sinh viên quy định như sau:

### 1. Yêu cầu đối với Chương trình đào tạo (CTĐT)
*   **Cấu trúc:** CTĐT được xây dựng theo đơn vị tín chỉ, bao gồm các học phần bắt buộc và đáp ứng chuẩn theo quy định của Bộ Giáo dục và Đào tạo. Đối với đào tạo song ngành hoặc ngành chính – ngành phụ, CTĐT phải thể hiện rõ khối lượng học tập chung và riêng.
*   **Tính công khai:** CTĐT được công khai trước khi tuyển sinh và khi bắt đầu khóa học. Mọi thay đổi, điều chỉnh sẽ được công bố trước khi áp dụng và đảm bảo không gây tác động bất lợi cho sinh viên.
*   **Đối với người đã tốt nghiệp trình độ/ngành khác:** Khối lượng học tập thực tế được xác định dựa trên việc công nhận, chuyển đổi tín chỉ đã tích lũy và miễn trừ học phần trong CTĐT trước đó.

### 2. Thời gian học tập
Thời gian học tập được quy định tùy theo hình thức đào tạo và chương trình cụ thể.

**Lưu ý:** Bạn vui lòng cho biết **khóa tuyển sinh** của bạn (ví dụ: khóa 2025 trở về sau hay các khóa trước đó) để tôi cung cấp số liệu chính xác nhất, vì quy định về thời gian học tập đã có sự thay đổi/bổ sung tại Quyết định số 4743/QĐ-ĐHSP áp dụng từ khóa tuyển sinh năm 2025.

*   **Đối với sinh viên học liên thông:** Thời gian tối đa để hoàn thành khóa học được xác định trên cơ sở thời gian theo kế hoạch học tập chuẩn toàn khóa giảm tương ứng với khối lượng tín chỉ được miễn trừ.

Nếu bạn cần tra cứu bảng thời gian cụ thể cho một khóa học hoặc hình thức đào tạo nhất định, vui lòng cung cấp thêm thông tin để tôi hỗ trợ chính xác.

---
## v85_ans_049 — non_hallucination_answer_failure
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / general
- **Human score:** 0.40
- **Faithfulness PDF:** 0.95
- **Citation PDF:** 0.50
- **Critical false pass:** False
- **Câu hỏi:** Nếu cần áp dụng đúng quy định cố vấn học tập, bcs lớp có điểm nào dễ bị hiểu nhầm không?
- **Ground truth:** Đôn đốc sinh viên thực hiện việc đăng ký ngoại trú, cập nhật thông tin thay đổi nơi tạm trú theo đúng thời hạn quy định. Căn cứ nhận xét của địa phương (nếu có) để đánh giá điểm rèn luyện sinh viên.
- **Kết luận kiểm PDF:** Đối chiếu K50 Điều 12 về ngoại trú: nguồn đúng phải nói CVHT/BCS đôn đốc đăng ký, cập nhật nơi tạm trú và dùng nhận xét địa phương khi đánh giá rèn luyện. Câu trả lời truy xuất sang nhiệm vụ CVHT chung nên lệch trọng tâm.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K48_49.pdf` — Nhiệm vụ; trang [64, 65]
  - `so_tay_K48_49.pdf` — Mục đích Công tác Cố vấn học tập; trang [64]
  - `so_tay_K48_49.pdf` — Cố vấn học tập; trang [49, 50]
  - `so_tay_K51.pdf` — Cố vấn học tập; trang [67, 68]
  - `so_tay_K50.pdf` — Cố vấn học tập; trang [69]
- **Judge:** {"faithfulness": 0.0, "answer_relevancy": 0.0, "answer_correctness": 0.0, "context_precision": 0.2, "context_recall": 0.0, "citation_correctness": 0.0, "unsupported_claim": false, "critical_false_pass": false, "rationale": "Answer irrelevant, missing required fact about external residence"}
- **Câu trả lời Gemini:**

Theo quy định tại Trường Đại học Sư phạm Thành phố Hồ Chí Minh, nhiệm vụ của Cố vấn học tập (CVHT) được áp dụng chung cho các đơn vị đào tạo, bao gồm các nội dung chính sau:

*   **Tư vấn học tập:** Hướng dẫn sinh viên xây dựng kế hoạch học tập cho từng học kỳ và toàn khóa học; tư vấn đăng ký hoặc điều chỉnh kế hoạch học tập dựa trên kết quả học tập, năng lực và hoàn cảnh của sinh viên [1, 3, 4, 5].
*   **Quản lý lớp:** Quản lý thông tin cá nhân sinh viên; giới thiệu nhân sự để bầu ban cán sự lớp và đề nghị Trưởng khoa (hoặc Giám đốc phân hiệu) phê duyệt/công nhận [1, 3, 4, 5].
*   **Hỗ trợ sinh viên:** Hướng dẫn sinh viên tham gia các hoạt động học thuật, nghiên cứu khoa học; hướng dẫn thực hiện các thủ tục điều chỉnh, khiếu nại về kết quả học tập, rèn luyện, khen thưởng và kỷ luật [1, 3, 4, 5].
*   **Nắm bắt tình hình:** Theo dõi tình hình học tập, đời sống, sinh hoạt của lớp; thường xuyên cập nhật các quy chế, quy định của Bộ Giáo dục và Đào tạo cũng như của Trường để tư vấn kịp thời cho sinh viên [1, 3, 4, 5].
*   **Công tác khác:** Chủ trì họp lớp xét khen thưởng, kỷ luật; tham dự họp Hội đồng Khen thưởng – Kỷ luật cấp Khoa; thực hiện chế độ báo cáo theo yêu cầu của Trưởng khoa [1, 3, 4, 5].

Mục đích của công tác CVHT là giúp các đơn vị đào tạo theo dõi tình hình lớp, kịp thời đề xuất phương pháp xử lý các tình huống phát sinh và là cơ sở để đánh giá, bình xét thi đua hằng năm [2].

Sổ tay sinh viên không ghi nhận quy định riêng biệt hoặc khác biệt về nhiệm vụ của CVHT dành riêng cho Khoa Ngữ văn hay các ngành cụ thể như Sư phạm Ngữ văn và Văn học. Nếu bạn có thắc mắc về một tình huống cụ thể tại Khoa, bạn nên liên hệ trực tiếp với Văn phòng Khoa để được giải đáp chính xác nhất.

---
## v85_ans_052 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K48-K49
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Bạn em khóa khác nói khác về học cùng lúc hai chương trình; với K48-K49 thì nguồn nào mới đúng?
- **Ground truth:** Đối với hình thức đào tạo chính quy, sinh viên có thể đăng ký học thêm các học phần của một chương trình khác, ngành khác khi điều kiện của Trường cho phép, nhưng chỉ được hưởng các quyền lợi chính thức và được xem xét công nhận tốt nghiệp chương trình thứ hai khi đã đăng ký thành công học chương trình thứ hai theo quy định tại khoản 2 Điều này. Sinh viên được đăng ký học chương trình thứ hai sớm nhất khi đã được xếp trình độ năm thứ hai của chương trình thứ nhất. Tại thời điểm đăng ký, sinh viên phải đáp ứng một trong hai điều kiện sau và một số điều kiện bổ sung khác theo các quy định hiện hành của Trường về học cùng lúc hai chương trình: a) Học lực tính theo điểm trung bình tích lũy xếp loại khá trở lên và đáp ứng ngưỡng bảo đảm chất
- **Kết luận kiểm PDF:** Đối chiếu K48-K49 Điều 19 và Điều 25: điều kiện học hai chương trình, cảnh báo học tập, thời gian và xét tốt nghiệp đều đúng.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K48_49.pdf` — Học cùng lúc hai chương trình; trang [30, 31]
  - `so_tay_K48_49.pdf` — Lớp sinh viên; trang [50, 51]
  - `so_tay_K48_49.pdf` — Chương trình đào tạo và thời gian học tập; trang [11, 12, 13]
  - `so_tay_K48_49.pdf` — Các trường hợp đánh giá; trang [74, 75]
  - `so_tay_K48_49.pdf` — Tổ chức đăng ký học tập; trang [17, 18]
- **Judge:** {"faithfulness": 0.35, "answer_relevancy": 0.75, "answer_correctness": 0.45, "context_precision": 0.7, "context_recall": 0.9, "citation_correctness": 0.8, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Partial facts, some unsupported details"}
- **Câu trả lời Gemini:**

Đối với sinh viên khóa K48-K49, quy định về việc học cùng lúc hai chương trình đào tạo được thực hiện theo các nội dung chính sau:

**1. Điều kiện đăng ký**
Sinh viên được phép đăng ký học chương trình thứ hai sớm nhất khi đã được xếp trình độ năm thứ hai của chương trình thứ nhất. Tại thời điểm đăng ký, sinh viên phải đáp ứng một trong hai điều kiện về học lực sau:
*   **Loại khá trở lên:** Đáp ứng ngưỡng bảo đảm chất lượng của chương trình thứ hai trong năm tuyển sinh.
*   **Loại trung bình:** Đáp ứng điều kiện trúng tuyển của chương trình thứ hai trong năm tuyển sinh.
Ngoài ra, sinh viên cần tuân thủ các điều kiện bổ sung khác theo quy định hiện hành của Trường.

**2. Quy định trong quá trình học**
*   **Kết quả học tập:** Nếu điểm trung bình tích lũy của chương trình thứ nhất đạt dưới mức trung bình hoặc thuộc diện cảnh báo kết quả học tập, sinh viên sẽ bị buộc thôi học chương trình thứ hai ở học kỳ tiếp theo.
*   **Thời gian học:** Thời gian tối đa để hoàn thành chương trình học là thời gian tối đa quy định cho chương trình thứ nhất. Sinh viên được công nhận kết quả các học phần có nội dung và khối lượng kiến thức tương đương giữa hai chương trình.
*   **Đánh giá rèn luyện:** Sinh viên được đánh giá kết quả rèn luyện tại đơn vị quản lý chương trình thứ nhất, đồng thời lấy ý kiến nhận xét của đơn vị quản lý chương trình thứ hai làm căn cứ. Nếu đã hoàn thành chương trình thứ nhất, đơn vị quản lý chương trình thứ hai sẽ tiếp tục thực hiện đánh giá.

**3. Điều kiện xét tốt nghiệp**
Sinh viên chỉ được xét tốt nghiệp chương trình thứ hai khi:
*   Đã đủ điều kiện tốt nghiệp ở chương trình thứ nhất.
*   Đã đủ 02 năm tính từ thời điểm đăng ký thành công chương trình thứ hai.

**4. Quản lý lớp sinh viên**
Sau khi tốt nghiệp chương trình thứ nhất, sinh viên sẽ được xếp vào lớp sinh viên có chương trình ngành thứ hai tương ứng khi có sự đồng ý của khoa, Phòng Đào tạo và Phòng Công tác chính trị và Học sinh sinh viên để được quản lý và chấm điểm rèn luyện theo quy định.

*

---
## v85_ans_058 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K50
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em nghe mỗi người nói một kiểu về hỗ trợ và dịch vụ sinh viên; nếu em thuộc K50 thì quy định chính xác trong sổ tay là gì?
- **Ground truth:** Tư vấn học tập Tư vấn, cố vấn, hỗ trợ sinh viên xây dựng kế hoạch, phương pháp học tập phù hợp với mục tiêu và năng lực; cung cấp thông tin về CTĐT, hướng dẫn sinh viên tiếp cận các nguồn lực (về học thuật, tài chính, kỹ thuật,...) nhằm nâng cao hiệu quả học tập. Công tác hướng nghiệp, tư vấn việc làm Tổ chức thực hiện các nội dung, biện pháp công tác tư vấn hướng nghiệp, việc làm theo quy định.
- **Kết luận kiểm PDF:** Đối chiếu K50 Điều 6, Điều 13 và Điều 29: nhóm hỗ trợ, đầu mối CTCT&HSSV và thủ tục hồ sơ đều được hỗ trợ.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K50.pdf` — Điều khoản thi hành; trang [140, 141]
  - `so_tay_K50.pdf` — Phạm vi điều chỉnh và đối tượng áp dụng; trang [141, 142]
  - `so_tay_K50.pdf` — Chính sách miễn, giảm học phí và hỗ trợ chi phí, phương tiện đồ dùng học tập, cấp học bổng đối với sinh viên khuyết tật, sinh viên người dân tộc thiểu số; trang [74, 75]
  - `so_tay_K50.pdf` — Phòng Công tác chính trị và Học sinh, sinh viên; trang [65, 66, 67]
  - `so_tay_K50.pdf` — Hỗ trợ và dịch vụ sinh viên; trang [59, 60]
- **Judge:** {"faithfulness": 0.3, "answer_relevancy": 0.95, "answer_correctness": 0.9, "context_precision": 0.4, "context_recall": 0.9, "citation_correctness": 0.9, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Extra unsupported services lower faithfulness despite correct core fact"}
- **Câu trả lời Gemini:**

Đối với sinh viên khóa K50, các nội dung về hỗ trợ và dịch vụ sinh viên được quy định cụ thể tại Điều 6, Chương II của Quy chế công tác sinh viên, bao gồm các nhóm chính sau:

1. **Tư vấn học tập:** Hỗ trợ sinh viên xây dựng kế hoạch, phương pháp học tập phù hợp với năng lực; cung cấp thông tin về chương trình đào tạo và hướng dẫn tiếp cận các nguồn lực học thuật, tài chính, kỹ thuật.
2. **Hướng nghiệp và tư vấn việc làm:** Thực hiện các biện pháp tư vấn hướng nghiệp và việc làm theo quy định.
3. **Tư vấn tâm lý và chăm sóc sức khỏe:**
   - Tư vấn, hỗ trợ các vấn đề tâm lý – xã hội.
   - Quản lý khám sức khỏe đầu vào và định kỳ; tư vấn, tổ chức thực hiện Luật Bảo hiểm y tế; xử lý các tình huống cấp cứu.
4. **Hỗ trợ tài chính:** Phối hợp xây dựng, quản lý các quỹ học bổng và tổ chức trao học bổng cho sinh viên xuất sắc hoặc sinh viên có hoàn cảnh khó khăn.
5. **Hỗ trợ đặc biệt:** Triển khai dịch vụ công tác xã hội để giúp đỡ sinh viên khuyết tật, sinh viên diện chính sách và sinh viên có hoàn cảnh đặc biệt khó khăn.

**Đơn vị đầu mối thực hiện:**
Phòng Công tác chính trị và Học sinh, sinh viên là đơn vị chịu trách nhiệm hướng dẫn, thực hiện các chế độ chính sách về học bổng, học phí, miễn giảm học phí, trợ cấp xã hội, bảo hiểm; tiếp nhận và xử lý các hồ sơ liên quan đến công tác sinh viên.

**Lưu ý về thủ tục:**
Đối với sinh viên thuộc diện được miễn, giảm học phí, cấp học bổng và hỗ trợ chi phí học tập, bạn cần nộp hồ sơ về Phòng Công tác chính trị và Học sinh, sinh viên đúng thời hạn quy định theo từng học kỳ.

*

---
## v85_ans_059 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K50
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** K50 hoi ve hội đồng đánh giá kết quả rèn luyện của sinh viên ma em khong go dau, he thong can tim dung dieu nao?
- **Ground truth:** Hội đồng đánh giá kết quả rèn luyện của sinh viên Mỗi học kỳ, Hiệu trưởng ban hành Quyết định thành lập Hội đồng đánh giá kết quả rèn luyện sinh viên và tự giải thể khi hoàn thành nhiệm vụ. Hội đồng cấp Trường a) Thẩm quyền thành lập: Hiệu trưởng; Thành phần Hội đồng cấp Trường bao gồm: – Chủ tịch Hội đồng: Hiệu trưởng hoặc Phó Hiệu trưởng được ủy quyền;
- **Kết luận kiểm PDF:** Đối chiếu K50 Điều 12: thành phần và nhiệm vụ hai cấp Hội đồng được trả lời đúng.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K50.pdf` — Hội đồng đánh giá kết quả rèn luyện của sinh viên; trang [97, 98]
  - `so_tay_K50.pdf` — Quy trình đánh giá kết quả rèn luyện sinh viên; trang [95, 96, 97]
  - `so_tay_K50.pdf` — Nội dung đánh giá và thang điểm; trang [92]
  - `so_tay_K50.pdf` — Thời gian đánh giá kết quả rèn luyện; trang [98, 99]
  - `so_tay_K50.pdf` — Sử dụng kết quả rèn luyện; trang [99]
- **Judge:** {"faithfulness": 0.45, "answer_relevancy": 0.9, "answer_correctness": 0.9, "context_precision": 0.85, "context_recall": 0.9, "citation_correctness": 0.9, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Extra details not in source, but core correct"}
- **Câu trả lời Gemini:**

Đối với sinh viên khóa K50, việc đánh giá kết quả rèn luyện được thực hiện thông qua hai cấp Hội đồng theo quy định tại Quy chế đánh giá kết quả rèn luyện của sinh viên hệ chính quy tại Trường Đại học Sư phạm Thành phố Hồ Chí Minh:

**1. Hội đồng cấp cơ sở (Khoa và Phân hiệu)**
*   **Thẩm quyền thành lập:** Trưởng khoa hoặc Giám đốc phân hiệu.
*   **Thành phần:**
    *   **Chủ tịch:** Trưởng/Phó Trưởng khoa hoặc Giám đốc/Phó Giám đốc phân hiệu.
    *   **Ủy viên:**
        *   Đối với các khoa: Giáo vụ khoa, Cố vấn học tập (CVHT), đại diện BCH Đoàn khoa, đại diện BCH Liên Chi hội Sinh viên khoa.
        *   Đối với phân hiệu: Tổ trưởng tổ Đào tạo – Khảo thí – Công tác sinh viên, Trưởng/Phó Trưởng khoa có sinh viên đào tạo tại phân hiệu, CVHT các lớp, đại diện BCH Đoàn phân hiệu, đại diện BCH Liên Chi hội Sinh viên phân hiệu (và các thành phần khác do Giám đốc phân hiệu bổ sung nếu cần).
*   **Nhiệm vụ:** Giúp Trưởng đơn vị xem xét, đánh giá kết quả rèn luyện của sinh viên trong khoa/phân hiệu một cách chính xác, công bằng, công khai, dân chủ; tổng hợp và đề nghị Trưởng đơn vị gửi kết quả về Hội đồng cấp Trường.

**2. Hội đồng cấp Trường**
*   **Thẩm quyền thành lập:** Hiệu trưởng (được thành lập mỗi học kỳ và tự giải thể khi hoàn thành nhiệm vụ).
*   **Thành phần:**
    *   **Chủ tịch:** Hiệu trưởng hoặc Phó Hiệu trưởng được ủy quyền.
    *   **Phó Chủ tịch:** Trưởng Phòng CTCT&HSSV.
    *   **Ủy viên thường trực:** Phó Trưởng Phòng CTCT&HSSV.
    *   **Các ủy viên:** Bí thư Đoàn Thanh niên, Chủ tịch Hội Sinh viên Trường, đại diện lãnh đạo các khoa, phân hiệu, phòng có liên quan.
    *   **Ủy viên thư ký:** Chuyên viên phụ trách công tác điểm rèn luyện sinh viên.
*   **Nhiệm vụ:** Tư vấn cho Hiệu trưởng xem xét, công nhận kết quả rèn luyện của từng sinh viên; xem xét, đánh giá kết quả rèn luyện của từng khoa, phân hiệu trên cơ sở đề nghị của các đơn vị để trình Hiệu trưởng quyết định công nhận.

*

---
## v85_ans_063 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K51
- **Human score:** 0.90
- **Faithfulness PDF:** 0.95
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em nghe mỗi người nói một kiểu về hiệu lực thi hành; nếu em thuộc K51 thì quy định chính xác trong sổ tay là gì?
- **Ground truth:** Quyết định này có hiệu lực kể từ ngày ký và thay thế Quyết định số 3738/QĐ-ĐHSP ngày 02/12/2022 của Hiệu trưởng Trường Đại học Sư phạm Thành phố Hồ Chí Minh về việc ban hành Quy định công tác CVHT cho sinh viên đại học hệ chính quy tại Trường Đại học Sư phạm Thành phố Hồ Chí Minh. Trong quá trình thực hiện, nếu có vấn đề phát sinh hoặc khó khăn, vướng mắc, các đơn vị có liên quan đề xuất ý kiến về Phòng CTCT&HSSV để trình Hiệu trưởng xem xét sửa đổi, bổ sung. HIỆU TRƯỞNG (đã ký) Huỳnh Văn Sơn CVHT quét mã QR hoặc truy cập đường dẫn sau để xem các phụ lục và biểu mẫu có liên quan đến quy định: http://tracuu.hcmue.edu.vn/Hoso_danhgiaCVHT 88 SỔ TAY SINH VIÊN KHÓA 51 BỘ GIÁO DỤC VÀ ĐÀO TẠO TRƯỜNG ĐẠI HỌC SƯ PHẠM THÀNH PHỐ HỒ CHÍ MINH CỘNG HÒA
- **Kết luận kiểm PDF:** Đối chiếu K51: các hiệu lực của từng văn bản đều có trong nguồn, nhưng câu trả lời rộng hơn ground truth neo vào quy định CVHT.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K51.pdf` — Hiệu lực thi hành; trang [81, 82]
  - `so_tay_K51.pdf` — Hiệu lực thi hành; trang [155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170]
  - `so_tay_K51.pdf` — Hiệu lực thi hành; trang [87, 88]
  - `so_tay_K51.pdf` — Điều khoản thi hành; trang [122, 123]
  - `so_tay_K51.pdf` — Hiệu lực thi hành; trang [30, 31]
- **Judge:** {"faithfulness": 0.3, "answer_relevancy": 0.6, "answer_correctness": 0.6, "context_precision": 0.4, "context_recall": 0.9, "citation_correctness": 0.9, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Contains correct fact but many unsupported statements"}
- **Câu trả lời Gemini:**

Đối với sinh viên khóa K51 (nhập học năm 2025), hiệu lực thi hành của các quy định trong Sổ tay sinh viên được xác định như sau:

*   **Quy chế công tác sinh viên:** Có hiệu lực kể từ ngày ký, áp dụng cho tất cả các khóa tuyển sinh theo hình thức đào tạo chính quy [1].
*   **Quy định chính sách phát triển người học tài năng:** Có hiệu lực kể từ ngày ký và áp dụng đối với các khóa tuyển sinh từ năm 2025 (bao gồm khóa K51) [2].
*   **Quy định công tác cố vấn học tập:** Có hiệu lực kể từ ngày ký và thay thế cho Quyết định số 3738/QĐ-ĐHSP ngày 02/12/2022 [3].
*   **Quy định về hoạt động nghiên cứu khoa học của sinh viên:** Có hiệu lực kể từ ngày ký và thay thế cho Quyết định số 1673/ĐHSP-KHCN&MT-TCKH ngày 11/9/2012 [4].
*   **Quy chế đào tạo trình độ đại học:** Có hiệu lực kể từ ngày ký và áp dụng đối với các khóa tuyển sinh sau ngày Quy chế có hiệu lực [5].

Trong quá trình thực hiện, nếu có vấn đề phát sinh hoặc vướng mắc, sinh viên và các đơn vị liên quan sẽ phản ánh về các phòng ban chức năng tương ứng (như Phòng Công tác chính trị & Học sinh sinh viên, Phòng Khoa học Công nghệ và Môi trường – Tạp chí Khoa học) để trình Hiệu trưởng xem xét, quyết định [1, 2, 3, 4, 5].

---
## v85_ans_065 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / general
- **Human score:** 0.80
- **Faithfulness PDF:** 0.95
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Nếu trường hợp của em hơi khác bình thường, các đơn vị, đoàn thể trong trường của general được hiểu thế nào theo sổ tay?
- **Ground truth:** Các đơn vị, đoàn thể trong Trường 1. Phối hợp với Phòng CTCT&HSSV và các đơn vị có liên quan trong việc triển khai thực hiện công tác ngoại trú sinh viên theo Quy định này. Tư vấn, giới thiệu chỗ ở, tạo điều kiện để sinh viên có nhu cầu tham gia các hoạt động rèn luyện tại nơi cư trú.
- **Kết luận kiểm PDF:** Đối chiếu K50 Điều 14 về ngoại trú: trách nhiệm phối hợp, tư vấn chỗ ở và tạo điều kiện rèn luyện đều có nguồn; cách mở đầu còn mơ hồ.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K50.pdf` — Đánh giá về ý thức và kết quả tham gia phụ trách lớp, các đoàn thể, tổ chức trong Nhà trường hoặc sinh viên đạt được thành tích đặc biệt trong học tập, rèn luyện; trang [93, 94]
  - `so_tay_K51.pdf` — Đánh giá về ý thức và kết quả tham gia phụ trách lớp, các đoàn thể, tổ chức trong Nhà trường hoặc sinh viên đạt được thành tích đặc biệt trong học tập, rèn luyện; trang [90, 91]
  - `so_tay_K48_49.pdf` — Đánh giá về ý thức và kết quả tham gia phụ trách lớp, các đoàn thể, tổ chức trong Nhà trường hoặc sinh viên đạt được thành tích đặc biệt trong học tập, rèn luyện; trang [73]
  - `so_tay_K48_49.pdf` — Sổ tay sinh viên; trang [44]
  - `so_tay_K50.pdf` — Các đơn vị, đoàn thể trong Trường; trang [120]
- **Judge:** {"faithfulness": 0.3, "answer_relevancy": 0.7, "answer_correctness": 0.2, "context_precision": 0.6, "context_recall": 0.9, "citation_correctness": 0.9, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Inaccurate claim, missing required fact"}
- **Câu trả lời Gemini:**

Sổ tay sinh viên hiện không cung cấp định nghĩa chi tiết cho từng đơn vị, đoàn thể trong Trường.

Tuy nhiên, theo các quy định trong Sổ tay, các tổ chức này được nhắc đến trong bối cảnh tham gia hoạt động và quản lý sinh viên bao gồm:
*   **Các tổ chức Đảng, Đoàn Thanh niên Cộng sản Hồ Chí Minh, Hội Sinh viên Việt Nam** và các tổ chức khác trong Trường [1, 2, 3].
*   **Phòng Công tác chính trị và Học sinh sinh viên (CTCT&HSSV)**: Đơn vị có vai trò phối hợp với các đơn vị, đoàn thể trong việc triển khai các công tác như quản lý ngoại trú, tư vấn chỗ ở và xây dựng Sổ tay sinh viên [4, 5].

Các đơn vị, đoàn thể này có trách nhiệm phối hợp thực hiện công tác sinh viên, tư vấn, giới thiệu chỗ ở và tạo điều kiện cho sinh viên tham gia các hoạt động rèn luyện [5]. Ngoài ra, sinh viên tham gia quản lý các tổ chức này sẽ được đánh giá điểm rèn luyện dựa trên ý thức, tinh thần, thái độ và kỹ năng tổ chức, quản lý [1, 2, 3].

---
## v85_ans_078 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / K51
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em thuộc K51, mục "Quy trình đánh giá kết quả rèn luyện sinh viên" quy định những điểm chính nào?
- **Ground truth:** Quy trình đánh giá kết quả rèn luyện sinh viên 1. CVHT thông báo đến lớp trưởng lớp sinh viên về quy trình và thời gian thực hiện việc chấm điểm rèn luyện. Sinh viên căn cứ vào kết quả rèn luyện của bản thân, tự đánh giá theo mức điểm chi tiết do Trường quy định kèm theo các minh chứng hoạt động và gửi về BCS lớp.
- **Kết luận kiểm PDF:** Đối chiếu K51 Điều 10–14: các bước, ngưỡng biểu quyết, công bố và lưu hồ sơ đều có căn cứ.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K51.pdf` — Nguyên tắc đánh giá kết quả rèn luyện của sinh viên; trang [88]
  - `so_tay_K51.pdf` — Quy trình đánh giá kết quả rèn luyện sinh viên; trang [92, 93]
  - `so_tay_K51.pdf` — Nội dung đánh giá và thang điểm; trang [88, 89]
  - `so_tay_K51.pdf` — Sử dụng kết quả rèn luyện; trang [95, 96]
  - `so_tay_K51.pdf` — Phạm vi điều chỉnh và đối tượng áp dụng; trang [88]
- **Judge:** {"faithfulness": 0.4, "answer_relevancy": 0.9, "answer_correctness": 0.9, "context_precision": 0.8, "context_recall": 0.9, "citation_correctness": 0.9, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Answer adds unsupported steps beyond retrieved context"}
- **Câu trả lời Gemini:**

Quy trình đánh giá kết quả rèn luyện đối với sinh viên K51 được thực hiện theo các bước chính sau đây:

1. **Thông báo:** Cố vấn học tập (CVHT) thông báo cho lớp trưởng về quy trình và thời gian thực hiện.
2. **Sinh viên tự đánh giá:** Sinh viên căn cứ vào kết quả rèn luyện của bản thân, tự đánh giá theo thang điểm 100 (kèm minh chứng) và gửi về Ban cán sự (BCS) lớp.
3. **Chấm điểm sơ bộ:** BCS lớp, Ban chấp hành Chi đoàn, Ban chấp hành Chi hội và CVHT thực hiện chấm lại điểm rèn luyện cho sinh viên dựa trên kết quả tự đánh giá.
4. **Họp lớp:** CVHT tổ chức họp lớp để xem xét, thông qua mức điểm của từng sinh viên. Kết quả phải được trên 50% ý kiến tập thể lớp đồng ý và có biên bản họp kèm theo.
5. **Lập hồ sơ:** Lớp sinh viên lập hồ sơ (gồm biên bản họp, bảng kết quả, minh chứng và đơn xin không đánh giá nếu có) gửi lên Hội đồng đánh giá rèn luyện cấp khoa/phân hiệu (Hội đồng cấp cơ sở).
6. **Xét duyệt cấp cơ sở:** Hội đồng cấp cơ sở họp xét, thống nhất và trình kết quả lên Hội đồng đánh giá rèn luyện cấp Trường.
7. **Xét duyệt cấp Trường:** Hội đồng cấp Trường họp xét, thống nhất trình Hiệu trưởng xem xét và quyết định công nhận kết quả.
8. **Công bố:** Kết quả được công bố công khai và thông báo cho sinh viên biết trước 20 ngày trước khi ban hành quyết định chính thức. Sau đó, các đơn vị sẽ cập nhật kết quả vào phần mềm quản lý sinh viên.

**Lưu ý:** Việc đánh giá phải đảm bảo các nguyên tắc khách quan, công khai, công bằng, chính xác, bình đẳng và dân chủ. Kết quả rèn luyện là căn cứ để xét học bổng, khen thưởng, kỷ luật, xét thôi học/ngừng học và các ưu tiên khác theo quy định của Trường.

---
## v85_ans_084 — elaboration
- **Nhóm:** low21
- **Case type / cohort:** regulation_true_rag / general
- **Human score:** 0.75
- **Faithfulness PDF:** 0.85
- **Citation PDF:** 0.80
- **Critical false pass:** False
- **Câu hỏi:** Trong sổ tay, mục "Thu hồi chi phí bồi hoàn" nêu những quy định chính nào?
- **Ground truth:** Hằng năm, căn cứ vào kết quả rèn luyện, học tập của sinh viên sư phạm, cơ sở đào tạo giáo viên thông báo danh sách sinh viên thuộc đối tượng quy định tại điểm c khoản 1 Điều 6 Nghị định này cho Ủy ban nhân dân cấp tỉnh để thông báo thu hồi kinh phí đã hỗ trợ cho sinh viên sư phạm và gia đình theo quy định tại khoản 2 Điều 8 Nghị định này. Đối với sinh viên sư phạm thuộc đối tượng phải bồi hoàn kinh phí theo quy định tại điểm a và điểm b khoản 1 Điều 6 Nghị định này, Ủy ban nhân dân cấp tỉnh ra thông báo thu hồi kinh phí hỗ trợ để sinh viên sư phạm hoặc gia đình thực hiện nộp trả đầy đủ khoản tiền phải bồi hoàn theo quy định tại Điều 8 Nghị định này. Trong thời hạn 30 ngày, kể từ ngày nhận được quyết định của cơ quan Nhà nước có thẩm quyền,
- **Kết luận kiểm PDF:** Đối chiếu cả ba sổ tay: các mốc 30 ngày, 4 năm, lãi suất, miễn/giảm/xóa và khởi kiện đều có; tuy nhiên câu trả lời trộn bản K48/K50 với quy định sửa đổi trong K51 mà không tách phạm vi khóa.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K48_49.pdf` — Thu hồi chi phí bồi hoàn; trang [113, 114]
  - `so_tay_K50.pdf` — Thu hồi chi phí bồi hoàn; trang [148, 149]
  - `so_tay_K51.pdf` — Thu hồi kinh phí hỗ trợ; trang [138, 139]
  - `so_tay_K50.pdf` — Bồi hoàn kinh phí hỗ trợ; trang [145, 146]
  - `so_tay_K51.pdf` — Bồi hoàn kinh phí hỗ trợ; trang [135, 136]
- **Judge:** {"faithfulness": 0.4, "answer_relevancy": 0.9, "answer_correctness": 0.6, "context_precision": 0.85, "context_recall": 0.95, "citation_correctness": 0.9, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Core fact present but many unsupported details"}
- **Câu trả lời Gemini:**

Quy định về thu hồi kinh phí bồi hoàn đối với sinh viên sư phạm được thực hiện như sau:

**1. Thủ tục và thời hạn thực hiện:**
*   **Thông báo thu hồi:** Hằng năm, cơ sở đào tạo giáo viên hoặc cơ quan có thẩm quyền sẽ thông báo danh sách sinh viên thuộc đối tượng phải bồi hoàn cho Ủy ban nhân dân cấp tỉnh hoặc cơ quan liên quan để ra thông báo thu hồi kinh phí.
*   **Liên hệ làm thủ tục:** Trong thời hạn 30 ngày kể từ ngày nhận được quyết định/thông báo của cơ quan có thẩm quyền, sinh viên hoặc gia đình phải liên hệ với cơ quan thu hồi để làm thủ tục bồi hoàn.
*   **Thời hạn bồi hoàn:** Tối đa là 04 năm kể từ khi sinh viên nhận được thông báo bồi hoàn kinh phí.

**2. Xử lý chậm trễ và khởi kiện:**
*   Nếu chậm thực hiện nghĩa vụ bồi hoàn quá thời hạn quy định, sinh viên hoặc gia đình phải chịu lãi suất tối đa áp dụng đối với tiền gửi không kỳ hạn do Ngân hàng Nhà nước Việt Nam quy định (hoặc lãi suất tiền gửi không kỳ hạn của Ngân hàng Thương mại cổ phần Công thương Việt Nam nếu Ngân hàng Nhà nước không quy định).
*   Trường hợp không thực hiện nghĩa vụ bồi hoàn, cơ quan có thẩm quyền có quyền khởi kiện tại Tòa án theo quy định pháp luật.

**3. Chính sách miễn, giảm hoặc xóa kinh phí:**
*   Nếu sinh viên thuộc đối tượng chính sách, khó khăn, Ủy ban nhân dân cấp tỉnh sẽ căn cứ vào điều kiện cụ thể để quyết định phương thức thu hồi, chính sách miễn, giảm hoặc xóa kinh phí bồi hoàn.
*   Đối với trường hợp sinh viên được xác nhận bị suy giảm khả năng lao động từ 61% trở lên hoặc từ trần, sinh viên sẽ được xóa kinh phí bồi hoàn.
*   Đối với sinh viên thuộc đối tượng hưởng chính sách miễn hoặc giảm học phí theo quy định của Chính phủ, mức bồi hoàn kinh phí hỗ trợ tiền đóng học phí sẽ được miễn hoặc giảm tương ứng.

**4. Nộp trả ngân sách:**
*   Số tiền thu hồi được nộp vào ngân sách Nhà nước theo quy định hiện hành. Đối với các cơ sở đào tạo hoặc cơ quan đặt hàng, việc nộp trả phải thực hiện chậm nhất 05 ngày làm việc kể từ khi nhận được tiền bồi hoàn từ sinh viên.

*Lưu ý: Bạn cần đối chiếu với các đối tượng phải bồi hoàn (quy định tại Điều 6) và cách tính chi phí bồi hoàn (quy định tại Điều 8) để xác định chính xác nghĩa vụ tài chính của mình.*

---
## v85_ans_092 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** unanswerable / K50
- **Human score:** 0.95
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 0.90
- **Critical false pass:** False
- **Câu hỏi:** K51 có chính sách cấp laptop miễn phí cho mọi sinh viên không?
- **Ground truth:** Sổ tay không cung cấp căn cứ để khẳng định nội dung này; hệ thống cần nói rõ không tìm thấy thông tin phù hợp.
- **Kết luận kiểm PDF:** Tìm toàn văn K51 không thấy chính sách cấp laptop miễn phí cho mọi sinh viên. Câu trả lời abstain hợp lý; nguồn hỗ trợ gần nhất chỉ nói chính sách cho nhóm cụ thể.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K51.pdf` — Chính sách miễn, giảm học phí và hỗ trợ chi phí, phương tiện đồ dùng học tập, cấp học bổng đối với sinh viên khuyết tật, sinh viên người dân tộc thiểu số; trang [73]
- **Judge:** {"faithfulness": 0.2, "answer_relevancy": 1.0, "answer_correctness": 1.0, "context_precision": 0.3, "context_recall": 0.2, "citation_correctness": 0.0, "unsupported_claim": false, "critical_false_pass": false, "rationale": "Correctly states no laptop policy, but citations irrelevant"}
- **Câu trả lời Gemini:**

Hiện tại, trong Sổ tay sinh viên không có quy định về chính sách cấp laptop miễn phí cho sinh viên khóa K51.

Theo Điều 29, Chương V của Quy chế công tác sinh viên, nhà trường thực hiện các chính sách hỗ trợ về học phí, chi phí học tập và phương tiện đồ dùng học tập đối với các đối tượng cụ thể như sau:

*   **Sinh viên là người khuyết tật:** Được hỗ trợ phương tiện, đồ dùng học tập theo quy định tại Nghị định số 28/2012/NĐ-CP và Thông tư liên tịch số 42/2013/TTLT-BGDĐT-BLĐTBXH-BTC.
*   **Sinh viên là người dân tộc thiểu số:** Được hỗ trợ chi phí học tập theo Quyết định 66/2013/QĐ-CP và Thông tư liên tịch số 35/2014/TTLT-BGDĐT-BTC.

Sinh viên thuộc các diện nêu trên cần nộp hồ sơ về Phòng Công tác chính trị và Học sinh sinh viên (CTCT&HSSV) đúng thời gian quy định theo từng học kỳ để được xem xét giải quyết.

---
## v85_ans_095 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** unanswerable / K50
- **Human score:** 0.95
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 0.90
- **Critical false pass:** False
- **Câu hỏi:** Điểm rèn luyện có được mua thêm bằng hoạt động bên ngoài trường không?
- **Ground truth:** Sổ tay không cung cấp căn cứ để khẳng định nội dung này; hệ thống cần nói rõ không tìm thấy thông tin phù hợp.
- **Kết luận kiểm PDF:** Đối chiếu toàn bộ quy trình rèn luyện K50: không có cơ chế 'mua điểm'. Câu trả lời đúng về bản chất, nhưng nên nói 'không tìm thấy căn cứ' thay vì phủ định tuyệt đối.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K50.pdf` — Sử dụng kết quả rèn luyện; trang [99]
  - `so_tay_K50.pdf` — Thời gian đánh giá kết quả rèn luyện; trang [98, 99]
  - `so_tay_K50.pdf` — Các trường hợp xem xét phân loại điểm rèn luyện; trang [94, 95]
  - `so_tay_K50.pdf` — Quy trình đánh giá kết quả rèn luyện sinh viên; trang [95, 96, 97]
  - `so_tay_K50.pdf` — Nội dung đánh giá và thang điểm; trang [92]
- **Judge:** {"faithfulness": 0.4, "answer_relevancy": 0.7, "answer_correctness": 0.7, "context_precision": 0.5, "context_recall": 0.6, "citation_correctness": 0.3, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Makes unsupported negative claim, lacks supporting citation"}
- **Câu trả lời Gemini:**

Theo quy định tại Sổ tay sinh viên khóa 50, việc đánh giá kết quả rèn luyện được thực hiện dựa trên các nội dung và thang điểm do Trường quy định.

Hiện tại, các quy định về đánh giá kết quả rèn luyện không có điều khoản nào cho phép sinh viên "mua thêm" điểm rèn luyện bằng các hoạt động bên ngoài trường. Việc đánh giá điểm rèn luyện được thực hiện theo quy trình cụ thể, trong đó sinh viên tự đánh giá dựa trên các mức điểm chi tiết do Trường quy định kèm theo minh chứng hoạt động, sau đó được thông qua bởi Cố vấn học tập và tập thể lớp trước khi trình Hội đồng đánh giá các cấp xem xét.

Các nội dung đánh giá rèn luyện tập trung vào ý thức và thái độ của sinh viên trong các hoạt động học tập, chấp hành nội quy, tham gia các hoạt động chính trị, xã hội, văn hóa, thể thao, công tác cán bộ lớp hoặc các đoàn thể, tổ chức trong Trường.

---
## v85_ans_096 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** unanswerable / K50
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Sinh viên K50 được tự động nâng điểm nếu tham gia nghiên cứu khoa học không?
- **Ground truth:** Sổ tay không cung cấp căn cứ để khẳng định nội dung này; hệ thống cần nói rõ không tìm thấy thông tin phù hợp.
- **Kết luận kiểm PDF:** Đối chiếu K50 Điều 14: tác giả chính đề tài NCKH đạt Khá trở lên có thể nộp đơn xin dùng điểm đề tài thay điểm thi kết thúc học phần, tối đa 3 tín chỉ. Nhãn unanswerable của dataset là lỗi annotation.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K50.pdf` — Quy trình tổ chức và tiến độ triển khai hoạt động nghiên cứu khoa học của sinh viên; trang [124, 125, 126, 127]
  - `so_tay_K50.pdf` — Chuyển đổi điểm nghiên cứu khoa học của sinh viên; trang [131, 132]
  - `so_tay_K50.pdf` — Quyền lợi và trách nhiệm của sinh viên tham gia nghiên cứu khoa học; trang [130, 131]
  - `so_tay_K50.pdf` — Khen thưởng và xử lý vi phạm; trang [132]
  - `so_tay_K50.pdf` — Phân cấp quản lý hoạt động nghiên cứu khoa học của sinh viên; trang [128, 129, 130]
- **Judge:** {"faithfulness": 0.4, "answer_relevancy": 0.6, "answer_correctness": 0.2, "context_precision": 0.5, "context_recall": 0.0, "citation_correctness": 0.8, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Answer asserts unsupported policy, lacks required abstention"}
- **Câu trả lời Gemini:**

Sinh viên K50 không được tự động nâng điểm khi tham gia nghiên cứu khoa học.

Tuy nhiên, sinh viên là tác giả chính của đề tài nghiên cứu khoa học được đánh giá đạt loại **Khá trở lên** có quyền nộp đơn cho Trưởng khoa để đăng ký sử dụng điểm đánh giá đề tài thay thế cho điểm thi kết thúc học phần (không quá 3 tín chỉ) liên quan gần với đề tài đó.

**Điều kiện và thủ tục:**
*   **Điều kiện:** Đề tài phải đạt loại Khá trở lên.
*   **Thủ tục:** Sinh viên nộp đơn cho Trưởng khoa để đăng ký chuyển đổi điểm.

Việc chuyển đổi điểm này được thực hiện theo quy định tại Điều 14 của Quy định về việc tổ chức hoạt động nghiên cứu khoa học của sinh viên.

---
## v85_ans_097 — judge_error
- **Nhóm:** low21
- **Case type / cohort:** unanswerable / K48-K49
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 0.90
- **Critical false pass:** False
- **Câu hỏi:** K51 có thể bỏ qua chuẩn ngoại ngữ bằng cách đóng phí thay thế không?
- **Ground truth:** Sổ tay không cung cấp căn cứ để khẳng định nội dung này; hệ thống cần nói rõ không tìm thấy thông tin phù hợp.
- **Kết luận kiểm PDF:** Quy định ngoại ngữ được xác minh trong văn bản áp dụng cho khóa tuyển sinh từ 2022 trở đi; K51 thuộc phạm vi áp dụng. Tuy nhiên phần nội dung không được in đầy đủ lại trong bản PDF K51 nên citation là dẫn xuất liên khóa, cần ghi rõ.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K51.pdf` — Lệ phí kiểm tra trình độ đầu vào, học và thi kết thúc chương trình ngoại ngữ; trang dẫn xuất liên khóa
  - `so_tay_K51.pdf` — Phạm vi điều chỉnh và đối tượng áp dụng; trang dẫn xuất liên khóa
  - `so_tay_K51.pdf` — Điều khoản chuyển tiếp; trang dẫn xuất liên khóa
  - `so_tay_K51.pdf` — Công nhận đạt chuẩn đầu ra ngoại ngữ để xét tốt nghiệp; trang dẫn xuất liên khóa
  - `so_tay_K51.pdf` — Tổ chức dạy học ngoại ngữ; trang dẫn xuất liên khóa
- **Judge:** {"faithfulness": 0.4, "answer_relevancy": 0.9, "answer_correctness": 0.9, "context_precision": 0.6, "context_recall": 0.3, "citation_correctness": 0.5, "unsupported_claim": false, "critical_false_pass": false, "rationale": "Correct overall, but lacks supporting citation for negative claim"}
- **Câu trả lời Gemini:**

Theo quy định hiện hành, không có điều khoản nào cho phép sinh viên đóng phí thay thế để bỏ qua chuẩn đầu ra ngoại ngữ.

Để được công nhận đạt chuẩn đầu ra ngoại ngữ nhằm xét tốt nghiệp, sinh viên khóa K51 cần đáp ứng một trong các trường hợp sau:
1. Đạt yêu cầu kỳ thi kết thúc chương trình ngoại ngữ do Trường tổ chức.
2. Có bằng tốt nghiệp trình độ đại học trở lên ngành ngôn ngữ nước ngoài.
3. Có chứng chỉ ngoại ngữ bậc 3/6 trở lên (theo Khung năng lực ngoại ngữ 6 bậc dùng cho Việt Nam) hoặc chứng chỉ ngoại ngữ quốc tế tương đương theo quy định.
4. Đạt giải khuyến khích cấp Trường trở lên trong các kỳ thi Olympic ngoại ngữ, thi hùng biện ngoại ngữ dành cho sinh viên không thuộc nhóm ngành ngôn ngữ nước ngoài trong thời gian học tại Trường.
5. Các trường hợp đặc biệt khác do Hiệu trưởng quyết định.

Đối với các trường hợp tại mục 2, 3, 4 và 5, sinh viên cần thực hiện thủ tục nộp đơn xét miễn học, miễn thi hoặc công nhận trình độ ngoại ngữ theo quy định tại Điều 5 của văn bản này.

*Lưu ý: Sinh viên có thể phải nộp lệ phí xét hồ sơ xin miễn học, miễn thi hoặc xét công nhận trình độ ngoại ngữ là 30.000 đ/sinh viên/lần.*

---
## v85_ans_099 — true_hallucination
- **Nhóm:** low21
- **Case type / cohort:** unanswerable / K51
- **Human score:** 0.40
- **Faithfulness PDF:** 0.50
- **Citation PDF:** 0.70
- **Critical false pass:** False
- **Câu hỏi:** Sinh viên có được chọn bất kỳ tháng nào để nhận bằng tốt nghiệp không?
- **Ground truth:** Sổ tay không cung cấp căn cứ để khẳng định nội dung này; hệ thống cần nói rõ không tìm thấy thông tin phù hợp.
- **Kết luận kiểm PDF:** K51 chỉ quy định các đợt xét tốt nghiệp và thời hạn cấp bằng trong 3 tháng. Không có căn cứ để suy ra sinh viên 'không được tự chọn tháng nhận bằng'; đây là suy diễn không được nguồn hỗ trợ.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K51.pdf` — Công nhận tốt nghiệp và cấp bằng tốt nghiệp; trang [23, 24, 25]
  - `so_tay_K51.pdf` — Quyền của sinh viên; trang [60, 61]
  - `so_tay_K51.pdf` — Học cùng lúc hai chương trình; trang [27, 28]
  - `so_tay_K51.pdf` — Học liên thông đối với người có văn bằng khác; trang [28, 29]
  - `so_tay_K51.pdf` — Tiêu chuẩn đối với học viên sau đại học; trang [149, 150, 151]
- **Judge:** {"faithfulness": 0.2, "answer_relevancy": 0.8, "answer_correctness": 0.0, "context_precision": 0.4, "context_recall": 0.2, "citation_correctness": 0.1, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Answer asserts unsupported policy; should have abstained."}
- **Câu trả lời Gemini:**

Theo quy định tại Trường Đại học Sư phạm Thành phố Hồ Chí Minh, sinh viên không được tự chọn tháng nhận bằng tốt nghiệp.

Việc xét và cấp bằng tốt nghiệp được thực hiện theo các đợt xét tốt nghiệp chính thức do Nhà trường quy định trong kế hoạch năm học:

*   **Đối với sinh viên hình thức đào tạo chính quy:** Có 03 đợt xét tốt nghiệp chính thức, thường được tổ chức vào tháng 5, tháng 8 và tháng 10.
*   **Đối với sinh viên hình thức đào tạo vừa làm vừa học:** Có 05 đợt xét tốt nghiệp chính thức, thường được tổ chức vào tháng 3, tháng 5, tháng 8, tháng 10 và tháng 12.

Ngoài ra, căn cứ vào điều kiện cụ thể của từng năm học, Hiệu trưởng sẽ quyết định các đợt xét tốt nghiệp bổ sung. Sinh viên đủ điều kiện tốt nghiệp sẽ được Hiệu trưởng ký quyết định công nhận và cấp bằng trong thời hạn 03 tháng kể từ thời điểm đáp ứng đầy đủ các điều kiện tốt nghiệp và hoàn thành nghĩa vụ với Trường.

---
## v85_ans_004 — correct_supported
- **Nhóm:** random4
- **Case type / cohort:** regulation_true_rag / K48-K49
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em thuộc K48-K49, công nhận kết quả học tập và chuyển đổi tín chỉ la sao va can luu y gi theo so tay?
- **Ground truth:** Công nhận kết quả học tập và chuyển đổi tín chỉ 1. Kết quả học tập của người học đã tích lũy từ một trình độ đào tạo khác, một ngành đào tạo hoặc một CTĐT khác, một khóa học khác hoặc từ một cơ sở đào tạo khác được Trường xem xét công nhận, chuyển đổi sang tín chỉ của những học phần trong CTĐT theo học. Hội đồng chuyên môn của Trường xem xét công nhận, chuyển đổi tín chỉ trên cơ sở đối sánh chuẩn đầu ra, nội dung và khối lượng học tập, cách thức đánh giá học phần và các điều kiện bảo đảm chất lượng thực hiện chương trình theo các cấp độ: a) Công nhận, chuyển đổi theo từng học phần;
- **Kết luận kiểm PDF:** Đối chiếu K48-K49 Điều 14 và Điều 18: cấp độ công nhận, giới hạn 50%, hồ sơ và giới hạn 25% trong hợp tác đào tạo đều đúng.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K48_49.pdf` — Công nhận kết quả học tập và chuyển đổi tín chỉ; trang [25]
  - `so_tay_K48_49.pdf` — Chuyển ngành, chuyển nơi học, chuyển cơ sở đào tạo, chuyển hình thức học; trang [28, 29]
  - `so_tay_K48_49.pdf` — Trao đổi sinh viên và hợp tác trong đào tạo; trang [29, 30]
  - `so_tay_K48_49.pdf` — Công nhận tốt nghiệp và cấp bằng tốt nghiệp; trang [25, 26, 27]
  - `so_tay_K48_49.pdf` — Công nhận đạt chuẩn đầu ra ngoại ngữ để xét tốt nghiệp; trang dẫn xuất liên khóa
- **Judge:** {"faithfulness": 0.55, "answer_relevancy": 0.9, "answer_correctness": 0.9, "context_precision": 0.6, "context_recall": 0.9, "citation_correctness": 0.9, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Mostly correct but includes unsupported details"}
- **Câu trả lời Gemini:**

Đối với sinh viên khóa K48-K49, quy định về công nhận kết quả học tập và chuyển đổi tín chỉ được thực hiện theo Điều 14, Chương III của Quy chế đào tạo trình độ đại học tại Trường Đại học Sư phạm Thành phố Hồ Chí Minh, cụ thể như sau:

**1. Nguyên tắc công nhận và chuyển đổi:**
*   Trường xem xét công nhận, chuyển đổi sang tín chỉ của các học phần trong chương trình đào tạo (CTĐT) đối với kết quả học tập mà người học đã tích lũy từ: trình độ đào tạo khác, ngành đào tạo khác, CTĐT khác, khóa học khác hoặc từ cơ sở đào tạo khác.
*   Hội đồng chuyên môn của Trường sẽ đối sánh dựa trên chuẩn đầu ra, nội dung, khối lượng học tập, cách thức đánh giá và các điều kiện bảo đảm chất lượng.
*   Việc công nhận, chuyển đổi được thực hiện theo các cấp độ: từng học phần, nhóm học phần hoặc cả CTĐT.

**2. Giới hạn khối lượng:**
*   Khối lượng tối đa được công nhận, chuyển đổi không vượt quá 50% khối lượng học tập tối thiểu của CTĐT.
*   Riêng đối với ngành đào tạo giáo viên, việc thực hiện theo hướng dẫn của Bộ Giáo dục và Đào tạo.

**3. Quy trình và thủ tục:**
*   Quy trình và hồ sơ thực hiện theo quy định xét miễn học, miễn thi công nhận điểm học phần trong CTĐT trình độ đại học của Trường.
*   Đối với trường hợp sinh viên học một số học phần tại cơ sở đào tạo khác thông qua hợp tác đào tạo (theo Điều 18), khối lượng công nhận không vượt quá 25% tổng khối lượng của CTĐT.

*

---
## v85_ans_005 — correct_but_partially_relevant
- **Nhóm:** random4
- **Case type / cohort:** regulation_true_rag / K48-K49
- **Human score:** 0.75
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Em thuộc K48-K49, Nếu cần áp dụng đúng quy định công tác sinh viên có điểm nào dễ bị hiểu nhầm không?
- **Ground truth:** Công tác sinh viên là một trong những công tác trọng tâm của Trường bao gồm tổng thể các hoạt động giáo dục, tuyên truyền; hỗ trợ và dịch vụ đối với sinh viên nhằm đảm bảo các mục tiêu của giáo dục đại học. Công tác sinh viên phải thực hiện đúng đường lối của Đảng, chính sách, pháp luật của Nhà nước và các quy chế, quy định của Bộ Giáo dục và Đào tạo.
- **Kết luận kiểm PDF:** Đối chiếu K48-K49: các nguyên tắc và thông tin bồi hoàn đều có nguồn, nhưng câu trả lời không nêu trực tiếp định nghĩa công tác sinh viên và mở rộng hơi xa.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K48_49.pdf` — Công tác sinh viên; trang [36, 37]
  - `so_tay_K48_49.pdf` — Phạm vi điều chỉnh và đối tượng áp dụng; trang [36]
  - `so_tay_K48_49.pdf` — Sinh viên; trang [36]
  - `so_tay_K48_49.pdf` — Bồi hoàn kinh phí hỗ trợ; trang [110, 111]
  - `so_tay_K48_49.pdf` — Tổ chức đăng ký học tập; trang [17, 18]
- **Judge:** {"faithfulness": 0.9, "answer_relevancy": 0.4, "answer_correctness": 0.2, "context_precision": 0.5, "context_recall": 0.8, "citation_correctness": 0.9, "unsupported_claim": false, "critical_false_pass": false, "rationale": "Answer vague, misses specific confusing point"}
- **Câu trả lời Gemini:**

Chào bạn, đối với sinh viên khóa K48-K49, các quy định về công tác sinh viên được thực hiện theo "Quy chế công tác sinh viên đối với chương trình đào tạo đại học hệ chính quy" của Trường Đại học Sư phạm Thành phố Hồ Chí Minh.

Để tránh hiểu nhầm, bạn cần lưu ý các nguyên tắc cốt lõi sau đây:

1. **Phạm vi áp dụng:** Quy chế này áp dụng cho tất cả sinh viên hệ đại học chính quy đang học tập tại Trường [2]. Sinh viên được xác định là trung tâm của các hoạt động giáo dục, được đảm bảo điều kiện thực hiện đầy đủ quyền và nghĩa vụ trong quá trình học tập và rèn luyện [3].
2. **Nguyên tắc thực hiện:** Công tác sinh viên phải đảm bảo tính khách quan, công bằng, công khai và minh bạch trong mọi vấn đề liên quan đến sinh viên [1].
3. **Phân biệt với các chính sách hỗ trợ:** Nếu bạn là sinh viên sư phạm thuộc đối tượng hưởng chính sách hỗ trợ tiền đóng học phí và chi phí sinh hoạt, cần lưu ý các quy định về **bồi hoàn kinh phí** (Điều 6, Nghị định về chính sách hỗ trợ sinh viên sư phạm). Cụ thể:
    * Bạn có thể phải bồi hoàn nếu không công tác trong ngành giáo dục sau 02 năm tốt nghiệp, hoặc tự thôi học, bị kỷ luật buộc thôi học [4].
    * Các trường hợp dừng học do ốm đau, tai nạn, học lại, lưu ban (không quá một lần) hoặc lý do khác không do kỷ luật vẫn được xem xét tiếp tục hưởng chính sách hỗ trợ, nhưng tổng thời gian hưởng không vượt quá thời gian tối đa hoàn thành chương trình đào tạo [4].

Nếu bạn đang gặp vướng mắc cụ thể tại một điều khoản nào đó trong Sổ tay sinh viên khiến bạn cảm thấy khó hiểu, bạn vui lòng cung cấp chi tiết nội dung đó để tôi có thể giải đáp chính xác hơn dựa trên quy định hiện hành.

---
## v85_ans_045 — correct_supported
- **Nhóm:** random4
- **Case type / cohort:** regulation_true_rag / general
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 0.95
- **Critical false pass:** False
- **Câu hỏi:** Sinh viên cần hiểu thế nào về công nhận đạt chuẩn đầu ra ngoại ngữ để xét tốt nghiệp thì em cần thực hiện hoặc đáp ứng những gì?
- **Ground truth:** Công nhận đạt chuẩn đầu ra ngoại ngữ để xét tốt nghiệp 1. Sinh viên theo quy định Điều 1 tốt nghiệp trình độ đại học phải đạt tối thiểu bậc 3/6 theo Khung năng lực ngoại ngữ 6 bậc dùng cho Việt Nam hoặc tương đương để được công nhận tốt nghiệp. Sinh viên được công nhận đạt chuẩn đầu ra ngoại ngữ để xét tốt nghiệp nếu thuộc 01 trong các trường hợp sau: a) Đạt yêu cầu kỳ thi kết thúc chương trình ngoại ngữ theo quy định tại Điều 3;
- **Kết luận kiểm PDF:** Nội dung chuẩn đầu ra ngoại ngữ, các trường hợp công nhận và thủ tục 15/10 ngày được xác minh trong quy định áp dụng từ khóa tuyển sinh 2022 trở đi; citation liên khóa cần được mô tả rõ.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K50.pdf` — Công nhận đạt chuẩn đầu ra ngoại ngữ để xét tốt nghiệp; trang [111, 112]
  - `so_tay_K50.pdf` — Quy trình và thủ tục công nhận trình độ ngoại ngữ để xét tốt nghiệp; trang [112]
  - `so_tay_K48_49.pdf` — Công nhận đạt chuẩn đầu ra ngoại ngữ để xét tốt nghiệp; trang dẫn xuất liên khóa
  - `so_tay_K48_49.pdf` — Quy trình và thủ tục công nhận trình độ ngoại ngữ để xét tốt nghiệp; trang dẫn xuất liên khóa
- **Judge:** {"faithfulness": 0.7, "answer_relevancy": 0.7, "answer_correctness": 0.7, "context_precision": 0.6, "context_recall": 0.9, "citation_correctness": 0.9, "unsupported_claim": true, "critical_false_pass": false, "rationale": "Some claims lack supporting evidence"}
- **Câu trả lời Gemini:**

Để được công nhận đạt chuẩn đầu ra ngoại ngữ phục vụ xét tốt nghiệp, sinh viên cần đạt tối thiểu bậc 3/6 theo Khung năng lực ngoại ngữ 6 bậc dùng cho Việt Nam hoặc trình độ tương đương [1, 2, 3].

Sinh viên được công nhận đạt chuẩn nếu thuộc một trong các trường hợp sau:
*   Đạt yêu cầu kỳ thi kết thúc chương trình ngoại ngữ theo quy định của Trường [1, 2, 3].
*   Có bằng tốt nghiệp trình độ đại học trở lên ngành ngôn ngữ nước ngoài [1, 2, 3].
*   Có chứng chỉ ngoại ngữ bậc 3/6 trở lên theo Khung năng lực ngoại ngữ 6 bậc dùng cho Việt Nam hoặc chứng chỉ ngoại ngữ quốc tế tương đương theo quy định tại Phụ lục [1, 2, 3].
*   Đạt giải khuyến khích cấp Trường trở lên trong các kỳ thi Olympic ngoại ngữ, thi hùng biện ngoại ngữ dành cho sinh viên không thuộc nhóm ngành ngôn ngữ nước ngoài trong thời gian học tại Trường [1, 2, 3].
*   Các trường hợp đặc biệt khác do Hiệu trưởng quyết định [1, 2, 3].

**Lưu ý về thủ tục:**
Sinh viên thuộc các trường hợp có bằng đại học ngành ngôn ngữ, có chứng chỉ, đạt giải thi ngoại ngữ hoặc trường hợp đặc biệt cần thực hiện thủ tục theo Điều 5 [1, 2, 3]:
1.  **Bước 1:** Nộp đơn (theo mẫu) cho Phòng Khảo thí và Đảm bảo chất lượng theo thông báo của Trường [4, 5].
2.  **Bước 2:** Phòng Khảo thí và Đảm bảo chất lượng phối hợp với các khoa kiểm tra và báo cáo Hiệu trưởng ra quyết định công nhận trong vòng 15 ngày làm việc kể từ ngày hết hạn nộp đơn [4, 5].
3.  **Bước 3:** Kết quả được thông báo cho sinh viên và công khai trên Cổng thông tin điện tử của Trường trong vòng 10 ngày làm việc kể từ khi có quyết định [4, 5].

---
## v85_ans_090 — correct_supported
- **Nhóm:** random4
- **Case type / cohort:** structured_mixed / K50
- **Human score:** 1.00
- **Faithfulness PDF:** 1.00
- **Citation PDF:** 1.00
- **Critical false pass:** False
- **Câu hỏi:** Case 90: em thuộc K50, nhờ giải thích bảng quy đổi ngoại ngữ cho chứng chỉ phổ biến.
- **Ground truth:** Trả lời trực tiếp bằng dữ liệu structured catalog đúng cohort và đúng nguồn.
- **Kết luận kiểm PDF:** Đối chiếu bảng quy đổi K50: các ngưỡng chứng chỉ phổ biến trong structured result khớp bảng gốc.
- **Nguồn PDF đã kiểm:**
  - `so_tay_K50.pdf` — Bảng tham chiếu quy đổi chứng chỉ ngoại ngữ tương đương bậc 3 và bậc 4; trang [112, 113, 114, 115, 116]
- **Judge:** {"faithfulness": 0.96, "answer_relevancy": 0.95, "answer_correctness": 0.96, "context_precision": 0.94, "context_recall": 0.94, "citation_correctness": 0.92, "unsupported_claim": false, "critical_false_pass": false, "rationale": "Accurate table, fully supported by context"}
- **Câu trả lời Gemini:**

Dưới đây là bảng tham chiếu quy đổi chứng chỉ ngoại ngữ tương đương bậc 3 và bậc 4 dành cho sinh viên khóa K50:

| Ngôn ngữ | Chứng chỉ | Bậc 3 | Bậc 4 |
| :--- | :--- | :--- | :--- |
| **Tiếng Anh** | TOEFL iBT | 30 - 45 | 46 - 93 |
| | TOEFL ITP | 450 - 499 | - |
| | IELTS | 4.0 - 5.0 | 5.5 - 6.5 |
| | Cambridge/Linguaskill | B1 Preliminary; B1 Business Preliminary; Linguaskill 140 - 159 | B2 First; B2 Business Vantage; Linguaskill 160 - 179 |
| | TOEIC (4 kỹ năng) | Nghe 275-399; Đọc 275-384; Nói 120-159; Viết 120-149 | Nghe 400-489; Đọc 385-454; Nói 160-179; Viết 150-179 |
| **Tiếng Pháp** | TCF / DELF | TCF 300 - 399; DELF B1 | TCF 400 - 499; DELF B2 |
| **Tiếng Trung** | HSK | HSK bậc 3 | HSK bậc 4 |
| **Tiếng Nhật** | JLPT | N4 | N3 |
| **Tiếng Nga** | ТРКИ | ТРКИ-1 | ТРКИ-2 |
| **Tiếng Hàn** | TOPIK II | TOPIK II (120) | TOPIK II (150) |

---