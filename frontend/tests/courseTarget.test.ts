import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  analyzeCourseTarget,
  getGradeTarget,
  isTargetReached,
  requiredExamScore,
} from '../src/utils/courseTarget.ts';

const PASSING = [
  { letter: 'A', min10: 8.5 },
  { letter: 'B+', min10: 7.8 },
  { letter: 'B', min10: 7.0 },
  { letter: 'C+', min10: 6.3 },
  { letter: 'C', min10: 5.5 },
  { letter: 'D+', min10: 4.8 },
  { letter: 'D', min10: 4.0 },
];

function needs(columns: Array<{ weight: string; score: string }>) {
  const analysis = analyzeCourseTarget(columns, PASSING);
  return Object.fromEntries(analysis.targets.map((t) => [t.grade.letter, t]));
}

describe('analyzeCourseTarget', () => {
  it('rounds the course score to one decimal: scores 6 and 5.5 at 20%/20%', () => {
    const t = needs([
      { weight: '20', score: '6' },
      { weight: '20', score: '5.5' },
    ]);
    assert.equal(t.D.requiredScore, 2.75);
    assert.equal(t['D+'].requiredScore, 4.09);
    assert.equal(t.C.requiredScore, 5.25);
    assert.equal(t['C+'].requiredScore, 6.59);
    assert.equal(t.B.requiredScore, 7.75);
    assert.equal(t['B+'].requiredScore, 9.09);
    assert.equal(t.A.status, 'impossible');
  });

  it('matches the approved pass-grade examples', () => {
    const a = needs([
      { weight: '10', score: '8' },
      { weight: '40', score: '6.5' },
    ]);
    assert.equal(a.D.requiredScore, 1.1);
    const b = needs([
      { weight: '10', score: '10' },
      { weight: '30', score: '5.5' },
    ]);
    assert.equal(b.D.requiredScore, 2.17);
  });

  it('reports achieved when the columns alone reach the grade', () => {
    const t = needs([{ weight: '90', score: '9.5' }]);
    assert.equal(t.D.status, 'achieved');
    assert.equal(t.A.status, 'achieved');
  });

  it('reports impossible when even a 10 on the exam is not enough', () => {
    const t = needs([{ weight: '70', score: '1' }]);
    assert.equal(t.D.status, 'impossible');
    assert.equal(t.A.status, 'impossible');
  });

  it('with no exam weight left, reaches a grade only if the columns do (with the 0.05 rounding)', () => {
    const analysis = analyzeCourseTarget(
      [
        { weight: '50', score: '4' },
        { weight: '50', score: '3.9' },
      ],
      PASSING,
    );
    assert.equal(analysis.remainingWeight, 0);
    const byLetter = Object.fromEntries(analysis.targets.map((t) => [t.grade.letter, t]));
    assert.equal(byLetter.D.status, 'achieved'); // 3.95 rounds to 4.0
    assert.equal(byLetter.D.requiredScore, null);
    assert.equal(byLetter['D+'].status, 'impossible');
    const low = analyzeCourseTarget(
      [
        { weight: '50', score: '4' },
        { weight: '50', score: '3.8' },
      ],
      PASSING,
    );
    assert.equal(low.targets[low.targets.length - 1].status, 'impossible'); // 3.9 < 3.95
  });

  it('is not ready while a weighted column has no score', () => {
    const analysis = analyzeCourseTarget(
      [
        { weight: '20', score: '6' },
        { weight: '20', score: '' },
      ],
      PASSING,
    );
    assert.equal(analysis.isReady, false);
    assert.equal(analysis.errorMessage, null);
  });

  it('ignores a zero-weight column with no score, but needs at least one weighted column', () => {
    assert.equal(
      analyzeCourseTarget(
        [
          { weight: '30', score: '6' },
          { weight: '0', score: '' },
        ],
        PASSING,
      ).isReady,
      true,
    );
    assert.equal(analyzeCourseTarget([{ weight: '', score: '' }], PASSING).isReady, false);
  });

  it('flags total weight above 100 as an error', () => {
    const analysis = analyzeCourseTarget(
      [
        { weight: '60', score: '6' },
        { weight: '50', score: '6' },
      ],
      PASSING,
    );
    assert.equal(analysis.isReady, false);
    assert.equal(analysis.hasWeightOverflow, true);
    assert.equal(analysis.errorMessage, 'Tổng trọng số đang là 110%, vượt quá 100%. Hãy sửa lại các cột.');
  });

  it('flags invalid weights and scores', () => {
    const badWeight = analyzeCourseTarget([{ weight: '150', score: '6' }], PASSING);
    assert.equal(badWeight.isReady, false);
    assert.equal(badWeight.errorMessage, 'Trọng số mỗi cột phải từ 0 đến 100%.');
    const badScore = analyzeCourseTarget([{ weight: '30', score: '11' }], PASSING);
    assert.equal(badScore.isReady, false);
    assert.equal(badScore.errorMessage, 'Điểm mỗi cột phải từ 0 đến 10.');
  });
});

describe('requiredExamScore', () => {
  it('never understates: the returned score always reaches the grade', () => {
    for (const min of [4.0, 4.8, 5.5, 6.3, 7.0, 7.8, 8.5]) {
      for (let accTenths = 0; accTenths <= 80; accTenths += 1) {
        const acc = accTenths / 10 + 0.037;
        for (const rem of [10, 20, 30, 40, 50, 60, 70, 100]) {
          const need = requiredExamScore(min, acc, rem);
          if (need <= 0) {
            assert.ok(isTargetReached(min, acc), `${min}/${acc}/${rem}: claimed secured`);
            continue;
          }
          assert.ok(isTargetReached(min, acc + (need * rem) / 100), `${min}/${acc}/${rem}: need ${need} falls short`);
        }
      }
    }
  });

  it('is minimal on the 0.01 grid', () => {
    for (const min of [4.0, 5.5, 8.5]) {
      for (let accTenths = 0; accTenths <= 60; accTenths += 1) {
        const acc = accTenths / 10 + 0.013;
        const need = requiredExamScore(min, acc, 60);
        if (need <= 0.01) continue;
        const lower = Math.round((need - 0.01) * 100) / 100;
        assert.ok(!isTargetReached(min, acc + (lower * 60) / 100), `${min}/${acc}: ${need} is not the smallest`);
      }
    }
  });

  it('survives float noise on exact boundaries', () => {
    assert.equal(requiredExamScore(4.0, 0.2 * 6 + 0.2 * 5.5, 60), 2.75);
  });
});

describe('getGradeTarget', () => {
  it('treats exactly min - 0.05 as reached when there is no exam', () => {
    assert.equal(getGradeTarget({ min10: 4.0 }, 3.95, 0).status, 'achieved');
    assert.equal(getGradeTarget({ min10: 4.0 }, 3.94, 0).status, 'impossible');
  });
});
