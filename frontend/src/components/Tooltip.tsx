import type { ReactNode } from 'react';

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Tooltip({ content, children, className = '' }: TooltipProps) {
  return (
    <span className={`ui-tooltip ${className}`.trim()}>
      {children}
      <span className="ui-tooltip-content" role="tooltip">
        {content}
      </span>
    </span>
  );
}
