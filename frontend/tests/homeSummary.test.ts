import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { summarizeProfile } from '../src/utils/homeSummary.ts';

const base = { currentGpa: '', currentCredits: '', totalDegreeCredits: '' };

describe('summarizeProfile', () => {
  it('reports no profile for an empty save', () => {
    const s = summarizeProfile(base);
    assert.equal(s.hasProfile, false);
    assert.equal(s.gpa, null);
    assert.equal(s.credits, null);
  });
  it('reads GPA with a decimal comma and rejects out-of-range values', () => {
    assert.equal(summarizeProfile({ ...base, currentGpa: '3,2' }).gpa, 3.2);
    assert.equal(summarizeProfile({ ...base, currentGpa: '3,2' }).gpaPercent, 80);
    assert.equal(summarizeProfile({ ...base, currentGpa: '5' }).gpa, null);
  });
  it('needs both credit numbers', () => {
    assert.equal(summarizeProfile({ ...base, currentCredits: '60' }).credits, null);
    assert.deepEqual(summarizeProfile({ ...base, currentCredits: '60', totalDegreeCredits: '135' }).credits, {
      done: 60,
      total: 135,
      percent: 44,
    });
  });
});
