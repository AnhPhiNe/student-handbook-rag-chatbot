import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { elapsedLabel, sourceLabels, waitingHint } from '../src/utils/waitingStatus.ts';

describe('waiting status', () => {
  it('shows seconds from the third second on', () => {
    assert.equal(elapsedLabel(2900), '');
    assert.equal(elapsedLabel(3000), '3 giây');
    assert.equal(elapsedLabel(41500), '41 giây');
  });

  it('reassures only after a long wait', () => {
    assert.equal(waitingHint(19999), '');
    assert.match(waitingHint(20000), /30–40 giây/);
    assert.match(waitingHint(60000), /kiên nhẫn/);
  });

  it('labels each article once, shortens titles and counts the rest', () => {
    const sources = [
      { article_label: 'Điều 27', title: 'Tiêu chuẩn, mức, quỹ học bổng khuyến khích học tập', cohort: 'K51' },
      { article_label: 'Điều 27', title: 'Xếp loại học bổng', cohort: 'K51' },
      { article_label: 'Điều 26', title: 'Học bổng', cohort: 'K51' },
      { title: 'Danh sach nganh dao tao', cohort: 'K51' },
      { article_label: 'Điều 3', cohort: 'K51' },
      { article_label: 'Điều 10', title: 'Đánh giá học phần', cohort: 'K51' },
    ];
    const { labels, more } = sourceLabels(sources);
    assert.deepEqual(labels, [
      'Điều 27 · Tiêu chuẩn, mức, quỹ học bổng khuyến…',
      'Điều 26 · Học bổng',
      'Điều 3',
    ]);
    assert.equal(more, 1);
  });

  it('keeps the same article of two cohorts apart', () => {
    const { labels } = sourceLabels([
      { article_label: 'Điều 9', cohort: 'K50' },
      { article_label: 'Điều 9', cohort: 'K51' },
    ]);
    assert.equal(labels.length, 2);
  });
});
