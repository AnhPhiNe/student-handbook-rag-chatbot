import { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';

interface ScrollCueProps {
  activeTab: string;
}

const SCROLL_CUE_EXCLUDED_TABS = new Set(['chat']);

export function ScrollCue({ activeTab }: ScrollCueProps) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (SCROLL_CUE_EXCLUDED_TABS.has(activeTab)) {
      setIsVisible(false);
      return;
    }

    const container = document.querySelector<HTMLElement>('.content-area .page-container');
    if (!container) {
      setIsVisible(false);
      return;
    }

    let dismissed = false;

    const updateVisibility = () => {
      const hasOverflow = container.scrollHeight - container.clientHeight > 80;
      const nearTop = container.scrollTop < 24;
      const nearBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 80;
      setIsVisible(hasOverflow && nearTop && !nearBottom && !dismissed);
    };

    const handleScroll = () => {
      if (container.scrollTop > 24) {
        dismissed = true;
      }
      updateVisibility();
    };

    const timer = window.setTimeout(() => {
      dismissed = true;
      updateVisibility();
    }, 7000);

    updateVisibility();
    container.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('resize', updateVisibility);

    return () => {
      window.clearTimeout(timer);
      container.removeEventListener('scroll', handleScroll);
      window.removeEventListener('resize', updateVisibility);
    };
  }, [activeTab]);

  if (!isVisible) return null;

  return (
    <div className="scroll-cue" role="status" aria-live="polite">
      <span>Kéo xuống để xem thêm</span>
      <ChevronDown size={16} />
    </div>
  );
}
