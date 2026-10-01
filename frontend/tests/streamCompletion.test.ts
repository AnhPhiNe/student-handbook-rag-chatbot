import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { completeStream, requireStreamTerminal } from '../src/utils/streamCompletion.ts';

describe('SSE completion', () => {
  it('rejects EOF without a terminal event but accepts a completed transport', () => {
    assert.throws(() => requireStreamTerminal(false), /INCOMPLETE_STREAM/);
    assert.doesNotThrow(() => requireStreamTerminal(true));
  });
  it('routes unexpected EOF to the same partial-preserving failure handling', () => {
    let result;
    try {
      requireStreamTerminal(false);
    } catch {
      result = completeStream('error', { error_message: 'Lỗi kết nối.' }, 'Phần đã nhận.');
    }
    assert.ok(result?.failed);
    assert.ok(result.content.startsWith('Phần đã nhận.\n\n'));
  });
  it('keeps a complete answer unchanged', () => {
    assert.deepEqual(completeStream('done', { status: 'answered' }, 'Đủ ý.'),
      { content: 'Đủ ý.', failed: false });
  });
  it('preserves a truncated answer and marks the terminal error', () => {
    const result = completeStream('done', { status: 'api_error', error_type: 'output_truncated' }, 'Ý đầu.');
    assert.ok(result.content.startsWith('Ý đầu.\n\n'));
    assert.ok(result.content.includes('chưa hoàn tất'));
    assert.equal(result.failed, true);
  });
  it('shows an error even if no token arrived', () => {
    const result = completeStream('error', { error_message: 'Vui lòng đợi.' }, '');
    assert.deepEqual(result, { content: 'Vui lòng đợi.', failed: true });
  });
  it('does not overwrite partial text with a provider error or append the notice twice', () => {
    const first = completeStream('error', { error_message: 'Lỗi kết nối.' }, 'Phần đã nhận.');
    const second = completeStream('done', { status: 'api_error' }, first.content, first.failed);
    assert.deepEqual(second, first);
    assert.ok(second.content.startsWith('Phần đã nhận.'));
  });
});
