import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { hasStoredProfile, integerCredits, parseStoredProfile } from '../src/utils/studentProfile.ts';

describe('parseStoredProfile', () => {
  it('keeps the existing three string fields', () => {
    const profile = parseStoredProfile({ currentGpa: '3.1', currentCredits: '60', totalDegreeCredits: '130' });
    assert.deepEqual(profile, { currentGpa: '3.1', currentCredits: '60', totalDegreeCredits: '130' });
  });
  it('returns an empty profile for corrupt values', () => {
    for (const bad of [null, undefined, 5, 'x', [], true]) {
      assert.deepEqual(parseStoredProfile(bad), { currentGpa: '', currentCredits: '', totalDegreeCredits: '' });
    }
  });
  it('drops non-string fields', () => {
    assert.equal(parseStoredProfile({ currentGpa: 3.2, currentCredits: null }).currentGpa, '');
  });
  it('normalises a valid last semester GPA and ignores out-of-range ones', () => {
    assert.equal(parseStoredProfile({ lastSemesterGpa: '3.456' }).lastSemesterGpa, '3.46');
    assert.equal(parseStoredProfile({ lastSemesterGpa: '4.5' }).lastSemesterGpa, undefined);
    assert.equal(parseStoredProfile({ lastSemesterGpa: 'abc' }).lastSemesterGpa, undefined);
    assert.equal(parseStoredProfile({ lastSemesterGpa: '' }).lastSemesterGpa, undefined);
  });
});

describe('hasStoredProfile', () => {
  it('is false when everything is empty', () => {
    assert.equal(hasStoredProfile(parseStoredProfile({})), false);
    assert.equal(hasStoredProfile(parseStoredProfile({ lastSemesterGpa: '3.00' })), true);
  });
});

describe('integerCredits', () => {
  it('accepts whole numbers only', () => {
    assert.equal(integerCredits('130'), '130');
    assert.equal(integerCredits('130.5'), '');
    assert.equal(integerCredits(''), '');
    assert.equal(integerCredits('abc'), '');
  });
});
