import type { ReactNode } from 'react';
import { Minus, Plus } from 'lucide-react';
import { sanitizeInteger } from '../../utils/numberInput';

interface NumberStepperProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  min: number;
  /** Used by the −/+ buttons while the input is empty. */
  fallback: number;
  hint?: ReactNode;
}

export function NumberStepper({ id, label, value, onChange, min, fallback, hint }: NumberStepperProps) {
  const current = Number(value || fallback);
  const hintId = hint ? `${id}-hint` : undefined;

  return (
    <div className="tool-control">
      <label htmlFor={id}>{label}</label>
      <div className="tool-stepper">
        <button
          type="button"
          onClick={() => onChange(String(Math.max(min, current - 1)))}
          aria-label={`Giảm ${label.toLowerCase()}`}
        >
          <Minus size={15} aria-hidden="true" />
        </button>
        <input
          id={id}
          type="text"
          inputMode="numeric"
          maxLength={3}
          value={value}
          onChange={(e) => onChange(sanitizeInteger(e.target.value))}
          aria-describedby={hintId}
        />
        <button
          type="button"
          onClick={() => onChange(String(Math.max(min, current) + 1))}
          aria-label={`Tăng ${label.toLowerCase()}`}
        >
          <Plus size={15} aria-hidden="true" />
        </button>
      </div>
      {hint && <p id={hintId} className="tool-hint">{hint}</p>}
    </div>
  );
}
