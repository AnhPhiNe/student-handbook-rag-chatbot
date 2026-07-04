export type Cohort = 'K48-K49' | 'K50' | 'K51';
export type CourseGroup = 'foundation' | 'remaining';
export type LetterGrade = 'A' | 'B+' | 'B' | 'C+' | 'C' | 'D+' | 'D' | 'F+' | 'F';
export type GradeStatus = 'Đạt' | 'Không đạt';

export type GradeScaleRow = {
  letter: LetterGrade;
  score4: number;
  min10: number;
  max10: number;
  status: GradeStatus;
};

export type GradeScaleDefinition = {
  id: CourseGroup;
  label: string;
  shortLabel: string;
  applicability: string;
  passThreshold: number;
  rows: GradeScaleRow[];
};

export type CourseInput = {
  id: string;
  name: string;
  credits: string;
  inputType: 'score10' | 'letter';
  score10: string;
  letter: LetterGrade;
  courseGroup?: CourseGroup;
};

const SCORE4_BY_LETTER: Record<LetterGrade, number> = {
  A: 4.0,
  'B+': 3.5,
  B: 3.0,
  'C+': 2.5,
  C: 2.0,
  'D+': 1.5,
  D: 1.0,
  'F+': 0.5,
  F: 0.0,
};

const SCORE_RANGES: Array<Omit<GradeScaleRow, 'score4' | 'status'>> = [
  { letter: 'A', min10: 8.5, max10: 10.0 },
  { letter: 'B+', min10: 7.8, max10: 8.4 },
  { letter: 'B', min10: 7.0, max10: 7.7 },
  { letter: 'C+', min10: 6.3, max10: 6.9 },
  { letter: 'C', min10: 5.5, max10: 6.2 },
  { letter: 'D+', min10: 4.8, max10: 5.4 },
  { letter: 'D', min10: 4.0, max10: 4.7 },
  { letter: 'F+', min10: 3.0, max10: 3.9 },
  { letter: 'F', min10: 0.0, max10: 2.9 },
];

function makeRows(passThreshold: number): GradeScaleRow[] {
  return SCORE_RANGES.map((row) => ({
    ...row,
    score4: SCORE4_BY_LETTER[row.letter],
    status: row.max10 >= passThreshold ? 'Đạt' : 'Không đạt',
  }));
}

const COMMON_SCALE: GradeScaleDefinition = {
  id: 'foundation',
  label: 'Bảng quy đổi chung',
  shortLabel: 'Bảng chung',
  applicability: 'Áp dụng chung cho các học phần có đánh giá theo thang điểm 10.',
  passThreshold: 4.0,
  rows: makeRows(4.0),
};

export const GRADE_SCALE_BY_COHORT: Record<Cohort, GradeScaleDefinition[]> = {
  'K48-K49': [
    {
      ...COMMON_SCALE,
      label: 'Bảng quy đổi chung K48-K49',
    },
  ],
  K50: [
    {
      ...COMMON_SCALE,
      label: 'Bảng quy đổi chung K50',
    },
  ],
  K51: [
    {
      id: 'foundation',
      label: 'Môn chung / nhóm học phần nền tảng',
      shortLabel: 'Môn chung',
      applicability: 'Học phần giáo dục đại cương hoặc học phần chung thuộc nhóm học phần nền tảng.',
      passThreshold: 4.0,
      rows: makeRows(4.0),
    },
    {
      id: 'remaining',
      label: 'Môn chuyên ngành / các học phần còn lại',
      shortLabel: 'Môn chuyên ngành',
      applicability: 'Các học phần còn lại. D và D+ vẫn quy đổi hệ 4, nhưng không được xem là đạt học phần.',
      passThreshold: 5.5,
      rows: makeRows(5.5),
    },
  ],
};

export const GRADE_SCALE = GRADE_SCALE_BY_COHORT['K48-K49'][0].rows;

export function normalizeFrontendCohort(cohort: string | null | undefined): Cohort {
  if (cohort === 'K50-K51') return 'K51';
  if (cohort === 'K50' || cohort === 'K51' || cohort === 'K48-K49') return cohort;
  return 'K48-K49';
}

export function isNewCohort(cohort: Cohort): boolean {
  return cohort === 'K50' || cohort === 'K51';
}

export function isSplitGradeCohort(cohort: Cohort): boolean {
  return cohort === 'K51';
}

export function getDefaultCourseGroup(cohort: Cohort): CourseGroup {
  return isSplitGradeCohort(cohort) ? 'remaining' : 'foundation';
}

export function getCourseGroupOptions(cohort: Cohort): GradeScaleDefinition[] {
  return GRADE_SCALE_BY_COHORT[cohort];
}

export function getGradeScales(cohort: Cohort): GradeScaleDefinition[] {
  return GRADE_SCALE_BY_COHORT[cohort];
}

export function getGradeScale(cohort: Cohort, courseGroup?: CourseGroup): GradeScaleDefinition {
  const scales = GRADE_SCALE_BY_COHORT[cohort];
  const fallback = scales[0];
  return scales.find((scale) => scale.id === (courseGroup ?? getDefaultCourseGroup(cohort))) ?? fallback;
}

export function convertScore10ToGrade(
  score: number,
  cohort: Cohort = 'K48-K49',
  courseGroup?: CourseGroup,
): GradeScaleRow | null {
  if (!Number.isFinite(score) || score < 0 || score > 10) return null;
  const scale = getGradeScale(cohort, courseGroup);
  return scale.rows.find((row) => score >= row.min10 && score <= row.max10) ?? null;
}

export function convertLetterToScore4(
  letter: LetterGrade,
  cohort: Cohort = 'K48-K49',
  courseGroup?: CourseGroup,
): GradeScaleRow {
  const scale = getGradeScale(cohort, courseGroup);
  return scale.rows.find((row) => row.letter === letter) ?? scale.rows[scale.rows.length - 1];
}

export function getCourseGrade(course: CourseInput, cohort: Cohort = 'K48-K49'): GradeScaleRow | null {
  if (course.inputType === 'letter') {
    return convertLetterToScore4(course.letter, cohort, course.courseGroup);
  }
  const score = Number(course.score10);
  return convertScore10ToGrade(score, cohort, course.courseGroup);
}

export function calculateGpa(courses: CourseInput[], cohort: Cohort = 'K48-K49'): {
  gpa: number;
  totalCredits: number;
  countedCourses: number;
  error?: string;
} {
  let totalCredits = 0;
  let totalWeightedScore = 0;
  let countedCourses = 0;

  for (const course of courses) {
    const credits = Number(course.credits);
    const grade = getCourseGrade(course, cohort);
    const hasStarted =
      course.name.trim() ||
      course.credits.trim() ||
      course.score10.trim() ||
      course.inputType === 'letter';

    if (!hasStarted) continue;
    if (!Number.isFinite(credits) || credits <= 0) {
      return { gpa: 0, totalCredits: 0, countedCourses: 0, error: 'Vui lòng nhập số tín chỉ lớn hơn 0 cho các môn cần tính.' };
    }
    if (!grade) {
      return { gpa: 0, totalCredits: 0, countedCourses: 0, error: 'Vui lòng nhập điểm thang 10 từ 0 đến 10 hoặc chọn điểm chữ hợp lệ.' };
    }

    totalCredits += credits;
    totalWeightedScore += grade.score4 * credits;
    countedCourses += 1;
  }

  if (totalCredits <= 0) {
    return { gpa: 0, totalCredits: 0, countedCourses: 0, error: 'Vui lòng nhập ít nhất một môn học để tính GPA.' };
  }

  return {
    gpa: Math.round((totalWeightedScore / totalCredits) * 100) / 100,
    totalCredits,
    countedCourses,
  };
}
