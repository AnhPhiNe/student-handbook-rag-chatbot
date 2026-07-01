import {
  ADMISSION_CUTOFFS,
  ADMISSION_PLANS_2025,
  type AdmissionCutoff,
  type AdmissionMethod,
  type AdmissionPlan,
} from '../data/admissions';

export type AdmissionChanceLevel =
  | 'very_safe'
  | 'safe'
  | 'consider'
  | 'risky'
  | 'very_risky'
  | 'insufficient';

export type AdmissionConfidence = 'high' | 'medium' | 'low';

export interface AdmissionEstimateInput {
  programName: string;
  admissionMethod: AdmissionMethod;
  subjectGroup: string;
  score: number;
}

export interface AdmissionEstimate {
  level: AdmissionChanceLevel;
  levelLabel: string;
  levelDescription: string;
  confidence: AdmissionConfidence;
  confidenceLabel: string;
  latestCutoff?: AdmissionCutoff;
  scoreDelta?: number;
  averageCutoff?: number;
  minCutoff?: number;
  maxCutoff?: number;
  matchedRecords: AdmissionCutoff[];
  matchScope: 'exact' | 'method' | 'program' | 'none';
  warnings: string[];
}

export function normalizeText(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export function splitSubjectGroups(subjectGroup: string): string[] {
  return subjectGroup
    .split(/[;,/]+/)
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
}

export function getAdmissionPrograms(): string[] {
  return Array.from(new Set([
    ...ADMISSION_CUTOFFS.map((item) => item.programName),
    ...ADMISSION_PLANS_2025.map((item) => item.programName),
  ])).sort((a, b) =>
    a.localeCompare(b, 'vi'),
  );
}

export function getAdmissionFaculties(): string[] {
  return Array.from(new Set(ADMISSION_CUTOFFS.map((item) => item.faculty))).sort((a, b) =>
    a.localeCompare(b, 'vi'),
  );
}

export function searchAdmissionPrograms(query: string, limit = 8): string[] {
  const normalizedQuery = normalizeText(query);
  const programs = getAdmissionPrograms();
  if (!normalizedQuery) return programs.slice(0, limit);

  return programs
    .filter((program) => normalizeText(program).includes(normalizedQuery))
    .slice(0, limit);
}

export function getCutoffsForProgram(programName: string): AdmissionCutoff[] {
  const normalizedProgram = normalizeText(programName);
  return ADMISSION_CUTOFFS
    .filter((item) => normalizeText(item.programName) === normalizedProgram)
    .sort((a, b) => b.year - a.year || b.cutoffScore - a.cutoffScore);
}

export function getAdmissionPlanForProgram(programName: string): AdmissionPlan | undefined {
  const normalizedProgram = normalizeText(programName);
  return ADMISSION_PLANS_2025.find((item) => normalizeText(item.programName) === normalizedProgram);
}

export function getMethodsForProgram(programName: string): AdmissionMethod[] {
  return Array.from(new Set(getCutoffsForProgram(programName).map((item) => item.admissionMethod)));
}

export function getSubjectGroupsForProgram(programName: string, method?: AdmissionMethod): string[] {
  const records = getCutoffsForProgram(programName).filter(
    (item) => !method || item.admissionMethod === method,
  );
  return Array.from(new Set(records.flatMap((item) => splitSubjectGroups(item.subjectGroup)))).sort();
}

function average(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function roundScore(value: number): number {
  return Math.round(value * 100) / 100;
}

function pickLevel(scoreDelta: number): AdmissionChanceLevel {
  if (scoreDelta >= 1.5) return 'very_safe';
  if (scoreDelta >= 0.5) return 'safe';
  if (scoreDelta >= -0.5) return 'consider';
  if (scoreDelta >= -1.5) return 'risky';
  return 'very_risky';
}

function getLevelText(level: AdmissionChanceLevel): Pick<AdmissionEstimate, 'levelLabel' | 'levelDescription'> {
  switch (level) {
    case 'very_safe':
      return {
        levelLabel: 'Rất an toàn',
        levelDescription: 'Điểm của bạn cao hơn điểm chuẩn gần nhất khá rõ. Vẫn nên kiểm tra điều kiện phụ và chỉ tiêu năm nay.',
      };
    case 'safe':
      return {
        levelLabel: 'Khá an toàn',
        levelDescription: 'Điểm của bạn đang cao hơn điểm chuẩn gần nhất. Đây là mức có thể cân nhắc đặt nguyện vọng.',
      };
    case 'consider':
      return {
        levelLabel: 'Cần cân nhắc',
        levelDescription: 'Điểm của bạn đang sát vùng điểm chuẩn gần nhất. Nên chuẩn bị thêm ngành/nguyện vọng dự phòng.',
      };
    case 'risky':
      return {
        levelLabel: 'Rủi ro',
        levelDescription: 'Điểm của bạn thấp hơn điểm chuẩn gần nhất. Chỉ nên đặt nếu đây là nguyện vọng yêu thích và có phương án dự phòng.',
      };
    case 'very_risky':
      return {
        levelLabel: 'Rất rủi ro',
        levelDescription: 'Điểm của bạn thấp hơn điểm chuẩn gần nhất khá nhiều. Nên ưu tiên thêm ngành hoặc phương thức xét tuyển khác.',
      };
    default:
      return {
        levelLabel: 'Thiếu dữ liệu',
        levelDescription: 'Chưa đủ dữ liệu phù hợp để ước lượng. Hãy kiểm tra lại ngành, phương thức hoặc tổ hợp.',
      };
  }
}

function downgradeLevel(level: AdmissionChanceLevel): AdmissionChanceLevel {
  const order: AdmissionChanceLevel[] = ['very_safe', 'safe', 'consider', 'risky', 'very_risky'];
  const index = order.indexOf(level);
  if (index < 0) return level;
  return order[Math.min(index + 1, order.length - 1)];
}

export function estimateAdmissionChance(input: AdmissionEstimateInput): AdmissionEstimate {
  const programRecords = getCutoffsForProgram(input.programName);
  const warnings: string[] = [];

  if (!Number.isFinite(input.score) || input.score <= 0 || input.score > 30) {
    return {
      level: 'insufficient',
      ...getLevelText('insufficient'),
      confidence: 'low',
      confidenceLabel: 'Thấp',
      matchedRecords: [],
      matchScope: 'none',
      warnings: ['Vui lòng nhập tổng điểm hợp lệ theo thang 30.'],
    };
  }

  if (programRecords.length === 0) {
    return {
      level: 'insufficient',
      ...getLevelText('insufficient'),
      confidence: 'low',
      confidenceLabel: 'Thấp',
      matchedRecords: [],
      matchScope: 'none',
      warnings: ['Chưa có dữ liệu điểm chuẩn cho ngành này trong bộ dữ liệu hiện tại.'],
    };
  }

  const subjectGroup = input.subjectGroup.trim().toUpperCase();
  const exactMatches = programRecords.filter(
    (item) =>
      item.admissionMethod === input.admissionMethod &&
      splitSubjectGroups(item.subjectGroup).includes(subjectGroup),
  );
  const methodMatches = programRecords.filter((item) => item.admissionMethod === input.admissionMethod);

  let matchedRecords = exactMatches;
  let matchScope: AdmissionEstimate['matchScope'] = 'exact';
  if (matchedRecords.length === 0 && methodMatches.length > 0) {
    matchedRecords = methodMatches;
    matchScope = 'method';
    warnings.push('Chưa có điểm chuẩn đúng tổ hợp này, hệ thống đang so với cùng ngành và cùng phương thức xét tuyển.');
  }
  if (matchedRecords.length === 0) {
    matchedRecords = programRecords;
    matchScope = 'program';
    warnings.push('Chưa có dữ liệu đúng phương thức/tổ hợp, hệ thống chỉ dùng xu hướng chung của ngành.');
  }

  const latestYear = Math.max(...matchedRecords.map((item) => item.year));
  const latestRecords = matchedRecords.filter((item) => item.year === latestYear);
  const latestCutoff = latestRecords.reduce((best, item) =>
    Math.abs(item.cutoffScore - input.score) < Math.abs(best.cutoffScore - input.score) ? item : best,
  );

  const scoreDelta = roundScore(input.score - latestCutoff.cutoffScore);
  const cutoffs = matchedRecords.map((item) => item.cutoffScore);
  const averageCutoff = roundScore(average(cutoffs));
  const minCutoff = Math.min(...cutoffs);
  const maxCutoff = Math.max(...cutoffs);
  const volatility = maxCutoff - minCutoff;
  let level = pickLevel(scoreDelta);
  let confidence: AdmissionConfidence = 'medium';

  if (matchScope !== 'exact') {
    confidence = 'low';
    level = downgradeLevel(level);
  }
  if (matchedRecords.length < 2) {
    warnings.push('Bộ dữ liệu phù hợp hiện mới có 1 năm, nên chỉ xem đây là tham khảo nhanh.');
  }
  if (
    matchScope === 'exact' &&
    matchedRecords.length === 1 &&
    programRecords.some((item) => item.admissionRegime === 'pre_2025')
  ) {
    warnings.push('Tổ hợp/phương thức này có thể đã thay đổi so với các năm trước, nên hệ thống ưu tiên mốc 2025.');
  }
  if (
    matchedRecords.some((item) => item.admissionRegime === 'pre_2025') &&
    matchedRecords.some((item) => item.admissionRegime === 'post_2025')
  ) {
    warnings.push('Kết quả đang dùng cả dữ liệu trước và sau mốc 2025; hãy xem xu hướng cũ như tham khảo, không so sánh tuyệt đối.');
  }
  if (!matchedRecords.some((item) => item.admissionRegime === 'post_2025')) {
    confidence = 'low';
    warnings.push('Dữ liệu chưa có mốc sau thay đổi chương trình GDPT 2018, độ tin cậy thấp.');
  }
  if (matchedRecords.length >= 3 && volatility >= 1.5) {
    warnings.push('Điểm chuẩn nhóm dữ liệu này dao động khá mạnh, nên tăng biên an toàn khi đặt nguyện vọng.');
  }
  if (matchScope === 'exact' && matchedRecords.length >= 3 && volatility < 1) {
    confidence = 'high';
  }

  return {
    level,
    ...getLevelText(level),
    confidence,
    confidenceLabel: confidence === 'high' ? 'Cao' : confidence === 'medium' ? 'Trung bình' : 'Thấp',
    latestCutoff,
    scoreDelta,
    averageCutoff,
    minCutoff,
    maxCutoff,
    matchedRecords,
    matchScope,
    warnings,
  };
}

export function getNearScorePrograms(score: number, limit = 6): AdmissionCutoff[] {
  if (!Number.isFinite(score) || score <= 0) return [];
  const latestByProgram = new Map<string, AdmissionCutoff>();

  for (const item of ADMISSION_CUTOFFS) {
    const key = `${item.programName}-${item.admissionMethod}-${item.subjectGroup}-${item.campus}`;
    const current = latestByProgram.get(key);
    if (!current || item.year > current.year) {
      latestByProgram.set(key, item);
    }
  }

  return Array.from(latestByProgram.values())
    .filter((item) => item.cutoffScore <= score + 1)
    .sort((a, b) => Math.abs(a.cutoffScore - score) - Math.abs(b.cutoffScore - score))
    .slice(0, limit);
}
