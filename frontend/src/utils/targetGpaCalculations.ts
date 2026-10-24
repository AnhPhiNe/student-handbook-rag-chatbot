export interface RetakeCourse {
  id: string;
  oldGrade: number;
  targetGrade: number;
  credits: number;
  label?: string;
}

export interface CoursePrescription {
  coursesA: number;
  coursesBPlus: number;
  coursesB: number;
  totalCourses: number;
  summary: string;
}

export interface TermPlanResult {
  isComplete: boolean;
  requiredGpa: number;
  status: 'achieved' | 'feasible' | 'impossible' | 'empty';
  minCreditsNeeded: number | null;
  totalCredits: number;
  equivalentLetter: string;
}

export interface RetakePlanResult {
  newBaselineGpa: number;
  deltaGpa: number;
  qualityPointsAdded: number;
  nextTermRequiredGpa: number;
  isFeasible: boolean;
}

export interface RoadmapMilestone {
  title: string;
  score: string;
  sub: string;
}

export interface RoadmapPlanResult {
  averageGpaNeeded: number;
  termsRemaining: number;
  isFeasible: boolean;
  milestones: RoadmapMilestone[];
}

/**
 * Định dạng số thập phân hiển thị 2 chữ số sau dấu phẩy.
 */
export function format2(val: number): string {
  if (!Number.isFinite(val)) return '0.00';
  return val.toFixed(2);
}

/**
 * Quy đổi điểm trung bình học kỳ sang mức điểm chữ tương đương.
 */
export function getEquivalentLetter(gpa: number): string {
  if (!Number.isFinite(gpa) || gpa <= 0) return 'C+ đến B';
  if (gpa >= 3.6) return 'A (Xuất sắc)';
  if (gpa >= 3.2) return 'B+ (Giỏi)';
  if (gpa >= 2.5) return 'B (Khá)';
  return 'C+ đến B';
}

/**
 * Tính toán kế hoạch GPA theo học kỳ dựa trên quy chế đào tạo tín chỉ.
 * Công thức: requiredGpa = (targetGpa * (currentCredits + futureCredits) - currentGpa * currentCredits) / futureCredits
 */
export function calculateTermPlan(
  currentGpa: number,
  currentCredits: number,
  targetGpa: number,
  futureCredits: number,
): TermPlanResult {
  if (
    !Number.isFinite(currentGpa) ||
    !Number.isFinite(currentCredits) ||
    !Number.isFinite(targetGpa) ||
    !Number.isFinite(futureCredits) ||
    futureCredits <= 0 ||
    currentCredits < 0 ||
    currentGpa < 0 ||
    targetGpa <= 0
  ) {
    return {
      isComplete: false,
      requiredGpa: 0,
      status: 'empty',
      minCreditsNeeded: null,
      totalCredits: Math.max(0, Number.isFinite(currentCredits) ? currentCredits : 0),
      equivalentLetter: '',
    };
  }

  const totalCredits = currentCredits + futureCredits;
  const rawRequiredGpa = (targetGpa * totalCredits - currentGpa * currentCredits) / futureCredits;
  const requiredGpa = Math.round(rawRequiredGpa * 100) / 100;

  // Khi requiredGpa <= 0 hoặc currentGpa >= targetGpa: status = 'achieved'
  if (requiredGpa <= 0 || currentGpa >= targetGpa) {
    return {
      isComplete: true,
      requiredGpa: Math.max(0, requiredGpa),
      status: 'achieved',
      minCreditsNeeded: null,
      totalCredits,
      equivalentLetter: getEquivalentLetter(Math.max(0, requiredGpa)),
    };
  }

  // Khi requiredGpa > 4.0: status = 'impossible'
  if (requiredGpa > 4.0) {
    let minCreditsNeeded: number | null = null;
    if (targetGpa < 4.0 && targetGpa > currentGpa) {
      const needed = ((targetGpa - currentGpa) * currentCredits) / (4.0 - targetGpa);
      if (Number.isFinite(needed) && needed > 0) {
        minCreditsNeeded = Math.ceil(Math.round(needed * 1e4) / 1e4);
      }
    }

    return {
      isComplete: true,
      requiredGpa,
      status: 'impossible',
      minCreditsNeeded,
      totalCredits,
      equivalentLetter: getEquivalentLetter(requiredGpa),
    };
  }

  // Khi 0 < requiredGpa <= 4.0: status = 'feasible'
  return {
    isComplete: true,
    requiredGpa,
    status: 'feasible',
    minCreditsNeeded: null,
    totalCredits,
    equivalentLetter: getEquivalentLetter(requiredGpa),
  };
}

/**
 * Tính toán tác động của việc học cải thiện điểm (Retake Plan).
 * Delta Quality Points = sum((retake.targetGrade - retake.oldGrade) * retake.credits)
 * newBaselineGpa = (currentGpa * currentCredits + qualityPointsAdded) / currentCredits
 * deltaGpa = newBaselineGpa - currentGpa
 * nextTermRequiredGpa: điểm GPA cần đạt ở kỳ tới để đạt targetGpa dựa trên newBaselineGpa.
 */
export function calculateRetakeImpact(
  currentGpa: number,
  currentCredits: number,
  retakes: RetakeCourse[],
  futureCredits: number,
  targetGpa: number = 3.20,
): RetakePlanResult {
  if (
    !Number.isFinite(currentGpa) ||
    !Number.isFinite(currentCredits) ||
    currentCredits <= 0 ||
    currentGpa < 0
  ) {
    return {
      newBaselineGpa: Math.max(0, Number.isFinite(currentGpa) ? currentGpa : 0),
      deltaGpa: 0,
      qualityPointsAdded: 0,
      nextTermRequiredGpa: 0,
      isFeasible: false,
    };
  }

  let rawQualityPointsAdded = 0;
  if (Array.isArray(retakes)) {
    for (const r of retakes) {
      if (
        r &&
        Number.isFinite(r.oldGrade) &&
        Number.isFinite(r.targetGrade) &&
        Number.isFinite(r.credits) &&
        r.credits > 0
      ) {
        rawQualityPointsAdded += (r.targetGrade - r.oldGrade) * r.credits;
      }
    }
  }

  const qualityPointsAdded = Math.round(rawQualityPointsAdded * 100) / 100;
  const currentTotalPoints = currentGpa * currentCredits;
  const rawNewBaselineGpa = (currentTotalPoints + rawQualityPointsAdded) / currentCredits;
  const newBaselineGpa = Math.min(4.0, Math.max(0, Math.round(rawNewBaselineGpa * 100) / 100));
  const deltaGpa = Math.round((newBaselineGpa - currentGpa) * 100) / 100;

  const validTargetGpa = Number.isFinite(targetGpa) && targetGpa > 0 ? targetGpa : 3.20;
  const validFutureCredits = Number.isFinite(futureCredits) && futureCredits > 0 ? futureCredits : 0;

  let nextTermRequiredGpa: number;
  let isFeasible: boolean;

  if (validFutureCredits > 0) {
    const rawNextGpa =
      (validTargetGpa * (currentCredits + validFutureCredits) - newBaselineGpa * currentCredits) /
      validFutureCredits;
    const roundedNextGpa = Math.round(rawNextGpa * 100) / 100;

    if (roundedNextGpa <= 0) {
      nextTermRequiredGpa = 0;
      isFeasible = true;
    } else if (roundedNextGpa <= 4.0) {
      nextTermRequiredGpa = roundedNextGpa;
      isFeasible = true;
    } else {
      nextTermRequiredGpa = roundedNextGpa;
      isFeasible = false;
    }
  } else {
    nextTermRequiredGpa = 0;
    isFeasible = newBaselineGpa >= validTargetGpa;
  }

  return {
    newBaselineGpa,
    deltaGpa,
    qualityPointsAdded,
    nextTermRequiredGpa,
    isFeasible,
  };
}

/**
 * Tính toán lộ trình tốt nghiệp nhiều học kỳ (Roadmap Plan).
 * neededQualityPoints = targetGradGpa * totalDegreeCredits - currentGpa * currentCredits
 * averageGpaNeeded = neededQualityPoints / remainingCredits
 * termsRemaining = Math.max(1, Math.ceil(remainingCredits / 15))
 */
export function calculateRoadmapPlan(
  currentGpa: number,
  currentCredits: number,
  targetGradGpa: number,
  remainingCredits: number,
  totalDegreeCredits: number = 135,
): RoadmapPlanResult {
  const safeTargetGradGpa = Number.isFinite(targetGradGpa) && targetGradGpa > 0 ? targetGradGpa : 3.20;
  const gradSub =
    safeTargetGradGpa >= 3.6
      ? 'Xuất Sắc 🎓'
      : safeTargetGradGpa >= 3.2
        ? 'Bằng Giỏi 🎓'
        : 'Bằng Khá 🎓';

  if (
    !Number.isFinite(currentGpa) ||
    !Number.isFinite(currentCredits) ||
    !Number.isFinite(remainingCredits) ||
    !Number.isFinite(totalDegreeCredits) ||
    currentGpa < 0 ||
    currentCredits < 0 ||
    remainingCredits <= 0 ||
    totalDegreeCredits <= 0
  ) {
    const fallbackTerms =
      Number.isFinite(remainingCredits) && remainingCredits > 0
        ? Math.max(1, Math.ceil(Math.round((remainingCredits / 15) * 1e4) / 1e4))
        : 1;

    return {
      averageGpaNeeded: 0,
      termsRemaining: fallbackTerms,
      isFeasible: false,
      milestones: [
        { title: 'Kỳ 1 Tới', score: '0.00', sub: '15 TC' },
        { title: 'Các Kỳ Sau', score: '~0.00', sub: '~15 TC/kỳ' },
        { title: 'Tốt Nghiệp', score: format2(safeTargetGradGpa), sub: gradSub },
      ],
    };
  }

  const neededQualityPoints = safeTargetGradGpa * totalDegreeCredits - currentGpa * currentCredits;
  const rawAverageGpaNeeded = neededQualityPoints / remainingCredits;
  const termsRemaining = Math.max(1, Math.ceil(Math.round((remainingCredits / 15) * 1e4) / 1e4));

  let averageGpaNeeded: number;
  let isFeasible: boolean;

  if (rawAverageGpaNeeded <= 0) {
    averageGpaNeeded = 0;
    isFeasible = true;
  } else if (rawAverageGpaNeeded <= 4.0) {
    averageGpaNeeded = Math.round(rawAverageGpaNeeded * 100) / 100;
    isFeasible = true;
  } else {
    averageGpaNeeded = Math.round(rawAverageGpaNeeded * 100) / 100;
    isFeasible = false;
  }

  const milestones: RoadmapMilestone[] = [
    { title: 'Kỳ 1 Tới', score: format2(averageGpaNeeded), sub: '15 TC' },
    { title: 'Các Kỳ Sau', score: `~${format2(averageGpaNeeded)}`, sub: '~15 TC/kỳ' },
    { title: 'Tốt Nghiệp', score: format2(safeTargetGradGpa), sub: gradSub },
  ];

  return {
    averageGpaNeeded,
    termsRemaining,
    isFeasible,
    milestones,
  };
}

/**
 * Phân bổ thực tế số môn A (4.0), B+ (3.5), và B (3.0) theo số tín chỉ (trung bình 3 TC/môn).
 */
export function getCoursePrescription(requiredGpa: number, credits: number): CoursePrescription {
  if (!Number.isFinite(credits) || credits <= 0) {
    return {
      coursesA: 0,
      coursesBPlus: 0,
      coursesB: 0,
      totalCourses: 0,
      summary: 'Chưa có môn học',
    };
  }

  const totalCourses = Math.max(1, Math.round(credits / 3));
  const safeRequiredGpa = Number.isFinite(requiredGpa) ? requiredGpa : 0;

  if (safeRequiredGpa <= 0) {
    return {
      coursesA: 0,
      coursesBPlus: 0,
      coursesB: totalCourses,
      totalCourses,
      summary: 'Đã đạt mục tiêu, chỉ cần hoàn thành các môn',
    };
  }

  if (safeRequiredGpa > 4.0) {
    return {
      coursesA: totalCourses,
      coursesBPlus: 0,
      coursesB: 0,
      totalCourses,
      summary: `Cần toàn bộ điểm A (${totalCourses} môn)`,
    };
  }

  if (safeRequiredGpa <= 3.0) {
    return {
      coursesA: 0,
      coursesBPlus: 0,
      coursesB: totalCourses,
      totalCourses,
      summary: `${totalCourses} môn điểm B (3.0)`,
    };
  }

  if (safeRequiredGpa <= 3.5) {
    const rawBPlus = ((safeRequiredGpa - 3.0) * totalCourses) / 0.5;
    const coursesBPlus = Math.min(totalCourses, Math.max(0, Math.ceil(Math.round(rawBPlus * 1e4) / 1e4)));
    const coursesB = totalCourses - coursesBPlus;
    const summaryParts: string[] = [];
    if (coursesBPlus > 0) summaryParts.push(`${coursesBPlus} môn điểm B+ (3.5)`);
    if (coursesB > 0) summaryParts.push(`${coursesB} môn điểm B (3.0)`);

    return {
      coursesA: 0,
      coursesBPlus,
      coursesB,
      totalCourses,
      summary: summaryParts.join(', '),
    };
  }

  // safeRequiredGpa > 3.5 && safeRequiredGpa <= 4.0
  const rawA = ((safeRequiredGpa - 3.5) * totalCourses) / 0.5;
  const coursesA = Math.min(totalCourses, Math.max(0, Math.ceil(Math.round(rawA * 1e4) / 1e4)));
  const coursesBPlus = totalCourses - coursesA;
  const summaryParts: string[] = [];
  if (coursesA > 0) summaryParts.push(`${coursesA} môn điểm A (4.0)`);
  if (coursesBPlus > 0) summaryParts.push(`${coursesBPlus} môn điểm B+ (3.5)`);

  return {
    coursesA,
    coursesBPlus,
    coursesB: 0,
    totalCourses,
    summary: summaryParts.join(', '),
  };
}
