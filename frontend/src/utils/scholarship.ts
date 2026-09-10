export type ScholarshipClassification = 'Khá' | 'Giỏi' | 'Xuất sắc';

export type ScholarshipTierDetail = {
  label: ScholarshipClassification;
  multiplier: number;
  badgeColor: string;
  minScholarshipScore: number;
  minAcademicScore: number;
  minConductScore: number;
  isScoreMet: boolean;
  isAcademicMet: boolean;
  isConductMet: boolean;
  isFullyMet: boolean;
};

export type ScholarshipResult = {
  score: number;
  classification: ScholarshipClassification | null;
  multiplier: number;
  message: string;
  tierDetails: ScholarshipTierDetail[];
};

export const SCHOLARSHIP_RULES: Array<{
  label: ScholarshipClassification;
  multiplier: number;
  badgeColor: string;
  minScholarshipScore: number;
  minAcademicScore: number;
  minConductScore: number;
}> = [
  {
    label: 'Xuất sắc',
    multiplier: 1.5,
    badgeColor: '#ec4899',
    minScholarshipScore: 3.6,
    minAcademicScore: 3.6,
    minConductScore: 90,
  },
  {
    label: 'Giỏi',
    multiplier: 1.25,
    badgeColor: '#8b5cf6',
    minScholarshipScore: 3.2,
    minAcademicScore: 3.2,
    minConductScore: 80,
  },
  {
    label: 'Khá',
    multiplier: 1.0,
    badgeColor: '#3b82f6',
    minScholarshipScore: 2.56,
    minAcademicScore: 2.5,
    minConductScore: 70,
  },
];

export function getScholarshipTierDetails(
  academicScore4: number | null,
  conductScore100: number | null,
  calculatedScore: number | null
): ScholarshipTierDetail[] {
  return SCHOLARSHIP_RULES.map((rule) => {
    const isScoreMet = calculatedScore !== null ? calculatedScore >= rule.minScholarshipScore : false;
    const isAcademicMet = academicScore4 !== null ? academicScore4 >= rule.minAcademicScore : false;
    const isConductMet = conductScore100 !== null ? conductScore100 >= rule.minConductScore : false;
    const isFullyMet = isScoreMet && isAcademicMet && isConductMet;

    return {
      ...rule,
      isScoreMet,
      isAcademicMet,
      isConductMet,
      isFullyMet,
    };
  });
}

export function calculateScholarshipScore(academicScore4: number, conductScore100: number): ScholarshipResult | null {
  if (!Number.isFinite(academicScore4) || academicScore4 < 0 || academicScore4 > 4) return null;
  if (!Number.isFinite(conductScore100) || conductScore100 < 0 || conductScore100 > 100) return null;

  const score = Math.round(((academicScore4 * 80 + (conductScore100 / 25) * 20) / 100) * 1000) / 1000;
  
  const tierDetails = getScholarshipTierDetails(academicScore4, conductScore100, score);

  // Find the first rule (highest classification) where all 3 criteria are met
  const matchedRule = tierDetails.find((tier) => tier.isFullyMet);

  return {
    score,
    classification: matchedRule?.label ?? null,
    multiplier: matchedRule?.multiplier ?? 0,
    tierDetails,
    message: matchedRule
      ? `Kết quả tham khảo đạt học bổng loại ${matchedRule.label} (Hệ số ${matchedRule.multiplier}x).`
      : 'Điểm hiện tại chưa thỏa mãn đồng thời cả 3 điều kiện (Điểm xét, Học tập, Rèn luyện) của bất kỳ mức học bổng nào.',
  };
}

