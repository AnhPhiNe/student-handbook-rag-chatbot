import { useEffect, useRef, useState, type RefObject } from 'react';
import { ChevronDown } from 'lucide-react';

interface MobileScrollAffordanceProps {
  activeKey: string;
  containerRef: RefObject<HTMLDivElement | null>;
  disabled?: boolean;
}

export function MobileScrollAffordance({
  activeKey,
  containerRef,
  disabled = false,
}: MobileScrollAffordanceProps) {
  const [isVisible, setIsVisible] = useState(false);
  const scrollTargetRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (disabled) return;

    const root = containerRef.current;
    if (!root) return;

    let resizeObserver: ResizeObserver | null = null;
    let mutationObserver: MutationObserver | null = null;
    let frameId = 0;

    const updateVisibility = () => {
      const target = scrollTargetRef.current;
      const isMobile = window.matchMedia('(max-width: 900px)').matches;

      if (!target || !isMobile) {
        setIsVisible(false);
        return;
      }

      const remaining = target.scrollHeight - target.scrollTop - target.clientHeight;
      setIsVisible(target.scrollHeight > target.clientHeight + 24 && remaining > 32);
    };

    const connectTarget = () => {
      const nextTarget = root.querySelector<HTMLElement>('.page-container');

      if (scrollTargetRef.current !== nextTarget) {
        scrollTargetRef.current?.removeEventListener('scroll', updateVisibility);
        resizeObserver?.disconnect();
        scrollTargetRef.current = nextTarget;

        if (nextTarget) {
          nextTarget.addEventListener('scroll', updateVisibility, { passive: true });
          resizeObserver = new ResizeObserver(updateVisibility);
          resizeObserver.observe(nextTarget);
          if (nextTarget.firstElementChild instanceof HTMLElement) {
            resizeObserver.observe(nextTarget.firstElementChild);
          }
        }
      }

      updateVisibility();
    };

    frameId = window.requestAnimationFrame(connectTarget);
    window.addEventListener('resize', connectTarget);
    mutationObserver = new MutationObserver(connectTarget);
    mutationObserver.observe(root, { childList: true, subtree: true });

    return () => {
      window.cancelAnimationFrame(frameId);
      window.removeEventListener('resize', connectTarget);
      mutationObserver?.disconnect();
      resizeObserver?.disconnect();
      scrollTargetRef.current?.removeEventListener('scroll', updateVisibility);
      scrollTargetRef.current = null;
    };
  }, [activeKey, containerRef, disabled]);

  const scrollDown = () => {
    const target = scrollTargetRef.current;
    if (!target) return;
    target.scrollBy({ top: target.clientHeight * 0.65, behavior: 'smooth' });
  };

  if (disabled || !isVisible) return null;

  return (
    <div className="mobile-scroll-affordance">
      <button
        type="button"
        onClick={scrollDown}
        aria-label="Cuộn xuống xem nội dung tiếp theo"
        title="Còn nội dung bên dưới"
      >
        <ChevronDown size={18} aria-hidden="true" />
      </button>
    </div>
  );
}
