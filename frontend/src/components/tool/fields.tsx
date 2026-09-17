import type { ReactNode } from 'react';

interface TextFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  suffix?: string;
  placeholder?: string;
  hint?: ReactNode;
  error?: string | null;
  inputMode?: 'decimal' | 'numeric';
  /** Rendered right under the input, e.g. quick-pick chips. */
  children?: ReactNode;
}

export function TextField({
  id,
  label,
  value,
  onChange,
  suffix,
  placeholder,
  hint,
  error,
  inputMode = 'decimal',
  children,
}: TextFieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined;

  return (
    <div className="tool-control">
      <label htmlFor={id}>{label}</label>
      <div className={`tool-text-input ${error ? 'invalid' : ''}`}>
        <input
          id={id}
          type="text"
          inputMode={inputMode}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={describedBy}
        />
        {suffix && <span aria-hidden="true">{suffix}</span>}
      </div>
      {children}
      {error && <p id={errorId} className="tool-error">{error}</p>}
      {hint && <p id={hintId} className="tool-hint">{hint}</p>}
    </div>
  );
}

interface SelectFieldProps<T extends string> {
  id: string;
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}

export function SelectField<T extends string>({ id, label, value, options, onChange }: SelectFieldProps<T>) {
  return (
    <div className="tool-control">
      <label htmlFor={id}>{label}</label>
      <select id={id} className="tool-select-input" value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
