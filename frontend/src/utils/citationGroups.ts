// How an answer's sources are listed under it: one row per article, grouped by the
// cohort handbook they come from, the student's own cohort first.

export interface CitationLike {
  chunk_id: string;
  cohort?: string;
  article_label?: string;
  parent_article?: string;
  parent_title?: string;
  title?: string;
  source_section?: string;
  source_pages?: number[];
  document_identity?: string;
  canonical_source_id?: string;
  source_parent_id?: string;
  parent_section_id?: string;
}

export interface SourceRow {
  key: string;
  /** "Điều 30", or "Mục" when the source is not an article (a table, a directory record). */
  article: string;
  title: string;
  document: string;
  pages: string;
  /** Index of the first citation merged into this row, for opening its detail. */
  citationIndex: number;
  citationIndexes: number[];
}

export interface SourceGroup {
  cohort: string;
  rows: SourceRow[];
}

const ARTICLE = /(?:Điều|Dieu)[\s_-]*(\d+[a-z]?)/iu;
const DOCUMENT_MAX = 40;
const NO_COHORT = 'Chung';

function articleOf(citation: CitationLike): string | null {
  for (const text of [citation.article_label, citation.parent_article, citation.title, citation.source_section]) {
    const match = text?.match(ARTICLE);
    if (match) return `Điều ${match[1].toLocaleLowerCase('vi')}`;
  }
  return null;
}

/** "Quy chế công tác sinh viên đối với chương trình …" → "Quy chế công tác sinh viên". */
export function shortDocumentName(section: string | undefined): string {
  const text = (section ?? '').trim();
  if (!text) return '';
  const cut = text.split(/\s+(?:đối với|của Trường|ban hành|áp dụng)\s+/u)[0].trim();
  return cut.length > DOCUMENT_MAX ? `${cut.slice(0, DOCUMENT_MAX).trimEnd()}…` : cut;
}

/** "tr. 50", "tr. 50–51", or "" when the pages are unknown. */
export function pageLabel(pages: number[]): string {
  const sorted = [...new Set(pages)].filter((page) => Number.isInteger(page) && page > 0).sort((a, b) => a - b);
  if (sorted.length === 0) return '';
  const ranges: string[] = [];
  for (let i = 0; i < sorted.length; i++) {
    const first = sorted[i];
    let last = first;
    while (sorted[i + 1] === last + 1) last = sorted[++i];
    ranges.push(first === last ? String(first) : `${first}–${last}`);
  }
  return `tr. ${ranges.join(', ')}`;
}

function rowTitle(citation: CitationLike, article: string | null): string {
  const raw = (citation.parent_title || citation.title || citation.source_section || '').trim();
  // Titles often repeat the article ("Điều 30. Chính sách …"); the row already shows it.
  const stripped = article ? raw.replace(new RegExp(`^${article}\\s*[.:—-]?\\s*`, 'iu'), '') : raw;
  return stripped || raw || citation.chunk_id;
}

export function groupCitations(citations: CitationLike[], currentCohort?: string): SourceGroup[] {
  const groups = new Map<string, Map<string, { row: SourceRow; pages: number[] }>>();
  citations.forEach((citation, index) => {
    const cohort = citation.cohort?.trim() || NO_COHORT;
    const article = articleOf(citation);
    const title = rowTitle(citation, article);
    // Canonical ids already identify an article/table in a document. Legacy sources
    // need document + article, or an exact parent id. Never merge by number alone.
    const identity = citation.canonical_source_id?.trim()
      || (citation.document_identity?.trim() && article
        ? JSON.stringify([citation.document_identity.trim(), article]) : '')
      || citation.source_parent_id?.trim() || citation.parent_section_id?.trim()
      || `chunk:${citation.chunk_id}`;
    const key = JSON.stringify([cohort, identity]);
    const rows = groups.get(cohort) ?? new Map();
    groups.set(cohort, rows);
    const existing = rows.get(key);
    if (existing) {
      existing.pages.push(...(citation.source_pages ?? []));
      existing.row.citationIndexes.push(index);
      return;
    }
    rows.set(key, {
      pages: [...(citation.source_pages ?? [])],
      row: {
        key,
        article: article ?? 'Mục',
        title,
        document: shortDocumentName(citation.source_section),
        pages: '',
        citationIndex: index,
        citationIndexes: [index],
      },
    });
  });

  const ordered = [...groups.entries()].sort(([a], [b]) => {
    if (a === currentCohort) return -1;
    if (b === currentCohort) return 1;
    if (a === NO_COHORT) return 1;
    if (b === NO_COHORT) return -1;
    return a.localeCompare(b);
  });
  return ordered.map(([cohort, rows]) => ({
    cohort,
    rows: [...rows.values()].map(({ row, pages }) => ({ ...row, pages: pageLabel(pages) })),
  }));
}
