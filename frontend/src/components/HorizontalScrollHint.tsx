import { useEffect, useState, type RefObject } from 'react';
import { MoveRight } from 'lucide-react';

interface HorizontalScrollHintProps {
  targetRef: RefObject<HTMLElement | null>;
  className?: string;
}

export function HorizontalScrollHint({ targetRef, className = '' }: HorizontalScrollHintProps) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const target = targetRef.current;
    if (!target) return;

    const updateVisibility = () => {
      const hasOverflow = target.scrollWidth - target.clientWidth > 12;
      const isNearEnd = target.scrollLeft + target.clientWidth >= target.scrollWidth - 16;
      setIsVisible(hasOverflow && !isNearEnd);
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

  if (!isVisible) return null;

  return (
    <div className={`horizontal-scroll-hint ${className}`} role="status" aria-live="polite">
      <MoveRight size={14} />
      <span>Vuốt ngang để xem tiếp</span>
    </div>
  );
}
