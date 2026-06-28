import type { Cohort } from '../utils/gradeScale';

export type FaqCohort = Cohort | 'all';

export type FaqItem = {
  id: string;
  cohort: FaqCohort;
  category: string;
  question: string;
  shortAnswer: string;
  aiPrompt: string;
};

export const FAQ_ITEMS: FaqItem[] = [
  {
    id: 'pass-score-k48',
    cohort: 'K48-K49',
    category: 'Điểm số',
    question: 'Mấy điểm thì qua môn?',
    shortAnswer: 'K48-K49: học phần đạt từ D, tức từ 4.0/10 trở lên. F+ và F là không đạt.',
    aiPrompt: 'Sinh viên K48-K49 mấy điểm thì qua môn? Liệt kê ngắn gọn bảng Đạt/Không đạt và trích nguồn.',
  },
  {
    id: 'pass-score-k50',
    cohort: 'K50-K51',
    category: 'Điểm số',
    question: 'K50-K51 mấy điểm thì qua môn?',
    shortAnswer: 'K50-K51: môn chung/nhóm nền tảng đạt từ 4.0; các học phần còn lại đạt từ 5.5. Cần xác định đúng loại học phần trước.',
    aiPrompt: 'Sinh viên K50-K51 mấy điểm thì qua môn? Phân biệt môn chung/nhóm nền tảng và các học phần còn lại, liệt kê ngắn gọn bảng Đạt/Không đạt và trích nguồn.',
  },
  {
    id: 'd-plus-k50',
    cohort: 'K50-K51',
    category: 'Điểm số',
    question: 'Điểm D hoặc D+ của K50-K51 có qua môn không?',
    shortAnswer: 'Môn chung/nhóm nền tảng: D và D+ đạt. Các học phần còn lại: D và D+ không đạt dù vẫn có điểm hệ 4 tương ứng.',
    aiPrompt: 'Với sinh viên K50-K51, điểm D hoặc D+ có được xem là đạt học phần không? Phân biệt theo nhóm học phần và trích nguồn.',
  },
  {
    id: 'grade-4-conversion',
    cohort: 'all',
    category: 'Điểm số',
    question: 'Điểm chữ đổi sang hệ 4 như thế nào?',
    shortAnswer: 'A=4.0, B+=3.5, B=3.0, C+=2.5, C=2.0, D+=1.5, D=1.0, F+=0.5, F=0.0.',
    aiPrompt: 'Bảng quy đổi điểm chữ sang thang điểm 4 trong sổ tay sinh viên HCMUE là gì? Trả lời dạng bảng ngắn và trích nguồn.',
  },
  {
    id: 'conduct-score',
    cohort: 'all',
    category: 'Rèn luyện',
    question: 'Điểm rèn luyện bao nhiêu là tốt/xuất sắc?',
    shortAnswer: '90-100: Xuất sắc; 80-dưới 90: Tốt; 65-dưới 80: Khá; 50-dưới 65: Trung bình; 35-dưới 50: Yếu; dưới 35: Kém.',
    aiPrompt: 'Bảng phân loại kết quả rèn luyện HCMUE theo thang 100 là gì? Trả lời ngắn gọn và trích nguồn.',
  },
  {
    id: 'scholarship-condition',
    cohort: 'all',
    category: 'Học bổng',
    question: 'Muốn xét học bổng khuyến khích học tập cần mức nào?',
    shortAnswer: 'Mốc nhanh: loại Khá cần điểm học tập 2.50-3.19 và rèn luyện >=70; Giỏi cần 3.20-3.59 và rèn luyện >=80; Xuất sắc cần 3.60-4.0 và rèn luyện >=90.',
    aiPrompt: 'Điều kiện xét học bổng khuyến khích học tập HCMUE gồm những mức nào? Nêu điểm học tập, điểm rèn luyện, điểm học bổng nếu có và trích nguồn.',
  },
  {
    id: 'scholarship-formula',
    cohort: 'all',
    category: 'Học bổng',
    question: 'Điểm học bổng tính như thế nào?',
    shortAnswer: 'Công thức đang dùng trong công cụ: (điểm học tập x 80 + điểm rèn luyện / 25 x 20) / 100. Điểm rèn luyện nhập theo thang 100.',
    aiPrompt: 'Công thức tính điểm học bổng khuyến khích học tập HCMUE là gì? Giải thích các biến và trích nguồn.',
  },
  {
    id: 'retake-improve',
    cohort: 'all',
    category: 'Học lại',
    question: 'Rớt môn hoặc muốn cải thiện điểm thì làm sao?',
    shortAnswer: 'Không đạt học phần thì phải đăng ký học lại theo CTĐT. Nếu học phần đã đạt, sinh viên được đăng ký học lại chính học phần đó để cải thiện điểm nếu lớp được mở và đáp ứng điều kiện đăng ký.',
    aiPrompt: 'Sinh viên HCMUE rớt môn hoặc muốn học cải thiện điểm thì xử lý thế nào? Nêu quy định học lại/cải thiện và trích nguồn.',
  },
  {
    id: 'retake-final-grade',
    cohort: 'K48-K49',
    category: 'Học lại',
    question: 'Học cải thiện thì lấy điểm nào?',
    shortAnswer: 'Theo quy định cũ cho K48-K49, điểm lần học cuối là điểm chính thức của học phần.',
    aiPrompt: 'Với sinh viên K48-K49, học lại hoặc học cải thiện thì điểm chính thức của học phần được lấy như thế nào? Trích nguồn.',
  },
  {
    id: 'retake-final-grade-k50',
    cohort: 'K50-K51',
    category: 'Học lại',
    question: 'K50-K51 học cải thiện thì lấy điểm nào?',
    shortAnswer: 'Với quy định áp dụng từ khóa tuyển sinh 2025 trở về sau, điểm đánh giá cao nhất trong những điểm đã đạt của học phần là điểm chính thức.',
    aiPrompt: 'Với sinh viên K50-K51, học cải thiện thì điểm chính thức của học phần được lấy như thế nào? Nêu quy định sửa đổi áp dụng từ khóa 2025 và trích nguồn.',
  },
  {
    id: 'warning-dismissal',
    cohort: 'all',
    category: 'Cảnh báo học vụ',
    question: 'Khi nào bị cảnh báo học tập hoặc buộc thôi học?',
    shortAnswer: 'Cảnh báo nếu tín chỉ không đạt trong học kỳ vượt 50% khối lượng đăng ký hoặc nợ từ đầu khóa vượt 24 tín chỉ; cũng có ngưỡng GPA theo năm học. Buộc thôi học nếu bị cảnh báo 3 lần liên tiếp, lần thứ 4 từ đầu khóa, hoặc quá thời gian tối đa.',
    aiPrompt: 'Điều kiện cảnh báo học tập và buộc thôi học của sinh viên chính quy HCMUE là gì? Trả lời theo checklist và trích nguồn.',
  },
  {
    id: 'degree-downgrade-risk',
    cohort: 'all',
    category: 'Tốt nghiệp',
    question: 'Học lại bao nhiêu thì có nguy cơ hạ bằng?',
    shortAnswer: 'Hạng tốt nghiệp loại Xuất sắc/Giỏi sẽ bị giảm một mức nếu khối lượng học phần phải học lại vượt quá 5% tổng số tín chỉ toàn chương trình hoặc sinh viên bị kỷ luật từ mức cảnh cáo trở lên.',
    aiPrompt: 'Quy định về nguy cơ hạ mức bằng tốt nghiệp do học lại ở HCMUE là gì? Nêu ngưỡng 5% nếu có trong nguồn và trích nguồn.',
  },
  {
    id: 'exam-review',
    cohort: 'all',
    category: 'Thi cử',
    question: 'Điểm nào được phúc khảo?',
    shortAnswer: 'Điểm đánh giá quá trình không được phúc khảo. Điểm thi kết thúc học phần có thể được phúc khảo.',
    aiPrompt: 'Điểm quá trình và điểm thi kết thúc học phần ở HCMUE có được phúc khảo không? Trả lời ngắn gọn và trích nguồn.',
  },
  {
    id: 'temporary-leave',
    cohort: 'all',
    category: 'Tạm nghỉ',
    question: 'Muốn tạm nghỉ học cần đơn gì?',
    shortAnswer: 'Dùng Đơn xin tạm nghỉ học. Đơn gửi Hiệu trưởng, Trưởng khoa và Phòng CTCT&HSSV; có thông tin MSSV, lớp, khoa, khóa, email, điểm TBC tích lũy, thời gian và lý do xin tạm nghỉ.',
    aiPrompt: 'Muốn tạm nghỉ học ở HCMUE cần mẫu đơn nào và điền những thông tin gì? Trả lời theo biểu mẫu và trích nguồn.',
  },
  {
    id: 'return-after-leave',
    cohort: 'all',
    category: 'Tạm nghỉ',
    question: 'Hết tạm nghỉ muốn quay lại học thì dùng đơn gì?',
    shortAnswer: 'Dùng Đơn xin học lại. Đơn ghi thời gian đã tạm nghỉ, số quyết định cho tạm nghỉ và đề nghị được trở lại học; sinh viên nên liên hệ CVHT để chọn CTĐT phù hợp tiến độ.',
    aiPrompt: 'Sinh viên HCMUE hết thời gian tạm nghỉ muốn quay lại học thì dùng đơn gì và cần thông tin nào? Trích nguồn.',
  },
  {
    id: 'student-confirmation',
    cohort: 'all',
    category: 'Giấy tờ',
    question: 'Xin giấy xác nhận sinh viên/vay vốn ở đâu?',
    shortAnswer: 'Giấy xác nhận sinh viên thuộc nhóm giấy tờ do Phòng CTCT&HSSV xử lý. Mẫu giấy xác nhận vay vốn có các thông tin: họ tên, MSSV/lớp/khoa/khóa, thời gian học, học phí, diện miễn/giảm nếu có.',
    aiPrompt: 'Quy trình và biểu mẫu giấy xác nhận sinh viên/vay vốn của HCMUE gồm những thông tin gì, liên hệ phòng nào? Trích nguồn.',
  },
  {
    id: 'tuition-exemption',
    cohort: 'all',
    category: 'Học phí',
    question: 'Miễn giảm học phí liên hệ ai?',
    shortAnswer: 'Liên hệ Phòng CTCT&HSSV: hopthusinhvien@hcmue.edu.vn, số nội bộ 127/128/143. Riêng học phí và tài chính liên hệ Phòng Kế hoạch - Tài chính: phongkhtc@hcmue.edu.vn hoặc hocphi@hcmue.edu.vn.',
    aiPrompt: 'Muốn hỏi miễn giảm học phí hoặc học phí ở HCMUE thì liên hệ phòng nào, email/số máy nào? Trích nguồn.',
  },
  {
    id: 'dormitory',
    cohort: 'all',
    category: 'KTX',
    question: 'Đăng ký Ký túc xá cần hồ sơ gì?',
    shortAnswer: 'Hồ sơ nội trú tối thiểu gồm: đơn xin ở nội trú, giấy tờ nhập học/thẻ sinh viên, biên nhận hồ sơ nhập học, giấy tờ diện ưu tiên nếu có, hợp đồng nội trú, bản khai nhân khẩu, CCCD bản sao kèm bản chính đối chiếu và 03 ảnh 2x3.',
    aiPrompt: 'Đăng ký Ký túc xá HCMUE cần hồ sơ gì và quy trình xét gồm những bước nào? Trích nguồn.',
  },
  {
    id: 'dormitory-contact',
    cohort: 'all',
    category: 'KTX',
    question: 'Ký túc xá ở đâu, liên hệ thế nào?',
    shortAnswer: 'KTX HCMUE: 351A Lạc Long Quân, phường Hòa Bình, TP.HCM. Điện thoại: (028) 38650758. Email: ktx@hcmue.edu.vn.',
    aiPrompt: 'Thông tin liên hệ Ký túc xá HCMUE là gì? Nêu địa chỉ, số điện thoại, email và trích nguồn.',
  },
  {
    id: 'department-contact',
    cohort: 'all',
    category: 'Liên hệ',
    question: 'Có vấn đề học vụ thì liên hệ phòng nào?',
    shortAnswer: 'CTĐT, học phần, tốt nghiệp: Phòng Đào tạo. Tạm nghỉ, học lại, miễn giảm học phí, học bổng, giấy xác nhận: Phòng CTCT&HSSV. Điểm số/thi cử/phúc khảo: Phòng Khảo thí & ĐBCL.',
    aiPrompt: 'Sinh viên HCMUE cần liên hệ phòng ban nào cho các vấn đề học vụ, học bổng, giấy xác nhận, điểm thi? Nêu phòng, email/số máy nếu có và trích nguồn.',
  },
  {
    id: 'account-contact',
    cohort: 'all',
    category: 'Liên hệ',
    question: 'Lỗi tài khoản hệ thống thì liên hệ ai?',
    shortAnswer: 'Liên hệ Phòng Công nghệ Thông tin: phongcntt@hcmue.edu.vn, số máy nội bộ 166. Phòng này hỗ trợ tài khoản sinh viên trên hệ thống phần mềm quản lý đào tạo.',
    aiPrompt: 'Sinh viên HCMUE bị lỗi tài khoản hệ thống phần mềm quản lý đào tạo thì liên hệ đơn vị nào? Trích nguồn.',
  },
];

export function getFaqItemsForCohort(cohort: Cohort): FaqItem[] {
  return FAQ_ITEMS.filter((item) => item.cohort === 'all' || item.cohort === cohort);
}

export function getFaqCategoriesForCohort(cohort: Cohort): string[] {
  return Array.from(new Set(getFaqItemsForCohort(cohort).map((item) => item.category)));
}
