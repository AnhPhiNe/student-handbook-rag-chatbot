import { useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';

interface DetailsToggleProps {
  id: string;
  label: string;
  children: ReactNode;
}

/** A collapsed-by-default panel for detail that only some students need, e.g. the calculation. */
export function DetailsToggle({ id, label, children }: DetailsToggleProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="tool-details-wrap">
      <button
        type="button"
        className="tool-details-toggle"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((value) => !value)}
      >
        <ChevronDown size={15} aria-hidden="true" />
        {label}
      </button>
      <div id={id} className={`tool-details ${open ? 'open' : ''}`} inert={!open}>
        <div>{children}</div>
      </div>
    </div>
  );
}
