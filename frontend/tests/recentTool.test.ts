import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { RECENT_TOOL_KEY, readRecentTool } from '../src/utils/recentTool.ts';

describe('readRecentTool', () => {
  it('keeps a known tool id', () => {
    assert.equal(readRecentTool('gpa'), 'gpa');
    assert.equal(readRecentTool('course-target'), 'course-target');
  });
  it('drops unknown ids and non-string values', () => {
    assert.equal(readRecentTool('danh-ba'), null);
    assert.equal(readRecentTool(''), null);
    assert.equal(readRecentTool(null), null);
    assert.equal(readRecentTool(undefined), null);
    assert.equal(readRecentTool(42), null);
    assert.equal(readRecentTool(['gpa']), null);
  });
  it('uses the agreed storage key', () => {
    assert.equal(RECENT_TOOL_KEY, 'hcmue-recent-tool');
  });
});
