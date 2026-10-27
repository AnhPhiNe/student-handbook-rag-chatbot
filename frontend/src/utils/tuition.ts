import type { SchoolYear, TuitionProgram } from '../data/tuitionRates';

export interface TuitionEstimate {
  /** Tuition of one main semester (annual / 2). */
  semester: number;
  /** Cost of retaken / improved credits, charged per credit. */
  extra: number;
  /** semester + extra. */
  total: number;
  perCredit: number;
  annual: number;
}

/** HCMUE charges tuition per semester: a main semester is half of the annual tuition. */
export function semesterTuition(annual: number): number {
  return annual / 2;
}

/** The per-credit price applies only to retaken or improved credits. */
export function retakeCost(perCredit: number, credits: number): number {
  if (!Number.isFinite(credits) || credits <= 0) return 0;
  return perCredit * credits;
}

export function estimateSemester(program: TuitionProgram, year: SchoolYear, retakeCredits: number): TuitionEstimate {
  const annual = program.annual[year];
  const perCredit = program.perCredit[year];
  const semester = semesterTuition(annual);
  const extra = retakeCost(perCredit, retakeCredits);
  return { semester, extra, total: semester + extra, perCredit, annual };
}

/** Teacher-training programs (Nghi dinh 116 scope): 5140201 and 71402xx, not 7140101 / 7140104. */
export function isTeacherTraining(code: string): boolean {
  return code.slice(1, 5) === '1402';
}
