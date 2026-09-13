import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { calculateCreditThreshold } from '../src/utils/creditThreshold.ts';

describe('calculateCreditThreshold', () => {
  it('rounds a fractional 5% allowance down to whole credits', () => {
    assert.equal(calculateCreditThreshold(130, 0)?.maxCredits, 6); // 6.5
    assert.equal(calculateCreditThreshold(135, 0)?.maxCredits, 6); // 6.75
    assert.equal(calculateCreditThreshold(125, 0)?.maxCredits, 6); // 6.25
  });

  it('keeps an exact 5% allowance despite floating-point noise', () => {
    // 140 * 0.05 evaluates to 7.000000000000001 in IEEE-754.
    const result = calculateCreditThreshold(140, 0);
    assert.equal(result?.threshold, 7);
    assert.equal(result?.maxCredits, 7);
  });

  it('never rounds the allowance up', () => {
    for (let total = 1; total <= 300; total += 1) {
      const result = calculateCreditThreshold(total, 0);
      assert.ok(result, `no result for ${total}`);
      assert.ok(Number.isInteger(result.maxCredits), `${total}: ${result.maxCredits} is not whole`);
      assert.ok(result.maxCredits <= result.threshold, `${total}: rounded up`);
      assert.ok(result.threshold - result.maxCredits < 1, `${total}: rounded down too far`);
    }
  });

  it('reports the whole credits left before the limit', () => {
    assert.equal(calculateCreditThreshold(130, 4)?.creditsLeft, 2);
    assert.equal(calculateCreditThreshold(130, 6)?.creditsLeft, 0);
  });

  it('counts the excess against the rounded-down limit', () => {
    const result = calculateCreditThreshold(135, 7);
    assert.equal(result?.status, 'exceeded');
    assert.equal(result?.creditsLeft, -1);
  });

  it('classifies safe, near and exceeded', () => {
    assert.equal(calculateCreditThreshold(130, 5)?.status, 'safe'); // 5 / 6.5 = 77%
    assert.equal(calculateCreditThreshold(130, 6)?.status, 'near'); // 6 / 6.5 = 92%
    assert.equal(calculateCreditThreshold(130, 7)?.status, 'exceeded');
  });

  it('rejects invalid input', () => {
    assert.equal(calculateCreditThreshold(0, 0), null);
    assert.equal(calculateCreditThreshold(-130, 0), null);
    assert.equal(calculateCreditThreshold(Number.NaN, 0), null);
    assert.equal(calculateCreditThreshold(130, -1), null);
  });
});
