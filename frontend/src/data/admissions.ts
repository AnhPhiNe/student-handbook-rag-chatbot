export type AdmissionMethod = 'THPT' | 'COMBINED' | 'PRIORITY_DIRECT';
export type AdmissionRegime = 'pre_2025' | 'post_2025';
export type AdmissionCampus = 'TP.HCM';
export type AdmissionSourceKind = 'html' | 'api';

export interface AdmissionCutoff {
  id: string;
  year: number;
  programName: string;
  faculty: string;
  admissionMethod: AdmissionMethod;
  admissionMethodLabel: string;
  subjectGroup: string;
  cutoffScore: number;
  scoreScale: number;
  admissionRegime: AdmissionRegime;
  campus: AdmissionCampus;
  note?: string;
  sourceLabel: string;
  sourceUrl: string;
  sourceKind: AdmissionSourceKind;
  verified: boolean;
}

export interface AdmissionPlan {
  year: number;
  programName: string;
  programLabel: string;
  admissionCode: string;
  majorCode: string;
  quota: number;
  campus: AdmissionCampus;
  examMethodLabel: string;
  examSubjectGroups: Array<{
    code: string;
    subjects: string;
  }>;
  sourcePage: number;
  sourceUrl: string;
}

export const ADMISSION_SOURCE_URL =
  'https://diemthi.tuyensinh247.com/diem-chuan/dai-hoc-su-pham-tphcm-SPS.html';

export const ADMISSION_PLAN_SOURCE_URL =
  'https://drive.google.com/file/d/1JWc0ctdH1HUthfrurouF9Wne8rGu9kLu/view';

export const ADMISSION_SOURCE_URLS_BY_YEAR: Record<number, string> = {
  2025: ADMISSION_SOURCE_URL,
  2024: 'https://vnexpress.net/diem-chuan-dai-hoc-su-pham-tp-hcm-nam-2024-4782845.html',
  2023: 'https://thuvienphapluat.vn/chinh-sach-phap-luat-moi/vn/ho-tro-phap-luat/tu-van-phap-luat/67437/diem-chuan-truong-dai-hoc-su-pham-tphcm-nam-2023',
  2022: 'https://huongnghiepviet.com/tuyen-sinh/diem-chuan/diem-chuan-nam-2022-sps-truong-dai-hoc-su-pham-tp-hcm',
  2021: 'https://vnexpress.net/dai-hoc-su-pham-tp-hcm-lay-diem-chuan-cao-nhat-27-15-4357165.html',
};

export const ADMISSION_DATA_NOTE =
  'Bản beta đang có dữ liệu điểm chuẩn THPT 2021-2025 và kế hoạch tuyển sinh 2026. Dữ liệu 2025 được ưu tiên khi ước lượng điểm chuẩn vì chương trình GDPT 2018 làm thay đổi cấu trúc thi; tổ hợp và chỉ tiêu nên đối chiếu theo kế hoạch 2026.';

export const ADMISSION_METHOD_LABELS: Record<AdmissionMethod, string> = {
  THPT: 'Điểm thi THPT',
  COMBINED: 'Xét tuyển kết hợp',
  PRIORITY_DIRECT: 'Ưu tiên xét tuyển / xét tuyển thẳng',
};

let recordIndex = 0;

function getAdmissionSourceUrl(year: number): string {
  return ADMISSION_SOURCE_URLS_BY_YEAR[year] ?? ADMISSION_SOURCE_URL;
}

function getAdmissionSourceKind(year: number): AdmissionSourceKind {
  return ADMISSION_SOURCE_URLS_BY_YEAR[year] ? 'html' : 'api';
}

function thpt2025(
  programName: string,
  faculty: string,
  subjectGroup: string,
  cutoffScore: number,
  note?: string,
  campus: AdmissionCampus = 'TP.HCM',
): AdmissionCutoff {
  recordIndex += 1;
  return {
    id: `hcmue-2025-thpt-${recordIndex}`,
    year: 2025,
    programName,
    faculty,
    admissionMethod: 'THPT',
    admissionMethodLabel: ADMISSION_METHOD_LABELS.THPT,
    subjectGroup,
    cutoffScore,
    scoreScale: 30,
    admissionRegime: 'post_2025',
    campus,
    note,
    sourceLabel: 'Điểm chuẩn HCMUE 2025 - phương thức điểm thi THPT',
    sourceUrl: getAdmissionSourceUrl(2025),
    sourceKind: getAdmissionSourceKind(2025),
    verified: true,
  };
}

function historicalThpt(
  year: number,
  programName: string,
  faculty: string,
  subjectGroup: string,
  cutoffScore: number,
  note?: string,
  campus: AdmissionCampus = 'TP.HCM',
): AdmissionCutoff {
  recordIndex += 1;
  return {
    id: `hcmue-${year}-thpt-${recordIndex}`,
    year,
    programName,
    faculty,
    admissionMethod: 'THPT',
    admissionMethodLabel: ADMISSION_METHOD_LABELS.THPT,
    subjectGroup,
    cutoffScore,
    scoreScale: 30,
    admissionRegime: year >= 2025 ? 'post_2025' : 'pre_2025',
    campus,
    note,
    sourceLabel: `Điểm chuẩn HCMUE ${year} - phương thức điểm thi THPT`,
    sourceUrl: getAdmissionSourceUrl(year),
    sourceKind: getAdmissionSourceKind(year),
    verified: true,
  };
}

function plan2026(
  programName: string,
  programLabel: string,
  admissionCode: string,
  majorCode: string,
  quota: number,
  sourcePage: number,
  examMethodLabel: string,
  examSubjectGroups: AdmissionPlan['examSubjectGroups'],
): AdmissionPlan {
  return {
    year: 2026,
    programName,
    programLabel,
    admissionCode,
    majorCode,
    quota,
    campus: 'TP.HCM',
    examMethodLabel,
    examSubjectGroups,
    sourcePage,
    sourceUrl: ADMISSION_PLAN_SOURCE_URL,
  };
}

export const ADMISSION_PLANS_2026: AdmissionPlan[] = [
  plan2026('Giáo dục học', 'Giáo dục học', '7140101', '7140101', 80, 1, 'THPT', [{ code: 'A00', subjects: 'Toán, Vật lí, Hóa học' }, { code: 'C03', subjects: 'Ngữ văn, Toán, Lịch sử' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'X01', subjects: 'Toán, Ngữ văn, GDKTPL' }]),
  plan2026('Công nghệ giáo dục', 'Công nghệ giáo dục', '7140103', '7140103', 50, 2, 'THPT', [{ code: 'A01', subjects: 'Toán, Vật lí, Tiếng Anh' }, { code: 'B08', subjects: 'Toán, Sinh học, Tiếng Anh' }, { code: 'D07', subjects: 'Toán, Hóa học, Tiếng Anh' }, { code: 'X26', subjects: 'Toán, Tin học, Tiếng Anh' }]),
  plan2026('Quản lý giáo dục', 'Quản lý giáo dục', '7140114', '7140114', 80, 3, 'THPT', [{ code: 'A00', subjects: 'Toán, Vật lí, Hóa học' }, { code: 'C03', subjects: 'Ngữ văn, Toán, Lịch sử' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'X01', subjects: 'Toán, Ngữ văn, GDKTPL' }]),
  plan2026('Giáo dục Mầm non', 'Giáo dục Mầm non (đào tạo tại trụ sở chính)', '7140201', '7140201', 440, 4, 'THPT kết hợp thi tuyển năng khiếu', [{ code: 'M02', subjects: 'Toán, Năng khiếu GDMN 1, Năng khiếu GDMN 2' }, { code: 'M03', subjects: 'Ngữ văn, Năng khiếu GDMN 1, Năng khiếu GDMN 2' }]),
  plan2026('Giáo dục Tiểu học', 'Giáo dục Tiểu học (đào tạo tại trụ sở chính)', '7140202', '7140202', 265, 4, 'THPT', [{ code: 'A00', subjects: 'Toán, Vật lí, Hóa học' }, { code: 'A01', subjects: 'Toán, Vật lí, Tiếng Anh' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }]),
  plan2026('Giáo dục Tiểu học (dạy bằng song ngữ Việt - Anh)', 'Giáo dục Tiểu học (dạy bằng song ngữ Việt - Anh)', '7140202SN', '7140202SN', 35, 5, 'THPT', [{ code: 'A00', subjects: 'Toán, Vật lí, Hóa học' }, { code: 'A01', subjects: 'Toán, Vật lí, Tiếng Anh' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }]),
  plan2026('Giáo dục Đặc biệt', 'Giáo dục Đặc biệt', '7140203', '7140203', 50, 6, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'C03', subjects: 'Ngữ văn, Toán, Lịch sử' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'X70', subjects: 'Ngữ văn, Lịch sử, GDKTPL' }, { code: 'C19', subjects: 'Ngữ văn, Lịch sử, GDCD' }]),
  plan2026('Giáo dục Công dân', 'Giáo dục Công dân', '7140204', '7140204', 40, 7, 'THPT', [{ code: 'X01', subjects: 'Toán, Ngữ văn, GDKTPL' }, { code: 'X70', subjects: 'Ngữ văn, Lịch sử, GDKTPL' }, { code: 'X78', subjects: 'Ngữ văn, GDKTPL, Tiếng Anh' }, { code: 'C14', subjects: 'Ngữ văn, Toán, GDCD' }, { code: 'C19', subjects: 'Ngữ văn, Lịch sử, GDCD' }, { code: 'D66', subjects: 'Ngữ văn, GDCD, Tiếng Anh' }]),
  plan2026('Giáo dục Chính trị', 'Giáo dục Chính trị', '7140205', '7140205', 20, 8, 'THPT', [{ code: 'X01', subjects: 'Toán, Ngữ văn, GDKTPL' }, { code: 'X70', subjects: 'Ngữ văn, Lịch sử, GDKTPL' }, { code: 'X78', subjects: 'Ngữ văn, GDKTPL, Tiếng Anh' }, { code: 'C14', subjects: 'Ngữ văn, Toán, GDCD' }, { code: 'C19', subjects: 'Ngữ văn, Lịch sử, GDCD' }, { code: 'D66', subjects: 'Ngữ văn, GDCD, Tiếng Anh' }]),
  plan2026('Giáo dục Thể chất', 'Giáo dục Thể chất (đào tạo tại trụ sở chính)', '7140206', '7140206', 80, 9, 'THPT kết hợp thi tuyển năng khiếu', [{ code: 'M08', subjects: 'Ngữ Văn - NK TDTT1 - NK TDTT2' }, { code: 'T01', subjects: 'Toán - NK TDTT1 - NK TDTT2' }]),
  plan2026('Giáo dục Quốc phòng - An ninh', 'Giáo dục Quốc phòng - An ninh (đào tạo tại trụ sở chính)', '7140208', '7140208', 40, 10, 'THPT kết hợp thi tuyển năng khiếu', [{ code: 'Q01', subjects: 'Toán, NK TDTT1, NK GDQP-AN' }, { code: 'Q02', subjects: 'Ngữ văn, NK TDTT1, NK GDQP-AN' }]),
  plan2026('Sư phạm Toán học', 'Sư phạm Toán học (đào tạo tại trụ sở chính)', '7140209', '7140209', 140, 10, 'THPT', [{ code: 'A00', subjects: 'Toán, Vật lí, Hóa học' }, { code: 'A01', subjects: 'Toán, Vật lí, Tiếng Anh' }, { code: 'X06', subjects: 'Toán, Vật lí, Tin học' }]),
  plan2026('Sư phạm Tin học', 'Sư phạm Tin học', '7140210', '7140210', 100, 11, 'THPT', [{ code: 'A01', subjects: 'Toán, Vật lí, Tiếng Anh' }, { code: 'B08', subjects: 'Toán, Sinh học, Tiếng Anh' }, { code: 'D07', subjects: 'Toán, Hóa học, Tiếng Anh' }, { code: 'X26', subjects: 'Toán, Tin học, Tiếng Anh' }]),
  plan2026('Sư phạm Vật lý', 'Sư phạm Vật lý', '7140211', '7140211', 32, 12, 'THPT', [{ code: 'A00', subjects: 'Toán, Vật lí, Hóa học' }, { code: 'A01', subjects: 'Toán, Vật lí, Tiếng Anh' }]),
  plan2026('Sư phạm Hoá học', 'Sư phạm Hoá học', '7140212', '7140212', 40, 12, 'THPT', [{ code: 'A00', subjects: 'Toán, Vật lí, Hóa học' }, { code: 'B00', subjects: 'Toán, Hóa học, Sinh học' }, { code: 'D07', subjects: 'Toán, Hóa học, Tiếng Anh' }]),
  plan2026('Sư phạm Sinh học', 'Sư phạm Sinh học', '7140213', '7140213', 45, 13, 'THPT', [{ code: 'B00', subjects: 'Toán, Hóa học, Sinh học' }, { code: 'D08', subjects: 'Toán, Sinh học, Tiếng Anh' }]),
  plan2026('Sư phạm Ngữ văn', 'Sư phạm Ngữ văn (đào tạo tại trụ sở chính)', '7140217', '7140217', 90, 14, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'D14', subjects: 'Ngữ văn, Lịch sử, Tiếng Anh' }]),
  plan2026('Sư phạm Lịch sử', 'Sư phạm Lịch sử', '7140218', '7140218', 45, 14, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'X70', subjects: 'Ngữ văn, Lịch sử, GDKTPL' }, { code: 'C19', subjects: 'Ngữ văn, Lịch sử, GDCD' }]),
  plan2026('Sư phạm Địa lý', 'Sư phạm Địa lý', '7140219', '7140219', 50, 15, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'C04', subjects: 'Ngữ văn, Toán, Địa lí' }, { code: 'D15', subjects: 'Ngữ văn, Địa lí, Tiếng Anh' }, { code: 'X74', subjects: 'Ngữ văn, Địa lí, GDKTPL' }, { code: 'C20', subjects: 'Ngữ văn, Địa lí, GDCD' }]),
  plan2026('Sư phạm Tiếng Anh', 'Sư phạm Tiếng Anh (đào tạo tại trụ sở chính)', '7140231', '7140231', 165, 16, 'THPT', [{ code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'X79', subjects: 'Ngữ văn, Tiếng Anh, Tin học' }]),
  plan2026('Sư phạm Tiếng Nga', 'Sư phạm Tiếng Nga', '7140232', '7140232', 20, 17, 'THPT', [{ code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'D02', subjects: 'Ngữ văn, Toán, Tiếng Nga' }, { code: 'D14', subjects: 'Ngữ văn, Lịch sử, Tiếng Anh' }, { code: 'X78', subjects: 'Ngữ văn, Tiếng Anh, GDKTPL' }, { code: 'D66', subjects: 'Ngữ văn, Tiếng Anh, GDCD' }]),
  plan2026('Sư phạm Tiếng Pháp', 'Sư phạm Tiếng Pháp', '7140233', '7140233', 20, 18, 'THPT', [{ code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'D03', subjects: 'Ngữ văn, Toán, Tiếng Pháp' }]),
  plan2026('Sư phạm Tiếng Trung Quốc', 'Sư phạm Tiếng Trung Quốc', '7140234', '7140234', 20, 18, 'THPT', [{ code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'D04', subjects: 'Ngữ văn, Toán, Tiếng Trung' }]),
  plan2026('Sư phạm công nghệ', 'Sư phạm công nghệ', '7140246', '7140246', 50, 19, 'THPT', [{ code: 'A01', subjects: 'Toán, Vật lí, Tiếng Anh' }, { code: 'A02', subjects: 'Toán, Vật lí, Sinh học' }]),
  plan2026('Sư phạm khoa học tự nhiên', 'Sư phạm khoa học tự nhiên (đào tạo tại trụ sở chính)', '7140247', '7140247', 100, 19, 'THPT', [{ code: 'A00', subjects: 'Toán, Vật lí, Hóa học' }, { code: 'A02', subjects: 'Toán, Vật lí, Sinh học' }, { code: 'B00', subjects: 'Toán, Hóa học, Sinh học' }]),
  plan2026('Sư phạm Lịch sử - Địa lý', 'Sư phạm Lịch sử - Địa lý (đào tạo tại trụ sở chính)', '7140249', '7140249', 100, 21, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'X70', subjects: 'Ngữ văn, Lịch sử, GDKTPL' }, { code: 'X74', subjects: 'Ngữ văn, Địa lí, GDKTPL' }, { code: 'C19', subjects: 'Ngữ văn, Lịch sử, GDCD' }, { code: 'C20', subjects: 'Ngữ văn, Địa lí, GDCD' }]),
  plan2026('Tiếng Việt và văn hoá Việt Nam', 'Tiếng Việt và văn hoá Việt Nam', '7210101', '7210101', 10, 22, 'Không có tổ hợp THPT trong đề án nguồn', []),
  plan2026('Ngôn ngữ Anh', 'Ngôn ngữ Anh', '7220201', '7220201', 220, 22, 'THPT', [{ code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'X79', subjects: 'Ngữ văn, Tiếng Anh, Tin học' }]),
  plan2026('Ngôn ngữ Nga', 'Ngôn ngữ Nga', '7220202', '7220202', 100, 22, 'THPT', [{ code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'D02', subjects: 'Ngữ văn, Toán, Tiếng Nga' }, { code: 'D14', subjects: 'Ngữ văn, Lịch sử, Tiếng Anh' }, { code: 'X78', subjects: 'Ngữ văn, Tiếng Anh, GDKTPL' }, { code: 'D66', subjects: 'Ngữ văn, Tiếng Anh, GDCD' }]),
  plan2026('Ngôn ngữ Pháp', 'Ngôn ngữ Pháp', '7220203', '7220203', 100, 23, 'THPT', [{ code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'D03', subjects: 'Ngữ văn, Toán, Tiếng Pháp' }]),
  plan2026('Ngôn ngữ Trung Quốc', 'Ngôn ngữ Trung Quốc', '7220204', '7220204', 220, 24, 'THPT', [{ code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'D04', subjects: 'Ngữ văn, Toán, Tiếng Trung' }]),
  plan2026('Ngôn ngữ Nhật', 'Ngôn ngữ Nhật', '7220209', '7220209', 160, 24, 'THPT', [{ code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'D06', subjects: 'Ngữ văn, Toán, Tiếng Nhật' }]),
  plan2026('Ngôn ngữ Hàn Quốc', 'Ngôn ngữ Hàn Quốc (đào tạo tại trụ sở chính)', '7220210', '7220210', 100, 25, 'THPT', [{ code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'DD2', subjects: 'Ngữ văn, Toán, Tiếng Hàn' }, { code: 'D14', subjects: 'Ngữ văn, Lịch sử, Tiếng Anh' }]),
  plan2026('Văn học', 'Văn học', '7229030', '7229030', 130, 25, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'D14', subjects: 'Ngữ văn, Lịch sử, Tiếng Anh' }]),
  plan2026('Chính trị học', 'Chính trị học', '7310201', '7310201', 40, 26, 'THPT', [{ code: 'X01', subjects: 'Toán, Ngữ văn, GDKTPL' }, { code: 'X70', subjects: 'Ngữ văn, Lịch sử, GDKTPL' }, { code: 'X78', subjects: 'Ngữ văn, GDKTPL, Tiếng Anh' }, { code: 'C14', subjects: 'Ngữ văn, Toán, GDCD' }, { code: 'C19', subjects: 'Ngữ văn, Lịch sử, GDCD' }, { code: 'D66', subjects: 'Ngữ văn, GDCD, Tiếng Anh' }]),
  plan2026('Tâm lý học', 'Tâm lý học', '7310401', '7310401', 124, 27, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'C03', subjects: 'Ngữ văn, Toán, Lịch sử' }, { code: 'C04', subjects: 'Ngữ văn, Toán, Địa lí' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }]),
  plan2026('Tâm lý học giáo dục', 'Tâm lý học giáo dục', '7310403', '7310403', 104, 28, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'C03', subjects: 'Ngữ văn, Toán, Lịch sử' }, { code: 'C04', subjects: 'Ngữ văn, Toán, Địa lí' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }]),
  plan2026('Địa lý học', 'Địa lý học', '7310501', '7310501', 50, 29, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'C04', subjects: 'Ngữ văn, Toán, Địa lí' }, { code: 'D15', subjects: 'Ngữ văn, Địa lí, Tiếng Anh' }, { code: 'X74', subjects: 'Ngữ văn, Địa lí, GDKTPL' }, { code: 'C20', subjects: 'Ngữ văn, Địa lí, GDCD' }]),
  plan2026('Quốc tế học', 'Quốc tế học', '7310601', '7310601', 100, 30, 'THPT', [{ code: 'D09', subjects: 'Toán, Lịch sử, Tiếng Anh' }, { code: 'D14', subjects: 'Ngữ văn, Lịch sử, Tiếng Anh' }]),
  plan2026('Việt Nam học', 'Việt Nam học', '7310630', '7310630', 100, 31, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'D14', subjects: 'Ngữ văn, Lịch sử, Tiếng Anh' }]),
  plan2026('Sinh học ứng dụng', 'Sinh học ứng dụng', '7420203', '7420203', 50, 32, 'THPT', [{ code: 'B00', subjects: 'Toán, Hóa học, Sinh học' }, { code: 'D08', subjects: 'Toán, Sinh học, Tiếng Anh' }, { code: 'X14', subjects: 'Toán, Sinh học, Tin học' }, { code: 'X16', subjects: 'Toán, Sinh học, Công nghệ nông nghiệp' }, { code: 'A02', subjects: 'Toán, Vật lí, Sinh học' }]),
  plan2026('Vật lý học', 'Vật lý học', '7440102', '7440102', 110, 33, 'THPT', [{ code: 'A00', subjects: 'Toán, Vật lí, Hóa học' }, { code: 'A01', subjects: 'Toán, Vật lí, Tiếng Anh' }, { code: 'X07', subjects: 'Toán, Vật lí, Công nghệ công nghiệp' }, { code: 'X08', subjects: 'Toán, Vật lí, Công nghệ nông nghiệp' }]),
  plan2026('Hoá học', 'Hoá học', '7440112', '7440112', 110, 34, 'THPT', [{ code: 'A00', subjects: 'Toán, Vật lí, Hóa học' }, { code: 'B00', subjects: 'Toán, Hóa học, Sinh học' }, { code: 'D07', subjects: 'Toán, Hóa học, Tiếng Anh' }, { code: 'X10', subjects: 'Toán, Hóa học, Tin học' }]),
  plan2026('Toán ứng dụng', 'Toán ứng dụng', '7460112', '7460112', 100, 35, 'THPT', [{ code: 'A00', subjects: 'Toán, Vật lí, Hóa học' }, { code: 'A01', subjects: 'Toán, Vật lí, Tiếng Anh' }, { code: 'X06', subjects: 'Toán, Vật lí, Tin học' }]),
  plan2026('Công nghệ thông tin', 'Công nghệ thông tin', '7480201', '7480201', 160, 35, 'THPT', [{ code: 'A01', subjects: 'Toán, Vật lí, Tiếng Anh' }, { code: 'B08', subjects: 'Toán, Sinh học, Tiếng Anh' }, { code: 'D07', subjects: 'Toán, Hóa học, Tiếng Anh' }, { code: 'X26', subjects: 'Toán, Tin học, Tiếng Anh' }]),
  plan2026('Công tác xã hội', 'Công tác xã hội', '7760101', '7760101', 109, 36, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'D14', subjects: 'Ngữ văn, Lịch sử, Tiếng Anh' }, { code: 'X70', subjects: 'Ngữ văn, Lịch sử, GDKTPL' }, { code: 'C19', subjects: 'Ngữ văn, Lịch sử, GDCD' }]),
  plan2026('Hỗ trợ giáo dục người khuyết tật', 'Hỗ trợ giáo dục người khuyết tật', '7760103', '7760103', 30, 37, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'C03', subjects: 'Ngữ văn, Toán, Lịch sử' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'X70', subjects: 'Ngữ văn, Lịch sử, GDKTPL' }, { code: 'C19', subjects: 'Ngữ văn, Lịch sử, GDCD' }]),
  plan2026('Du lịch', 'Du lịch (đào tạo tại trụ sở chính)', '7810101', '7810101', 100, 38, 'THPT', [{ code: 'C00', subjects: 'Ngữ văn, Lịch sử, Địa lí' }, { code: 'D01', subjects: 'Ngữ văn, Toán, Tiếng Anh' }, { code: 'D14', subjects: 'Ngữ văn, Lịch sử, Tiếng Anh' }, { code: 'D15', subjects: 'Ngữ văn, Địa lí, Tiếng Anh' }]),
];

const LATEST_THPT_CUTOFFS: AdmissionCutoff[] = [
  thpt2025('Công nghệ giáo dục', 'Khoa Công nghệ Thông tin', 'A01', 19.25),
  thpt2025('Công nghệ giáo dục', 'Khoa Công nghệ Thông tin', 'B08', 20),
  thpt2025('Công nghệ giáo dục', 'Khoa Công nghệ Thông tin', 'D07', 19.75),
  thpt2025('Công nghệ giáo dục', 'Khoa Công nghệ Thông tin', 'X26', 19.25),
  thpt2025('Công nghệ thông tin', 'Khoa Công nghệ Thông tin', 'A01; X26', 19),
  thpt2025('Công nghệ thông tin', 'Khoa Công nghệ Thông tin', 'B08', 19.75),
  thpt2025('Công nghệ thông tin', 'Khoa Công nghệ Thông tin', 'D07', 19.5),
  thpt2025('Sư phạm Tin học', 'Khoa Công nghệ Thông tin', 'A01; X26', 23.23),
  thpt2025('Sư phạm Tin học', 'Khoa Công nghệ Thông tin', 'B08', 23.98),
  thpt2025('Sư phạm Tin học', 'Khoa Công nghệ Thông tin', 'D07', 23.73),

  thpt2025('Sư phạm Toán học', 'Khoa Toán - Tin học', 'A00; X06', 28.25),
  thpt2025('Sư phạm Toán học', 'Khoa Toán - Tin học', 'A01', 28.75),
  thpt2025('Toán ứng dụng', 'Khoa Toán - Tin học', 'A00; X06; X07', 26.17),
  thpt2025('Toán ứng dụng', 'Khoa Toán - Tin học', 'A01', 26.67),

  thpt2025('Sư phạm Vật lý', 'Khoa Vật lý', 'A00', 28.42),
  thpt2025('Sư phạm Vật lý', 'Khoa Vật lý', 'A01', 28.92),
  thpt2025('Sư phạm Vật lý', 'Khoa Vật lý', 'C01', 28.17),
  thpt2025('Vật lý học', 'Khoa Vật lý', 'A00', 24.25),
  thpt2025('Vật lý học', 'Khoa Vật lý', 'A01', 24.75),
  thpt2025('Vật lý học', 'Khoa Vật lý', 'X07', 24.5),
  thpt2025('Vật lý học', 'Khoa Vật lý', 'X08', 24),
  thpt2025('Sư phạm công nghệ', 'Khoa Vật lý', 'A01', 22.85),
  thpt2025('Sư phạm công nghệ', 'Khoa Vật lý', 'A02; X07', 22.6),
  thpt2025('Sư phạm công nghệ', 'Khoa Vật lý', 'X08', 22.1),

  thpt2025('Sư phạm Hoá học', 'Khoa Hóa học', 'A00', 29.38),
  thpt2025('Sư phạm Hoá học', 'Khoa Hóa học', 'B00', 30.38),
  thpt2025('Sư phạm Hoá học', 'Khoa Hóa học', 'D07', 30.88),
  thpt2025('Hoá học', 'Khoa Hóa học', 'A00; X10', 24.75),
  thpt2025('Hoá học', 'Khoa Hóa học', 'B00', 25.75),
  thpt2025('Hoá học', 'Khoa Hóa học', 'D07', 26.25),

  thpt2025('Sư phạm Sinh học', 'Khoa Sinh học', 'B00', 26.21),
  thpt2025('Sư phạm Sinh học', 'Khoa Sinh học', 'D08', 26.71),
  thpt2025('Sinh học ứng dụng', 'Khoa Sinh học', 'B00; X14', 19.5),
  thpt2025('Sinh học ứng dụng', 'Khoa Sinh học', 'D08', 20),
  thpt2025('Sinh học ứng dụng', 'Khoa Sinh học', 'X16', 19.25),

  thpt2025('Sư phạm Ngữ văn', 'Khoa Ngữ văn', 'C00', 29.07),
  thpt2025('Sư phạm Ngữ văn', 'Khoa Ngữ văn', 'D01', 30.57),
  thpt2025('Sư phạm Ngữ văn', 'Khoa Ngữ văn', 'D14', 29.57),
  thpt2025('Văn học', 'Khoa Ngữ văn', 'C00', 27.47),
  thpt2025('Văn học', 'Khoa Ngữ văn', 'D01', 28.97),
  thpt2025('Văn học', 'Khoa Ngữ văn', 'D14', 27.97),
  thpt2025('Việt Nam học', 'Khoa Ngữ văn', 'C00', 25.95),
  thpt2025('Việt Nam học', 'Khoa Ngữ văn', 'D01', 27.45),
  thpt2025('Việt Nam học', 'Khoa Ngữ văn', 'D14', 26.45),

  thpt2025('Sư phạm Lịch sử', 'Khoa Lịch sử', 'C00', 28.73),
  thpt2025('Sư phạm Lịch sử', 'Khoa Lịch sử', 'C19; X70', 28.48),
  thpt2025('Sư phạm Lịch sử', 'Khoa Lịch sử', 'D14', 29.23),

  thpt2025('Sư phạm Địa lý', 'Khoa Địa lý', 'C00', 28.83),
  thpt2025('Sư phạm Địa lý', 'Khoa Địa lý', 'C04', 29.08),
  thpt2025('Sư phạm Địa lý', 'Khoa Địa lý', 'C20; X74', 28.58),
  thpt2025('Sư phạm Địa lý', 'Khoa Địa lý', 'D15', 29.33),
  thpt2025('Địa lý học', 'Khoa Địa lý', 'C00', 26.73),
  thpt2025('Địa lý học', 'Khoa Địa lý', 'C04', 26.98),
  thpt2025('Địa lý học', 'Khoa Địa lý', 'C20; X74', 26.48),
  thpt2025('Địa lý học', 'Khoa Địa lý', 'D15', 27.23),
  thpt2025('Sư phạm Lịch sử - Địa lý', 'Khoa Địa lý', 'C00', 27.59),
  thpt2025('Sư phạm Lịch sử - Địa lý', 'Khoa Địa lý', 'A07', 27.84),
  thpt2025('Sư phạm Lịch sử - Địa lý', 'Khoa Địa lý', 'C19; C20; X70; X74', 27.34),

  thpt2025('Sư phạm Tiếng Anh', 'Khoa Tiếng Anh', 'D01', 26.79),
  thpt2025('Sư phạm Tiếng Anh', 'Khoa Tiếng Anh', 'X79', 26.54),
  thpt2025('Ngôn ngữ Anh', 'Khoa Tiếng Anh', 'D01', 24.8),
  thpt2025('Ngôn ngữ Anh', 'Khoa Tiếng Anh', 'X79', 24.55),

  thpt2025('Sư phạm Tiếng Pháp', 'Khoa Tiếng Pháp', 'D01; D03', 21.75),
  thpt2025('Ngôn ngữ Pháp', 'Khoa Tiếng Pháp', 'D01; D03', 19),
  thpt2025('Sư phạm Tiếng Trung Quốc', 'Khoa Tiếng Trung', 'D01; D04', 25.39),
  thpt2025('Ngôn ngữ Trung Quốc', 'Khoa Tiếng Trung', 'D01; D04', 22.75),
  thpt2025('Ngôn ngữ Nhật', 'Khoa Tiếng Nhật', 'D01; D06', 21),
  thpt2025('Ngôn ngữ Hàn quốc', 'Khoa Tiếng Hàn', 'D01; DD2', 22),
  thpt2025('Ngôn ngữ Hàn quốc', 'Khoa Tiếng Hàn', 'D14; DH5', 21.75),

  thpt2025('Giáo dục Tiểu học', 'Khoa Giáo dục Tiểu học', 'A00', 24.94),
  thpt2025('Giáo dục Tiểu học', 'Khoa Giáo dục Tiểu học', 'A01', 25.44),
  thpt2025('Giáo dục Tiểu học', 'Khoa Giáo dục Tiểu học', 'D01', 25.94),
  thpt2025('Giáo dục Mầm non', 'Khoa Giáo dục Mầm non', 'M02', 26.3),
  thpt2025('Giáo dục Mầm non', 'Khoa Giáo dục Mầm non', 'M03', 26.05),
  thpt2025('Giáo dục Đặc biệt', 'Khoa Giáo dục Đặc biệt', 'C00', 27.2),
  thpt2025('Giáo dục Đặc biệt', 'Khoa Giáo dục Đặc biệt', 'C03', 27.7),
  thpt2025('Giáo dục Đặc biệt', 'Khoa Giáo dục Đặc biệt', 'C19', 26.95),
  thpt2025('Giáo dục Đặc biệt', 'Khoa Giáo dục Đặc biệt', 'D01', 28.7),
  thpt2025('Giáo dục Đặc biệt', 'Khoa Giáo dục Đặc biệt', 'X70', 27.45),

  thpt2025('Tâm lý học', 'Khoa Tâm lý học', 'C00', 26.5),
  thpt2025('Tâm lý học', 'Khoa Tâm lý học', 'C03; C04', 27.5),
  thpt2025('Tâm lý học', 'Khoa Tâm lý học', 'D01', 28),
  thpt2025('Tâm lý học giáo dục', 'Khoa Tâm lý học', 'C00', 25.82),
  thpt2025('Tâm lý học giáo dục', 'Khoa Tâm lý học', 'C03; C04', 26.82),
  thpt2025('Tâm lý học giáo dục', 'Khoa Tâm lý học', 'D01', 27.32),

  thpt2025('Du lịch', 'Khoa Du lịch', 'C00', 25.89),
  thpt2025('Du lịch', 'Khoa Du lịch', 'D01', 27.39),
  thpt2025('Du lịch', 'Khoa Du lịch', 'D14; D15', 26.39),
  thpt2025('Công tác xã hội', 'Khoa Công tác xã hội', 'A00', 27.13),
  thpt2025('Công tác xã hội', 'Khoa Công tác xã hội', 'C00', 25.63),
  thpt2025('Công tác xã hội', 'Khoa Công tác xã hội', 'C19; X70', 25.38),
  thpt2025('Công tác xã hội', 'Khoa Công tác xã hội', 'D14', 26.13),
];

const HISTORICAL_THPT_CUTOFFS: AdmissionCutoff[] = [
  // 2024
  historicalThpt(2024, 'Giáo dục học', 'Khoa Khoa học Giáo dục', 'D01; A00; A01; C14', 24.82),
  historicalThpt(2024, 'Quản lý giáo dục', 'Khoa Khoa học Giáo dục', 'D01; A00; A01; C14', 25.22),
  historicalThpt(2024, 'Giáo dục Mầm non', 'Khoa Giáo dục Mầm non', 'M02; M03', 24.24),
  historicalThpt(2024, 'Giáo dục Tiểu học', 'Khoa Giáo dục Tiểu học', 'A00; A01; D01', 26.13),
  historicalThpt(2024, 'Giáo dục Đặc biệt', 'Khoa Giáo dục Đặc biệt', 'C00; C15; D01', 26.5),
  historicalThpt(2024, 'Giáo dục Công dân', 'Khoa Giáo dục Chính trị', 'C00; C19; D01', 27.34),
  historicalThpt(2024, 'Giáo dục Chính trị', 'Khoa Giáo dục Chính trị', 'C00; C19; D01', 27.58),
  historicalThpt(2024, 'Giáo dục Thể chất', 'Khoa Giáo dục Thể chất', 'M08; T01', 26.71),
  historicalThpt(2024, 'Giáo dục Quốc phòng - An ninh', 'Trung tâm Giáo dục Quốc phòng và An ninh', 'A08; C00; C19', 27.28),
  historicalThpt(2024, 'Sư phạm Toán học', 'Khoa Toán - Tin học', 'A00; A01', 27.6),
  historicalThpt(2024, 'Sư phạm Tin học', 'Khoa Công nghệ Thông tin', 'A00; A01; B08', 24.73),
  historicalThpt(2024, 'Sư phạm Vật lý', 'Khoa Vật lý', 'A00; A01; C01', 27.25),
  historicalThpt(2024, 'Sư phạm Hoá học', 'Khoa Hóa học', 'A00; B00; D07', 27.67),
  historicalThpt(2024, 'Sư phạm Sinh học', 'Khoa Sinh học', 'B00; D08', 26.22),
  historicalThpt(2024, 'Sư phạm Ngữ văn', 'Khoa Ngữ văn', 'C00; D01; D78', 28.6),
  historicalThpt(2024, 'Sư phạm Lịch sử', 'Khoa Lịch sử', 'C00; D14', 28.6),
  historicalThpt(2024, 'Sư phạm Địa lý', 'Khoa Địa lý', 'C00; C04; D15; D78', 28.37),
  historicalThpt(2024, 'Sư phạm Tiếng Anh', 'Khoa Tiếng Anh', 'D01', 27.01),
  historicalThpt(2024, 'Sư phạm Tiếng Nga', 'Khoa Tiếng Nga', 'D01; D02; D78; D80', 23.69),
  historicalThpt(2024, 'Sư phạm Tiếng Pháp', 'Khoa Tiếng Pháp', 'D01; D03', 24.93),
  historicalThpt(2024, 'Sư phạm Tiếng Trung Quốc', 'Khoa Tiếng Trung', 'D01; D04', 26.44),
  historicalThpt(2024, 'Sư phạm công nghệ', 'Khoa Vật lý', 'A00; A01; A02; D90', 24.31),
  historicalThpt(2024, 'Sư phạm khoa học tự nhiên', 'Khoa Sinh học', 'A00; A02; B00; D90', 25.6),
  historicalThpt(2024, 'Sư phạm Lịch sử - Địa lý', 'Khoa Địa lý', 'C00; C19; C20; D78', 27.75),
  historicalThpt(2024, 'Ngôn ngữ Anh', 'Khoa Tiếng Anh', 'D01', 25.86),
  historicalThpt(2024, 'Ngôn ngữ Nga', 'Khoa Tiếng Nga', 'D01; D02; D78; D80', 22),
  historicalThpt(2024, 'Ngôn ngữ Pháp', 'Khoa Tiếng Pháp', 'D01; D03', 22.7),
  historicalThpt(2024, 'Ngôn ngữ Trung Quốc', 'Khoa Tiếng Trung', 'D01; D04', 25.05),
  historicalThpt(2024, 'Ngôn ngữ Nhật', 'Khoa Tiếng Nhật', 'D01; D06', 23.77),
  historicalThpt(2024, 'Ngôn ngữ Hàn quốc', 'Khoa Tiếng Hàn', 'D01; D78; D96; DD2', 25.02),
  historicalThpt(2024, 'Văn học', 'Khoa Ngữ văn', 'C00; D01; D78', 26.62),
  historicalThpt(2024, 'Tâm lý học', 'Khoa Tâm lý học', 'B00; C00; D01', 27.1),
  historicalThpt(2024, 'Tâm lý học giáo dục', 'Khoa Tâm lý học', 'A00; C00; D01', 26.03),
  historicalThpt(2024, 'Địa lý học', 'Khoa Địa lý', 'C00; D10; D15; D78', 25.17),
  historicalThpt(2024, 'Quốc tế học', 'Khoa Lịch sử', 'D01; D14; D78', 24.42),
  historicalThpt(2024, 'Việt Nam học', 'Khoa Ngữ văn', 'C00; D01; D78', 25.28),
  historicalThpt(2024, 'Sinh học ứng dụng', 'Khoa Sinh học', 'B00; D08', 21.9),
  historicalThpt(2024, 'Vật lý học', 'Khoa Vật lý', 'A00; A01; D90', 24.44),
  historicalThpt(2024, 'Hoá học', 'Khoa Hóa học', 'A00; B00; D07', 24.65),
  historicalThpt(2024, 'Công nghệ thông tin', 'Khoa Công nghệ Thông tin', 'A00; A01; B08', 23.05),
  historicalThpt(2024, 'Công tác xã hội', 'Khoa Công tác xã hội', 'A00; C00; D01', 24.44),
  historicalThpt(2024, 'Du lịch', 'Khoa Du lịch', 'C00; C04; D01; D78', 25.25),

  // 2023
  historicalThpt(2023, 'Giáo dục học', 'Khoa Khoa học Giáo dục', 'D01; A00; A01; C14', 23.5),
  historicalThpt(2023, 'Quản lý giáo dục', 'Khoa Khoa học Giáo dục', 'D01; A00; A01; C14', 23.1),
  historicalThpt(2023, 'Giáo dục Mầm non', 'Khoa Giáo dục Mầm non', 'M02; M03', 24.21),
  historicalThpt(2023, 'Giáo dục Tiểu học', 'Khoa Giáo dục Tiểu học', 'A00; A01; D01', 24.9),
  historicalThpt(2023, 'Giáo dục Đặc biệt', 'Khoa Giáo dục Đặc biệt', 'C00; C15; D01', 25.01),
  historicalThpt(2023, 'Giáo dục Công dân', 'Khoa Giáo dục Chính trị', 'C00; C19; D01', 26.75),
  historicalThpt(2023, 'Giáo dục Chính trị', 'Khoa Giáo dục Chính trị', 'C00; C19; D01', 26.04),
  historicalThpt(2023, 'Giáo dục Thể chất', 'Khoa Giáo dục Thể chất', 'M08; T01', 26.1),
  historicalThpt(2023, 'Giáo dục Quốc phòng - An ninh', 'Trung tâm Giáo dục Quốc phòng và An ninh', 'A08; C00; C19', 25.71),
  historicalThpt(2023, 'Sư phạm Toán học', 'Khoa Toán - Tin học', 'A00; A01', 26.5),
  historicalThpt(2023, 'Sư phạm Tin học', 'Khoa Công nghệ Thông tin', 'A00; A01; B08', 22.75),
  historicalThpt(2023, 'Sư phạm Vật lý', 'Khoa Vật lý', 'A00; A01; C01', 26.1),
  historicalThpt(2023, 'Sư phạm Hoá học', 'Khoa Hóa học', 'A00; B00; D07', 26.55),
  historicalThpt(2023, 'Sư phạm Sinh học', 'Khoa Sinh học', 'B00; D08', 24.9),
  historicalThpt(2023, 'Sư phạm Ngữ văn', 'Khoa Ngữ văn', 'C00; D01; D78', 27),
  historicalThpt(2023, 'Sư phạm Lịch sử', 'Khoa Lịch sử', 'C00; D14', 26.85),
  historicalThpt(2023, 'Sư phạm Địa lý', 'Khoa Địa lý', 'C00; C04; D15; D78', 26.15),
  historicalThpt(2023, 'Sư phạm Tiếng Anh', 'Khoa Tiếng Anh', 'D01', 26.62),
  historicalThpt(2023, 'Sư phạm Tiếng Nga', 'Khoa Tiếng Nga', 'D01; D02; D78; D80', 19.4),
  historicalThpt(2023, 'Sư phạm Tiếng Pháp', 'Khoa Tiếng Pháp', 'D01; D03', 22.7),
  historicalThpt(2023, 'Sư phạm Tiếng Trung Quốc', 'Khoa Tiếng Trung', 'D01; D04', 25.83),
  historicalThpt(2023, 'Sư phạm công nghệ', 'Khoa Vật lý', 'A00; A01; A02; D90', 22.4),
  historicalThpt(2023, 'Sư phạm khoa học tự nhiên', 'Khoa Sinh học', 'A00; A02; B00; D90', 24.56),
  historicalThpt(2023, 'Sư phạm Lịch sử - Địa lý', 'Khoa Địa lý', 'C00; C19; C20; D78', 26.03),
  historicalThpt(2023, 'Ngôn ngữ Anh', 'Khoa Tiếng Anh', 'D01', 25.1),
  historicalThpt(2023, 'Ngôn ngữ Nga', 'Khoa Tiếng Nga', 'D01; D02; D78; D80', 19),
  historicalThpt(2023, 'Ngôn ngữ Pháp', 'Khoa Tiếng Pháp', 'D01; D03', 20.7),
  historicalThpt(2023, 'Ngôn ngữ Trung Quốc', 'Khoa Tiếng Trung', 'D01; D04', 24.54),
  historicalThpt(2023, 'Ngôn ngữ Nhật', 'Khoa Tiếng Nhật', 'D01; D06', 23.1),
  historicalThpt(2023, 'Ngôn ngữ Hàn quốc', 'Khoa Tiếng Hàn', 'D01; D78; D96; DD2', 24.9),
  historicalThpt(2023, 'Văn học', 'Khoa Ngữ văn', 'C00; D01; D78', 24.6),
  historicalThpt(2023, 'Tâm lý học', 'Khoa Tâm lý học', 'B00; C00; D01', 25.5),
  historicalThpt(2023, 'Tâm lý học giáo dục', 'Khoa Tâm lý học', 'A00; C00; D01', 24.17),
  historicalThpt(2023, 'Địa lý học', 'Khoa Địa lý', 'C00; D10; D15; D78', 19.75),
  historicalThpt(2023, 'Quốc tế học', 'Khoa Lịch sử', 'D01; D14; D78', 23.5),
  historicalThpt(2023, 'Việt Nam học', 'Khoa Ngữ văn', 'C00; D01; D78', 23),
  historicalThpt(2023, 'Sinh học ứng dụng', 'Khoa Sinh học', 'B00; D08', 19),
  historicalThpt(2023, 'Vật lý học', 'Khoa Vật lý', 'A00; A01; D90', 22.55),
  historicalThpt(2023, 'Hoá học', 'Khoa Hóa học', 'A00; B00; D07', 23.47),
  historicalThpt(2023, 'Công nghệ thông tin', 'Khoa Công nghệ Thông tin', 'A00; A01; B08', 23.34),
  historicalThpt(2023, 'Công tác xã hội', 'Khoa Công tác xã hội', 'A00; C00; D01', 22),
  historicalThpt(2023, 'Du lịch', 'Khoa Du lịch', 'C00; C04; D01; D78', 22),

  // 2022
  historicalThpt(2022, 'Giáo dục học', 'Khoa Khoa học Giáo dục', 'B00; C00; C01; D01', 22.4),
  historicalThpt(2022, 'Giáo dục Tiểu học', 'Khoa Giáo dục Tiểu học', 'A00; A01; D01', 24.25),
  historicalThpt(2022, 'Giáo dục Đặc biệt', 'Khoa Giáo dục Đặc biệt', 'D01; C00; C15', 21.75),
  historicalThpt(2022, 'Giáo dục Công dân', 'Khoa Giáo dục Chính trị', 'C00; C19; D01', 25.5),
  historicalThpt(2022, 'Giáo dục Thể chất', 'Khoa Giáo dục Thể chất', 'T01; M08', 22.75),
  historicalThpt(2022, 'Giáo dục Quốc phòng - An ninh', 'Trung tâm Giáo dục Quốc phòng và An ninh', 'C00; C19; A08', 24.05),
  historicalThpt(2022, 'Sư phạm Toán học', 'Khoa Toán - Tin học', 'A00; A01', 27),
  historicalThpt(2022, 'Sư phạm Tin học', 'Khoa Công nghệ Thông tin', 'A00; A01; B08', 22.5),
  historicalThpt(2022, 'Sư phạm Vật lý', 'Khoa Vật lý', 'A00; A01; C01', 26.5),
  historicalThpt(2022, 'Sư phạm Hoá học', 'Khoa Hóa học', 'A00; B00; D07', 27.35),
  historicalThpt(2022, 'Sư phạm Sinh học', 'Khoa Sinh học', 'B00; D08', 24.8),
  historicalThpt(2022, 'Sư phạm Ngữ văn', 'Khoa Ngữ văn', 'D01; C00; D78', 28.25),
  historicalThpt(2022, 'Sư phạm Lịch sử', 'Khoa Lịch sử', 'C00; C14', 26.83),
  historicalThpt(2022, 'Sư phạm Địa lý', 'Khoa Địa lý', 'C00; C04; D15; D78', 26.5),
  historicalThpt(2022, 'Sư phạm Tiếng Trung Quốc', 'Khoa Tiếng Trung', 'D01; D04', 25.1),
  historicalThpt(2022, 'Sư phạm Tiếng Anh', 'Khoa Tiếng Anh', 'D01', 26.5),
  historicalThpt(2022, 'Sư phạm công nghệ', 'Khoa Vật lý', 'A00; B00; D90; A02', 21.6),
  historicalThpt(2022, 'Sư phạm khoa học tự nhiên', 'Khoa Sinh học', 'A00; A02; B00; D90', 24),
  historicalThpt(2022, 'Sư phạm Lịch sử - Địa lý', 'Khoa Địa lý', 'C00; C19; C20; D78', 25),
  historicalThpt(2022, 'Ngôn ngữ Anh', 'Khoa Tiếng Anh', 'D01', 25.5),
  historicalThpt(2022, 'Ngôn ngữ Nga', 'Khoa Tiếng Nga', 'D01; D02; D80; D78', 20.05),
  historicalThpt(2022, 'Ngôn ngữ Pháp', 'Khoa Tiếng Pháp', 'D01; D03', 22.35),
  historicalThpt(2022, 'Ngôn ngữ Trung Quốc', 'Khoa Tiếng Trung', 'D01; D04', 24.6),
  historicalThpt(2022, 'Ngôn ngữ Nhật', 'Khoa Tiếng Nhật', 'D01; D06', 24),
  historicalThpt(2022, 'Văn học', 'Khoa Ngữ văn', 'D01; C00; D78', 24.7),
  historicalThpt(2022, 'Tâm lý học', 'Khoa Tâm lý học', 'B00; C00; D01', 25.75),
  historicalThpt(2022, 'Tâm lý học giáo dục', 'Khoa Tâm lý học', 'A00; D01; C00', 24),
  historicalThpt(2022, 'Quốc tế học', 'Khoa Lịch sử', 'D01; D14; D78', 23.75),
  historicalThpt(2022, 'Việt Nam học', 'Khoa Ngữ văn', 'C00; D01; D78', 23.3),
  historicalThpt(2022, 'Giáo dục Mầm non', 'Khoa Giáo dục Mầm non', 'M00', 20.03),
  historicalThpt(2022, 'Vật lý học', 'Khoa Vật lý', 'A00; A01', 21.05),
  historicalThpt(2022, 'Hoá học', 'Khoa Hóa học', 'A00; B00; D07', 23),
  historicalThpt(2022, 'Công nghệ thông tin', 'Khoa Công nghệ Thông tin', 'A00; A01', 24.1),
  historicalThpt(2022, 'Ngôn ngữ Hàn quốc', 'Khoa Tiếng Hàn', 'D01; D96; D78', 24.97),
  historicalThpt(2022, 'Công tác xã hội', 'Khoa Công tác xã hội', 'A00; D01; C00', 20.4),

  // 2021
  historicalThpt(2021, 'Giáo dục học', 'Khoa Khoa học Giáo dục', 'B00; C00; C01; D01', 19.5),
  historicalThpt(2021, 'Quản lý giáo dục', 'Khoa Khoa học Giáo dục', 'D01; A00; C00', 23.3),
  historicalThpt(2021, 'Giáo dục Mầm non', 'Khoa Giáo dục Mầm non', 'M00', 22.05),
  historicalThpt(2021, 'Giáo dục Tiểu học', 'Khoa Giáo dục Tiểu học', 'A00; A01; D01', 25.4),
  historicalThpt(2021, 'Giáo dục Đặc biệt', 'Khoa Giáo dục Đặc biệt', 'D01; C00; C15', 23.4),
  historicalThpt(2021, 'Giáo dục Chính trị', 'Khoa Giáo dục Chính trị', 'C00; C19; D01', 25.75),
  historicalThpt(2021, 'Giáo dục Thể chất', 'Khoa Giáo dục Thể chất', 'M08; T01', 23.75),
  historicalThpt(2021, 'Giáo dục Quốc phòng - An ninh', 'Trung tâm Giáo dục Quốc phòng và An ninh', 'C00; C19; A08', 24.4),
  historicalThpt(2021, 'Sư phạm Toán học', 'Khoa Toán - Tin học', 'A00; A01', 26.7),
  historicalThpt(2021, 'Sư phạm Tin học', 'Khoa Công nghệ Thông tin', 'A00; A01', 23),
  historicalThpt(2021, 'Sư phạm Vật lý', 'Khoa Vật lý', 'A00; A01; C01', 25.8),
  historicalThpt(2021, 'Sư phạm Hoá học', 'Khoa Hóa học', 'A00; B00; D07', 27),
  historicalThpt(2021, 'Sư phạm Sinh học', 'Khoa Sinh học', 'B00; D08', 25),
  historicalThpt(2021, 'Sư phạm Ngữ văn', 'Khoa Ngữ văn', 'D01; C00; D78', 27),
  historicalThpt(2021, 'Sư phạm Lịch sử', 'Khoa Lịch sử', 'C00; D14', 26),
  historicalThpt(2021, 'Sư phạm Địa lý', 'Khoa Địa lý', 'C00; C04; D78', 25.2),
  historicalThpt(2021, 'Sư phạm Tiếng Anh', 'Khoa Tiếng Anh', 'D01', 27.15),
  historicalThpt(2021, 'Sư phạm Tiếng Trung Quốc', 'Khoa Tiếng Trung', 'D04; D01', 25.5),
  historicalThpt(2021, 'Sư phạm khoa học tự nhiên', 'Khoa Sinh học', 'A00; B00; D90', 24.4),
  historicalThpt(2021, 'Sư phạm Lịch sử - Địa lý', 'Khoa Địa lý', 'C00; C19; C20', 25),
  historicalThpt(2021, 'Ngôn ngữ Anh', 'Khoa Tiếng Anh', 'D01', 26),
  historicalThpt(2021, 'Ngôn ngữ Nga', 'Khoa Tiếng Nga', 'D02; D80; D01; D78', 20.53),
  historicalThpt(2021, 'Ngôn ngữ Pháp', 'Khoa Tiếng Pháp', 'D03; D01', 22.8),
  historicalThpt(2021, 'Ngôn ngữ Trung Quốc', 'Khoa Tiếng Trung', 'D04; D01', 25.2),
  historicalThpt(2021, 'Ngôn ngữ Nhật', 'Khoa Tiếng Nhật', 'D06; D01', 24.9),
  historicalThpt(2021, 'Ngôn ngữ Hàn quốc', 'Khoa Tiếng Hàn', 'D01; D96; D78; DD2', 25.8),
  historicalThpt(2021, 'Văn học', 'Khoa Ngữ văn', 'D01; C00; D78', 24.3),
  historicalThpt(2021, 'Tâm lý học', 'Khoa Tâm lý học', 'B00; C00; D01', 25.5),
  historicalThpt(2021, 'Tâm lý học giáo dục', 'Khoa Tâm lý học', 'A00; D01; C00', 23.7),
  historicalThpt(2021, 'Quốc tế học', 'Khoa Lịch sử', 'D01; D14; D78', 24.6),
  historicalThpt(2021, 'Việt Nam học', 'Khoa Ngữ văn', 'C00; D01; D78', 22.92),
  historicalThpt(2021, 'Hoá học', 'Khoa Hóa học', 'A00; B00; D07', 23.25),
  historicalThpt(2021, 'Công nghệ thông tin', 'Khoa Công nghệ Thông tin', 'A00; A01', 24),
  historicalThpt(2021, 'Công tác xã hội', 'Khoa Công tác xã hội', 'A00; D01; C00', 22.5),
];

export const ADMISSION_CUTOFFS: AdmissionCutoff[] = [
  ...LATEST_THPT_CUTOFFS,
  ...HISTORICAL_THPT_CUTOFFS,
];
