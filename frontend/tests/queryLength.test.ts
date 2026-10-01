import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { MAX_QUERY_CHARS, queryLengthState } from '../src/utils/queryLength.ts';

describe('question length', () => {
  it('warns starting at 1600 characters and blocks only above 2000', () => {
    assert.equal(MAX_QUERY_CHARS, 2000);
    assert.equal(queryLengthState('a'.repeat(1599)).isNearLimit, false);
    assert.equal(queryLengthState('a'.repeat(1600)).isNearLimit, true);
    assert.equal(queryLengthState('a'.repeat(2000)).isOverLimit, false);
    assert.equal(queryLengthState('a'.repeat(2001)).isOverLimit, true);
  });
  it('counts Vietnamese text and emoji as code points consistently with the API', () => {
    const question = '🙂'.repeat(1999) + 'ế';
    assert.deepEqual(queryLengthState(question),
      { normalizedText: question, charCount: 2000, isNearLimit: true, isOverLimit: false });
    assert.equal(queryLengthState(question + 'ế').isOverLimit, true);
  });
  it('does not truncate or change a pasted question', () => {
    const question = '  ' + 'ầ'.repeat(2001) + '  ';
    assert.equal(queryLengthState(question).charCount, 2001);
    assert.equal(question.length, 2005);
    assert.equal(queryLengthState(question).normalizedText, 'ầ'.repeat(2001));
  });
  it('submits the same normalized string that is counted, including a pasted BOM', () => {
    const question = 'ế'.repeat(1999) + '🙂';
    const state = queryLengthState('\ufeff  ' + question + '  \ufeff');
    assert.equal(state.normalizedText, question);
    assert.equal(Array.from(state.normalizedText).length, state.charCount);
    assert.equal(state.charCount, 2000);
    assert.equal(state.isOverLimit, false);
  });
});
