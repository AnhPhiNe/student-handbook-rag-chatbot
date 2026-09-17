import type { ReactNode } from 'react';
import { AlertTriangle, CircleCheck, Lightbulb } from 'lucide-react';
import type { ResultTone } from './ResultCard';

interface ResultCalloutProps {
  tone?: ResultTone | null;
  children: ReactNode;
}

/** The one thing to act on in a result, tinted by tone; put the key figures in <strong>. */
export function ResultCallout({ tone = null, children }: ResultCalloutProps) {
  const Icon = tone === 'danger' || tone === 'warning' ? AlertTriangle : tone === 'success' ? CircleCheck : Lightbulb;

  return (
    <div className={`tool-advice ${tone ? `tone-${tone}` : 'neutral'}`}>
      <Icon size={17} aria-hidden="true" />
      <p>{children}</p>
    </div>
  );
}
