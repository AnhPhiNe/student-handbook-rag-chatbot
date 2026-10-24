import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  calculateTermPlan,
  calculateRetakeImpact,
  calculateRoadmapPlan,
  getCoursePrescription,
  getEquivalentLetter,
  format2,
  type RetakeCourse,
} from '../src/utils/targetGpaCalculations.ts';

describe('format2 & getEquivalentLetter helpers', () => {
  it('formats numbers to 2 decimal places safely', () => {
    assert.equal(format2(3.2), '3.20');
    assert.equal(format2(3.567), '3.57');
    assert.equal(format2(0), '0.00');
    assert.equal(format2(Number.NaN), '0.00');
    assert.equal(format2(Number.POSITIVE_INFINITY), '0.00');
  });

  it('maps gpa to equivalent letter grades correctly', () => {
    assert.equal(getEquivalentLetter(3.8), 'A (Xuất sắc)');
    assert.equal(getEquivalentLetter(3.6), 'A (Xuất sắc)');
    assert.equal(getEquivalentLetter(3.5), 'B+ (Giỏi)');
    assert.equal(getEquivalentLetter(3.2), 'B+ (Giỏi)');
    assert.equal(getEquivalentLetter(3.0), 'B (Khá)');
    assert.equal(getEquivalentLetter(2.5), 'B (Khá)');
    assert.equal(getEquivalentLetter(2.1), 'C+ đến B');
    assert.equal(getEquivalentLetter(0), 'C+ đến B');
    assert.equal(getEquivalentLetter(-1), 'C+ đến B');
  });
});

describe('calculateTermPlan', () => {
  it('calculates a feasible target in one term correctly', () => {
    // Current: GPA 3.0, 60 credits. Target: 3.2 in 15 credits.
    // Total credits: 75. Needed points: 3.2 * 75 - 3.0 * 60 = 240 - 180 = 60.
    // Required GPA: 60 / 15 = 4.0.
    const result = calculateTermPlan(3.0, 60, 3.2, 15);
    assert.equal(result.isComplete, true);
    assert.equal(result.status, 'feasible');
    assert.equal(result.requiredGpa, 4.0);
    assert.equal(result.totalCredits, 75);
    assert.equal(result.minCreditsNeeded, null);
    assert.equal(result.equivalentLetter, 'A (Xuất sắc)');
  });

  it('detects when student has already achieved the target GPA', () => {
    // Current GPA 3.5 exceeds target 3.2
    const result = calculateTermPlan(3.5, 60, 3.2, 15);
    assert.equal(result.isComplete, true);
    assert.equal(result.status, 'achieved');
    assert.equal(result.minCreditsNeeded, null);
    // (3.2 * 75 - 3.5 * 60) / 15 = (240 - 210) / 15 = 2.0
    assert.equal(result.requiredGpa, 2.0);
  });

  it('detects achieved status when required GPA calculation is zero or negative', () => {
    // High current GPA with low target
    const result = calculateTermPlan(3.8, 90, 2.5, 15);
    assert.equal(result.isComplete, true);
    assert.equal(result.status, 'achieved');
    assert.equal(result.requiredGpa, 0);
    assert.equal(result.minCreditsNeeded, null);
  });

  it('identifies impossible one-term targets and calculates minCreditsNeeded', () => {
    // Current GPA 2.5, 60 credits. Target 3.5, 15 credits.
    // Needed points = 3.5 * 75 - 2.5 * 60 = 262.5 - 150 = 112.5.
    // Required GPA = 112.5 / 15 = 7.5 > 4.0 -> impossible.
    // minCreditsNeeded = ((3.5 - 2.5) * 60) / (4.0 - 3.5) = 60 / 0.5 = 120.
    const result = calculateTermPlan(2.5, 60, 3.5, 15);
    assert.equal(result.isComplete, true);
    assert.equal(result.status, 'impossible');
    assert.equal(result.requiredGpa, 7.5);
    assert.equal(result.minCreditsNeeded, 120);
  });

  it('handles target GPA of 4.0 safely without division by zero', () => {
    // If current GPA is 3.5 and target is 4.0, denominator (4.0 - targetGpa) is 0.
    // It is mathematically impossible to reach 4.0 cumulative GPA with finite credits.
    const result = calculateTermPlan(3.5, 60, 4.0, 15);
    assert.equal(result.isComplete, true);
    assert.equal(result.status, 'impossible');
    assert.equal(result.minCreditsNeeded, null);
  });

  it('supports fresh student with 0 initial credits', () => {
    const result = calculateTermPlan(0, 0, 3.5, 15);
    assert.equal(result.isComplete, true);
    assert.equal(result.status, 'feasible');
    assert.equal(result.requiredGpa, 3.5);
    assert.equal(result.totalCredits, 15);
    assert.equal(result.minCreditsNeeded, null);
  });

  it('returns empty result for invalid inputs (negative or zero future credits, NaN)', () => {
    const empty1 = calculateTermPlan(3.0, 60, 3.2, 0);
    assert.equal(empty1.isComplete, false);
    assert.equal(empty1.status, 'empty');

    const empty2 = calculateTermPlan(Number.NaN, 60, 3.2, 15);
    assert.equal(empty2.isComplete, false);
    assert.equal(empty2.status, 'empty');

    const empty3 = calculateTermPlan(3.0, -10, 3.2, 15);
    assert.equal(empty3.isComplete, false);
    assert.equal(empty3.status, 'empty');
  });
});

describe('calculateRetakeImpact', () => {
  it('computes quality points added and new baseline GPA for retakes', () => {
    // Current: GPA 2.80, 60 credits.
    // Retake 1 course: D (1.0) -> A (4.0), 3 credits.
    // Delta points = (4.0 - 1.0) * 3 = 9.0.
    // newBaselineGpa = (2.80 * 60 + 9.0) / 60 = 177 / 60 = 2.95.
    // deltaGpa = 2.95 - 2.80 = 0.15.
    // Target 3.20 in 15 future credits:
    // nextTermRequiredGpa = (3.20 * 75 - 2.95 * 60) / 15 = (240 - 177) / 15 = 63 / 15 = 4.20.
    // isFeasible: false (4.20 > 4.0).
    const retakes: RetakeCourse[] = [
      { id: 'c1', oldGrade: 1.0, targetGrade: 4.0, credits: 3, label: 'Toán cao cấp' },
    ];
    const result = calculateRetakeImpact(2.80, 60, retakes, 15, 3.20);
    assert.equal(result.qualityPointsAdded, 9.0);
    assert.equal(result.newBaselineGpa, 2.95);
    assert.equal(result.deltaGpa, 0.15);
    assert.equal(result.nextTermRequiredGpa, 4.20);
    assert.equal(result.isFeasible, false);
  });

  it('turns an impossible plan feasible with sufficient retakes', () => {
    // Add a second retake course: D (1.0) -> B+ (3.5), 3 credits (points: 7.5).
    // Total added points = 9.0 + 7.5 = 16.5.
    // newBaselineGpa = (168 + 16.5) / 60 = 184.5 / 60 = 3.08 (rounded).
    // deltaGpa = 3.08 - 2.80 = 0.28.
    // Target 3.20 in 15 credits:
    // nextTermRequiredGpa = (240 - 3.08 * 60) / 15 = (240 - 184.8) / 15 = 55.2 / 15 = 3.68.
    // isFeasible: true (3.68 <= 4.0).
    const retakes: RetakeCourse[] = [
      { id: 'c1', oldGrade: 1.0, targetGrade: 4.0, credits: 3 },
      { id: 'c2', oldGrade: 1.0, targetGrade: 3.5, credits: 3 },
    ];
    const result = calculateRetakeImpact(2.80, 60, retakes, 15, 3.20);
    assert.equal(result.qualityPointsAdded, 16.5);
    assert.equal(result.newBaselineGpa, 3.08);
    assert.equal(result.deltaGpa, 0.28);
    assert.equal(result.nextTermRequiredGpa, 3.68);
    assert.equal(result.isFeasible, true);
  });

  it('uses default target GPA of 3.20 when omitted', () => {
    const result = calculateRetakeImpact(3.0, 60, [], 15);
    // (3.20 * 75 - 3.0 * 60) / 15 = (240 - 180) / 15 = 4.0
    assert.equal(result.nextTermRequiredGpa, 4.0);
    assert.equal(result.isFeasible, true);
  });

  it('handles retakes when futureCredits is 0', () => {
    const retakes: RetakeCourse[] = [
      { id: 'c1', oldGrade: 0.0, targetGrade: 4.0, credits: 3 },
    ];
    // Baseline rises from 3.10 to 3.50 with 30 credits
    const result = calculateRetakeImpact(3.10, 30, retakes, 0, 3.20);
    assert.equal(result.newBaselineGpa, 3.50);
    assert.equal(result.isFeasible, true); // newBaselineGpa (3.50) >= targetGpa (3.20)
    assert.equal(result.nextTermRequiredGpa, 0);
  });

  it('safely handles empty or invalid inputs', () => {
    const result = calculateRetakeImpact(Number.NaN, 0, [], 15);
    assert.equal(result.newBaselineGpa, 0);
    assert.equal(result.deltaGpa, 0);
    assert.equal(result.isFeasible, false);
  });
});

describe('calculateRoadmapPlan', () => {
  it('calculates degree roadmap milestones and feasibility correctly', () => {
    // Current GPA 2.8, 60 credits. Target graduation GPA 3.2.
    // Remaining credits: 75. Total degree credits: 135.
    // Needed points: 3.2 * 135 - 2.8 * 60 = 432 - 168 = 264.
    // Average GPA needed: 264 / 75 = 3.52.
    // Terms remaining: ceil(75 / 15) = 5.
    const result = calculateRoadmapPlan(2.8, 60, 3.2, 75, 135);
    assert.equal(result.averageGpaNeeded, 3.52);
    assert.equal(result.termsRemaining, 5);
    assert.equal(result.isFeasible, true);
    assert.equal(result.milestones.length, 3);
    assert.deepEqual(result.milestones[0], { title: 'Kỳ 1 Tới', score: '3.52', sub: '15 TC' });
    assert.deepEqual(result.milestones[1], { title: 'Các Kỳ Sau', score: '~3.52', sub: '~15 TC/kỳ' });
    assert.deepEqual(result.milestones[2], { title: 'Tốt Nghiệp', score: '3.20', sub: 'Bằng Giỏi 🎓' });
  });

  it('assigns correct honors label based on target graduation GPA', () => {
    // >= 3.6 -> Xuất Sắc
    const excellent = calculateRoadmapPlan(3.5, 60, 3.65, 75, 135);
    assert.equal(excellent.milestones[2].sub, 'Xuất Sắc 🎓');

    // >= 3.2 -> Bằng Giỏi
    const veryGood = calculateRoadmapPlan(3.0, 60, 3.25, 75, 135);
    assert.equal(veryGood.milestones[2].sub, 'Bằng Giỏi 🎓');

    // < 3.2 -> Bằng Khá
    const good = calculateRoadmapPlan(2.4, 60, 2.80, 75, 135);
    assert.equal(good.milestones[2].sub, 'Bằng Khá 🎓');
  });

  it('marks unfeasible if average GPA needed exceeds 4.0', () => {
    // Low GPA with few credits remaining
    const result = calculateRoadmapPlan(2.0, 105, 3.5, 30, 135);
    assert.ok(result.averageGpaNeeded > 4.0);
    assert.equal(result.isFeasible, false);
  });

  it('handles case where current GPA already exceeds target graduation GPA', () => {
    const result = calculateRoadmapPlan(3.8, 120, 3.2, 15, 135);
    assert.equal(result.averageGpaNeeded, 0);
    assert.equal(result.isFeasible, true);
    assert.equal(result.milestones[0].score, '0.00');
  });

  it('safely handles division by zero or invalid remaining credits', () => {
    const result = calculateRoadmapPlan(3.0, 60, 3.2, 0, 135);
    assert.equal(result.averageGpaNeeded, 0);
    assert.equal(result.termsRemaining, 1);
    assert.equal(result.isFeasible, false);
  });
});

describe('getCoursePrescription', () => {
  it('prescribes mix of A and B+ courses for required GPA between 3.5 and 4.0', () => {
    // 15 credits -> 5 courses.
    // Required GPA 3.7:
    // rawA = ((3.7 - 3.5) * 5) / 0.5 = 2.
    // coursesA: 2, coursesBPlus: 3, coursesB: 0.
    // Average: (2 * 4.0 + 3 * 3.5) / 5 = 18.5 / 5 = 3.70 >= 3.7.
    const result = getCoursePrescription(3.7, 15);
    assert.equal(result.totalCourses, 5);
    assert.equal(result.coursesA, 2);
    assert.equal(result.coursesBPlus, 3);
    assert.equal(result.coursesB, 0);
    assert.equal(result.summary, '2 môn điểm A (4.0), 3 môn điểm B+ (3.5)');
  });

  it('prescribes all A courses when required GPA is 4.0', () => {
    const result = getCoursePrescription(4.0, 15);
    assert.equal(result.totalCourses, 5);
    assert.equal(result.coursesA, 5);
    assert.equal(result.coursesBPlus, 0);
    assert.equal(result.coursesB, 0);
    assert.equal(result.summary, '5 môn điểm A (4.0)');
  });

  it('prescribes mix of B+ and B courses for required GPA between 3.0 and 3.5', () => {
    // 15 credits -> 5 courses.
    // Required GPA 3.2:
    // rawBPlus = ((3.2 - 3.0) * 5) / 0.5 = 2.
    // coursesA: 0, coursesBPlus: 2, coursesB: 3.
    // Average: (2 * 3.5 + 3 * 3.0) / 5 = 16 / 5 = 3.20.
    const result = getCoursePrescription(3.2, 15);
    assert.equal(result.totalCourses, 5);
    assert.equal(result.coursesA, 0);
    assert.equal(result.coursesBPlus, 2);
    assert.equal(result.coursesB, 3);
    assert.equal(result.summary, '2 môn điểm B+ (3.5), 3 môn điểm B (3.0)');
  });

  it('prescribes all B courses for required GPA <= 3.0', () => {
    const result = getCoursePrescription(2.8, 15);
    assert.equal(result.totalCourses, 5);
    assert.equal(result.coursesA, 0);
    assert.equal(result.coursesBPlus, 0);
    assert.equal(result.coursesB, 5);
    assert.equal(result.summary, '5 môn điểm B (3.0)');
  });

  it('handles already achieved target with required GPA <= 0', () => {
    const result = getCoursePrescription(0, 15);
    assert.equal(result.totalCourses, 5);
    assert.equal(result.coursesB, 5);
    assert.equal(result.summary, 'Đã đạt mục tiêu, chỉ cần hoàn thành các môn');
  });

  it('handles required GPA > 4.0 as maximum effort', () => {
    const result = getCoursePrescription(4.5, 15);
    assert.equal(result.totalCourses, 5);
    assert.equal(result.coursesA, 5);
    assert.equal(result.summary, 'Cần toàn bộ điểm A (5 môn)');
  });

  it('handles invalid or zero credits safely', () => {
    const result = getCoursePrescription(3.5, 0);
    assert.equal(result.totalCourses, 0);
    assert.equal(result.coursesA, 0);
    assert.equal(result.summary, 'Chưa có môn học');
  });
});
