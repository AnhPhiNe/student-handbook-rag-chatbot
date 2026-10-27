import { useEffect, useRef } from 'react';
import type { Cohort } from '../utils/gradeScale';

interface CohortSheetProps {
  cohort: Cohort;
  onSelect: (cohort: Cohort) => void;
  onClose: () => void;
}

const OPTIONS: Array<{ value: Cohort | 'K52'; label: string; disabled?: boolean }> = [
  { value: 'K49', label: 'Khóa 49' },
  { value: 'K50', label: 'Khóa 50' },
  { value: 'K51', label: 'Khóa 51' },
  { value: 'K52', label: 'Khóa 52', disabled: true },
];

// A bottom sheet instead of the browser's <select>: large rows a thumb can hit, and the
// current cohort is named rather than only highlighted.
export function CohortSheet({ cohort, onSelect, onClose }: CohortSheetProps) {
  const currentRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    currentRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="cohort-sheet-backdrop" onClick={onClose}>
      <div
        className="cohort-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cohort-sheet-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="cohort-sheet-grab" aria-hidden="true" />
        <h2 id="cohort-sheet-title">Bạn thuộc khóa nào?</h2>
        <p>Quy chế và thang điểm sẽ theo khóa bạn chọn.</p>
        {OPTIONS.map((option) => {
          const isCurrent = option.value === cohort;
          return (
            <button
              key={option.value}
              ref={isCurrent ? currentRef : undefined}
              type="button"
              className={`cohort-sheet-option${isCurrent ? ' current' : ''}`}
              disabled={option.disabled}
              aria-pressed={isCurrent}
              onClick={() => {
                if (option.value !== 'K52') onSelect(option.value);
                onClose();
              }}
            >
              <span>{option.label}</span>
              {isCurrent && <small>Đang chọn</small>}
              {option.disabled && <small>Sắp có</small>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
