import { useState, type ReactNode } from 'react';
import {
  Contact,
  Copy,
  Mail,
  MapPin,
  MessageCircle,
  Phone,
  Search,
  X,
} from 'lucide-react';
import { DIRECTORY_SOURCE, FACULTIES, OFFICES, type DirectoryUnit } from '../../data/directory';
import { contactText, findHighlight, searchUnits, telHref, unitsForTask } from '../../utils/directory';
import { useToast } from '../Toast';
import { ToolPageHeader } from '../tool/ToolPageHeader';

interface DirectoryPageProps {
  onAskChat: (text: string) => void;
}

interface DirectoryTask {
  /** Short label for the chip button. */
  label: string;
  /** Full wording for tooltip and accessibility. */
  full: string;
  /** Part of a unit name the task points at. */
  match: string;
}

const TASKS: DirectoryTask[] = [
  { label: 'Học phí', full: 'Học phí, biên lai', match: 'Kế hoạch – Tài chính' },
  { label: 'Học bổng', full: 'Học bổng, rèn luyện', match: 'Công tác chính trị' },
  { label: 'Nghị định 116', full: 'Nghị định 116 (sinh viên sư phạm)', match: 'Công tác chính trị' },
  { label: 'Đăng ký học phần', full: 'Đăng ký học phần, học vụ', match: 'Phòng Đào tạo' },
  { label: 'Phúc khảo & Lịch thi', full: 'Lịch thi, phúc khảo, bảng điểm', match: 'Khảo thí' },
  { label: 'Tài khoản & Wifi', full: 'Email, tài khoản, wifi', match: 'Phòng Công nghệ Thông tin' },
  { label: 'Ký túc xá', full: 'Ký túc xá', match: 'Ký túc xá' },
  { label: 'Y tế & BHYT', full: 'Bảo hiểm y tế, khám sức khỏe', match: 'Trạm Y tế' },
];

type UnitKind = 'office' | 'faculty';

const MAX_SERVICES = 3;
const GENERIC_QUESTION = 'Các phòng ban của trường phụ trách những việc gì cho sinh viên?';
const queryQuestion = (query: string) => `Tôi cần liên hệ đơn vị nào về "${query}"?`;
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

function formatOffice(office: string): string {
  if (!office) return '';
  return office
    .replace(/,?\s*số 280 An Dương Vương[^;]*?(?=\s*(?:;|$))/gi, ' (Cơ sở ADV)')
    .replace(/,?\s*số 222 Lê Văn Sỹ[^;]*?(?=\s*(?:;|$))/gi, ' (Cơ sở LVS)')
    .replace(/^351A?\s*Lạc Long Quân[^;]*?(?=\s*(?:;|$))/gi, '351A Lạc Long Quân (Cơ sở LLQ)')
    .replace(/\. HCM/gi, '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[\.\s]+$/, '');
}

interface UnitCardProps {
  unit: DirectoryUnit;
  query: string;
}

function UnitCard({ unit, query }: UnitCardProps) {
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

  const tagText =
    unit.campus && unit.campus !== 'TP.HCM'
      ? unit.campus
      : unit.aliases.length > 0
        ? unit.aliases.join(' · ')
        : null;

  return (
    <article className="dir-card">
      <div className="dir-card-header">
        <div className="dir-card-title-group">
          <h3 className="dir-card-name">
            <Highlight text={unit.name} query={query} />
          </h3>
          {tagText && (
            <span className="dir-card-tag" title={tagText}>
              {tagText}
            </span>
          )}
        </div>

        {unit.office && (
          <div className="dir-card-loc-pill" title={unit.office}>
            <MapPin size={13} aria-hidden="true" className="dir-card-loc-icon" />
            <span className="dir-card-loc-text">{formatOffice(unit.office)}</span>
          </div>
        )}
      </div>

      {shown.length > 0 && (
        <div className="dir-card-services">
          <ul className="dir-card-list">
            {shown.map((service) => (
              <li key={service}>
                <Highlight text={service} query={query} />
              </li>
            ))}
          </ul>
          {hidden > 0 && (
            <button
              type="button"
              className="dir-more-btn"
              onClick={() => setShowAll((prev) => !prev)}
            >
              {showAll ? 'Thu gọn' : `+${hidden} việc khác`}
            </button>
          )}
        </div>
      )}

      <div className="dir-card-actions">
        {phone ? (
          <a className="dir-btn-call" href={callHref(unit)} aria-label={`Gọi ${unit.name}`}>
            <Phone size={14} aria-hidden="true" />
            <span>
              Gọi {unit.ext.length > 0 ? `(Nhánh ${unit.ext.join(', ')})` : phone}
            </span>
          </a>
        ) : (
          <span className="dir-no-phone">Chưa có số hotline</span>
        )}

        {unit.emails[0] && (
          <a
            className="dir-btn-icon"
            href={`mailto:${unit.emails[0]}`}
            title={`Email: ${unit.emails[0]}`}
            aria-label={`Gửi email đến ${unit.emails[0]}`}
          >
            <Mail size={15} aria-hidden="true" />
          </a>
        )}

        <button
          type="button"
          className="dir-btn-icon"
          onClick={() => void handleCopy()}
          title="Sao chép toàn bộ liên hệ"
          aria-label={`Sao chép liên hệ ${unit.name}`}
        >
          <Copy size={15} aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}

const KINDS: { value: UnitKind; label: string }[] = [
  { value: 'office', label: 'Phòng ban' },
  { value: 'faculty', label: 'Khoa đào tạo' },
];

export function DirectoryPage({ onAskChat }: DirectoryPageProps) {
  const [query, setQuery] = useState('');
  const [taskLabel, setTaskLabel] = useState<string | null>(null);
  const [kind, setKind] = useState<UnitKind>('office');

  const trimmed = query.trim();
  const task = TASKS.find((item) => item.label === taskLabel) ?? null;
  const pool = kind === 'office' ? OFFICES : FACULTIES;
  const browsing = !task && !trimmed;

  const groups: { label: string; units: DirectoryUnit[] }[] = browsing
    ? [{ label: '', units: pool }]
    : task
      ? [{ label: 'Phòng ban phụ trách', units: unitsForTask(OFFICES, task.match) }]
      : [
          { label: 'Phòng ban', units: searchUnits(OFFICES, trimmed) },
          { label: 'Khoa', units: searchUnits(FACULTIES, trimmed) },
        ].filter((group) => group.units.length > 0);

  const items = groups.flatMap((group) => group.units);
  const question = trimmed ? queryQuestion(trimmed) : GENERIC_QUESTION;

  const changeQuery = (value: string) => {
    setQuery(value);
    setTaskLabel(null);
  };

  const toggleTask = (label: string) => {
    setQuery('');
    setTaskLabel((current) => (current === label ? null : label));
  };

  const switchKind = (next: UnitKind) => {
    setKind(next);
    setTaskLabel(null);
  };

  const resetFilters = () => {
    setQuery('');
    setTaskLabel(null);
  };

  return (
    <div className="page-container tool-page simplified dir-page">
      <ToolPageHeader
        icon={Contact}
        title="Danh bạ Đơn vị & Khoa"
        description="Tìm nhanh số điện thoại máy lẻ, email và địa chỉ văn phòng của các phòng ban, khoa phụ trách công việc bạn cần."
      />

      <div className="gpa-m-page-header dir-m-header">
        <div className="gpa-m-title-wrap">
          <Contact size={18} aria-hidden="true" className="dir-m-title-icon" />
          <h1 className="gpa-m-page-title">Danh bạ</h1>
        </div>
      </div>

      <div className="dir-body">
        <section className="dir-sheet" aria-label="Tìm kiếm danh bạ">
          <div className="dir-search">
            <div className="dir-box">
              <Search size={17} aria-hidden="true" />
              <input
                type="text"
                inputMode="search"
                enterKeyHint="search"
                autoComplete="off"
                placeholder="Bạn cần làm gì? VD: xin bảng điểm, phúc khảo, học bổng, KTX, wifi..."
                aria-label="Tìm theo việc cần làm hoặc tên đơn vị"
                value={query}
                onChange={(event) => changeQuery(event.target.value)}
              />
              {query && (
                <button
                  type="button"
                  className="dir-clear"
                  aria-label="Xóa tìm kiếm"
                  onClick={() => changeQuery('')}
                >
                  <X size={16} aria-hidden="true" />
                </button>
              )}
            </div>
          </div>

          <div className="dir-chips-wrapper">
            <div className="dir-chips-scroller" role="group" aria-label="Gợi ý việc cần làm">
              <span className="dir-chips-label">
                <span className="dir-chips-label-full">Gợi ý tìm kiếm:</span>
                <span className="dir-chips-label-short">Gợi ý:</span>
              </span>
              {TASKS.map(({ label, full }) => (
                <button
                  key={label}
                  type="button"
                  className={`dir-chip-pill${taskLabel === label ? ' active' : ''}`}
                  title={full}
                  aria-label={full}
                  aria-pressed={taskLabel === label}
                  onClick={() => toggleTask(label)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {browsing ? (
            <div className="dir-tabs-row">
              <div className="dir-tabs" role="tablist" aria-label="Loại đơn vị">
                {KINDS.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    role="tab"
                    aria-selected={kind === value}
                    aria-pressed={kind === value}
                    className={`dir-tab-btn${kind === value ? ' active' : ''}`}
                    onClick={() => switchKind(value)}
                  >
                    <span>{label}</span>
                    <span className="dir-tab-badge">
                      {value === 'office' ? OFFICES.length : FACULTIES.length}
                    </span>
                  </button>
                ))}
              </div>
              <div className="dir-count-indicator">
                Hiển thị <strong>{items.length}</strong> {kind === 'office' ? 'phòng ban' : 'khoa'}
              </div>
            </div>
          ) : (
            <div className="dir-search-summary">
              <span>
                {task
                  ? `Đơn vị phụ trách: ${task.label}`
                  : `Kết quả tìm kiếm cho: “${trimmed}” (${items.length})`}
              </span>
              <button
                type="button"
                className="dir-reset-filter-btn"
                onClick={resetFilters}
              >
                Xem tất cả
              </button>
            </div>
          )}
        </section>

        <div className="dir-results" aria-live="polite">
          {items.length === 0 ? (
            <div className="dir-empty">
              Không tìm thấy đơn vị phù hợp với “{trimmed}”.
              <br />
              <button type="button" className="dir-link" onClick={() => onAskChat(question)}>
                <MessageCircle size={14} aria-hidden="true" />
                Hỏi chatbot
              </button>
            </div>
          ) : (
            groups.map((group) => (
              <section
                key={group.label || 'all'}
                className="dir-group"
                aria-label={`${group.label || 'Danh sách'}: ${group.units.length} đơn vị`}
              >
                {group.label && !task && (
                  <h2 className="dir-group-title">
                    {group.label} <span>({group.units.length})</span>
                  </h2>
                )}
                <div className="dir-grid">
                  {group.units.map((unit) => (
                    <UnitCard key={unitKey(unit)} unit={unit} query={task ? '' : trimmed} />
                  ))}
                </div>
              </section>
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
