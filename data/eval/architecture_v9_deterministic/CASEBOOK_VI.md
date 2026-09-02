# Architecture V9 Deterministic — Pre-run review

> Bộ 140 câu mới cho runtime 7f1fc82b; chưa chứa output của hệ thống.

- Realistic: 112; stress: 28.
- Case types: `{'single_structured': 60, 'capability_boundary': 24, 'compound': 28, 'missing_or_ambiguous': 12, 'unsupported_in_domain': 8, 'out_of_domain': 8}`.
- Exact historical overlap: 0.
- `fact_lock_applicable=true` chỉ dùng cho lookup một bảng–một hàng xác định.
- Retrieval/answer/production files đi kèm chỉ để tương thích runner; không phải metric V9 mới.

| ID | Split | Cohort | Type | Fact lock tasks | Query |
|---|---|---|---|---:|---|
| `v9_det_001` | `realistic` | `K51` | `single_structured` | 1 | Em học K51; bảng ngoại ngữ quy đổi TOEIC (4 kỹ năng) sang bậc 3 và bậc 4 thế nào? |
| `v9_det_002` | `realistic` | `K50` | `single_structured` | 1 | Trong bảng áp dụng cho K50, hai mức tương đương của TCF / DELF là gì? |
| `v9_det_003` | `realistic` | `K48-K49` | `single_structured` | 1 | Cho em tra dòng ТРКИ - Тест по русскому языку как иностранному: chuẩn bậc 3 và bậc 4 được ghi ra sao? |
| `v9_det_004` | `realistic` | `K51` | `single_structured` | 1 | Em học K51; bảng ngoại ngữ quy đổi TOPIK II sang bậc 3 và bậc 4 thế nào? |
| `v9_det_005` | `realistic` | `K50` | `single_structured` | 1 | Trong bảng áp dụng cho K50, hai mức tương đương của TOEFL iBT là gì? |
| `v9_det_006` | `realistic` | `K51` | `single_structured` | 1 | Cho em tra dòng Hanyu Shuiping Kaoshi (HSK): chuẩn bậc 3 và bậc 4 được ghi ra sao? |
| `v9_det_007` | `realistic` | `K51` | `single_structured` | 1 | Sinh viên K51 hệ chính quy học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? |
| `v9_det_008` | `realistic` | `K51` | `single_structured` | 1 | Sinh viên K51 hệ vừa làm vừa học học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? |
| `v9_det_009` | `realistic` | `K50` | `single_structured` | 1 | Ở K50, đào tạo đại học cấp bằng thứ nhất theo hệ chính quy học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? |
| `v9_det_010` | `realistic` | `K50` | `single_structured` | 1 | Ở K50, đào tạo đại học cấp bằng thứ nhất theo hệ vừa làm vừa học học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? |
| `v9_det_011` | `realistic` | `K48-K49` | `single_structured` | 1 | Ở K48-K49, đào tạo liên thông từ trình độ cao đẳng lên trình độ đại học theo hệ chính quy học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? |
| `v9_det_012` | `realistic` | `K48-K49` | `single_structured` | 1 | Ở K48-K49, đào tạo liên thông trình độ đại học đối với người đã có một bằng đại học theo hệ vừa làm vừa học học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? |
| `v9_det_013` | `realistic` | `K51` | `single_structured` | 1 | Mức học bổng Giỏi của K51 dùng hệ số nào và lấy mức học phí nào làm căn cứ? |
| `v9_det_014` | `realistic` | `K51` | `single_structured` | 1 | Ở K51, học lực Giỏi và rèn luyện Tốt trở lên thì được xếp học bổng mức nào? |
| `v9_det_015` | `realistic` | `K51` | `single_structured` | 0 | Điều kiện học bổng K51 ở tiêu chí đối tượng yêu cầu gì? |
| `v9_det_016` | `realistic` | `K50` | `single_structured` | 1 | Mức học bổng Xuất sắc của K50 dùng hệ số nào và lấy mức học phí nào làm căn cứ? |
| `v9_det_017` | `realistic` | `K50` | `single_structured` | 1 | Khoảng điểm nào được xếp học bổng loại Giỏi ở K50? |
| `v9_det_018` | `realistic` | `K48-K49` | `single_structured` | 0 | Điều kiện học bổng K48-K49 ở tiêu chí học tập, rèn luyện và kỷ luật yêu cầu gì? |
| `v9_det_019` | `realistic` | `K51` | `single_structured` | 1 | Học phần nền tảng của K51 được 8,3 thì quy thành điểm chữ nào? |
| `v9_det_020` | `realistic` | `K51` | `single_structured` | 1 | Một môn còn lại ở K51 đạt 5,1 điểm thì nhận điểm chữ gì và có qua không? |
| `v9_det_021` | `realistic` | `K50` | `single_structured` | 1 | Điểm học phần 7,6 của sinh viên K50 tương ứng điểm chữ nào? |
| `v9_det_022` | `realistic` | `K48-K49` | `single_structured` | 1 | Ở K48-K49, môn học được 4,5 thì đổi sang điểm chữ gì? |
| `v9_det_023` | `realistic` | `K51` | `single_structured` | 1 | B+ trong thang điểm K51 bằng bao nhiêu điểm hệ 4? |
| `v9_det_024` | `realistic` | `K50` | `single_structured` | 1 | Theo bảng K50, điểm chữ F có giá trị hệ 4 là bao nhiêu? |
| `v9_det_025` | `realistic` | `K51` | `single_structured` | 1 | GPA 3,58 của K51 thuộc xếp loại học lực nào? |
| `v9_det_026` | `realistic` | `K48-K49` | `single_structured` | 1 | Sinh viên K48-K49 có GPA 0,90 thì xếp học lực gì? |
| `v9_det_027` | `realistic` | `K51` | `single_structured` | 1 | 31 điểm rèn luyện ở K51 được xếp loại gì? |
| `v9_det_028` | `realistic` | `K51` | `single_structured` | 1 | 58 điểm rèn luyện ở K51 được xếp loại gì? |
| `v9_det_029` | `realistic` | `K50` | `single_structured` | 1 | 72 điểm rèn luyện ở K50 được xếp loại gì? |
| `v9_det_030` | `realistic` | `K50` | `single_structured` | 1 | 85 điểm rèn luyện ở K50 được xếp loại gì? |
| `v9_det_031` | `realistic` | `K48-K49` | `single_structured` | 1 | 88 điểm rèn luyện ở K48-K49 được xếp loại gì? |
| `v9_det_032` | `realistic` | `K48-K49` | `single_structured` | 1 | 96 điểm rèn luyện ở K48-K49 được xếp loại gì? |
| `v9_det_033` | `realistic` | `K51` | `single_structured` | 0 | Cách tính GPA có trọng số tín chỉ được viết như thế nào? |
| `v9_det_034` | `realistic` | `K50` | `single_structured` | 0 | Công thức điểm dùng để xếp hạng học bổng kết hợp học tập và rèn luyện ra sao? |
| `v9_det_035` | `realistic` | `K51` | `single_structured` | 0 | Danh bạ K51 ghi địa chỉ làm việc của Thư viện là gì? |
| `v9_det_036` | `realistic` | `K50` | `single_structured` | 0 | Danh bạ K50 ghi số điện thoại của Phòng Công nghệ Thông tin là gì? |
| `v9_det_037` | `realistic` | `K48-K49` | `single_structured` | 0 | Danh bạ K48-K49 ghi email của Phòng Sau Đại học là gì? |
| `v9_det_038` | `realistic` | `K51` | `single_structured` | 0 | Danh bạ K51 ghi địa chỉ làm việc của Phòng Quản trị – Thiết bị là gì? |
| `v9_det_039` | `realistic` | `K50` | `single_structured` | 0 | Danh bạ K50 ghi địa chỉ làm việc của Phòng Khảo thí và Đảm bảo chất lượng là gì? |
| `v9_det_040` | `realistic` | `K48-K49` | `single_structured` | 0 | Danh bạ K48-K49 ghi email của Phòng Khoa học Công nghệ và Môi trường – Tạp chí Khoa học là gì? |
| `v9_det_041` | `realistic` | `K51` | `single_structured` | 0 | Danh bạ K51 ghi địa chỉ làm việc của Khoa Tâm lý học là gì? |
| `v9_det_042` | `realistic` | `K50` | `single_structured` | 0 | Danh bạ K50 ghi số điện thoại của Khoa Khoa học Giáo dục là gì? |
| `v9_det_043` | `realistic` | `K48-K49` | `single_structured` | 0 | Danh bạ K48-K49 ghi email của Khoa Giáo dục Tiểu học là gì? |
| `v9_det_044` | `realistic` | `K51` | `single_structured` | 0 | Danh bạ K51 ghi website của Khoa Tiếng Hàn Quốc là gì? |
| `v9_det_045` | `realistic` | `K50` | `single_structured` | 0 | Danh bạ K50 ghi địa chỉ làm việc của Khoa Sinh học là gì? |
| `v9_det_046` | `realistic` | `K48-K49` | `single_structured` | 0 | Danh bạ K48-K49 ghi số điện thoại của Khoa Vật lí là gì? |
| `v9_det_047` | `realistic` | `K51` | `single_structured` | 0 | Sinh viên K51 học ngành Công tác xã hội thì ngành này do khoa nào quản lý? |
| `v9_det_048` | `realistic` | `K50` | `single_structured` | 0 | Sinh viên K50 học ngành Sư phạm Công nghệ thì ngành này do khoa nào quản lý? |
| `v9_det_049` | `realistic` | `K48-K49` | `single_structured` | 0 | Sinh viên K48-K49 học ngành Văn học thì ngành này do khoa nào quản lý? |
| `v9_det_050` | `realistic` | `K51` | `single_structured` | 0 | Sinh viên K51 học ngành Giáo dục Mầm non (trình độ cao đẳng và đại học) thì ngành này do khoa nào quản lý? |
| `v9_det_051` | `realistic` | `K50` | `single_structured` | 0 | Sinh viên K50 học ngành Sư phạm tiếng Pháp thì ngành này do khoa nào quản lý? |
| `v9_det_052` | `realistic` | `K48-K49` | `single_structured` | 0 | Sinh viên K48-K49 học ngành Sư phạm Tin học thì ngành này do khoa nào quản lý? |
| `v9_det_053` | `realistic` | `K51` | `single_structured` | 0 | Sinh viên K51 học ngành Công nghệ Giáo dục thì ngành này do khoa nào quản lý? |
| `v9_det_054` | `realistic` | `K50` | `single_structured` | 0 | Sinh viên K50 học ngành Quốc tế học thì ngành này do khoa nào quản lý? |
| `v9_det_055` | `realistic` | `K51` | `single_structured` | 0 | Ở K51, nếu cần quản lý trang thông tin điện tử của trường thì em liên hệ đơn vị nào? |
| `v9_det_056` | `realistic` | `K50` | `single_structured` | 0 | Ở K50, nếu cần thu học phí, lệ phí các hệ đào tạo thì em liên hệ đơn vị nào? |
| `v9_det_057` | `realistic` | `K48-K49` | `single_structured` | 0 | Ở K48-K49, nếu cần tổ chức khám sức khỏe đầu khoá học cho tân sinh viên thì em liên hệ đơn vị nào? |
| `v9_det_058` | `realistic` | `K51` | `single_structured` | 0 | Ở K51, nếu cần tổ chức tuyển sinh các hệ thì em liên hệ đơn vị nào? |
| `v9_det_059` | `realistic` | `K50` | `single_structured` | 0 | Ở K50, nếu cần công tác giáo dục đạo đức, lối sống, kỹ năng sống thì em liên hệ đơn vị nào? |
| `v9_det_060` | `realistic` | `K48-K49` | `single_structured` | 0 | Ở K48-K49, nếu cần liên hệ đoàn thanh niên và hội sinh viên trường thì em liên hệ đơn vị nào? |
| `v9_det_061` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 13 của chính sách người học tài năng dành cho K51, phần tổ chức thực hiện quy định những nội dung chính nào? |
| `v9_det_062` | `realistic` | `K50` | `capability_boundary` | 0 | Theo Điều 8 của quy tắc ứng xử dành cho K50, phần ứng xử với người học quy định những nội dung chính nào? |
| `v9_det_063` | `realistic` | `K50` | `capability_boundary` | 0 | Theo Điều 1 của quy định cố vấn học tập dành cho K50, phần phạm vi và đối tượng áp dụng quy định những nội dung chính nào? |
| `v9_det_064` | `realistic` | `K50` | `capability_boundary` | 0 | Theo Điều 3 của quy chế công tác sinh viên dành cho K50, phần công tác sinh viên quy định những nội dung chính nào? |
| `v9_det_065` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 2 của quy định cố vấn học tập dành cho K51, phần mục đích công tác cố vấn học tập quy định những nội dung chính nào? |
| `v9_det_066` | `realistic` | `K50` | `capability_boundary` | 0 | Theo Điều 1 của quy chế đào tạo đại học dành cho K50, phần phạm vi điều chỉnh và đối tượng áp dụng quy định những nội dung chính nào? |
| `v9_det_067` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 10 của quy chế công tác sinh viên dành cho K51, phần các hành vi sinh viên không được làm quy định những nội dung chính nào? |
| `v9_det_068` | `realistic` | `K50` | `capability_boundary` | 0 | Theo Điều 16 của quy chế rèn luyện dành cho K50, phần trách nhiệm của các đơn vị liên quan quy định những nội dung chính nào? |
| `v9_det_069` | `realistic` | `K48-K49` | `capability_boundary` | 0 | Theo Điều 6 của quy chế rèn luyện dành cho K48-K49, phần đánh giá về ý thức và kết quả tham gia các hoạt động chính trị – xã hội, văn hóa, văn nghệ, thể thao, phòng chống tệ nạn xã hội quy định những nội dung chính nào? |
| `v9_det_070` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 10 của quy định cố vấn học tập dành cho K51, phần hiệu lực thi hành quy định những nội dung chính nào? |
| `v9_det_071` | `realistic` | `K50` | `capability_boundary` | 0 | Theo Điều 15 của quy chế công tác sinh viên dành cho K50, phần phòng khảo thí và đảm bảo chất lượng quy định những nội dung chính nào? |
| `v9_det_072` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 7 của quy định nghiên cứu khoa học sinh viên dành cho K51, phần quy trình tổ chức và tiến độ triển khai hoạt động nghiên cứu khoa học của sinh viên quy định những nội dung chính nào? |
| `v9_det_073` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 34 của quy chế công tác sinh viên dành cho K51, phần hình thức kỷ luật và nội dung vi phạm quy định những nội dung chính nào? |
| `v9_det_074` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 6 của quy chế đào tạo đại học dành cho K51, phần liên kết đào tạo quy định những nội dung chính nào? |
| `v9_det_075` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 14 của chính sách người học tài năng dành cho K51, phần kiểm tra, khen thưởng, kỷ luật quy định những nội dung chính nào? |
| `v9_det_076` | `realistic` | `K48-K49` | `capability_boundary` | 0 | Theo Điều 12 của nghị định hỗ trợ sinh viên sư phạm dành cho K48-K49, phần trách nhiệm của cơ sở đào tạo giáo viên quy định những nội dung chính nào? |
| `v9_det_077` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 8 của quy định cố vấn học tập dành cho K51, phần đánh giá kết quả hoạt động quy định những nội dung chính nào? |
| `v9_det_078` | `realistic` | `K50` | `capability_boundary` | 0 | Theo Điều 7 của quy chế rèn luyện dành cho K50, phần đánh giá về phẩm chất công dân và quan hệ với cộng đồng quy định những nội dung chính nào? |
| `v9_det_079` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 12 của quy định ngoại trú dành cho K51, phần cố vấn học tập, bcs lớp quy định những nội dung chính nào? |
| `v9_det_080` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 1 của chính sách người học tài năng dành cho K51, phần phạm vi điều chỉnh và đối tượng áp dụng quy định những nội dung chính nào? |
| `v9_det_081` | `realistic` | `K51` | `capability_boundary` | 0 | Theo Điều 6 của quy chế công tác sinh viên dành cho K51, phần hỗ trợ và dịch vụ sinh viên quy định những nội dung chính nào? |
| `v9_det_082` | `realistic` | `K50` | `capability_boundary` | 0 | Theo Điều 34 của quy chế công tác sinh viên dành cho K50, phần hình thức kỷ luật và nội dung vi phạm quy định những nội dung chính nào? |
| `v9_det_083` | `realistic` | `K48-K49` | `capability_boundary` | 0 | Theo Điều 4 của quy định nghiên cứu khoa học sinh viên dành cho K48-K49, phần nội dung hoạt động nghiên cứu khoa học của sinh viên quy định những nội dung chính nào? |
| `v9_det_084` | `realistic` | `K48-K49` | `capability_boundary` | 0 | Theo Điều 21 của quy chế công tác sinh viên dành cho K48-K49, phần phòng thanh tra đào tạo quy định những nội dung chính nào? |
| `v9_det_085` | `stress` | `K51` | `compound` | 2 | Em hỏi hai ý riêng. Thứ nhất: em học K51; bảng ngoại ngữ quy đổi TOPIK II sang bậc 3 và bậc 4 thế nào? Thứ hai: ở K51, học lực Giỏi và rèn luyện Tốt trở lên thì được xếp học bổng mức nào? |
| `v9_det_086` | `stress` | `K50` | `compound` | 1 | Em hỏi hai ý riêng. Thứ nhất: 72 điểm rèn luyện ở K50 được xếp loại gì? Thứ hai: danh bạ K50 ghi số điện thoại của Khoa Khoa học Giáo dục là gì? |
| `v9_det_087` | `stress` | `K48-K49` | `compound` | 1 | Em hỏi hai ý riêng. Thứ nhất: ở K48-K49, nếu cần liên hệ đoàn thanh niên và hội sinh viên trường thì em liên hệ đơn vị nào? Thứ hai: ở K48-K49, môn học được 4,5 thì đổi sang điểm chữ gì? |
| `v9_det_088` | `stress` | `K51` | `compound` | 1 | Em hỏi hai ý riêng. Thứ nhất: ở K51, nếu cần quản lý trang thông tin điện tử của trường thì em liên hệ đơn vị nào? Thứ hai: sinh viên K51 hệ chính quy học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? |
| `v9_det_089` | `stress` | `K50` | `compound` | 1 | Em hỏi hai ý riêng. Thứ nhất: 85 điểm rèn luyện ở K50 được xếp loại gì? Thứ hai: danh bạ K50 ghi địa chỉ làm việc của Khoa Sinh học là gì? |
| `v9_det_090` | `stress` | `K48-K49` | `compound` | 1 | Em hỏi hai ý riêng. Thứ nhất: ở K48-K49, môn học được 4,5 thì đổi sang điểm chữ gì? Thứ hai: danh bạ K48-K49 ghi email của Phòng Khoa học Công nghệ và Môi trường – Tạp chí Khoa học là gì? |
| `v9_det_091` | `stress` | `K51` | `compound` | 1 | Em hỏi hai ý riêng. Thứ nhất: sinh viên K51 học ngành Công tác xã hội thì ngành này do khoa nào quản lý? Thứ hai: em học K51; bảng ngoại ngữ quy đổi TOEIC (4 kỹ năng) sang bậc 3 và bậc 4 thế nào? |
| `v9_det_092` | `stress` | `K50` | `compound` | 0 | Em hỏi hai ý riêng. Thứ nhất: công thức điểm dùng để xếp hạng học bổng kết hợp học tập và rèn luyện ra sao? Thứ hai: sinh viên K50 học ngành Sư phạm Công nghệ thì ngành này do khoa nào quản lý? |
| `v9_det_093` | `stress` | `K48-K49` | `compound` | 0 | Em hỏi hai ý riêng. Thứ nhất: danh bạ K48-K49 ghi email của Phòng Khoa học Công nghệ và Môi trường – Tạp chí Khoa học là gì? Thứ hai: ở K48-K49, nếu cần tổ chức khám sức khỏe đầu khoá học cho tân sinh viên thì em liên hệ đơn vị nào? |
| `v9_det_094` | `stress` | `K51` | `compound` | 0 | Em hỏi hai ý riêng. Thứ nhất: danh bạ K51 ghi địa chỉ làm việc của Phòng Quản trị – Thiết bị là gì? Thứ hai: sinh viên K51 học ngành Công nghệ Giáo dục thì ngành này do khoa nào quản lý? |
| `v9_det_095` | `stress` | `K50` | `compound` | 0 | Em hỏi hai ý riêng. Thứ nhất: danh bạ K50 ghi số điện thoại của Phòng Công nghệ Thông tin là gì? Thứ hai: sinh viên K50 học ngành Sư phạm tiếng Pháp thì ngành này do khoa nào quản lý? |
| `v9_det_096` | `stress` | `K48-K49` | `compound` | 0 | Em hỏi hai ý riêng. Thứ nhất: ở K48-K49, nếu cần tổ chức khám sức khỏe đầu khoá học cho tân sinh viên thì em liên hệ đơn vị nào? Thứ hai: điều kiện học bổng K48-K49 ở tiêu chí học tập, rèn luyện và kỷ luật yêu cầu gì? |
| `v9_det_097` | `stress` | `K51` | `compound` | 1 | Em hỏi ba ý riêng. Thứ nhất: 58 điểm rèn luyện ở K51 được xếp loại gì? Thứ hai: danh bạ K51 ghi website của Khoa Tiếng Hàn Quốc là gì? Thứ ba: ở K51, nếu cần tổ chức tuyển sinh các hệ thì em liên hệ đơn vị nào? |
| `v9_det_098` | `stress` | `K50` | `compound` | 1 | Em hỏi ba ý riêng. Thứ nhất: danh bạ K50 ghi địa chỉ làm việc của Phòng Khảo thí và Đảm bảo chất lượng là gì? Thứ hai: sinh viên K50 học ngành Quốc tế học thì ngành này do khoa nào quản lý? Thứ ba: ở K50, đào tạo đại học cấp bằng thứ nhất theo hệ chính quy học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? |
| `v9_det_099` | `stress` | `K48-K49` | `compound` | 0 | Em hỏi ba ý riêng. Thứ nhất: điều kiện học bổng K48-K49 ở tiêu chí học tập, rèn luyện và kỷ luật yêu cầu gì? Thứ hai: danh bạ K48-K49 ghi email của Phòng Sau Đại học là gì? Thứ ba: sinh viên K48-K49 học ngành Sư phạm Tin học thì ngành này do khoa nào quản lý? |
| `v9_det_100` | `stress` | `K51` | `compound` | 1 | Em hỏi ba ý riêng. Thứ nhất: b+ trong thang điểm K51 bằng bao nhiêu điểm hệ 4? Thứ hai: danh bạ K51 ghi địa chỉ làm việc của Thư viện là gì? Thứ ba: sinh viên K51 học ngành Giáo dục Mầm non (trình độ cao đẳng và đại học) thì ngành này do khoa nào quản lý? |
| `v9_det_101` | `realistic` | `K50` | `compound` | 1 | Em hỏi ba ý riêng. Thứ nhất: danh bạ K50 ghi số điện thoại của Khoa Khoa học Giáo dục là gì? Thứ hai: ở K50, nếu cần thu học phí, lệ phí các hệ đào tạo thì em liên hệ đơn vị nào? Thứ ba: ở K50, đào tạo đại học cấp bằng thứ nhất theo hệ vừa làm vừa học học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? |
| `v9_det_102` | `realistic` | `K48-K49` | `compound` | 1 | Em hỏi ba ý riêng. Thứ nhất: danh bạ K48-K49 ghi email của Phòng Sau Đại học là gì? Thứ hai: sinh viên K48-K49 học ngành Sư phạm Tin học thì ngành này do khoa nào quản lý? Thứ ba: ở K48-K49, đào tạo liên thông trình độ đại học đối với người đã có một bằng đại học theo hệ vừa làm vừa học học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? |
| `v9_det_103` | `realistic` | `K51` | `compound` | 1 | Em hỏi hai ý riêng. Thứ nhất: sinh viên K51 hệ chính quy học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? Thứ hai: theo Điều 10 của quy chế công tác sinh viên dành cho K51, phần các hành vi sinh viên không được làm quy định những nội dung chính nào? |
| `v9_det_104` | `realistic` | `K50` | `compound` | 0 | Em hỏi hai ý riêng. Thứ nhất: công thức điểm dùng để xếp hạng học bổng kết hợp học tập và rèn luyện ra sao? Thứ hai: theo Điều 34 của quy chế công tác sinh viên dành cho K50, phần hình thức kỷ luật và nội dung vi phạm quy định những nội dung chính nào? |
| `v9_det_105` | `realistic` | `K48-K49` | `compound` | 1 | Em hỏi hai ý riêng. Thứ nhất: ở K48-K49, đào tạo liên thông từ trình độ cao đẳng lên trình độ đại học theo hệ chính quy học chuẩn bao lâu và được phép hoàn thành tối đa trong mấy năm? Thứ hai: theo Điều 6 của quy chế rèn luyện dành cho K48-K49, phần đánh giá về ý thức và kết quả tham gia các hoạt động chính trị – xã hội, văn hóa, văn nghệ, thể thao, phòng chống tệ nạn xã hội quy định những nội dung chính nào? |
| `v9_det_106` | `realistic` | `K51` | `compound` | 1 | Em hỏi hai ý riêng. Thứ nhất: em học K51; bảng ngoại ngữ quy đổi TOEIC (4 kỹ năng) sang bậc 3 và bậc 4 thế nào? Thứ hai: theo Điều 34 của quy chế công tác sinh viên dành cho K51, phần hình thức kỷ luật và nội dung vi phạm quy định những nội dung chính nào? |
| `v9_det_107` | `realistic` | `K50` | `compound` | 0 | Em hỏi hai ý riêng. Thứ nhất: danh bạ K50 ghi số điện thoại của Phòng Công nghệ Thông tin là gì? Thứ hai: theo Điều 7 của quy chế rèn luyện dành cho K50, phần đánh giá về phẩm chất công dân và quan hệ với cộng đồng quy định những nội dung chính nào? |
| `v9_det_108` | `realistic` | `K48-K49` | `compound` | 1 | Em hỏi hai ý riêng. Thứ nhất: 88 điểm rèn luyện ở K48-K49 được xếp loại gì? Thứ hai: theo Điều 21 của quy chế công tác sinh viên dành cho K48-K49, phần phòng thanh tra đào tạo quy định những nội dung chính nào? |
| `v9_det_109` | `realistic` | `K51` | `compound` | 0 | Em hỏi hai ý riêng. Thứ nhất: sinh viên K51 học ngành Công nghệ Giáo dục thì ngành này do khoa nào quản lý? Thứ hai: theo Điều 8 của quy định cố vấn học tập dành cho K51, phần đánh giá kết quả hoạt động quy định những nội dung chính nào? |
| `v9_det_110` | `realistic` | `K50` | `compound` | 0 | Em hỏi hai ý riêng. Thứ nhất: danh bạ K50 ghi địa chỉ làm việc của Phòng Khảo thí và Đảm bảo chất lượng là gì? Thứ hai: theo Điều 15 của quy chế công tác sinh viên dành cho K50, phần phòng khảo thí và đảm bảo chất lượng quy định những nội dung chính nào? |
| `v9_det_111` | `realistic` | `K48-K49` | `compound` | 0 | Em hỏi hai ý riêng. Thứ nhất: danh bạ K48-K49 ghi số điện thoại của Khoa Vật lí là gì? Thứ hai: theo Điều 4 của quy định nghiên cứu khoa học sinh viên dành cho K48-K49, phần nội dung hoạt động nghiên cứu khoa học của sinh viên quy định những nội dung chính nào? |
| `v9_det_112` | `realistic` | `K51` | `compound` | 0 | Em hỏi hai ý riêng. Thứ nhất: danh bạ K51 ghi website của Khoa Tiếng Hàn Quốc là gì? Thứ hai: theo Điều 6 của quy chế công tác sinh viên dành cho K51, phần hỗ trợ và dịch vụ sinh viên quy định những nội dung chính nào? |
| `v9_det_113` | `stress` | `K51` | `missing_or_ambiguous` | 0 | Em thuộc K50 nhưng lại nhớ năm nhập học là 2025; nên dùng thông tin khóa nào để tra? |
| `v9_det_114` | `stress` | `K51` | `missing_or_ambiguous` | 0 | Em muốn quy đổi TOEIC bốn kỹ năng nhưng chưa có điểm Nói và Viết. |
| `v9_det_115` | `stress` | `K51` | `missing_or_ambiguous` | 0 | Cho em xin địa chỉ của khoa đó với. |
| `v9_det_116` | `stress` | `K51` | `missing_or_ambiguous` | 0 | Em muốn biết mức này được cấp theo tháng hay theo học kỳ, nhưng chưa nói loại hỗ trợ. |
| `v9_det_117` | `stress` | `K51` | `missing_or_ambiguous` | 0 | Đổi điểm này sang thang còn lại giúp em, em chưa gửi điểm. |
| `v9_det_118` | `stress` | `K51` | `missing_or_ambiguous` | 0 | Quy định này của K50 hay K51 vậy? Em chưa xác định được khóa. |
| `v9_det_119` | `stress` | `K51` | `missing_or_ambiguous` | 0 | Cho em thông tin liên hệ của hai phòng vừa nhắc tới. |
| `v9_det_120` | `stress` | `K51` | `missing_or_ambiguous` | 0 | Chứng chỉ ngoại ngữ này còn hiệu lực không? Em không nhớ loại chứng chỉ và ngày cấp. |
| `v9_det_121` | `stress` | `K51` | `missing_or_ambiguous` | 0 | Em cần nội dung Điều 16 nhưng chưa rõ đang nói đến văn bản nào. |
| `v9_det_122` | `stress` | `K51` | `missing_or_ambiguous` | 0 | So sánh thời gian đào tạo của hai khóa giúp em, nhưng em chưa nêu hai khóa. |
| `v9_det_123` | `stress` | `K51` | `missing_or_ambiguous` | 0 | Em cần hỏi bốn việc riêng: GPA, danh bạ khoa, danh sách ngành và thủ tục nghỉ học. |
| `v9_det_124` | `stress` | `K51` | `missing_or_ambiguous` | 0 | Tra giúp em bảng IELTS, email Thư viện, khoa quản lý ngành Hóa và quy định chuyển trường. |
| `v9_det_125` | `realistic` | `K51` | `unsupported_in_domain` | 0 | Hồ sơ miễn học phần ngoại ngữ của riêng em đang được ai xử lý? |
| `v9_det_126` | `realistic` | `K51` | `unsupported_in_domain` | 0 | Khoản học bổng cá nhân của em sẽ vào tài khoản lúc mấy giờ hôm nay? |
| `v9_det_127` | `realistic` | `K51` | `unsupported_in_domain` | 0 | Lớp học phần sáng mai còn bao nhiêu chỗ trống theo thời gian thực? |
| `v9_det_128` | `realistic` | `K51` | `unsupported_in_domain` | 0 | Bài thi của em hiện được giảng viên nào chấm? |
| `v9_det_129` | `realistic` | `K51` | `unsupported_in_domain` | 0 | Ca trực tối nay ở Trạm Y tế có những ai? |
| `v9_det_130` | `realistic` | `K51` | `unsupported_in_domain` | 0 | Ký túc xá đang còn chính xác bao nhiêu giường để đăng ký ngay? |
| `v9_det_131` | `realistic` | `K51` | `unsupported_in_domain` | 0 | Mã giao dịch học phí mới nhất trong tài khoản của em là gì? |
| `v9_det_132` | `realistic` | `K51` | `unsupported_in_domain` | 0 | Cho em danh sách tên sinh viên đang bị cảnh cáo trong lớp. |
| `v9_det_133` | `realistic` | `general` | `out_of_domain` | 0 | Viết giúp mình một hàm Python sắp xếp danh sách. |
| `v9_det_134` | `realistic` | `general` | `out_of_domain` | 0 | Gợi ý món ăn cuối tuần cho bốn người. |
| `v9_det_135` | `realistic` | `general` | `out_of_domain` | 0 | Tóm tắt nội dung bộ phim Interstellar. |
| `v9_det_136` | `realistic` | `general` | `out_of_domain` | 0 | Xe máy bị hết bình giữa đường thì xử lý thế nào? |
| `v9_det_137` | `realistic` | `general` | `out_of_domain` | 0 | Giá Bitcoin hôm nay tăng hay giảm? |
| `v9_det_138` | `realistic` | `general` | `out_of_domain` | 0 | Giải phương trình 2x bình cộng 7x trừ 4 bằng 0. |
| `v9_det_139` | `realistic` | `general` | `out_of_domain` | 0 | Viết caption quảng cáo cho quán cà phê. |
| `v9_det_140` | `realistic` | `general` | `out_of_domain` | 0 | Tạo bảng và index trong MySQL như thế nào? |
