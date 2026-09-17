import type { ReactNode } from 'react';
import type { ResultTone } from './ResultCard';

export interface ResultFact {
  label: string;
  value: ReactNode;
  /** Colours the value when it needs attention, e.g. failed courses. */
  tone?: ResultTone | null;
  /** A short hint under the value, e.g. the target still missing. */
  note?: string;
}

/** One row of key figures under the headline: quiet labels, strong values. */
export function ResultFacts({ facts }: { facts: ResultFact[] }) {
  // Every cell gets a note row once any fact has a note, so values stay on one line across cells.
  const hasNotes = facts.some((fact) => fact.note);

  return (
    <dl className={`tool-facts ${hasNotes ? 'has-notes' : ''}`}>
      {facts.map((fact) => (
        <div key={fact.label} className={fact.tone ? `tone-${fact.tone}` : undefined}>
          <dt>{fact.label}</dt>
          <dd>{fact.value}</dd>
          {hasNotes && <dd className="tool-fact-note">{fact.note}</dd>}
        </div>
      ))}
    </dl>
  );
}
