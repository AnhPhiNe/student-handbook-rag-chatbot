import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

interface ToolPageHeaderProps {
  icon: LucideIcon;
  title: string;
  description: ReactNode;
}

/** One solid-colour title and one line of description, aligned with the page content. */
export function ToolPageHeader({ icon: Icon, title, description }: ToolPageHeaderProps) {
  return (
    <div className="page-header compact">
      <h1 className="page-title-with-icon">
        <Icon aria-hidden="true" />
        <span>{title}</span>
      </h1>
      <p>{description}</p>
    </div>
  );
}
