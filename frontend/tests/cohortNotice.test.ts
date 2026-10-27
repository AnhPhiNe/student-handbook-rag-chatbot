import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { cohortChangeMessage, shouldNotifyCohortChange } from '../src/utils/cohortNotice.ts';

describe('cohortChangeMessage', () => {
  it('K51 splits the pass threshold by course group', () => {
    assert.equal(
      cohortChangeMessage('K51'),
      'Đã chuyển sang K51: môn chuyên ngành đạt từ C (5.5), môn đại cương từ D.',
    );
  });
  it('K49 and K50 pass every course from D', () => {
    assert.equal(cohortChangeMessage('K50'), 'Đã chuyển sang K50: mọi môn đạt từ D (4.0).');
    assert.equal(cohortChangeMessage('K49'), 'Đã chuyển sang K49: mọi môn đạt từ D (4.0).');
  });
  it('appends an optional note', () => {
    assert.ok(cohortChangeMessage('K50', 'Đã giữ.').endsWith(' Đã giữ.'));
  });
});

describe('shouldNotifyCohortChange', () => {
  it('only for a real change on a tool tab', () => {
    assert.equal(shouldNotifyCohortChange('K50', 'K51', 'gpa'), true);
    assert.equal(shouldNotifyCohortChange('K50', 'K50', 'gpa'), false);
    assert.equal(shouldNotifyCohortChange(null, 'K50', 'gpa'), false);
    assert.equal(shouldNotifyCohortChange('K50', 'K51', 'home'), false);
    assert.equal(shouldNotifyCohortChange('K50', 'K51', 'chat'), false);
  });
});
