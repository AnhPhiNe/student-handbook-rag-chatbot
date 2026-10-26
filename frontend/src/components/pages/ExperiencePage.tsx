import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowRight, Check, Paperclip, Star, X } from 'lucide-react';
import { EXPERIENCE, type ExperienceTip } from '../../data/experience';
import { filterTips, noteColor } from '../../utils/experience';
import { ToolPageHeader } from '../tool/ToolPageHeader';

interface ExperiencePageProps {
  onAskChat: (text: string) => void;
  onNavigate: (tab: string) => void;
}

const CHAT_QUESTION = 'Kinh nghiệm để đạt học bổng khuyến khích học tập loại Xuất sắc là gì?';
const ALL = 'all';
const PAGE_TITLE = 'Kinh nghiệm học bổng';
const PAGE_LEAD = 'Chia sẻ thật từ những bạn đã giữ học bổng Xuất sắc nhiều kỳ liên tiếp.';
const SHOWS_CHECKLIST = new Set([ALL, 'dieukien']);

type Proof = NonNullable<ExperienceTip['proof']>;

interface LightboxProps {
  proof: Proof;
  onClose: () => void;
}

function Lightbox({ proof, onClose }: LightboxProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      // Only the close button is focusable inside, so Tab stays on it.
      if (event.key === 'Tab') {
        event.preventDefault();
        closeRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Portaled to body: the page container makes its own stacking context under the fixed page controls.
  return createPortal(
    <div
      className="xp-lb"
      role="dialog"
      aria-modal="true"
      aria-label="Ảnh minh chứng"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <button ref={closeRef} type="button" className="xp-lb-close" aria-label="Đóng" onClick={onClose}>
        <X size={22} aria-hidden="true" />
      </button>
      <figure>
        <img src={proof.src} alt={proof.caption} />
        <figcaption>{proof.caption} · thông tin cá nhân đã che</figcaption>
      </figure>
    </div>,
    document.body,
  );
}

interface TipCardProps {
  tip: ExperienceTip;
  position: number;
  expanded: boolean;
  onToggle: () => void;
  onNavigate: (tab: string) => void;
  onOpenProof: (proof: Proof, trigger: HTMLButtonElement) => void;
}

function TipCard({ tip, position, expanded, onToggle, onNavigate, onOpenProof }: TipCardProps) {
  const topic = EXPERIENCE.topics.find((item) => item.id === tip.topic);
  const bodyId = `xp-body-${tip.id}`;
  const initial = tip.author.name.split(' ').pop() ?? '';
  const style = { '--t': topic?.color ?? '#2563eb', '--n': noteColor(position) } as React.CSSProperties;

  return (
    <article className="xp-card" style={style}>
      <span className="xp-tape" aria-hidden="true" />
      <div className="xp-head">
        <span className="xp-topic">{topic?.label}</span>
        {tip.tool && (
          <button
            type="button"
            className="xp-pill"
            aria-label={`Mở công cụ ${tip.tool.label}`}
            onClick={() => onNavigate(tip.tool!.tab)}
          >
            {tip.tool.label}
            <ArrowRight size={12} aria-hidden="true" />
          </button>
        )}
      </div>
      <p className="xp-quote">“{tip.quote}”</p>
      <p className={`xp-body${expanded ? '' : ' clamp'}`} id={bodyId}>
        {tip.body}
      </p>
      <button type="button" className="xp-more" aria-expanded={expanded} aria-controls={bodyId} onClick={onToggle}>
        {expanded ? 'Thu gọn' : 'Đọc tiếp'}
      </button>
      <div className="xp-who">
        <span className="xp-av" aria-hidden="true">
          {initial}
        </span>
        <span className="xp-name">
          <b>{tip.author.name}</b>
          <small>{tip.author.meta}</small>
        </span>
        <span className="xp-badge">{tip.author.badge}</span>
        {tip.proof && (
          <button
            type="button"
            className="xp-clip"
            title="Xem minh chứng"
            aria-label={`Xem ảnh minh chứng: ${tip.proof.caption}`}
            onClick={(event) => onOpenProof(tip.proof!, event.currentTarget)}
          >
            <Paperclip size={17} aria-hidden="true" />
          </button>
        )}
      </div>
    </article>
  );
}

export function ExperiencePage({ onAskChat, onNavigate }: ExperiencePageProps) {
  const { hero, topics, checklist, tips, isSample } = EXPERIENCE;
  const [topicId, setTopicId] = useState(ALL);
  const [openIds, setOpenIds] = useState<ReadonlySet<string>>(new Set());
  const [proof, setProof] = useState<Proof | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  const visible = filterTips(tips, topicId);
  const chips = [{ id: ALL, label: 'Tất cả', color: '' }, ...topics];

  const toggle = (id: string) =>
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const closeProof = () => {
    setProof(null);
    triggerRef.current?.focus();
  };

  return (
    <div className="page-container tool-page simplified xp-page">
      <ToolPageHeader icon={Star} title={PAGE_TITLE} description={PAGE_LEAD} />

      <div className="gpa-m-page-header xp-m-header">
        <div className="gpa-m-title-wrap">
          <Star size={18} aria-hidden="true" className="xp-m-title-icon" />
          <h1 className="gpa-m-page-title">{PAGE_TITLE}</h1>
        </div>
      </div>

      <div className="xp-body-wrap">
        <section className="xp-hero" aria-label="Giới thiệu">
          <h2>{hero.title}</h2>
          <p>{hero.lead}</p>
          <div className="xp-stats">
            {hero.stats.map((stat) => (
              <div key={stat.label}>
                <b>{stat.value}</b>
                <span>{stat.label}</span>
              </div>
            ))}
          </div>
          {isSample && <span className="xp-sample">NỘI DUNG MẪU</span>}
        </section>

        <div className="xp-chips" role="group" aria-label="Chủ đề">
          {chips.map((chip) => (
            <button
              key={chip.id}
              type="button"
              data-topic={chip.id}
              style={{ '--dot': chip.color } as React.CSSProperties}
              aria-pressed={topicId === chip.id}
              onClick={() => setTopicId(chip.id)}
            >
              {chip.label}
            </button>
          ))}
        </div>

        {SHOWS_CHECKLIST.has(topicId) && (
          <section className="xp-check" aria-labelledby="xp-check-title">
            <h3 id="xp-check-title">{checklist.title}</h3>
            <ul>
              {checklist.items.map((item) => (
                <li key={item}>
                  <Check size={16} strokeWidth={2.5} aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <div className="src">
              <span>{checklist.source}</span>
              <button type="button" className="xp-tool" onClick={() => onNavigate(checklist.link.tab)}>
                {checklist.link.label} →
              </button>
            </div>
          </section>
        )}

        <div className="xp-grid">
          {visible.map((tip, position) => (
            <TipCard
              key={tip.id}
              tip={tip}
              position={position}
              expanded={openIds.has(tip.id)}
              onToggle={() => toggle(tip.id)}
              onNavigate={onNavigate}
              onOpenProof={(selected, trigger) => {
                triggerRef.current = trigger;
                setProof(selected);
              }}
            />
          ))}
        </div>

        <div className="xp-foot">
          <span>Mỗi người một cách học, hãy chọn điều hợp với bạn.</span>
          <button type="button" className="xp-tool" onClick={() => onAskChat(CHAT_QUESTION)}>
            Hỏi chatbot về học bổng
          </button>
        </div>
      </div>

      {proof && <Lightbox proof={proof} onClose={closeProof} />}
    </div>
  );
}
