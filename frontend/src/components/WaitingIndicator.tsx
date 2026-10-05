import { useEffect, useState } from 'react';
import { BookOpen } from 'lucide-react';
import type { Citation } from '../hooks/useChat';
import { elapsedLabel, sourceLabels, waitingHint } from '../utils/waitingStatus';

interface WaitingIndicatorProps {
  startedAt?: number;
  progress?: string;
  sources?: Citation[];
  queuePosition?: number | null;
}

// Its own one-second clock, so only this line re-renders while the student
// waits, not the markdown of the whole conversation.
function useElapsed(startedAt?: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!startedAt) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);
  return startedAt ? Math.max(0, now - startedAt) : 0;
}

export function WaitingIndicator({ startedAt, progress, sources, queuePosition }: WaitingIndicatorProps) {
  const elapsedMs = useElapsed(startedAt);
  const elapsed = elapsedLabel(elapsedMs);
  const hint = waitingHint(elapsedMs);
  const { labels, more } = sourceLabels(sources ?? []);

  return (
    <div className="waiting-indicator" role="status" aria-live="polite">
      <div className="waiting-indicator-line">
        <div className="typing-dots-wrapper" aria-hidden="true">
          <div className="typing-dot"></div>
          <div className="typing-dot"></div>
          <div className="typing-dot"></div>
        </div>
        {queuePosition != null ? (
          <span className="waiting-indicator-step">
            Úi đông quá! Còn {queuePosition} lượt chờ nữa là tới bạn, nhâm nhi ngụm nước đợi AI xíu nha ☕
          </span>
        ) : (
          progress && <span className="waiting-indicator-step">{progress}</span>
        )}
        {elapsed && <span className="waiting-indicator-time">{elapsed}</span>}
      </div>
      {labels.length > 0 && (
        <div className="waiting-indicator-sources">
          <span className="waiting-indicator-sources-label">
            <BookOpen size={13} aria-hidden="true" />
            Đang đọc:
          </span>
          {labels.map((label) => (
            <span key={label} className="waiting-indicator-source">{label}</span>
          ))}
          {more > 0 && <span className="waiting-indicator-more">+{more}</span>}
        </div>
      )}
      {hint && <span className="waiting-indicator-hint">{hint}</span>}
    </div>
  );
}
