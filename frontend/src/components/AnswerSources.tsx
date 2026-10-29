import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { Citation } from '../hooks/useChat';
import { groupCitations } from '../utils/citationGroups';

interface AnswerSourcesProps {
  citations: Citation[];
  cohort?: string;
  onOpen: (citation: Citation) => void;
}

const ROWS_PER_GROUP = 3;

/** "K49" → "49" for the round cohort badge; anything else keeps its first letters. */
function badgeText(cohort: string): string {
  const digits = cohort.match(/\d+/);
  return digits ? digits[0] : cohort.slice(0, 2);
}

// Closed: one pill naming how many sources and from which cohort handbooks.
// Open: one row per article (article, title, short document name, page), grouped by
// cohort when the answer drew on more than one; a row opens the article itself.
export function AnswerSources({ citations, cohort, onOpen }: AnswerSourcesProps) {
  const groups = useMemo(() => groupCitations(citations, cohort), [citations, cohort]);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const total = groups.reduce((sum, group) => sum + group.rows.length, 0);
  const cohorts = groups.map((group) => group.cohort).filter((name) => name !== 'Chung');
  const showHeadings = groups.length > 1;

  return (
    <div className="answer-sources">
      <button type="button" className="answer-sources-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="answer-sources-stack" aria-hidden="true">
          {(cohorts.length ? cohorts : ['Chung']).slice(0, 3).map((name) => (
            <i key={name} className={`cohort-dot cohort-${name.toLowerCase()}`}>{badgeText(name)}</i>
          ))}
        </span>
        <span className="answer-sources-label">
          <b>{total} nguồn</b>
          {cohorts.length > 0 && (
            <>
              <span className="answer-sources-from"> từ Sổ tay </span>
              <span className="answer-sources-sep"> · </span>
              {cohorts.join(', ')}
            </>
          )}
        </span>
        <ChevronDown size={15} className="answer-sources-chevron" aria-hidden="true" />
      </button>

      {open && (
        <div className="answer-sources-list">
          {groups.map((group) => {
            const isExpanded = expanded.has(group.cohort);
            const rows = isExpanded ? group.rows : group.rows.slice(0, ROWS_PER_GROUP);
            const hidden = group.rows.length - rows.length;
            return (
              <div key={group.cohort} className="answer-sources-group">
                {showHeadings && (
                  <div className="answer-sources-heading">
                    <i className={`cohort-chip cohort-${group.cohort.toLowerCase()}`}>{group.cohort}</i>
                    <span>{group.cohort === 'Chung' ? 'Dữ liệu tra cứu' : `Sổ tay khóa ${badgeText(group.cohort)}`}</span>
                    <small>{group.rows.length} nguồn</small>
                  </div>
                )}
                {rows.map((row) => (
                  <button
                    key={row.key}
                    type="button"
                    className="answer-source-row"
                    onClick={() => {
                      const originals = row.citationIndexes.map((i) => citations[i]);
                      const text = [...new Set(originals.map((c) => c.parent_content || c.content).filter(Boolean))].join('\n\n');
                      onOpen({
                        ...citations[row.citationIndex],
                        parent_content: text,
                        source_pages: [...new Set(originals.flatMap((c) => c.source_pages ?? []))].sort((a, b) => a - b),
                      });
                    }}
                  >
                    <span className="answer-source-article">{row.article}</span>
                    <span className="answer-source-text">
                      <b>{row.title}</b>
                      {row.document && <small>{row.document}</small>}
                    </span>
                    {row.pages && <span className="answer-source-pages">{row.pages}</span>}
                    <ChevronRight size={15} aria-hidden="true" />
                  </button>
                ))}
                {hidden > 0 && (
                  <button
                    type="button"
                    className="answer-sources-more"
                    onClick={() => setExpanded((prev) => new Set(prev).add(group.cohort))}
                  >
                    Xem thêm {hidden} nguồn{showHeadings ? ` ${group.cohort}` : ''}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
