import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { getGradeScale, type Cohort, type CourseGroup, type LetterGrade } from '../src/utils/gradeScale.ts';
import { getGradeTone } from '../src/utils/gradeTone.ts';

function toneOf(cohort: Cohort, group: CourseGroup, letter: LetterGrade) {
  const row = getGradeScale(cohort, group).rows.find((candidate) => candidate.letter === letter);
  assert.ok(row, `${letter} missing from ${cohort}/${group}`);
  return getGradeTone(row);
}

describe('getGradeTone', () => {
  it('bands passing grades by letter', () => {
    assert.equal(toneOf('K48-K49', 'foundation', 'A'), 'excellent');
    assert.equal(toneOf('K48-K49', 'foundation', 'B+'), 'excellent');
    assert.equal(toneOf('K48-K49', 'foundation', 'B'), 'good');
    assert.equal(toneOf('K48-K49', 'foundation', 'C+'), 'good');
    assert.equal(toneOf('K48-K49', 'foundation', 'C'), 'fair');
    assert.equal(toneOf('K48-K49', 'foundation', 'D'), 'weak');
  });

  it('colours a grade as failing wherever the scale fails it', () => {
    // K51 major courses need C (5.5) to pass, so D+ and D fail there but pass in foundation courses.
    assert.equal(toneOf('K51', 'remaining', 'D+'), 'fail');
    assert.equal(toneOf('K51', 'remaining', 'D'), 'fail');
    assert.equal(toneOf('K51', 'foundation', 'D+'), 'fair');
    assert.equal(toneOf('K51', 'remaining', 'C'), 'fair');
  });

  it('always marks F grades as failing', () => {
    assert.equal(toneOf('K50', 'foundation', 'F+'), 'fail');
    assert.equal(toneOf('K50', 'remaining', 'F'), 'fail');
  });
});
