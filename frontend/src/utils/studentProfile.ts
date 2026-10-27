/** Numbers the student typed once and the tool pages share (stored under one localStorage key). */
export interface StudentProfile {
  currentGpa: string;
  currentCredits: string;
  totalDegreeCredits: string;
  /** Last valid semester GPA from the GPA page, 2 decimals. */
  lastSemesterGpa?: string;
}

export const PROFILE_STORAGE_KEY = 'hcmue_target_gpa_profile';

export const EMPTY_PROFILE: StudentProfile = {
  currentGpa: '',
  currentCredits: '',
  totalDegreeCredits: '',
};

const asString = (value: unknown): string => (typeof value === 'string' ? value : '');

/** Reads whatever was stored; anything that is not a string is dropped so a corrupt value cannot crash a page. */
export function parseStoredProfile(raw: unknown): StudentProfile {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return { ...EMPTY_PROFILE };
  const source = raw as Record<string, unknown>;
  const profile: StudentProfile = {
    currentGpa: asString(source.currentGpa),
    currentCredits: asString(source.currentCredits),
    totalDegreeCredits: asString(source.totalDegreeCredits),
  };
  const last = asString(source.lastSemesterGpa);
  const value = Number(last);
  if (last.trim() !== '' && Number.isFinite(value) && value >= 0 && value <= 4) {
    profile.lastSemesterGpa = value.toFixed(2);
  }
  return profile;
}

export function hasStoredProfile(profile: StudentProfile): boolean {
  return Boolean(
    profile.currentGpa || profile.currentCredits || profile.totalDegreeCredits || profile.lastSemesterGpa,
  );
}

/** Whole-number credits for pages that only accept integers; a decimal like "130.5" yields "". */
export function integerCredits(value: string): string {
  return /^\d{1,3}$/.test(value.trim()) ? value.trim() : '';
}
