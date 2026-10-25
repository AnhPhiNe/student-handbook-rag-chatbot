import { useCallback, useMemo } from 'react';
import { useLocalStorage } from './useLocalStorage';
import {
  EMPTY_PROFILE,
  PROFILE_STORAGE_KEY,
  parseStoredProfile,
  type StudentProfile,
} from '../utils/studentProfile';

/**
 * The student's saved numbers, shared by the tool pages. Pages are never mounted together,
 * so each reads the stored value on mount and no cross-component sync is needed.
 */
export function useStudentProfile() {
  const [stored, setStored] = useLocalStorage<unknown>(PROFILE_STORAGE_KEY, EMPTY_PROFILE);
  const profile = useMemo(() => parseStoredProfile(stored), [stored]);

  const update = useCallback(
    (patch: Partial<StudentProfile>) => setStored((prev: unknown) => ({ ...parseStoredProfile(prev), ...patch })),
    [setStored],
  );
  const clear = useCallback(() => setStored({ ...EMPTY_PROFILE }), [setStored]);

  return { profile, update, clear } as const;
}
