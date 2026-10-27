export type CreditThresholdStatus = 'safe' | 'near' | 'exceeded';

export type CreditThresholdResult = {
  /** Exact 5% of the programme's credits, e.g. 6.75 for 135 credits. */
  threshold: number;
  /** Whole credits a student may fail: the threshold rounded down, never up (6.75 -> 6). */
  maxCredits: number;
  /** maxCredits minus the failed credits; negative once the limit is exceeded. */
  creditsLeft: number;
  status: CreditThresholdStatus;
  message: string;
};

const NEAR_RATIO = 0.8;

export function calculateCreditThreshold(totalCredits: number, checkedCredits: number): CreditThresholdResult | null {
  if (!Number.isFinite(totalCredits) || totalCredits <= 0) return null;
  if (!Number.isFinite(checkedCredits) || checkedCredits < 0) return null;

  const threshold = Math.round(totalCredits * 0.05 * 100) / 100;
  // Every course carries a whole number of credits, so a fractional allowance can never be used.
  const maxCredits = Math.floor(threshold);
  const creditsLeft = maxCredits - checkedCredits;

  if (creditsLeft < 0) {
    return {
      threshold,
      maxCredits,
      creditsLeft,
      status: 'exceeded',
      message: 'Bạn đã vượt ngưỡng tham khảo. Hãy trao đổi sớm với cố vấn học tập hoặc phòng đào tạo để có kế hoạch xử lý phù hợp.',
    };
  }

  if (checkedCredits / threshold >= NEAR_RATIO) {
    return {
      threshold,
      maxCredits,
      creditsLeft,
      status: 'near',
      message: 'Bạn đang ở gần ngưỡng tham khảo. Vẫn còn thời gian để điều chỉnh kế hoạch học tập, đừng hoảng nhé.',
    };
  }

  return {
    threshold,
    maxCredits,
    creditsLeft,
    status: 'safe',
    message: 'Bạn vẫn còn trong vùng an toàn theo ngưỡng tham khảo. Cứ giữ nhịp học ổn định là được.',
  };
}

export type GraduationClassification = 'excellent' | 'good' | 'fair';

export type DowngradeVerdict = {
  tone: 'ok' | 'bad' | 'neutral';
  kind: 'fair-safe' | 'downgrade' | 'kept' | 'may-downgrade' | 'discipline-only';
  /** Classification name before a downgrade, or the kept one. */
  from?: string;
  /** Classification name after a downgrade. */
  to?: string;
};

const DOWNGRADE_NAMES: Record<'excellent' | 'good', [string, string]> = {
  excellent: ['Xuất sắc', 'Giỏi'],
  good: ['Giỏi', 'Khá'],
};

/** What the 5% rule means for the expected classification; `classification` may be unchosen. */
export function getDowngradeVerdict(
  status: CreditThresholdStatus,
  classification: GraduationClassification | null,
): DowngradeVerdict {
  const exceeded = status === 'exceeded';
  if (classification === 'fair') return { tone: 'ok', kind: 'fair-safe' };
  if (classification) {
    const [from, to] = DOWNGRADE_NAMES[classification];
    return exceeded ? { tone: 'bad', kind: 'downgrade', from, to } : { tone: 'ok', kind: 'kept', from };
  }
  return exceeded ? { tone: 'bad', kind: 'may-downgrade' } : { tone: 'neutral', kind: 'discipline-only' };
}
