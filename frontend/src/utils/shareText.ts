/**
 * One-line plain-text summaries of tool results, for the "Sao chép kết quả" button.
 * Pure functions over plain numbers and labels, so they are easy to test.
 */

const SEP = ' · ';

const fixed = (value: number, digits = 2) => (Number.isFinite(value) ? value.toFixed(digits) : '0.00');

/** Amount in Vietnamese grouping with the đ unit, e.g. "10.603.000 đ". */
export function vnd(value: number): string {
  return `${new Intl.NumberFormat('vi-VN').format(Math.round(value))} đ`;
}

const join = (parts: Array<string | null | undefined | false>) => parts.filter(Boolean).join(SEP);

export function gpaShareText(input: { gpa: number; tier: string; credits: number; cohort: string }): string {
  return join([`GPA học kỳ: ${fixed(input.gpa)}/4`, input.tier, `${input.credits} TC`, input.cohort]);
}

export type TermShareInput = {
  status: 'achieved' | 'feasible' | 'impossible';
  requiredGpa: number;
  targetGpa: number;
  currentGpa: number;
  cohort: string;
};

export function targetTermShareText(input: TermShareInput): string {
  const target = fixed(input.targetGpa);
  if (input.status === 'achieved') {
    return join([`Đã đạt mục tiêu tích lũy ${target} (hiện ${fixed(input.currentGpa)}/4)`, input.cohort]);
  }
  if (input.status === 'impossible') {
    return join([
      `Mục tiêu tích lũy ${target} vượt khả năng trong một kỳ (cần GPA ${fixed(input.requiredGpa)}/4)`,
      input.cohort,
    ]);
  }
  return join([`Kỳ tới cần GPA ${fixed(input.requiredGpa)}/4 để đạt tích lũy ${target}`, input.cohort]);
}

export type RetakeShareInput = {
  courses: number;
  credits: number;
  baselineGpa: number;
  newGpa: number;
  deltaGpa: number;
  cohort: string;
};

export function targetRetakeShareText(input: RetakeShareInput): string {
  return join([
    `Cải thiện ${input.courses} môn (${input.credits} TC): GPA tích lũy từ ${fixed(input.baselineGpa)} lên ${fixed(input.newGpa)} (+${fixed(input.deltaGpa)})`,
    input.cohort,
  ]);
}

export type RoadmapShareInput = {
  feasible: boolean;
  targetGpa: number;
  neededGpa: number;
  maxGpa: number;
  remainingCredits: number;
  terms: number;
  cohort: string;
};

export function targetRoadmapShareText(input: RoadmapShareInput): string {
  const target = fixed(input.targetGpa);
  if (!input.feasible) {
    return join([
      `Mục tiêu tốt nghiệp ${target} chưa khả thi, GPA cao nhất có thể đạt ${fixed(input.maxGpa)}/4`,
      input.cohort,
    ]);
  }
  return join([
    `Để tốt nghiệp GPA ${target} cần giữ ${fixed(input.neededGpa)}/4 mỗi kỳ, còn ${input.remainingCredits} TC (~${input.terms} học kỳ)`,
    input.cohort,
  ]);
}

export type CourseTargetShareInput = {
  status: 'possible' | 'achieved' | 'impossible';
  letter: string;
  isPassGrade: boolean;
  requiredScore: number | null;
  /** Percent of the course score already covered by entered columns. */
  coveredPercent: number;
  bestLetter: string | null;
  cohort: string;
};

export function courseTargetShareText(input: CourseTargetShareInput): string {
  const grade = `${input.letter}${input.isPassGrade ? ' (qua môn)' : ''}`;
  const covered = `Đã có ${Math.round(input.coveredPercent)}%`;
  if (input.status === 'achieved') {
    return join([`Đã đủ điểm để đạt ${grade}`, covered, input.cohort]);
  }
  if (input.status === 'impossible') {
    const best = input.bestLetter ? `cao nhất đạt ${input.bestLetter}` : 'không qua được môn';
    return join([`Thi 10 vẫn chưa đủ để đạt ${grade} (${best})`, covered, input.cohort]);
  }
  return join([`Thi cuối kỳ cần ${fixed(input.requiredScore ?? 0)}/10 để đạt ${grade}`, covered, input.cohort]);
}

export type ScholarshipShareInput = {
  classification: string | null;
  multiplier: number;
  score: number;
  amount: number | null;
  cohort: string;
};

export function scholarshipShareText(input: ScholarshipShareInput): string {
  if (!input.classification) {
    return join(['Học bổng dự kiến: chưa đạt mức học bổng', `Điểm xét ${input.score.toFixed(3)}`, input.cohort]);
  }
  return join([
    `Học bổng dự kiến: ${input.classification} × ${input.multiplier}`,
    `Điểm xét ${input.score.toFixed(3)}`,
    input.amount !== null && vnd(input.amount),
    input.cohort,
  ]);
}

export type TuitionShareInput = {
  total: number;
  semester: number;
  extra: number;
  programName: string;
  /** School year as displayed, e.g. "2026–27". */
  year: string;
};

export function tuitionShareText(input: TuitionShareInput): string {
  const breakdown = input.extra > 0 ? ` (học kỳ ${vnd(input.semester)} + học lại ${vnd(input.extra)})` : '';
  return join([`Học phí học kỳ: ${vnd(input.total)}${breakdown}`, input.programName, input.year]);
}

export type CreditsShareInput = {
  status: 'safe' | 'near' | 'exceeded';
  failedCredits: number;
  maxCredits: number;
  creditsLeft: number;
  totalCredits: number;
  cohort: string;
};

const CREDIT_STATUS: Record<CreditsShareInput['status'], string> = {
  safe: 'An toàn',
  near: 'Sát ngưỡng',
  exceeded: 'Vượt ngưỡng',
};

export function creditsShareText(input: CreditsShareInput): string {
  const head =
    input.creditsLeft < 0
      ? `Đã vượt mức: không đạt ${input.failedCredits} TC, tối đa ${input.maxCredits} TC`
      : `Còn được không đạt ${input.creditsLeft}/${input.maxCredits} TC`;
  return join([`${head} (${input.totalCredits} TC toàn khóa)`, CREDIT_STATUS[input.status], input.cohort]);
}
