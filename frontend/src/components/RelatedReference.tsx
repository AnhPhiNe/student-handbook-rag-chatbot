import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { BookOpen, ExternalLink } from 'lucide-react';

import type { RelatedReference } from '../hooks/useChat';

interface RelatedReferenceProps {
  reference: RelatedReference;
  children: ReactNode;
  onOpenDetail: (reference: RelatedReference) => void;
}

export function RelatedReferenceLink({
  reference,
  children,
  onOpenDetail,
}: RelatedReferenceProps) {
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [previewPlacement, setPreviewPlacement] = useState<'above' | 'below'>('above');
  const [previewStyle, setPreviewStyle] = useState<CSSProperties>();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const previewRef = useRef<HTMLSpanElement>(null);
  const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pagesLabel = reference.source_pages?.length
    ? `Trang ${reference.source_pages.join(', ')}`
    : null;
  const sourceLabel = reference.source_kind === 'primary'
    ? 'nguồn chính'
    : 'điều khoản liên quan';

  const cancelScheduledClose = () => {
    if (closeTimeoutRef.current !== null) {
      clearTimeout(closeTimeoutRef.current);
      closeTimeoutRef.current = null;
    }
  };

  const openPreview = () => {
    cancelScheduledClose();
    if (!isPreviewOpen) {
      setPreviewPlacement('above');
      setPreviewStyle(undefined);
      setIsPreviewOpen(true);
    }
  };

  const schedulePreviewClose = () => {
    cancelScheduledClose();
    closeTimeoutRef.current = setTimeout(() => {
      setIsPreviewOpen(false);
      closeTimeoutRef.current = null;
    }, 240);
  };

  useEffect(() => () => {
    if (closeTimeoutRef.current !== null) {
      clearTimeout(closeTimeoutRef.current);
    }
  }, []);

  useLayoutEffect(() => {
    if (!isPreviewOpen) return;

    const updatePosition = () => {
      const trigger = triggerRef.current;
      const preview = previewRef.current;
      if (!trigger || !preview) return;

      const gutter = 12;
      const gap = 8;
      const triggerRect = trigger.getBoundingClientRect();
      const previewRect = preview.getBoundingClientRect();
      const spaceAbove = triggerRect.top - gutter - gap;
      const spaceBelow = window.innerHeight - triggerRect.bottom - gutter - gap;
      const placeBelow = spaceAbove < previewRect.height && spaceBelow > spaceAbove;
      const availableHeight = Math.max(0, placeBelow ? spaceBelow : spaceAbove);

      setPreviewPlacement(placeBelow ? 'below' : 'above');
      setPreviewStyle({
        maxHeight: availableHeight,
      });
    };

    const animationFrame = requestAnimationFrame(updatePosition);
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);

    return () => {
      cancelAnimationFrame(animationFrame);
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [isPreviewOpen]);

  return (
    <span
      className="related-reference"
      onFocus={openPreview}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          schedulePreviewClose();
        }
      }}
    >
      <button
        type="button"
        className="related-reference-trigger"
        ref={triggerRef}
        onMouseEnter={openPreview}
        onMouseLeave={schedulePreviewClose}
        onClick={() => onOpenDetail(reference)}
        aria-haspopup="dialog"
        aria-label={`Mở ${sourceLabel}: ${reference.title}`}
      >
        {children}
        <sup aria-hidden="true">{reference.id}</sup>
      </button>

      {isPreviewOpen && (
        <span
          ref={previewRef}
          className={`related-reference-preview related-reference-preview--${previewPlacement}`}
          role="tooltip"
          style={previewStyle}
          onMouseEnter={cancelScheduledClose}
          onMouseLeave={schedulePreviewClose}
        >
          <span className="related-reference-preview-title">
            <BookOpen size={14} aria-hidden="true" />
            {reference.title}
          </span>
          {reference.cohort && (
            <span className="related-reference-preview-meta">{reference.cohort}</span>
          )}
          {pagesLabel && (
            <span className="related-reference-preview-meta">{pagesLabel}</span>
          )}
          {reference.preview && (
            <span className="related-reference-preview-copy">{reference.preview}</span>
          )}
          <span className="related-reference-preview-actions">
            <button type="button" onClick={() => onOpenDetail(reference)}>
              Xem đầy đủ
            </button>
            {reference.source_url && (
              <a
                href={reference.source_url}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => event.stopPropagation()}
              >
                Mở nguồn <ExternalLink size={12} aria-hidden="true" />
              </a>
            )}
          </span>
        </span>
      )}
    </span>
  );
}
