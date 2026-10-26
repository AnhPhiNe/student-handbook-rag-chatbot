import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { EXPERIENCE } from '../src/data/experience.ts';
import { NOTE_COLORS, filterTips, noteColor } from '../src/utils/experience.ts';

describe('EXPERIENCE data', () => {
  it('only references topics that exist', () => {
    const topics = new Set(EXPERIENCE.topics.map((topic) => topic.id));
    for (const tip of EXPERIENCE.tips) assert.ok(topics.has(tip.topic), `${tip.id}: unknown topic ${tip.topic}`);
  });

  it('has unique tip and topic ids', () => {
    const tipIds = EXPERIENCE.tips.map((tip) => tip.id);
    assert.equal(new Set(tipIds).size, tipIds.length);
    const topicIds = EXPERIENCE.topics.map((topic) => topic.id);
    assert.equal(new Set(topicIds).size, topicIds.length);
    assert.ok(!topicIds.includes('all'));
  });

  it('links only to real tool tabs', () => {
    const real = ['scholarship', 'target-gpa', 'course-target'];
    for (const tip of EXPERIENCE.tips) if (tip.tool) assert.ok(real.includes(tip.tool.tab), tip.id);
    assert.ok(real.includes(EXPERIENCE.checklist.link.tab));
  });

  it('serves proof images from /experience/', () => {
    for (const tip of EXPERIENCE.tips) if (tip.proof) assert.ok(tip.proof.src.startsWith('/experience/'), tip.id);
  });
});

describe('filterTips', () => {
  it('returns every tip for all', () => {
    assert.equal(filterTips(EXPERIENCE.tips, 'all').length, EXPERIENCE.tips.length);
  });

  it('keeps only the chosen topic', () => {
    const picked = filterTips(EXPERIENCE.tips, 'cotdiem');
    assert.equal(picked.length, 2);
    assert.ok(picked.every((tip) => tip.topic === 'cotdiem'));
  });
});

describe('noteColor', () => {
  it('never repeats a colour among neighbours', () => {
    for (let i = 0; i < 40; i += 1) {
      assert.notEqual(noteColor(i), noteColor(i + 1), `i=${i} vs i+1`);
      assert.notEqual(noteColor(i), noteColor(i + 3), `i=${i} vs i+3`);
    }
  });

  it('cycles through the palette', () => {
    assert.equal(noteColor(NOTE_COLORS.length), noteColor(0));
  });
});
