import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { groupCitations, pageLabel, shortDocumentName } from '../src/utils/citationGroups.ts';

describe('pageLabel', () => {
  it('shows one page, a range, or nothing', () => {
    assert.equal(pageLabel([52]), 'tr. 52');
    assert.equal(pageLabel([51, 50, 51]), 'tr. 50–51');
    assert.equal(pageLabel([]), '');
    assert.equal(pageLabel([50, 53, 54, NaN, -2, 0, 1.5]), 'tr. 50, 53–54');
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
    { chunk_id: 'a', cohort: 'K49', document_identity: 'Quy chế CTSV', article_label: 'Điều 30', parent_title: 'Điều 30. Chính sách miễn, giảm học phí', source_pages: [50] },
    { chunk_id: 'b', cohort: 'K49', document_identity: 'Quy chế CTSV', article_label: 'Điều 30', source_pages: [51] },
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
    assert.equal(k49.rows[0].document, 'Quy chế CTSV');
    assert.deepEqual(k49.rows[0].citationIndexes, [0, 1]);
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

  it('uses the backend document name rather than repeating the article heading', () => {
    const [group] = groupCitations([
      { chunk_id: 'a', cohort: 'K51', article_label: 'Điều 16',
        source_section: 'Điều 16. Nghỉ học tạm thời',
        document_identity: 'Quy chế đào tạo trình độ đại học tại Trường Đại học Sư phạm Thành phố Hồ Chí Minh' },
    ]);
    assert.equal(group.rows[0].document, 'Quy chế đào tạo trình độ đại học');
  });

  it('keeps equal article numbers from different documents separate', () => {
    const [group] = groupCitations([
      { chunk_id: 'a', cohort: 'K51', article_label: 'Điều 10', document_identity: 'Quy chế đào tạo' },
      { chunk_id: 'b', cohort: 'K51', article_label: 'Điều 10', document_identity: 'Quy chế CTSV' },
    ]);
    assert.equal(group.rows.length, 2);
  });

  it('does not assume legacy sources with missing identity are one document', () => {
    const [group] = groupCitations([
      { chunk_id: 'a', article_label: 'Điều 10' },
      { chunk_id: 'b', article_label: 'Điều 10' },
    ]);
    assert.equal(group.rows.length, 2);
  });

  it('merges canonical article ids, but keeps distinct table ids separate', () => {
    const [group] = groupCitations([
      { chunk_id: 'a', canonical_source_id: 'article-a', article_label: 'Điều 27' },
      { chunk_id: 'b', canonical_source_id: 'article-a', article_label: 'Điều 27' },
      { chunk_id: 'c', canonical_source_id: 'table-a', title: 'Bảng học phí' },
      { chunk_id: 'd', canonical_source_id: 'table-b', title: 'Bảng học phí' },
    ]);
    assert.equal(group.rows.length, 3);
  });
});
