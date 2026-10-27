import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { arrangePinnedTools, sanitizePinnedIds, togglePinnedId } from '../src/utils/pinnedTools.ts';

const groups = [
  { title: 'A', tools: [{ id: 'a1' }, { id: 'a2' }] },
  { title: 'B', tools: [{ id: 'b1' }] },
];

describe('arrangePinnedTools', () => {
  it('returns the groups untouched when nothing is pinned', () => {
    const result = arrangePinnedTools(groups, []);
    assert.deepEqual(result.pinned, []);
    assert.deepEqual(result.groups, groups);
  });
  it('lists pinned tools in pin order and removes them from their group', () => {
    const result = arrangePinnedTools(groups, ['b1', 'a1']);
    assert.deepEqual(result.pinned.map((t) => t.id), ['b1', 'a1']);
    assert.deepEqual(result.groups, [{ title: 'A', tools: [{ id: 'a2' }] }]);
  });
  it('ignores unknown and duplicate ids', () => {
    const result = arrangePinnedTools(groups, ['zzz', 'a2', 'a2']);
    assert.deepEqual(result.pinned.map((t) => t.id), ['a2']);
  });
  it('tolerates corrupt storage', () => {
    for (const bad of [null, 'a1', 7, { a1: true }]) {
      assert.deepEqual(arrangePinnedTools(groups, bad).pinned, []);
    }
  });
});

describe('sanitizePinnedIds / togglePinnedId', () => {
  it('keeps unique strings only', () => {
    assert.deepEqual(sanitizePinnedIds(['a', 1, 'a', null, 'b']), ['a', 'b']);
  });
  it('toggles an id on and off', () => {
    assert.deepEqual(togglePinnedId(['a'], 'b'), ['a', 'b']);
    assert.deepEqual(togglePinnedId(['a', 'b'], 'a'), ['b']);
  });
});
