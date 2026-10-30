import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import {
  ArrowRight,
  BookOpen,
  Contact,
  GraduationCap,
  LayoutGrid,
  Lightbulb,
  MessageSquare,
  Pin,
  RotateCw,
  Search,
} from 'lucide-react';
import { SHOW_EXPERIENCE_PAGE } from '../../config/features';
import { useLocalStorage } from '../../hooks/useLocalStorage';
import { sanitizePinnedIds } from '../../utils/pinnedTools';
import { OwlMascot, type OwlState } from '../OwlMascot';
import { QuickContacts, TipBoard } from './HomeExtras';
import { MAX_QUERY_CHARS } from '../../utils/queryLength';
import './HomePage.css';

interface HomePageProps {
  onNavigate: (tab: string) => void;
  onAskChat: (question: string) => void;
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





function Heading() {
  return (
    <h1 className="hp-title">
      Chào bạn,
      <br />
      <span>hôm nay cần gì nè?</span>
    </h1>
  );
}

interface AskBoxProps {
  onAsk: (question: string) => void;
  onLook: (on: boolean) => void;
  placeholder: string;
  large?: boolean;
  sending: boolean;
  question: string;
  onQuestionChange: (question: string) => void;
}

function AskBox({ onAsk, onLook, placeholder, large, sending, question, onQuestionChange }: AskBoxProps) {
  return (
    <form
      className={`hp-ask${large ? ' hp-ask-lg' : ''}`}
      aria-label="Hỏi về Sổ tay"
      onSubmit={(event) => {
        event.preventDefault();
        if (question.trim() && !sending) onAsk(question.trim());
      }}
      onMouseEnter={() => onLook(true)}
      onMouseLeave={() => onLook(false)}
      onFocus={() => onLook(true)}
      onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) onLook(false); }}
    >
      <Search size={18} aria-hidden="true" />
      <input className="hp-ask-input" aria-label="Câu hỏi về Sổ tay" placeholder={placeholder}
        value={question} onChange={(event) => onQuestionChange(event.target.value)}
        maxLength={MAX_QUERY_CHARS} disabled={sending} />
      <button className="hp-go" type="submit" aria-label="Gửi câu hỏi" disabled={!question.trim() || sending}>
        <ArrowRight size={18} aria-hidden="true" />
      </button>
    </form>
  );
}

interface WisdomTip {
  text: ReactNode;
  citation: string;
}

const HANDBOOK_TIPS: WisdomTip[] = [
  {
    text: (
      <>
        Điểm <b>D (1.0)</b> là qua môn, nhưng để tốt nghiệp loại <b>Khá</b> thì GPA tích lũy cần từ <b>2.50</b> trở lên.
      </>
    ),
    citation: 'Trích Điều 14 · Quy chế đào tạo tín chỉ HCMUE',
  },
  {
    text: (
      <>
        Sinh viên sư phạm được hỗ trợ sinh hoạt phí <b>3,63 triệu/tháng</b> theo diện <b>Nghị định 116</b>.
      </>
    ),
    citation: 'Trích Nghị định 116/2020/NĐ-CP',
  },
  {
    text: (
      <>
        Tránh tích lũy <b>điểm F quá 5%</b> tổng tín chỉ để không bị <b>hạ một bậc</b> tốt nghiệp.
      </>
    ),
    citation: 'Trích Điều 27 · Quy chế xét tốt nghiệp',
  },
  {
    text: (
      <>
        Mỗi học kỳ chính cần đăng ký <b>tối thiểu 14 tín chỉ</b> (trừ học kỳ cuối cùng của khóa học).
      </>
    ),
    citation: 'Trích Điều 8 · Đăng ký học phần',
  },
  {
    text: (
      <>
        Xét học bổng KKHT cần học <b>tối thiểu 15 tín chỉ</b> và điểm rèn luyện đạt từ <b>Khá (70đ)</b> trở lên.
      </>
    ),
    citation: 'Trích Quy định học bổng KKHT HCMUE',
  },
  {
    text: (
      <>
        Sinh viên được <b>rút học phần</b> trong 2 tuần đầu học kỳ mà <b>không bị ghi nhận điểm F</b>.
      </>
    ),
    citation: 'Trích Điều 10 · Rút bớt học phần đã đăng ký',
  },
];

function HandbookWisdomCard({
  tipIndex,
  onNextTip,
}: {
  tipIndex: number;
  onNextTip: () => void;
}) {
  const tip = HANDBOOK_TIPS[tipIndex];
  return (
    <div className="hp-wisdom-card">
      <div className="hp-wisdom-head">
        <span className="hp-wisdom-badge">
          <Lightbulb size={14} className="hp-wisdom-icon" aria-hidden="true" />
          Mẹo quy chế bạn nên biết
        </span>
        <button
          type="button"
          className="hp-wisdom-rotate"
          onClick={onNextTip}
          aria-label="Đổi mẹo quy chế khác"
        >
          <span>Đổi mẹo</span>
          <RotateCw size={12} aria-hidden="true" />
        </button>
      </div>
      <p className="hp-wisdom-text" key={tipIndex}>
        {tip.text}
      </p>
      <span className="hp-wisdom-cite">{tip.citation}</span>
    </div>
  );
}

// What the owl says, one line per tap. Every line must stay true of the app.
const OWL_LINES: ReactNode[] = [
  <>Mình <b>chỉ đọc Sổ tay sinh viên</b> thôi, trả lời kèm Điều, Khoản nha!</>,
  <>Gõ câu hỏi về <b>học bổng, học vụ</b> vào ô hỏi nha!</>,
  <>Cần số phòng ban? Mở <b>Danh bạ</b> nha!</>,
  <>Nhập GPA một lần, <b>các công cụ tự dùng lại</b>.</>,
];
const WAVE_MS = 1700;
const EUREKA_MS = 450;
const OWL_WELCOME_KEY = 'hcmue-owl-welcomed';

/** The owl waves once on arrival, reads while the ask box is hovered, and lights up on send. */
function useOwl(reduced: boolean) {
  const [greeting, setGreeting] = useState(() => {
    if (reduced) return false;
    try { return sessionStorage.getItem(OWL_WELCOME_KEY) !== 'true'; } catch { return true; }
  });
  const sendTimer = useRef<number | null>(null);
  const [mood, setMood] = useState<OwlState>('idle');
  const [line, setLine] = useState(0);
  const [hop, setHop] = useState(0);
  useEffect(() => {
    if (!greeting || reduced) return;
    try { sessionStorage.setItem(OWL_WELCOME_KEY, 'true'); } catch { /* animation still works without storage */ }
    const id = window.setTimeout(() => setGreeting(false), WAVE_MS);
    return () => window.clearTimeout(id);
  }, [greeting, reduced]);
  useEffect(() => () => {
    if (sendTimer.current !== null) window.clearTimeout(sendTimer.current);
  }, []);
  return {
    state: (!reduced && greeting && mood === 'idle' ? 'wave' : mood) as OwlState,
    sending: mood === 'eureka',
    line,
    hop,
    look: (on: boolean) => setMood((m) => (m === 'eureka' ? m : on ? 'reading' : 'idle')),
    poke: () => {
      setLine((i) => (i + 1) % OWL_LINES.length);
      setHop((n) => n + 1);
    },
    /** Light up, then go; reduced motion goes at once. */
    send: (go: () => void) => {
      if (reduced) return go();
      if (sendTimer.current !== null) return;
      setMood('eureka');
      sendTimer.current = window.setTimeout(() => {
        sendTimer.current = null;
        setMood('idle');
        go();
      }, EUREKA_MS);
    },
  };
}

export function HomePage({ onNavigate, onAskChat, cohort }: HomePageProps) {
  const desktop = useMedia(DESKTOP_QUERY);
  const reduced = useMedia(REDUCED_QUERY);
  const [phIndex, setPhIndex] = useState(0);
  const [question, setQuestion] = useState('');
  const [tipIndex, setTipIndex] = useState(0);
  const nextTip = () => {
    setTipIndex((i) => (i + 1) % HANDBOOK_TIPS.length);
  };
  const [storedPins] = useLocalStorage<unknown>('hcmue-pinned-tools', []);

  useEffect(() => {
    if (reduced) return;
    const id = window.setInterval(() => setPhIndex((i) => (i + 1) % PLACEHOLDERS.length), 2600);
    return () => window.clearInterval(id);
  }, [reduced]);

  const owl = useOwl(reduced);
  const askChat = (question: string) => owl.send(() => onAskChat(question));
  const placeholder = PLACEHOLDERS[reduced ? 0 : phIndex];
  const pins = sanitizePinnedIds(storedPins).filter((id) => id in PIN_TOOLS);

  return (
    <div className={`page-container home-page hp-page${desktop && pins.length > 0 ? ' hp-has-pins' : ''}`}>
      <section className="hp-hero">
        <div className="hp-mesh" aria-hidden="true" />
        {desktop ? (
          <div className="hp-hero-grid">
            <div className="hp-left">
              <span className="hp-pill">Sổ tay HCMUE{cohort ? ` · Khóa ${cohort.replace('K', '')}` : ''}</span>
              <Heading />
              <p className="hp-lead">Hỏi quy chế, tính GPA, học bổng, tìm phòng ban trong vài giây.</p>
              <AskBox large onAsk={askChat} onLook={owl.look} placeholder={placeholder} sending={owl.sending} question={question} onQuestionChange={setQuestion} />
            </div>
            <div className="hp-right">
              <div className="hp-mascot-row">
                <div className="hp-say" key={owl.line} aria-live="polite">
                  {OWL_LINES[owl.line]}
                </div>
                <button
                  type="button"
                  className="hp-owl hp-owl-lg hp-owl-btn"
                  key={`owl-${owl.hop}`}
                  data-hop={owl.hop > 0}
                  onClick={owl.poke}
                  aria-label="Cú Sư Phạm, bấm để nghe câu khác"
                >
                  <OwlMascot state={owl.state} size={88} showFrame={false} />
                </button>
              </div>
              <HandbookWisdomCard tipIndex={tipIndex} onNextTip={nextTip} />
            </div>
          </div>
        ) : (
          <div className="hp-hero-grid">
            <div className="hp-row">
              <button type="button" className="hp-owl hp-owl-btn" key={`owl-${owl.hop}`} data-hop={owl.hop > 0} onClick={owl.poke} aria-label="Cú Sư Phạm">
                <OwlMascot state={owl.state} size={78} showFrame={false} />
              </button>
              <div className="hp-row-text">
                <Heading />
                <span className="hp-pill">Chỉ đọc Sổ tay HCMUE{cohort ? ` · Khóa ${cohort.replace('K', '')}` : ''}</span>
              </div>
            </div>
            <AskBox onAsk={askChat} onLook={owl.look} placeholder={placeholder} sending={owl.sending} question={question} onQuestionChange={setQuestion} />
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

        {desktop && pins.length > 0 ? (
          <div className="hp-pins">
            <span className="hp-pins-k"><Pin size={14} aria-hidden="true" />Đã ghim</span>
            {pins.map((id) => {
              const tool = PIN_TOOLS[id];
              return (
                <button key={id} type="button" className="hp-pc" style={{ '--c': tool.color } as CSSProperties} onClick={() => onNavigate(id)}>
                  <i aria-hidden="true">{tool.symbol}</i>
                  {tool.name}
                </button>
              );
            })}
          </div>
        ) : null}
        {/* Tips read only from the experience page, so they appear when that page is on;
            until then the row shows real office numbers instead of sample quotes. */}
        {desktop && (SHOW_EXPERIENCE_PAGE ? <TipBoard onNavigate={onNavigate} /> : <QuickContacts onNavigate={onNavigate} />)}
        {desktop ? null : (
          <div className="hp-mobile-wisdom">
            <HandbookWisdomCard tipIndex={tipIndex} onNextTip={nextTip} />
            <p className="hp-hint">Kết quả chỉ để tham khảo, theo Sổ tay sinh viên.</p>
          </div>
        )}
      </div>
    </div>
  );
}
