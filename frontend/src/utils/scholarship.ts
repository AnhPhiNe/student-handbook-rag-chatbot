export type ScholarshipClassification = 'Khá' | 'Giỏi' | 'Xuất sắc';

export type ScholarshipResult = {
  score: number;
  classification: ScholarshipClassification | null;
  message: string;
};

const SCHOLARSHIP_RULES = [
  {
    label: 'Xuất sắc' as const,
    minScholarshipScore: 3.6,
    minAcademicScore: 3.6,
    minConductScore: 90,
  },
  {
    label: 'Giỏi' as const,
    minScholarshipScore: 3.2,
    minAcademicScore: 3.2,
    minConductScore: 80,
  },
  {
    label: 'Khá' as const,
    minScholarshipScore: 2.56,
    minAcademicScore: 2.5,
    minConductScore: 70,
  },
];

export function calculateScholarshipScore(academicScore4: number, conductScore100: number): ScholarshipResult | null {
  if (!Number.isFinite(academicScore4) || academicScore4 < 0 || academicScore4 > 4) return null;
  if (!Number.isFinite(conductScore100) || conductScore100 < 0 || conductScore100 > 100) return null;

  const score = Math.round(((academicScore4 * 80 + (conductScore100 / 25) * 20) / 100) * 1000) / 1000;
  
  // Find the first rule (highest classification) that matches the criteria
  const matchedRule = SCHOLARSHIP_RULES.find((rule) =>
    score >= rule.minScholarshipScore &&
    academicScore4 >= rule.minAcademicScore &&
    conductScore100 >= rule.minConductScore
  );

  return {
    score,
    classification: matchedRule?.label ?? null,
    message: matchedRule
      ? `Kết quả tham khảo đạt mức ${matchedRule.label}.`
      : 'Điểm hiện tại chưa khớp ngưỡng Khá/Giỏi/Xuất sắc trong bảng xét học bổng.',
  };
}
