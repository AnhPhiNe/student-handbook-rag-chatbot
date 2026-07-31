import { useEffect, useState, type RefObject } from 'react';

interface HorizontalScrollHintProps {
  targetRef: RefObject<HTMLElement | null>;
  className?: string;
  text?: string;
}

export function HorizontalScrollHint({ targetRef, className = '', text = 'Vuốt ngang để xem tiếp' }: HorizontalScrollHintProps) {
  const [status, setStatus] = useState({ hasOverflow: false, isNearEnd: false });

  useEffect(() => {
    const target = targetRef.current;
    if (!target) return;

    const updateVisibility = () => {
      const hasOverflow = target.scrollWidth - target.clientWidth > 12;
      const isNearEnd = target.scrollLeft + target.clientWidth >= target.scrollWidth - 16;
      setStatus({ hasOverflow, isNearEnd });
    };

    const resizeObserver = new ResizeObserver(updateVisibility);
    resizeObserver.observe(target);
    updateVisibility();

    target.addEventListener('scroll', updateVisibility, { passive: true });
    window.addEventListener('resize', updateVisibility);

    return () => {
      resizeObserver.disconnect();
      target.removeEventListener('scroll', updateVisibility);
      window.removeEventListener('resize', updateVisibility);
    };
  }, [targetRef]);

  if (!status.hasOverflow) return null;

  return (
    <div 
      className={`horizontal-scroll-hint ${className}`} 
      style={{ 
        opacity: status.isNearEnd ? 0 : 1,
        visibility: status.isNearEnd ? 'hidden' : 'visible',
        animation: status.isNearEnd ? 'none' : undefined
      }}
      role="status" 
      aria-live="polite"
    >
      {text}
    </div>
  );
}
