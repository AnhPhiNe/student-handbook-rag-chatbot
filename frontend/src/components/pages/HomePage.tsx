import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import {
  ArrowRight,
  BookOpen,
  Contact,
  GraduationCap,
  LayoutGrid,
  MessageSquare,
  Pin,
  Search,
} from 'lucide-react';
import { SHOW_EXPERIENCE_PAGE } from '../../config/features';
import { useLocalStorage } from '../../hooks/useLocalStorage';
import { useStudentProfile } from '../../hooks/useStudentProfile';
import { sanitizePinnedIds } from '../../utils/pinnedTools';
import { summarizeProfile, type HomeSummary } from '../../utils/homeSummary';
import { OwlMascot } from '../OwlMascot';
import { QuickContacts, TipBoard } from './HomeExtras';
import './HomePage.css';

interface HomePageProps {
  onNavigate: (tab: string) => void;
  /** e.g. 'K50'; named in the hero pill so the student sees which handbook answers. */
  cohort?: string;
}

interface Door {
  id: string;
  title: string;
  hint: string;
  color: string;
  icon: ReactNode;
  sticker?: { text: string; isNew?: boolean };
  filled?: boolean;
}

const PLACEHOLDERS = [
  'Học bổng Xuất sắc cần gì?',
  'Rớt môn có bị hạ bằng không?',
  'Phúc khảo bài thi ở đâu?',
  'Đăng ký tối thiểu bao nhiêu tín chỉ?',
];

const CHIPS = ['HB Xuất sắc cần gì?', 'Rớt môn có hạ bằng?', 'Phúc khảo ở đâu?'];

const DOORS: Door[] = [
  { id: 'chat', title: 'Hỏi AI', hint: 'Có dẫn Điều, Khoản', color: '#1E4FD8', icon: <MessageSquare size={22} />, filled: true },
  { id: 'tools', title: 'Công cụ', hint: 'GPA, học bổng, học phí', color: '#E11D48', icon: <LayoutGrid size={22} />, sticker: { text: 'Hay dùng' } },
  { id: 'danh-ba', title: 'Danh bạ', hint: 'Gọi đúng phòng ban', color: '#059669', icon: <Contact size={22} /> },
  SHOW_EXPERIENCE_PAGE
    ? { id: 'kinh-nghiem', title: 'Kinh nghiệm', hint: 'Từ bạn HB Xuất sắc', color: '#D97706', icon: <GraduationCap size={22} />, sticker: { text: 'Mới', isNew: true } }
    : { id: 'huong-dan', title: 'Cách dùng web', hint: 'Xem cách dùng trang', color: '#7C3AED', icon: <BookOpen size={22} /> },
];

const PIN_TOOLS: Record<string, { name: string; symbol: string; color: string }> = {
  gpa: { name: 'Tính GPA', symbol: 'Σ', color: '#2251CC' },
  'target-gpa': { name: 'Mục tiêu GPA', symbol: '↗', color: '#D7263D' },
  'course-target': { name: 'Mục tiêu môn', symbol: '≥', color: '#0E8A9E' },
  scholarship: { name: 'Học bổng', symbol: '★', color: '#6D3FD1' },
  tuition: { name: 'Học phí', symbol: '₫', color: '#E0A100' },
  credits: { name: 'Hạ bằng', symbol: '%', color: '#1E8A55' },
};

const DESKTOP_QUERY = '(min-width: 901px)';
const REDUCED_QUERY = '(prefers-reduced-motion: reduce)';

function useMedia(query: string): boolean {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}

/** Counts from 0 to target once on mount; shows the target at once for reduced motion. */
function useCountUp(target: number, skip: boolean): number {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (skip) return;
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 800);
      setValue(target * (1 - Math.pow(1 - t, 3)));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, skip]);
  return skip ? target : value;
}

function Ring({ percent, label, large }: { percent: number; label: string; large?: boolean }) {
  return (
    <span className={`hp-ring${large ? ' hp-ring-lg' : ''}`} style={{ '--p': `${percent}%` } as CSSProperties}>
      <b>{label}</b>
    </span>
  );
}

function Heading() {
  return (
    <h1 className="hp-title">
      Chào bạn,
      <br />
      <span>hôm nay cần gì nè?</span>
    </h1>
  );
}

function AskBox({ onNavigate, placeholder, large }: { onNavigate: (tab: string) => void; placeholder: string; large?: boolean }) {
  return (
    <button
      type="button"
      className={`hp-ask${large ? ' hp-ask-lg' : ''}`}
      aria-label="Mở Chat để hỏi về Sổ tay"
      onClick={() => onNavigate('chat')}
    >
      <Search size={18} aria-hidden="true" />
      <span className="hp-ask-text" key={placeholder}>{placeholder}</span>
      <span className="hp-go"><ArrowRight size={18} aria-hidden="true" /></span>
    </button>
  );
}

function SideCard({ summary, gpaText, onNavigate }: { summary: HomeSummary; gpaText: string; onNavigate: (tab: string) => void }) {
  const { gpa, credits } = summary;
  return (
    <div className="hp-glass">
      <span className="hp-glass-k">Của bạn</span>
      {summary.hasProfile ? (
        <>
          <div className="hp-glass-top">
            <Ring large percent={summary.gpaPercent} label={gpa === null ? '—' : `${summary.gpaPercent}%`} />
            <span className="hp-glass-gpa">
              <span className="hp-glass-num">{gpa === null ? '—' : gpaText}</span>
              <p>{gpa === null ? 'Chưa có GPA tích lũy' : 'GPA tích lũy'}</p>
            </span>
          </div>
          {credits && (
            <div className="hp-bar">
              <span>Tín chỉ</span>
              <i><b style={{ width: `${credits.percent}%` }} /></i>
              <span>{credits.done}/{credits.total}</span>
            </div>
          )}
          <button type="button" className="hp-glass-link" onClick={() => onNavigate('target-gpa')}>
            Mở Mục tiêu GPA <ArrowRight size={15} aria-hidden="true" />
          </button>
        </>
      ) : (
        <div className="hp-glass-empty">
          <p>Chưa có số liệu</p>
          <button type="button" className="hp-glass-btn" onClick={() => onNavigate('target-gpa')}>
            Nhập GPA của bạn
          </button>
        </div>
      )}
    </div>
  );
}

export function HomePage({ onNavigate, cohort }: HomePageProps) {
  const desktop = useMedia(DESKTOP_QUERY);
  const reduced = useMedia(REDUCED_QUERY);
  const [phIndex, setPhIndex] = useState(0);
  const { profile } = useStudentProfile();
  const [storedPins] = useLocalStorage<unknown>('hcmue-pinned-tools', []);

  useEffect(() => {
    if (reduced) return;
    const id = window.setInterval(() => setPhIndex((i) => (i + 1) % PLACEHOLDERS.length), 2600);
    return () => window.clearInterval(id);
  }, [reduced]);

  const summary = summarizeProfile(profile);
  const counted = useCountUp(summary.gpa ?? 0, reduced);
  const gpaText = counted.toFixed(2);
  const placeholder = PLACEHOLDERS[reduced ? 0 : phIndex];
  const pins = sanitizePinnedIds(storedPins).filter((id) => id in PIN_TOOLS);

  return (
    <div className="page-container home-page hp-page">
      <section className="hp-hero">
        <div className="hp-mesh" aria-hidden="true" />
        {desktop ? (
          <div className="hp-hero-grid">
            <div className="hp-left">
              <span className="hp-pill">Sổ tay HCMUE{cohort ? ` · Khóa ${cohort.replace('K', '')}` : ''}</span>
              <Heading />
              <p className="hp-lead">Hỏi quy chế, tính GPA, học bổng, tìm phòng ban trong vài giây.</p>
              <AskBox large onNavigate={onNavigate} placeholder={placeholder} />
              <div className="hp-chips">
                {CHIPS.map((chip) => (
                  <button key={chip} type="button" className="hp-chip" onClick={() => onNavigate('chat')}>
                    {chip}
                  </button>
                ))}
              </div>
            </div>
            <div className="hp-right">
              <div className="hp-say">
                Mình <b>chỉ đọc Sổ tay sinh viên</b> thôi, trả lời kèm Điều, Khoản nha!
              </div>
              <div className="hp-owl hp-owl-lg">
                <OwlMascot state="idle" size={104} showFrame={false} />
              </div>
              <SideCard summary={summary} gpaText={gpaText} onNavigate={onNavigate} />
            </div>
          </div>
        ) : (
          <div className="hp-hero-grid">
            <div className="hp-row">
              <div className="hp-owl">
                <OwlMascot state="idle" size={78} showFrame={false} />
              </div>
              <div className="hp-row-text">
                <Heading />
                <span className="hp-pill">Chỉ đọc Sổ tay HCMUE{cohort ? ` · Khóa ${cohort.replace('K', '')}` : ''}</span>
              </div>
            </div>
            <AskBox onNavigate={onNavigate} placeholder={placeholder} />
          </div>
        )}
      </section>

      <div className="hp-body">
        <div className="hp-doors">
          {DOORS.map((door, i) => (
            <button
              key={door.id}
              type="button"
              className={`hp-door${door.filled ? ' hp-door-fill' : ''}`}
              style={{ '--c': door.color, animationDelay: `${i * 60}ms` } as CSSProperties}
              onClick={() => onNavigate(door.id)}
            >
              {door.sticker && (
                <span className={`hp-sticker${door.sticker.isNew ? ' hp-sticker-new' : ''}`}>{door.sticker.text}</span>
              )}
              <span className="hp-door-icon" aria-hidden="true">{door.icon}</span>
              <b>{door.title}</b>
              <small>{door.hint}</small>
            </button>
          ))}
        </div>

        {desktop ? (
          <div className="hp-pins">
            {pins.length > 0 && (
              <span className="hp-pins-k"><Pin size={14} aria-hidden="true" />Đã ghim</span>
            )}
            {pins.map((id) => {
              const tool = PIN_TOOLS[id];
              return (
                <button key={id} type="button" className="hp-pc" style={{ '--c': tool.color } as CSSProperties} onClick={() => onNavigate(id)}>
                  <i aria-hidden="true">{tool.symbol}</i>
                  {tool.name}
                </button>
              );
            })}
            <button type="button" className="hp-pc hp-pc-add" onClick={() => onNavigate('tools')}>
              + Ghim thêm
            </button>
          </div>
        ) : null}
        {/* Tips read only from the experience page, so they appear when that page is on;
            until then the row shows real office numbers instead of sample quotes. */}
        {desktop && (SHOW_EXPERIENCE_PAGE ? <TipBoard onNavigate={onNavigate} /> : <QuickContacts onNavigate={onNavigate} />)}
        {desktop ? null : (
          <>
            {summary.hasProfile && (
              <button type="button" className="hp-mgpa" onClick={() => onNavigate('target-gpa')}>
                <Ring percent={summary.gpaPercent} label={summary.gpa === null ? '—' : `${summary.gpaPercent}%`} />
                <span className="hp-mgpa-tx">
                  <span className="hp-mgpa-num">{summary.gpa === null ? '—' : gpaText}</span>
                  <small><b>GPA tích lũy</b>{summary.gpa === null ? ' · Chưa có số liệu' : ''}</small>
                </span>
                <span className="hp-mgpa-lk">Xem <ArrowRight size={15} aria-hidden="true" /></span>
              </button>
            )}
            <p className="hp-hint">Kết quả chỉ để tham khảo, theo Sổ tay sinh viên.</p>
          </>
        )}
      </div>
    </div>
  );
}
