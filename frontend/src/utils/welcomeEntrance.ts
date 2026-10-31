/**
 * Key stored in localStorage indicating the user has seen the welcome entrance.
 */
export const WELCOME_ENTRANCE_STORAGE_KEY = 'hcmue-welcome-entrance-seen';

/**
 * Returns true if the welcome entrance animation should be displayed.
 */
export function shouldShowWelcomeEntrance(hasSeen: boolean | null | undefined): boolean {
  return hasSeen !== true;
}
