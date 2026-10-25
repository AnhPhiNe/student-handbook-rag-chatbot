import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { SCHOOL_YEARS, TUITION_RATES } from '../src/data/tuitionRates.ts';
import { estimateSemester, isTeacherTraining, retakeCost, semesterTuition } from '../src/utils/tuition.ts';

const math = TUITION_RATES.find((program) => program.code === '7140209');

describe('estimateSemester', () => {
  it('charges half the annual tuition for a main semester', () => {
    assert.ok(math);
    const result = estimateSemester(math, '2026-2027', 0);
    assert.equal(result.semester, 8_950_000);
    assert.equal(result.extra, 0);
    assert.equal(result.total, 8_950_000);
    assert.equal(result.annual, 17_900_000);
    assert.equal(result.perCredit, 551_000);
  });

  it('adds retaken credits at the per-credit price', () => {
    assert.ok(math);
    const result = estimateSemester(math, '2026-2027', 3);
    assert.equal(result.extra, 1_653_000);
    assert.equal(result.total, 10_603_000);
  });
});

describe('retakeCost', () => {
  it('is zero for zero, negative or invalid credits', () => {
    assert.equal(retakeCost(551_000, 0), 0);
    assert.equal(retakeCost(551_000, -2), 0);
    assert.equal(retakeCost(551_000, Number.NaN), 0);
  });

  it('halves the annual tuition', () => {
    assert.equal(semesterTuition(17_900_000), 8_950_000);
  });
});

describe('isTeacherTraining', () => {
  it('recognises teacher-training codes', () => {
    for (const code of ['7140209', '7140202', '5140201']) assert.equal(isTeacherTraining(code), true, code);
  });

  it('excludes other programs', () => {
    for (const code of ['7140101', '7140104', '7480201']) assert.equal(isTeacherTraining(code), false, code);
  });
});

describe('TUITION_RATES', () => {
  it('has positive tuition and per-credit price for every school year', () => {
    for (const program of TUITION_RATES) {
      for (const year of SCHOOL_YEARS) {
        assert.ok(program.annual[year] > 0, `${program.code} annual ${year}`);
        assert.ok(program.perCredit[year] > 0, `${program.code} perCredit ${year}`);
      }
    }
  });
});
