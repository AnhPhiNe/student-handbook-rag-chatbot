import type { ResultTone } from './ResultCard';

interface ToolMobileSummaryProps {
  label: string;
  value: string;
  unit?: string;
  chip?: string | null;
  tone?: ResultTone | null;
}

/**
 * A slim bar that stays at the top on phones for pages with long input tables,
 * so the result stays visible while typing. Hidden from assistive tech: the result card carries the same data.
 */
export function ToolMobileSummary({ label, value, unit, chip, tone }: ToolMobileSummaryProps) {
  return (
    <div className={['tool-mobile-summary', tone && `tone-${tone}`].filter(Boolean).join(' ')} aria-hidden="true">
      <span className="tool-mobile-summary-label">{label}</span>
      <strong>
        {value}
        {unit && <small>{unit}</small>}
      </strong>
      {chip && <span className="tool-status-chip">{chip}</span>}
    </div>
  );
}
