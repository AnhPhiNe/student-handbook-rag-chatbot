export type CreditThresholdStatus = 'safe' | 'near' | 'exceeded';

export type CreditThresholdResult = {
  threshold: number;
  remaining: number;
  status: CreditThresholdStatus;
  message: string;
};

export function calculateCreditThreshold(totalCredits: number, checkedCredits: number): CreditThresholdResult | null {
  if (!Number.isFinite(totalCredits) || totalCredits <= 0) return null;
  if (!Number.isFinite(checkedCredits) || checkedCredits < 0) return null;

  const threshold = Math.round(totalCredits * 0.05 * 100) / 100;
  const remaining = Math.round((threshold - checkedCredits) * 100) / 100;
  const ratio = checkedCredits / threshold;

  if (remaining < 0) {
    return {
      threshold,
      remaining,
      status: 'exceeded',
      message: 'Bạn đã vượt ngưỡng tham khảo. Hãy trao đổi sớm với cố vấn học tập hoặc phòng đào tạo để có kế hoạch xử lý phù hợp.',
    };
  }

  if (ratio >= 0.8) {
    return {
      threshold,
      remaining,
      status: 'near',
      message: 'Bạn đang ở gần ngưỡng tham khảo. Vẫn còn thời gian để điều chỉnh kế hoạch học tập, đừng hoảng nhé.',
    };
  }

  return {
    threshold,
    remaining,
    status: 'safe',
    message: 'Bạn vẫn còn trong vùng an toàn theo ngưỡng tham khảo. Cứ giữ nhịp học ổn định là được.',
  };
}
