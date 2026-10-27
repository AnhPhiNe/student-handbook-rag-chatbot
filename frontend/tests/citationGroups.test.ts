import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { groupCitations, pageLabel, shortDocumentName } from '../src/utils/citationGroups.ts';

describe('pageLabel', () => {
  it('shows one page, a range, or nothing', () => {
    assert.equal(pageLabel([52]), 'tr. 52');
    assert.equal(pageLabel([51, 50, 51]), 'tr. 50–51');
    assert.equal(pageLabel([]), '');
  });
});

describe('shortDocumentName', () => {
  it('cuts the long legal tail of a document name', () => {
    assert.equal(
      shortDocumentName('Quy chế công tác sinh viên đối với chương trình đào tạo đại học hệ chính quy'),
      'Quy chế công tác sinh viên',
    );
    assert.equal(shortDocumentName(undefined), '');
  });
});

describe('groupCitations', () => {
  const citations = [
    { chunk_id: 'a', cohort: 'K49', article_label: 'Điều 30', parent_title: 'Điều 30. Chính sách miễn, giảm học phí', source_pages: [50] },
    { chunk_id: 'b', cohort: 'K49', article_label: 'Điều 30', source_pages: [51] },
    { chunk_id: 'c', cohort: 'K51', article_label: 'Điều 9', title: 'Học phí theo học kỳ', source_pages: [21] },
    { chunk_id: 'd', title: 'Bảng xếp loại học bổng' },
  ];

  it('merges paragraphs of one article and joins their pages', () => {
    const [k49] = groupCitations(citations);
    assert.equal(k49.cohort, 'K49');
    assert.equal(k49.rows.length, 1);
    assert.equal(k49.rows[0].article, 'Điều 30');
    assert.equal(k49.rows[0].title, 'Chính sách miễn, giảm học phí');
    assert.equal(k49.rows[0].pages, 'tr. 50–51');
    assert.equal(k49.rows[0].citationIndex, 0);
  });

  it('puts the student cohort first and sources without a cohort last', () => {
    const groups = groupCitations(citations, 'K51');
    assert.deepEqual(groups.map((group) => group.cohort), ['K51', 'K49', 'Chung']);
    assert.equal(groups[2].rows[0].article, 'Mục');
  });

  it('keeps the same article from two cohorts apart', () => {
    const groups = groupCitations([
      { chunk_id: 'x', cohort: 'K49', article_label: 'Điều 30' },
      { chunk_id: 'y', cohort: 'K51', article_label: 'Điều 30' },
    ]);
    assert.equal(groups.length, 2);
  });
});
