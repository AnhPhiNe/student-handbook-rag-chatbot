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
  letter: LetterGrade | '';
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

export const GRADE_SCALE_BY_COHORT: Record<Cohort, GradeScaleDefinition[]> = {
  'K48-K49': [
    {
      id: 'foundation',
      label: 'Môn chung / học phần đại cương',
      shortLabel: 'Đại cương',
      applicability: 'Học phần giáo dục đại cương hoặc học phần chung. Đạt từ điểm D (4.0) trở lên.',
      passThreshold: 4.0,
      rows: makeRows(4.0),
    },
    {
      id: 'remaining',
      label: 'Môn chuyên ngành / học phần còn lại',
      shortLabel: 'Chuyên ngành',
      applicability: 'Học phần cơ sở ngành, chuyên ngành. Đạt từ điểm D (4.0) trở lên (từ 3.9 trở xuống mới rớt).',
      passThreshold: 4.0,
      rows: makeRows(4.0),
    },
  ],
  K50: [
    {
      id: 'foundation',
      label: 'Môn chung / học phần đại cương',
      shortLabel: 'Đại cương',
      applicability: 'Học phần giáo dục đại cương hoặc học phần chung. Đạt từ điểm D (4.0) trở lên.',
      passThreshold: 4.0,
      rows: makeRows(4.0),
    },
    {
      id: 'remaining',
      label: 'Môn chuyên ngành / học phần còn lại',
      shortLabel: 'Chuyên ngành',
      applicability: 'Học phần cơ sở ngành, chuyên ngành. Đạt từ điểm D (4.0) trở lên (từ 3.9 trở xuống mới rớt).',
      passThreshold: 4.0,
      rows: makeRows(4.0),
    },
  ],
  K51: [
    {
      id: 'foundation',
      label: 'Môn chung / nhóm học phần nền tảng',
      shortLabel: 'Đại cương',
      applicability: 'Học phần giáo dục đại cương hoặc học phần chung thuộc nhóm học phần nền tảng. Đạt từ điểm D (4.0) trở lên.',
      passThreshold: 4.0,
      rows: makeRows(4.0),
    },
    {
      id: 'remaining',
      label: 'Môn chuyên ngành / các học phần còn lại',
      shortLabel: 'Chuyên ngành',
      applicability: 'Các học phần còn lại. Đạt từ điểm C (5.5) trở lên. D và D+ (từ 5.4 trở xuống) là không đạt (rớt).',
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

export function hasCourseGroup(_cohort?: Cohort): boolean {
  return true;
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

export function isCreditsInvalid(rawCredits: string): boolean {
  const trimmed = rawCredits.trim();
  if (trimmed === '') return false;
  const val = Number(trimmed.replace(',', '.'));
  return !Number.isFinite(val) || val <= 0 || val > 30;
}

export function isScore10Invalid(rawScore: string): boolean {
  const trimmed = rawScore.trim();
  if (trimmed === '') return false;
  const val = Number(trimmed.replace(',', '.'));
  return !Number.isFinite(val) || val < 0 || val > 10;
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
    if (!course.letter || course.letter.trim() === '') {
      return null;
    }
    return convertLetterToScore4(course.letter as LetterGrade, cohort, course.courseGroup);
  }
  if (course.score10.trim() === '') {
    return null;
  }
  const score = Number(course.score10.trim().replace(',', '.'));
  if (!Number.isFinite(score) || score < 0 || score > 10) {
    return null;
  }
  const rounded = Math.round(score * 10) / 10;
  return convertScore10ToGrade(rounded, cohort, course.courseGroup);
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
    const rawCredits = course.credits.trim();
    if (!rawCredits) continue;

    const credits = Number(rawCredits.replace(',', '.'));
    if (!Number.isFinite(credits) || credits <= 0) {
      continue;
    }

    const grade = getCourseGrade(course, cohort);
    if (!grade) {
      continue;
    }

    totalCredits += credits;
    totalWeightedScore += grade.score4 * credits;
    countedCourses += 1;
  }

  if (totalCredits <= 0 || countedCourses === 0) {
    return { gpa: 0, totalCredits: 0, countedCourses: 0 };
  }

  return {
    gpa: Math.round((totalWeightedScore / totalCredits) * 100) / 100,
    totalCredits,
    countedCourses,
  };
}
