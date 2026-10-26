import { useState, type KeyboardEvent, type ReactNode } from 'react';
import {
  Award,
  BookOpen,
  ChevronRight,
  ClipboardCheck,
  Contact,
  Copy,
  CreditCard,
  GraduationCap,
  Heart,
  House,
  Mail,
  MessageCircle,
  Phone,
  Search,
  X,
  type LucideIcon,
} from 'lucide-react';
import { DIRECTORY_SOURCE, FACULTIES, OFFICES, type DirectoryUnit } from '../../data/directory';
import { contactText, findHighlight, searchUnits, telHref, unitsForTask } from '../../utils/directory';
import { useToast } from '../Toast';
import { ToolPageHeader } from '../tool/ToolPageHeader';

interface DirectoryPageProps {
  onAskChat: (text: string) => void;
}

interface DirectoryTask {
  /** Short label under the icon on phones. */
  label: string;
  /** Full wording for the tooltip and screen readers. */
  full: string;
  /** Part of a unit name the task points at. */
  match: string;
  icon: LucideIcon;
}

const TASKS: DirectoryTask[] = [
  { label: 'Học phí', full: 'Học phí, biên lai', match: 'Kế hoạch – Tài chính', icon: CreditCard },
  { label: 'Học bổng', full: 'Học bổng, rèn luyện', match: 'Công tác chính trị', icon: Award },
  { label: 'NĐ 116', full: 'Nghị định 116 (sinh viên sư phạm)', match: 'Công tác chính trị', icon: GraduationCap },
  { label: 'Học phần', full: 'Đăng ký học phần', match: 'Phòng Đào tạo', icon: BookOpen },
  { label: 'Thi cử', full: 'Lịch thi, phúc khảo, bảng điểm', match: 'Khảo thí', icon: ClipboardCheck },
  { label: 'Tài khoản', full: 'Email, tài khoản, wifi', match: 'Phòng Công nghệ Thông tin', icon: Mail },
  { label: 'KTX', full: 'Ký túc xá', match: 'Ký túc xá', icon: House },
  { label: 'Y tế', full: 'Bảo hiểm y tế, khám sức khỏe', match: 'Trạm Y tế', icon: Heart },
];

type UnitKind = 'office' | 'faculty';

const MAX_SERVICES = 3;
const GENERIC_QUESTION = 'Các phòng ban của trường phụ trách những việc gì cho sinh viên?';
const queryQuestion = (query: string) => `Tôi cần liên hệ đơn vị nào về "${query}"?`;
// Two faculty-level units can share a name (one per campus); the email tells them apart.
const unitKey = (unit: DirectoryUnit) => `${unit.name}|${unit.emails[0] ?? ''}`;
const callHref = (unit: DirectoryUnit) => telHref(unit.phones[0], unit.ext[0]);

function Highlight({ text, query }: { text: string; query: string }): ReactNode {
  const range = query ? findHighlight(text, query) : null;
  if (!range) return text;
  const source = text.normalize('NFC');
  return (
    <>
      {source.slice(0, range[0])}
      <mark>{source.slice(range[0], range[1])}</mark>
      {source.slice(range[1])}
    </>
  );
}

interface UnitCardProps {
  unit: DirectoryUnit;
  /** Text to highlight; empty for a task result or an opened browse row. */
  query: string;
  highlighted: boolean;
  /** An opened browse row already shows the name above, so the card leaves it out. */
  compact: boolean;
}

function UnitCard({ unit, query, highlighted, compact }: UnitCardProps) {
  const toast = useToast();
  const [showAll, setShowAll] = useState(false);
  const phone = unit.phones[0];
  const matched = query ? unit.services.filter((service) => findHighlight(service, query)) : [];
  const preferred = matched.length > 0 ? matched : unit.services;
  const shown = showAll ? unit.services : preferred.slice(0, MAX_SERVICES);
  const hidden = unit.services.length - shown.length;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(contactText(unit));
      toast.show('Đã sao chép liên hệ', 'success');
    } catch {
      toast.show('Không sao chép được. Hãy thử lại.', 'error');
    }
  };

  return (
    <article className={`dir-unit${highlighted ? ' hit' : ''}`}>
      {!compact && (
        <>
          <h3>
            <Highlight text={unit.name} query={query} />
          </h3>
          {unit.campus && unit.campus !== 'TP.HCM' && <div className="dir-alias">{unit.campus}</div>}
          {unit.aliases.length > 0 && <div className="dir-alias">{unit.aliases.join(' · ')}</div>}
        </>
      )}
      {shown.length > 0 && (
        <>
          <ul>
            {shown.map((service) => (
              <li key={service}>
                <Highlight text={service} query={query} />
              </li>
            ))}
          </ul>
          {hidden > 0 && (
            <button type="button" className="dir-more" onClick={() => setShowAll(true)}>
              +{hidden} việc khác
            </button>
          )}
        </>
      )}
      <div className="dir-acts">
        {phone && (
          <a className="call" href={callHref(unit)}>
            <Phone size={15} aria-hidden="true" />
            Gọi
            <small>
              {phone}
              {unit.ext.length > 0 && ` · nhánh ${unit.ext.join(', ')}`}
            </small>
          </a>
        )}
        {unit.emails.map((email) => (
          <a key={email} href={`mailto:${email}`}>
            <Mail size={15} aria-hidden="true" />
            {email}
          </a>
        ))}
        <button type="button" onClick={() => void handleCopy()} aria-label={`Sao chép liên hệ ${unit.name}`}>
          <Copy size={15} aria-hidden="true" />
          Sao chép
        </button>
      </div>
      {unit.office && <div className="dir-loc">{unit.office}</div>}
    </article>
  );
}

interface UnitRowProps {
  unit: DirectoryUnit;
  open: boolean;
  onToggle: () => void;
}

function UnitRow({ unit, open, onToggle }: UnitRowProps) {
  const keywords = unit.keywords.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' · ');
  const subtitle = keywords || unit.services[0] || unit.campus || unit.emails[0];

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    // Enter on the call link inside the row must dial, not toggle.
    if (event.target !== event.currentTarget) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onToggle();
    }
  };

  return (
    <>
      <div className="dir-row" role="button" tabIndex={0} aria-expanded={open} onClick={onToggle} onKeyDown={handleKeyDown}>
        <span className="dir-row-text">
          <b>{unit.name}</b>
          <span>{subtitle}</span>
        </span>
        {unit.phones[0] && (
          <a
            className="dir-rcall"
            href={callHref(unit)}
            aria-label={`Gọi ${unit.name}`}
            onClick={(event) => event.stopPropagation()}
          >
            <Phone size={16} aria-hidden="true" />
          </a>
        )}
        <ChevronRight className={`dir-chev${open ? ' open' : ''}`} size={16} aria-hidden="true" />
      </div>
      {open && <UnitCard unit={unit} query="" highlighted={false} compact />}
    </>
  );
}

const KINDS: { value: UnitKind; label: string }[] = [
  { value: 'office', label: 'Phòng ban' },
  { value: 'faculty', label: 'Khoa' },
];

export function DirectoryPage({ onAskChat }: DirectoryPageProps) {
  const [query, setQuery] = useState('');
  const [taskLabel, setTaskLabel] = useState<string | null>(null);
  const [kind, setKind] = useState<UnitKind>('office');
  const [openKey, setOpenKey] = useState<string | null>(null);

  const trimmed = query.trim();
  const task = TASKS.find((item) => item.label === taskLabel) ?? null;
  const pool = kind === 'office' ? OFFICES : FACULTIES;
  const browsing = !task && !trimmed;
  const items = task ? unitsForTask(pool, task.match) : searchUnits(pool, trimmed);
  const question = trimmed ? queryQuestion(trimmed) : GENERIC_QUESTION;

  const changeQuery = (value: string) => {
    setQuery(value);
    setTaskLabel(null);
  };

  const toggleTask = (label: string) => {
    setQuery('');
    setKind('office');
    setTaskLabel((current) => (current === label ? null : label));
  };

  const switchKind = (next: UnitKind) => {
    setKind(next);
    setTaskLabel(null);
    setOpenKey(null);
  };

  return (
    <div className="page-container tool-page simplified dir-page">
      <ToolPageHeader
        icon={Contact}
        title="Danh bạ"
        description="Tìm nhanh phòng ban, khoa phụ trách việc bạn cần và liên hệ trực tiếp."
      />

      <div className="gpa-m-page-header dir-m-header">
        <div className="gpa-m-title-wrap">
          <Contact size={18} aria-hidden="true" className="dir-m-title-icon" />
          <h1 className="gpa-m-page-title">Danh bạ</h1>
        </div>
      </div>

      <div className="dir-body">
        <section className="dir-sheet" aria-label="Tìm đơn vị">
          <div className="dir-search">
            <div className="dir-box">
              <Search size={17} aria-hidden="true" />
              <input
                type="text"
                inputMode="search"
                enterKeyHint="search"
                autoComplete="off"
                placeholder="Bạn cần làm gì? VD: phúc khảo"
                aria-label="Tìm theo việc cần làm hoặc tên đơn vị"
                value={query}
                onChange={(event) => changeQuery(event.target.value)}
              />
              {query && (
                <button type="button" className="dir-clear" aria-label="Xóa tìm kiếm" onClick={() => changeQuery('')}>
                  <X size={16} aria-hidden="true" />
                </button>
              )}
            </div>
          </div>

          <div className="dir-chips" role="group" aria-label="Việc hay gặp">
            {TASKS.map(({ label, full, icon: Icon }) => (
              <button
                key={label}
                type="button"
                title={full}
                aria-label={full}
                aria-pressed={taskLabel === label}
                onClick={() => toggleTask(label)}
              >
                <Icon aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>

          <div className="dir-tabs" role="group" aria-label="Loại đơn vị">
            {KINDS.map(({ value, label }) => (
              <button key={value} type="button" aria-pressed={kind === value} onClick={() => switchKind(value)}>
                {label}
              </button>
            ))}
          </div>
        </section>

        <div className={browsing ? 'dir-rows' : 'dir-list'} aria-live="polite">
          {items.length === 0 ? (
            <div className="dir-empty">
              Không tìm thấy đơn vị phù hợp với “{trimmed}”.
              <br />
              <button type="button" className="dir-link" onClick={() => onAskChat(question)}>
                <MessageCircle size={14} aria-hidden="true" />
                Hỏi chatbot
              </button>
            </div>
          ) : browsing ? (
            items.map((unit) => (
              <UnitRow
                key={unitKey(unit)}
                unit={unit}
                open={openKey === unitKey(unit)}
                onToggle={() => setOpenKey((current) => (current === unitKey(unit) ? null : unitKey(unit)))}
              />
            ))
          ) : (
            items.map((unit) => (
              <UnitCard key={unitKey(unit)} unit={unit} query={task ? '' : trimmed} highlighted compact={false} />
            ))
          )}
        </div>

        <div className="dir-foot">
          <span>Theo {DIRECTORY_SOURCE}</span>
          <button type="button" className="dir-link" onClick={() => onAskChat(question)}>
            <MessageCircle size={14} aria-hidden="true" />
            Không thấy? Hỏi chatbot
          </button>
        </div>
      </div>
    </div>
  );
}
