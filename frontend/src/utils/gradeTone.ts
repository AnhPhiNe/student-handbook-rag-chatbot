import type { GradeScaleRow, LetterGrade } from './gradeScale';

export type GradeTone = 'excellent' | 'good' | 'fair' | 'weak' | 'fail';

const TONE_BY_LETTER: Record<LetterGrade, GradeTone> = {
  A: 'excellent',
  'B+': 'excellent',
  B: 'good',
  'C+': 'good',
  C: 'fair',
  'D+': 'fair',
  D: 'weak',
  'F+': 'fail',
  F: 'fail',
};

/**
 * Colour band for a letter grade. A grade that fails the course is always 'fail',
 * so D+ reads red for K51 major courses but amber where it still passes.
 */
export function getGradeTone(row: Pick<GradeScaleRow, 'letter' | 'status'>): GradeTone {
  return row.status === 'Không đạt' ? 'fail' : TONE_BY_LETTER[row.letter];
}
