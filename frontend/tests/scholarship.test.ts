import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { calculateScholarshipScore, getFinalSemesterMinCredits } from '../src/utils/scholarship.ts';

describe('calculateScholarshipScore', () => {
  it('3.45 / 88 gives score 3.464 and Giỏi x1.25', () => {
    const result = calculateScholarshipScore(3.45, 88);
    assert.ok(result);
    assert.equal(result.score, 3.464);
    assert.equal(result.classification, 'Giỏi');
    assert.equal(result.multiplier, 1.25);
  });

  it('4 / 100 is Xuất sắc', () => {
    assert.equal(calculateScholarshipScore(4, 100)?.classification, 'Xuất sắc');
  });

  it('2.5 / 70 is Khá at exactly 2.56', () => {
    const result = calculateScholarshipScore(2.5, 70);
    assert.ok(result);
    assert.equal(result.score, 2.56);
    assert.equal(result.classification, 'Khá');
    assert.equal(result.multiplier, 1);
  });

  it('3.7 / 85 is capped to Giỏi by conduct', () => {
    assert.equal(calculateScholarshipScore(3.7, 85)?.classification, 'Giỏi');
  });

  it('2.4 / 90 reaches no tier', () => {
    const result = calculateScholarshipScore(2.4, 90);
    assert.ok(result);
    assert.equal(result.classification, null);
    assert.equal(result.multiplier, 0);
  });

  it('returns null for out-of-range input', () => {
    assert.equal(calculateScholarshipScore(-0.1, 80), null);
    assert.equal(calculateScholarshipScore(4.1, 80), null);
    assert.equal(calculateScholarshipScore(3, -1), null);
    assert.equal(calculateScholarshipScore(3, 101), null);
    assert.equal(calculateScholarshipScore(Number.NaN, 80), null);
  });
});

describe('getFinalSemesterMinCredits', () => {
  it('is 6 for K49 and K50, 11 for K51', () => {
    assert.equal(getFinalSemesterMinCredits('K49'), 6);
    assert.equal(getFinalSemesterMinCredits('K50'), 6);
    assert.equal(getFinalSemesterMinCredits('K51'), 11);
  });
});
