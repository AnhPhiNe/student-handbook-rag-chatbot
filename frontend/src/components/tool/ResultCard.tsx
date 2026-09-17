import { useState, type ReactNode } from 'react';

export type ResultTone = 'success' | 'warning' | 'danger';

interface ResultCardProps {
  id: string;
  title?: string;
  tone?: ResultTone | null;
  chip?: string | null;
  children: ReactNode;
}

/** The one lifted element on a tool page; its tint and accents follow `tone`. */
export function ResultCard({ id, title = 'Kết quả', tone = null, chip = null, children }: ResultCardProps) {
  // The chip pulses only when its label changes between two results, never on first render.
  const [lastChip, setLastChip] = useState(chip);
  const [chipChanges, setChipChanges] = useState(0);
  if (chip !== lastChip) {
    setLastChip(chip);
    if (lastChip && chip) setChipChanges((count) => count + 1);
  }

  const titleId = `${id}-title`;
  return (
    <aside className={['tool-result', tone && `tone-${tone}`].filter(Boolean).join(' ')} aria-labelledby={titleId}>
      <div className="tool-result-top">
        <span id={titleId}>{title}</span>
        {chip && (
          <span key={chipChanges} className={`tool-status-chip ${chipChanges > 0 ? 'pulse' : ''}`}>
            {chip}
          </span>
        )}
      </div>
      {children}
    </aside>
  );
}
