/**
 * Nội dung trang "Kinh nghiệm học bổng".
 *
 * Cách thay nội dung thật:
 * 1. Sửa chữ trong `hero`, `checklist` và `tips` ngay trong file này (không cần sửa component).
 * 2. Khi mọi thứ đã là chia sẻ thật, đặt `isSample` thành `false` để ẩn nhãn "NỘI DUNG MẪU".
 * 3. Ảnh minh chứng đặt trong `public/experience/`: định dạng WebP, rộng khoảng 1200px, và phải
 *    che sẵn họ tên, MSSV, chữ ký, mã vạch trước khi lưu. Tham chiếu bằng `/experience/ten-anh.webp`.
 * 4. Thứ tự trong `tips` là thứ tự hiển thị; màu giấy note tự đổi theo vị trí.
 */

export type ExperienceTab = 'scholarship' | 'target-gpa' | 'course-target';

export interface ExperienceTopic {
  id: string;
  label: string;
  /** Colour of the dot next to the topic label. */
  color: string;
}

export interface ExperienceTip {
  id: string;
  /** Id of an entry in `topics`. */
  topic: string;
  quote: string;
  body: string;
  author: { name: string; meta: string; badge: string };
  tool?: { label: string; tab: ExperienceTab };
  proof?: { src: string; caption: string };
}

export interface ExperienceContent {
  isSample: boolean;
  hero: { title: string; lead: string; stats: { value: string; label: string }[] };
  topics: ExperienceTopic[];
  checklist: {
    title: string;
    items: string[];
    source: string;
    link: { label: string; tab: ExperienceTab };
  };
  tips: ExperienceTip[];
}

export const EXPERIENCE: ExperienceContent = {
  isSample: true,
  hero: {
    title: 'Từ nhóm đã giữ HB Xuất sắc 4 kỳ liên tiếp',
    lead: 'Không có bí quyết thần kỳ: hiểu rõ điều kiện, giữ chắc điểm quá trình và học đều cả kỳ.',
    stats: [
      { value: '4', label: 'kỳ HB Xuất sắc' },
      { value: '4.0', label: 'GPA × 3 kỳ' },
      { value: '90+', label: 'Rèn luyện' },
    ],
  },
  topics: [
    { id: 'dieukien', label: 'Điều kiện', color: '#2563eb' },
    { id: 'hocphan', label: 'Đăng ký học phần', color: '#7c3aed' },
    { id: 'cotdiem', label: 'Cột điểm & thi', color: '#db2777' },
    { id: 'renluyen', label: 'Rèn luyện', color: '#059669' },
    { id: 'nhiphoc', label: 'Nhịp học', color: '#d97706' },
  ],
  checklist: {
    title: 'Điều kiện HB Xuất sắc trong một học kỳ',
    items: [
      'Từ 15 tín chỉ trong học kỳ, tất cả đều đạt',
      'GPA học kỳ từ 3,6',
      'Điểm rèn luyện từ 90',
      'Điểm xét học bổng từ 3,6',
      'Không bị kỷ luật từ mức khiển trách',
    ],
    source: 'Quy chế công tác sinh viên, Điều 27',
    link: { label: 'Tính điểm học bổng', tab: 'scholarship' },
  },
  tips: [
    {
      id: 'tip-1',
      topic: 'dieukien',
      quote: 'Mình coi học bổng là bài toán có điều kiện, không phải chuyện may mắn.',
      body: 'Xuất sắc cần đủ cả bốn: điểm xét từ 3,6, GPA học kỳ từ 3,6, rèn luyện từ 90 và không bị kỷ luật. Thiếu một điều là xuống mức dưới, nên mình kiểm tra cả bốn ngay từ giữa kỳ.',
      author: { name: 'Thành viên A', meta: 'K48 · Sư phạm Toán', badge: '4 kỳ HB Xuất sắc' },
      tool: { label: 'Tính điểm học bổng', tab: 'scholarship' },
      proof: { src: '/experience/sample-thong-bao.svg', caption: 'Thông báo HB Xuất sắc HK1 2025–2026' },
    },
    {
      id: 'tip-2',
      topic: 'hocphan',
      quote: 'Đăng ký vừa đủ 15–17 tín chỉ, đừng ôm 22 tín chỉ cho “nhanh ra trường”.',
      body: 'Học bổng chỉ xét khi học kỳ có từ 15 tín chỉ trở lên và tất cả đều đạt. Mình chọn 15–17 tín chỉ và trộn môn nặng với môn nhẹ, để môn nào cũng có thời gian ôn tới mức A.',
      author: { name: 'Thành viên B', meta: 'K48 · Ngôn ngữ Anh', badge: 'GPA 4.0 × 3 kỳ' },
      tool: { label: 'Mục tiêu GPA', tab: 'target-gpa' },
    },
    {
      id: 'tip-3',
      topic: 'cotdiem',
      quote: 'Điểm quá trình là phần “dễ ăn” nhất, mất ở đó rất phí.',
      body: 'Trước mỗi môn mình đọc đề cương để biết trọng số từng cột. Đi học đủ, nộp bài đúng hạn và làm kỹ bài giữa kỳ, nên lúc vào thi chỉ cần đạt mức vừa phải là đã chắc A.',
      author: { name: 'Thành viên C', meta: 'K49 · Công nghệ Thông tin', badge: 'GPA 4.0 × 3 kỳ' },
      tool: { label: 'Mục tiêu môn học', tab: 'course-target' },
    },
    {
      id: 'tip-4',
      topic: 'cotdiem',
      quote: 'Ôn bằng cách tự kiểm tra, không phải đọc lại.',
      body: 'Mỗi chương mình gấp vở lại và viết ra mọi thứ còn nhớ, rồi mới mở ra so. Chỗ nào quên thì làm thẻ nhớ, ôn lại sau 1 ngày, 3 ngày, 1 tuần.',
      author: { name: 'Thành viên A', meta: 'K48 · Sư phạm Toán', badge: '4 kỳ HB Xuất sắc' },
    },
    {
      id: 'tip-5',
      topic: 'renluyen',
      quote: '90 điểm rèn luyện không tự đến vào cuối kỳ.',
      body: 'Mình ghi lại mọi hoạt động đã tham gia kèm minh chứng ngay khi xong, gồm sinh hoạt lớp, tình nguyện, hội thảo. Đến lúc tự đánh giá thì chỉ cần mở danh sách ra điền.',
      author: { name: 'Thành viên D', meta: 'K49 · Giáo dục Tiểu học', badge: 'ĐRL Xuất sắc' },
      proof: { src: '/experience/sample-giay-khen.svg', caption: 'Giấy khen sinh viên 5 tốt cấp trường' },
    },
    {
      id: 'tip-6',
      topic: 'nhiphoc',
      quote: 'Tuần thi không phải lúc bắt đầu học.',
      body: 'Mỗi chủ nhật mình dành 30 phút xem lịch tuần tới: deadline nào, buổi nào có kiểm tra. Môn khó được ôn rải đều từ tuần 3, nên tuần thi chủ yếu là làm đề.',
      author: { name: 'Thành viên B', meta: 'K48 · Ngôn ngữ Anh', badge: 'GPA 4.0 × 3 kỳ' },
    },
  ],
};
