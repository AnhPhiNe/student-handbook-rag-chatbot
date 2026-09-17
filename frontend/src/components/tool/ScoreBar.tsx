interface ScoreBarProps {
  value: number;
  max: number;
  maxLabel: string;
}

/** A 0-to-max bar coloured by the surrounding result tone. Decorative: the number is announced already. */
export function ScoreBar({ value, max, maxLabel }: ScoreBarProps) {
  const percent = Math.min(100, Math.max(0, (value / max) * 100));

  return (
    <div className="tool-bar" aria-hidden="true">
      <div className="tool-bar-track">
        <div className="tool-bar-fill" style={{ width: `${percent}%` }} />
      </div>
      <div className="tool-scale">
        <span>0</span>
        <span>{maxLabel}</span>
      </div>
    </div>
  );
}
