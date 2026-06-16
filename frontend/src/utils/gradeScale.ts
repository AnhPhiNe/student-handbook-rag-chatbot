export type LetterGrade = 'A' | 'B+' | 'B' | 'C+' | 'C' | 'D+' | 'D' | 'F+' | 'F';

export type GradeScaleRow = {
  letter: LetterGrade;
  score4: number;
  min10: number;
  max10: number;
  status: 'Đạt' | 'Không đạt';
};

export type CourseInput = {
  id: string;
  name: string;
  credits: string;
  inputType: 'score10' | 'letter';
  score10: string;
  letter: LetterGrade;
};

export const GRADE_SCALE: GradeScaleRow[] = [
  { letter: 'A', score4: 4.0, min10: 8.5, max10: 10.0, status: 'Đạt' },
  { letter: 'B+', score4: 3.5, min10: 7.8, max10: 8.4, status: 'Đạt' },
  { letter: 'B', score4: 3.0, min10: 7.0, max10: 7.7, status: 'Đạt' },
  { letter: 'C+', score4: 2.5, min10: 6.3, max10: 6.9, status: 'Đạt' },
  { letter: 'C', score4: 2.0, min10: 5.5, max10: 6.2, status: 'Đạt' },
  { letter: 'D+', score4: 1.5, min10: 4.8, max10: 5.4, status: 'Đạt' },
  { letter: 'D', score4: 1.0, min10: 4.0, max10: 4.7, status: 'Đạt' },
  { letter: 'F+', score4: 0.5, min10: 3.0, max10: 3.9, status: 'Không đạt' },
  { letter: 'F', score4: 0.0, min10: 0.0, max10: 2.9, status: 'Không đạt' },
];

export function convertScore10ToGrade(score: number): GradeScaleRow | null {
  if (!Number.isFinite(score) || score < 0 || score > 10) return null;
  return GRADE_SCALE.find((row) => score >= row.min10 && score <= row.max10) ?? null;
}

export function convertLetterToScore4(letter: LetterGrade): GradeScaleRow {
  return GRADE_SCALE.find((row) => row.letter === letter) ?? GRADE_SCALE[GRADE_SCALE.length - 1];
}

export function getCourseGrade(course: CourseInput): GradeScaleRow | null {
  if (course.inputType === 'letter') return convertLetterToScore4(course.letter);
  const score = Number(course.score10);
  return convertScore10ToGrade(score);
}

export function calculateGpa(courses: CourseInput[]): {
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
    const grade = getCourseGrade(course);
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
