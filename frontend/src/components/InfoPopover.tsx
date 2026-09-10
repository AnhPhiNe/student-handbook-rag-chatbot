import { useState, useRef, useEffect, useLayoutEffect, type ReactNode } from 'react';
import { Info } from 'lucide-react';

export interface InfoPopoverProps {
  title?: string;
  content: ReactNode;
  align?: 'left' | 'right' | 'center';
  placement?: 'top' | 'bottom';
  className?: string;
  ariaLabel?: string;
  iconSize?: number;
}

export function InfoPopover({
  title,
  content,
  align = 'right',
  placement = 'top',
  className = '',
  ariaLabel,
  iconSize = 13,
}: InfoPopoverProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLSpanElement>(null);
  const bubbleRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<number | null>(null);

  const clearCloseTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const isTouchDevice = () => {
    if (typeof window === 'undefined') return false;
    return !window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  };

  const handleMouseEnter = () => {
    if (isTouchDevice()) return;
    clearCloseTimer();
    setIsOpen(true);
  };

  const handleMouseLeave = () => {
    if (isTouchDevice()) return;
    clearCloseTimer();
    timerRef.current = window.setTimeout(() => {
      setIsOpen(false);
    }, 180);
  };

  // Adjust position to ensure bubble never overflows screen
  useLayoutEffect(() => {
    if (!isOpen || !bubbleRef.current || !containerRef.current) return;

    const bubble = bubbleRef.current;
    const trigger = containerRef.current;
    const padding = 12; // min margin from screen edge

    // Reset inline overrides first to measure natural position
    bubble.style.transform = '';
    bubble.style.removeProperty('--arrow-left');
    bubble.style.removeProperty('--arrow-right');

    const bubbleRect = bubble.getBoundingClientRect();
    const triggerRect = trigger.getBoundingClientRect();
    let shift = 0;

    if (bubbleRect.left < padding) {
      shift = padding - bubbleRect.left;
    } else if (bubbleRect.right > window.innerWidth - padding) {
      shift = window.innerWidth - padding - bubbleRect.right;
    }

    if (shift !== 0) {
      bubble.style.transform = `translateX(${shift}px)`;
      // Arrow adjustment so it stays pinned above the trigger button
      const triggerCenterX = triggerRect.left + triggerRect.width / 2;
      const bubbleNewLeft = bubbleRect.left + shift;
      const arrowLeft = Math.max(12, Math.min(bubbleRect.width - 12, triggerCenterX - bubbleNewLeft));
      bubble.style.setProperty('--arrow-left', `${arrowLeft}px`);
      bubble.style.setProperty('--arrow-right', 'auto');
      bubble.style.setProperty('--arrow-transform', 'translateX(-50%)');
    }
  }, [isOpen]);

  // Close when clicking outside or pressing Escape
  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (e: MouseEvent | TouchEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
      clearCloseTimer();
    };
  }, [isOpen]);

  return (
    <span
      className={`info-popover-wrapper ${className}`.trim()}
      ref={containerRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        type="button"
        className={`course-target-ref-icon-btn info-popover-trigger ${isOpen ? 'active' : ''}`}
        aria-label={ariaLabel || title || 'Thông tin giải thích'}
        aria-expanded={isOpen}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setIsOpen((prev) => !prev);
        }}
        onFocus={handleMouseEnter}
      >
        <Info size={iconSize} />
      </button>

      {isOpen && (
        <div
          ref={bubbleRef}
          className={`info-popover-bubble align-${align} placement-${placement}`}
          role="tooltip"
          onClick={(e) => e.stopPropagation()}
        >
          {title && (
            <div className="info-popover-header">
              <Info size={14} className="info-popover-header-icon" />
              <span className="info-popover-title">{title}</span>
            </div>
          )}
          <div className="info-popover-body">{content}</div>
        </div>
      )}
    </span>
  );
}
