/**
 * Course-target maths: the final-exam score needed to reach a letter grade.
 * Pure functions, no React. Quy chế Điều 10 khoản 2 rounds the course score to ONE decimal,
 * so a grade whose lower bound is `min` is reached once the raw course score is >= min - 0.05.
 */

export interface ScoreColumn {
  weight: string;
  score: string;
}

export type TargetStatus = 'possible' | 'achieved' | 'impossible';

export interface GradeTargetResult<T extends { min10: number }> {
  grade: T;
  /** Exam score needed on a 0.01 grid, or null when there is no exam left to sit. */
  requiredScore: number | null;
  status: TargetStatus;
}

export interface CourseTargetAnalysis<T extends { min10: number }> {
  totalWeight: number;
  remainingWeight: number;
  accumulatedScore: number;
  weightedCount: number;
  hasWeightOverflow: boolean;
  /** True when every weighted column has a valid score and nothing is out of range. */
  isReady: boolean;
  errorMessage: string | null;
  targets: Array<GradeTargetResult<T>>;
}

/** Course scores are rounded to one decimal, so 3.95 already counts as 4.0. */
export const ROUNDING_HALF_STEP = 0.05;
/** A required exam score above this is reachable but hard. */
export const HARD_FINAL_SCORE = 8;
/** Tolerance for floating-point noise, far below the 0.01 exam-score grid. */
const EPSILON = 1e-6;

export function isWeightInvalid(raw: string): boolean {
  if (raw === '') return false;
  const value = Number(raw);
  return !Number.isFinite(value) || value < 0 || value > 100;
}

export function isScoreInvalid(raw: string): boolean {
  if (raw === '') return false;
  const value = Number(raw);
  return !Number.isFinite(value) || value < 0 || value > 10;
}

/** Whether a course score of `courseScore` (unrounded) reaches the grade starting at `min10`. */
export function isTargetReached(min10: number, courseScore: number): boolean {
  return courseScore + EPSILON >= min10 - ROUNDING_HALF_STEP;
}

/**
 * Smallest exam score (0.01 grid) that reaches `min10`, given the accumulated score and the
 * remaining weight in percent. Zero or negative means the grade is already secured; the caller
 * must handle remainingWeight = 0 itself (there is no exam to sit).
 */
export function requiredExamScore(min10: number, accumulated: number, remainingWeight: number): number {
  const raw = ((min10 - ROUNDING_HALF_STEP - accumulated) * 100) / remainingWeight;
  const needed = Math.ceil(raw * 100 - EPSILON) / 100;
  return needed === 0 ? 0 : needed; // avoid -0
}

export function getGradeTarget<T extends { min10: number }>(
  grade: T,
  accumulated: number,
  remainingWeight: number,
): GradeTargetResult<T> {
  if (remainingWeight <= 0) {
    return { grade, requiredScore: null, status: isTargetReached(grade.min10, accumulated) ? 'achieved' : 'impossible' };
  }
  const requiredScore = requiredExamScore(grade.min10, accumulated, remainingWeight);
  const status: TargetStatus = requiredScore <= 0 ? 'achieved' : requiredScore > 10 ? 'impossible' : 'possible';
  return { grade, requiredScore, status };
}

export function analyzeCourseTarget<T extends { min10: number }>(
  columns: ScoreColumn[],
  passingGrades: T[],
): CourseTargetAnalysis<T> {
  let totalWeight = 0;
  let accumulatedScore = 0;
  let weightedCount = 0;
  let hasInvalidWeight = false;
  let hasInvalidScore = false;
  let hasMissingScore = false;

  for (const column of columns) {
    const weight = Number(column.weight);
    const score = Number(column.score);
    const weightOk = column.weight !== '' && !isWeightInvalid(column.weight);

    if (column.weight !== '') {
      if (!weightOk) {
        hasInvalidWeight = true;
      } else {
        totalWeight += weight;
        if (weight > 0) {
          weightedCount += 1;
          if (column.score === '') hasMissingScore = true;
        }
      }
    }

    if (column.score !== '') {
      if (isScoreInvalid(column.score)) hasInvalidScore = true;
      else if (weightOk) accumulatedScore += (score * weight) / 100;
    }
  }

  const remainingWeight = Math.max(0, 100 - totalWeight);
  const hasWeightOverflow = totalWeight > 100;

  let errorMessage: string | null = null;
  if (hasWeightOverflow) errorMessage = `Tổng trọng số đang là ${totalWeight}%, vượt quá 100%. Hãy sửa lại các cột.`;
  else if (hasInvalidWeight) errorMessage = 'Trọng số mỗi cột phải từ 0 đến 100%.';
  else if (hasInvalidScore) errorMessage = 'Điểm mỗi cột phải từ 0 đến 10.';

  // A weighted column without a score would count as 0 and show alarming targets, so it blocks the result.
  const isReady = errorMessage === null && !hasMissingScore && weightedCount > 0;

  return {
    totalWeight,
    remainingWeight,
    accumulatedScore,
    weightedCount,
    hasWeightOverflow,
    isReady,
    errorMessage,
    targets: passingGrades.map((grade) => getGradeTarget(grade, accumulatedScore, remainingWeight)),
  };
}
