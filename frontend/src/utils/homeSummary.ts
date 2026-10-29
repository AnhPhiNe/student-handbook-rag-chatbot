import { hasStoredProfile, type StudentProfile } from './studentProfile.ts';

export interface HomeSummary {
  /** Any stored number at all (decides between the numbers and "Chưa có số liệu"). */
  hasProfile: boolean;
  /** Cumulative GPA on the 4.0 scale, or null when missing / out of range. */
  gpa: number | null;
  /** GPA as a share of 4.0, 0-100, for the ring. */
  gpaPercent: number;
  /** Earned and total credits, or null unless both are valid and total > 0. */
  credits: { done: number; total: number; percent: number } | null;
}

function toNumber(value: string): number | null {
  const text = value.trim().replace(',', '.');
  if (text === '') return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}

export function summarizeProfile(profile: StudentProfile): HomeSummary {
  const gpaRaw = toNumber(profile.currentGpa);
  const gpa = gpaRaw !== null && gpaRaw >= 0 && gpaRaw <= 4 ? gpaRaw : null;
  const done = toNumber(profile.currentCredits);
  const total = toNumber(profile.totalDegreeCredits);
  const credits =
    done !== null && total !== null && done >= 0 && total > 0
      ? { done, total, percent: Math.min(100, Math.round((done / total) * 100)) }
      : null;
  return {
    hasProfile: hasStoredProfile(profile),
    gpa,
    gpaPercent: gpa === null ? 0 : Math.round((gpa / 4) * 100),
    credits,
  };
}
