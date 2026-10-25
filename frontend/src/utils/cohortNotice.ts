import { GRADE_SCALE_BY_COHORT, isSplitGradeCohort, type Cohort } from './gradeScale.ts';

export const TOOL_TABS = new Set([
  'gpa',
  'target-gpa',
  'course-target',
  'scholarship',
  'tuition',
  'credits',
]);

/** "C (5.5)" style label of the lowest passing grade of a scale. */
function passLabel(cohort: Cohort, group: 'foundation' | 'remaining'): string {
  const scale = GRADE_SCALE_BY_COHORT[cohort].find((s) => s.id === group);
  if (!scale) return '';
  const passing = scale.rows.filter((row) => row.status === 'Đạt');
  const lowest = passing[passing.length - 1];
  return lowest ? `${lowest.letter} (${scale.passThreshold.toFixed(1)})` : '';
}

/** Short grading note shown when the cohort changes. */
export function cohortChangeMessage(cohort: Cohort, keptNote = ''): string {
  const body = isSplitGradeCohort(cohort)
    ? `môn chuyên ngành đạt từ ${passLabel(cohort, 'remaining')}, môn đại cương từ ${passLabel(cohort, 'foundation').split(' ')[0]}.`
    : `mọi môn đạt từ ${passLabel(cohort, 'remaining')}.`;
  return `Đã chuyển sang ${cohort}: ${body}${keptNote ? ` ${keptNote}` : ''}`;
}

/** Whether a toast is due: a real change, between known cohorts, on a tool tab. */
export function shouldNotifyCohortChange(
  previous: Cohort | null,
  next: Cohort,
  activeTab: string,
): boolean {
  return previous !== null && previous !== next && TOOL_TABS.has(activeTab);
}
