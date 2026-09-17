import type { ReactNode } from 'react';
import { RotateCcw } from 'lucide-react';

interface ToolSectionProps {
  id: string;
  title: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function ToolSection({ id, title, action, className, children }: ToolSectionProps) {
  const titleId = `${id}-title`;
  return (
    <section className={['tool-section', className].filter(Boolean).join(' ')} aria-labelledby={titleId}>
      <div className="tool-section-head">
        <h2 id={titleId}>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function ResetButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="tool-text-btn" onClick={onClick}>
      <RotateCcw size={14} aria-hidden="true" />
      Đặt lại
    </button>
  );
}
