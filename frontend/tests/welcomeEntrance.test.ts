import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { WELCOME_ENTRANCE_STORAGE_KEY, shouldShowWelcomeEntrance } from '../src/utils/welcomeEntrance.ts';

describe('welcomeEntrance', () => {
  it('uses the correct localStorage key', () => {
    assert.equal(WELCOME_ENTRANCE_STORAGE_KEY, 'hcmue-welcome-entrance-seen');
  });

  it('shows welcome entrance on first visit when false, null or undefined', () => {
    assert.equal(shouldShowWelcomeEntrance(false), true);
    assert.equal(shouldShowWelcomeEntrance(null), true);
    assert.equal(shouldShowWelcomeEntrance(undefined), true);
  });

  it('does not show welcome entrance if already seen', () => {
    assert.equal(shouldShowWelcomeEntrance(true), false);
  });
});
