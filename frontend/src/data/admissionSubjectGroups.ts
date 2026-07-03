export interface AdmissionSubject {
  key: string;
  label: string;
}

export interface AdmissionSubjectGroup {
  code: string;
  subjects: AdmissionSubject[];
  note?: string;
  calculable: boolean;
}

const SUBJECTS: Record<string, AdmissionSubject> = {
  math: { key: 'math', label: 'Toán' },
  literature: { key: 'literature', label: 'Ngữ văn' },
  english: { key: 'english', label: 'Tiếng Anh' },
  physics: { key: 'physics', label: 'Vật lý' },
  chemistry: { key: 'chemistry', label: 'Hóa học' },
  biology: { key: 'biology', label: 'Sinh học' },
  history: { key: 'history', label: 'Lịch sử' },
  geography: { key: 'geography', label: 'Địa lý' },
  civic: { key: 'civic', label: 'Giáo dục công dân' },
  russian: { key: 'russian', label: 'Tiếng Nga' },
  french: { key: 'french', label: 'Tiếng Pháp' },
  chinese: { key: 'chinese', label: 'Tiếng Trung' },
  japanese: { key: 'japanese', label: 'Tiếng Nhật' },
  korean: { key: 'korean', label: 'Tiếng Hàn' },
  naturalScience: { key: 'naturalScience', label: 'Khoa học tự nhiên' },
  socialScience: { key: 'socialScience', label: 'Khoa học xã hội' },
  informatics: { key: 'informatics', label: 'Tin học' },
  industrialTechnology: { key: 'industrialTechnology', label: 'Công nghệ công nghiệp' },
  agriculturalTechnology: { key: 'agriculturalTechnology', label: 'Công nghệ nông nghiệp' },
  economicLaw: { key: 'economicLaw', label: 'Giáo dục kinh tế và pháp luật' },
  aptitude: { key: 'aptitude', label: 'Môn năng khiếu' },
  aptitude2: { key: 'aptitude2', label: 'Môn năng khiếu 2' },
};

function group(code: string, subjectKeys: string[], note?: string): AdmissionSubjectGroup {
  return {
    code,
    subjects: subjectKeys.map((key) => SUBJECTS[key]),
    note,
    calculable: true,
  };
}

function customGroup(code: string, note = 'Tổ hợp riêng theo đề án tuyển sinh HCMUE. Vui lòng đối chiếu đề án tuyển sinh trước khi tính điểm.'): AdmissionSubjectGroup {
  return {
    code,
    subjects: [],
    note,
    calculable: false,
  };
}

export const ADMISSION_SUBJECT_GROUPS: Record<string, AdmissionSubjectGroup> = {
  A00: group('A00', ['math', 'physics', 'chemistry']),
  A01: group('A01', ['math', 'physics', 'english']),
  A02: group('A02', ['math', 'physics', 'biology']),
  A07: group('A07', ['math', 'history', 'geography']),
  A08: group('A08', ['math', 'history', 'civic']),

  B00: group('B00', ['math', 'chemistry', 'biology']),
  B08: group('B08', ['math', 'biology', 'english']),

  C00: group('C00', ['literature', 'history', 'geography']),
  C01: group('C01', ['literature', 'math', 'physics']),
  C03: group('C03', ['literature', 'math', 'history']),
  C04: group('C04', ['literature', 'math', 'geography']),
  C14: group('C14', ['literature', 'math', 'civic']),
  C15: group('C15', ['literature', 'math', 'socialScience']),
  C19: group('C19', ['literature', 'history', 'civic']),
  C20: group('C20', ['literature', 'geography', 'civic']),

  D01: group('D01', ['literature', 'math', 'english']),
  D02: group('D02', ['literature', 'math', 'russian']),
  D03: group('D03', ['literature', 'math', 'french']),
  D04: group('D04', ['literature', 'math', 'chinese']),
  D06: group('D06', ['literature', 'math', 'japanese']),
  D07: group('D07', ['math', 'chemistry', 'english']),
  D08: group('D08', ['math', 'biology', 'english']),
  D09: group('D09', ['math', 'history', 'english']),
  D10: group('D10', ['math', 'geography', 'english']),
  D14: group('D14', ['literature', 'history', 'english']),
  D15: group('D15', ['literature', 'geography', 'english']),
  D66: group('D66', ['literature', 'civic', 'english']),
  D78: group('D78', ['literature', 'socialScience', 'english']),
  D80: group('D80', ['literature', 'socialScience', 'russian']),
  D90: group('D90', ['math', 'naturalScience', 'english']),
  D96: group('D96', ['math', 'socialScience', 'english']),

  DD2: group('DD2', ['literature', 'math', 'korean']),
  DH5: group('DH5', ['literature', 'history', 'korean']),

  M00: group('M00', ['literature', 'math', 'aptitude'], 'Tổ hợp có môn năng khiếu; cách tính có thể khác theo đề án tuyển sinh.'),
  M02: group('M02', ['math', 'literature', 'aptitude'], 'Tổ hợp có môn năng khiếu; cách tính có thể khác theo đề án tuyển sinh.'),
  M03: group('M03', ['literature', 'english', 'aptitude'], 'Tổ hợp có môn năng khiếu; cách tính có thể khác theo đề án tuyển sinh.'),
  M08: group('M08', ['literature', 'aptitude', 'aptitude2'], 'Tổ hợp có môn năng khiếu; cách tính có thể khác theo đề án tuyển sinh.'),
  T01: group('T01', ['math', 'literature', 'aptitude'], 'Tổ hợp có môn năng khiếu thể chất; cách tính có thể khác theo đề án tuyển sinh.'),
  Q01: group('Q01', ['math', 'literature', 'aptitude'], 'Tổ hợp giáo dục quốc phòng - an ninh có thể có điều kiện phụ.'),
  Q02: group('Q02', ['math', 'english', 'aptitude'], 'Tổ hợp giáo dục quốc phòng - an ninh có thể có điều kiện phụ.'),

  X01: group('X01', ['math', 'literature', 'economicLaw']),
  X06: group('X06', ['math', 'physics', 'informatics']),
  X07: group('X07', ['math', 'physics', 'industrialTechnology']),
  X08: group('X08', ['math', 'physics', 'agriculturalTechnology']),
  X10: group('X10', ['math', 'chemistry', 'informatics']),
  X14: group('X14', ['math', 'biology', 'informatics']),
  X16: group('X16', ['math', 'biology', 'agriculturalTechnology']),
  X26: group('X26', ['math', 'informatics', 'english']),
  X70: group('X70', ['literature', 'history', 'economicLaw']),
  X74: group('X74', ['literature', 'geography', 'economicLaw']),
  X78: group('X78', ['literature', 'economicLaw', 'english']),
  X79: group('X79', ['literature', 'english', 'informatics']),
};

export function getSubjectGroupDefinition(code: string): AdmissionSubjectGroup {
  const normalizedCode = code.trim().toUpperCase();
  return ADMISSION_SUBJECT_GROUPS[normalizedCode] ?? customGroup(normalizedCode, 'Chưa có mô tả môn cho tổ hợp này trong dữ liệu hiện tại. Vui lòng nhập tổng điểm thủ công.');
}

export function calculateAdmissionTotal(
  groupCode: string,
  scores: Record<string, string>,
  priorityScore: string,
): number | null {
  const groupDefinition = getSubjectGroupDefinition(groupCode);
  if (!groupDefinition.calculable) return null;

  const total = groupDefinition.subjects.reduce((sum, subject) => {
    const value = Number(scores[subject.key]);
    if (!Number.isFinite(value)) return Number.NaN;
    return sum + value;
  }, 0);
  const priority = Number(priorityScore || 0);

  if (!Number.isFinite(total) || !Number.isFinite(priority)) return null;
  return Math.round((total + priority) * 100) / 100;
}
