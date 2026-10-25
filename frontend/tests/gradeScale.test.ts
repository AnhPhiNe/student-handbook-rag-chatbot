import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  convertScore10ToGrade,
  getDefaultCourseGroup,
  getGradeScale,
  isSplitGradeCohort,
  type Cohort,
} from '../src/utils/gradeScale.ts';

// Quy chế đào tạo Điều 10 khoản 2 điểm a. K51 uses the amended scale (QĐ 4743/QĐ-ĐHSP, from the 2025 intake):
// general-education courses pass from D, all remaining courses pass only from C.
const passingLetters = (cohort: Cohort, group?: 'foundation' | 'remaining') =>
  getGradeScale(cohort, group).rows.filter((row) => row.status === 'Đạt').map((row) => row.letter);

describe('grade scales per cohort', () => {
  it('K49 and K50 pass every course from D (4.0)', () => {
    for (const cohort of ['K49', 'K50'] as const) {
      assert.equal(isSplitGradeCohort(cohort), false);
      for (const group of ['foundation', 'remaining'] as const) {
        assert.deepEqual(passingLetters(cohort, group), ['A', 'B+', 'B', 'C+', 'C', 'D+', 'D']);
      }
      assert.equal(convertScore10ToGrade(4.0, cohort)?.status, 'Đạt');
      assert.equal(convertScore10ToGrade(3.9, cohort)?.status, 'Không đạt');
    }
  });

  it('K51 general-education courses pass from D, remaining courses from C', () => {
    assert.equal(isSplitGradeCohort('K51'), true);
    assert.deepEqual(passingLetters('K51', 'foundation'), ['A', 'B+', 'B', 'C+', 'C', 'D+', 'D']);
    assert.deepEqual(passingLetters('K51', 'remaining'), ['A', 'B+', 'B', 'C+', 'C']);
    assert.equal(convertScore10ToGrade(5.4, 'K51', 'remaining')?.status, 'Không đạt');
    assert.equal(convertScore10ToGrade(5.5, 'K51', 'remaining')?.status, 'Đạt');
    assert.equal(convertScore10ToGrade(4.0, 'K51', 'foundation')?.status, 'Đạt');
  });

  it('keeps the same letter bands and 4-point values for every cohort', () => {
    for (const cohort of ['K49', 'K50', 'K51'] as const) {
      const grade = (score: number) => convertScore10ToGrade(score, cohort, 'foundation');
      assert.deepEqual([grade(8.5)?.letter, grade(8.5)?.score4], ['A', 4]);
      assert.deepEqual([grade(7.8)?.letter, grade(7.8)?.score4], ['B+', 3.5]);
      assert.deepEqual([grade(6.2)?.letter, grade(6.2)?.score4], ['C', 2]);
      assert.deepEqual([grade(4.7)?.letter, grade(4.7)?.score4], ['D', 1]);
      assert.deepEqual([grade(3.0)?.letter, grade(3.0)?.score4], ['F+', 0.5]);
      assert.deepEqual([grade(2.9)?.letter, grade(2.9)?.score4], ['F', 0]);
    }
  });

  it('defaults K51 to the stricter group so a new course is not treated as passed too early', () => {
    assert.equal(getDefaultCourseGroup('K51'), 'remaining');
    assert.equal(getDefaultCourseGroup('K50'), 'foundation');
  });
});
