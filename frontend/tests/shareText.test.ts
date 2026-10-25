import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  courseTargetShareText,
  creditsShareText,
  gpaShareText,
  scholarshipShareText,
  targetRetakeShareText,
  targetRoadmapShareText,
  targetTermShareText,
  tuitionShareText,
  vnd,
} from '../src/utils/shareText.ts';

describe('vnd', () => {
  it('groups thousands with dots', () => {
    assert.equal(vnd(10603000), '10.603.000 đ');
    assert.equal(vnd(0), '0 đ');
  });
});

describe('gpaShareText', () => {
  it('summarises the semester', () => {
    assert.equal(
      gpaShareText({ gpa: 3.452, tier: 'Giỏi', credits: 18, cohort: 'K50' }),
      'GPA học kỳ: 3.45/4 · Giỏi · 18 TC · K50',
    );
  });
});

describe('target GPA texts', () => {
  it('term plan, feasible / achieved / impossible', () => {
    const base = { requiredGpa: 3.6, targetGpa: 3.2, currentGpa: 3.0, cohort: 'K50' };
    assert.equal(targetTermShareText({ ...base, status: 'feasible' }), 'Kỳ tới cần GPA 3.60/4 để đạt tích lũy 3.20 · K50');
    assert.equal(targetTermShareText({ ...base, status: 'achieved' }), 'Đã đạt mục tiêu tích lũy 3.20 (hiện 3.00/4) · K50');
    assert.match(targetTermShareText({ ...base, requiredGpa: 4.37, status: 'impossible' }), /vượt khả năng.*4\.37\/4/);
  });
  it('retake', () => {
    assert.equal(
      targetRetakeShareText({ courses: 2, credits: 6, baselineGpa: 2.85, newGpa: 2.97, deltaGpa: 0.12, cohort: 'K51' }),
      'Cải thiện 2 môn (6 TC): GPA tích lũy từ 2.85 lên 2.97 (+0.12) · K51',
    );
  });
  it('roadmap', () => {
    const base = { targetGpa: 3.2, neededGpa: 3.05, maxGpa: 3.62, remainingCredits: 75, terms: 5, cohort: 'K50' };
    assert.equal(
      targetRoadmapShareText({ ...base, feasible: true }),
      'Để tốt nghiệp GPA 3.20 cần giữ 3.05/4 mỗi kỳ, còn 75 TC (~5 học kỳ) · K50',
    );
    assert.equal(
      targetRoadmapShareText({ ...base, feasible: false }),
      'Mục tiêu tốt nghiệp 3.20 chưa khả thi, GPA cao nhất có thể đạt 3.62/4 · K50',
    );
  });
});

describe('courseTargetShareText', () => {
  const base = { letter: 'D', isPassGrade: true, requiredScore: 2.75, coveredPercent: 40, bestLetter: null, cohort: 'K50' };
  it('possible', () => {
    assert.equal(
      courseTargetShareText({ ...base, status: 'possible' }),
      'Thi cuối kỳ cần 2.75/10 để đạt D (qua môn) · Đã có 40% · K50',
    );
  });
  it('achieved and impossible', () => {
    assert.equal(courseTargetShareText({ ...base, status: 'achieved' }), 'Đã đủ điểm để đạt D (qua môn) · Đã có 40% · K50');
    assert.equal(
      courseTargetShareText({ ...base, letter: 'A', isPassGrade: false, status: 'impossible', bestLetter: 'B' }),
      'Thi 10 vẫn chưa đủ để đạt A (cao nhất đạt B) · Đã có 40% · K50',
    );
    assert.match(courseTargetShareText({ ...base, status: 'impossible' }), /không qua được môn/);
  });
});

describe('scholarshipShareText', () => {
  it('includes the amount when there is one', () => {
    assert.equal(
      scholarshipShareText({ classification: 'Giỏi', multiplier: 1.25, score: 3.464, amount: 15543750, cohort: 'K50' }),
      'Học bổng dự kiến: Giỏi × 1.25 · Điểm xét 3.464 · 15.543.750 đ · K50',
    );
  });
  it('omits the amount when none and handles not reached', () => {
    assert.equal(
      scholarshipShareText({ classification: 'Khá', multiplier: 1, score: 2.9, amount: null, cohort: 'K50' }),
      'Học bổng dự kiến: Khá × 1 · Điểm xét 2.900 · K50',
    );
    assert.equal(
      scholarshipShareText({ classification: null, multiplier: 0, score: 2.1, amount: null, cohort: 'K50' }),
      'Học bổng dự kiến: chưa đạt mức học bổng · Điểm xét 2.100 · K50',
    );
  });
});

describe('tuitionShareText', () => {
  it('shows the retake breakdown only when there is one', () => {
    assert.equal(
      tuitionShareText({ total: 10603000, semester: 8950000, extra: 1653000, programName: 'Sư phạm Toán học', year: '2026–27' }),
      'Học phí học kỳ: 10.603.000 đ (học kỳ 8.950.000 đ + học lại 1.653.000 đ) · Sư phạm Toán học · 2026–27',
    );
    assert.equal(
      tuitionShareText({ total: 8950000, semester: 8950000, extra: 0, programName: 'Sư phạm Toán học', year: '2026–27' }),
      'Học phí học kỳ: 8.950.000 đ · Sư phạm Toán học · 2026–27',
    );
  });
});

describe('creditsShareText', () => {
  it('left and exceeded', () => {
    assert.equal(
      creditsShareText({ status: 'safe', failedCredits: 2, maxCredits: 6, creditsLeft: 4, totalCredits: 130, cohort: 'K50' }),
      'Còn được không đạt 4/6 TC (130 TC toàn khóa) · An toàn · K50',
    );
    assert.equal(
      creditsShareText({ status: 'exceeded', failedCredits: 8, maxCredits: 6, creditsLeft: -2, totalCredits: 130, cohort: 'K50' }),
      'Đã vượt mức: không đạt 8 TC, tối đa 6 TC (130 TC toàn khóa) · Vượt ngưỡng · K50',
    );
  });
});
