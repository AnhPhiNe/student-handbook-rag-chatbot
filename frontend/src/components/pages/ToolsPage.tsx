import { BookOpenCheck, ChevronRight, Contact, Pin, PinOff, Star, type LucideIcon } from 'lucide-react';
import { SHOW_EXPERIENCE_PAGE } from '../../config/features';
import { useLocalStorage } from '../../hooks/useLocalStorage';
import { arrangePinnedTools, togglePinnedId } from '../../utils/pinnedTools';
import { RECENT_TOOL_KEY, readRecentTool } from '../../utils/recentTool';
import './ToolsPage.css';

interface ToolsPageProps {
  onNavigate: (tab: string) => void;
}

interface ToolItem {
  id: string;
  /** Short name shown on the tile. */
  title: string;
  /** Full name for screen readers. */
  fullTitle: string;
  question: string;
  symbol: string;
  color: string;
}

interface MoreLink {
  id: string;
  label: string;
  icon: LucideIcon;
}

const CALC_TOOLS: ToolItem[] = [
  { id: 'gpa', title: 'Tính GPA', fullTitle: 'Tính GPA học kỳ', question: 'GPA kỳ này bao nhiêu?', symbol: 'Σ', color: '#2251CC' },
  { id: 'target-gpa', title: 'Mục tiêu GPA', fullTitle: 'Mục tiêu GPA', question: 'Muốn lên Giỏi cần gì?', symbol: '↗', color: '#D7263D' },
  { id: 'course-target', title: 'Mục tiêu môn', fullTitle: 'Mục tiêu môn học', question: 'Cuối kỳ cần mấy điểm?', symbol: '≥', color: '#0E8A9E' },
  { id: 'scholarship', title: 'Học bổng', fullTitle: 'Tính điểm học bổng', question: 'Đủ học bổng chưa?', symbol: '★', color: '#6D3FD1' },
  { id: 'tuition', title: 'Học phí', fullTitle: 'Ước tính học phí', question: 'Học phí kỳ này?', symbol: '₫', color: '#E0A100' },
  { id: 'credits', title: 'Hạ bằng', fullTitle: 'Kiểm tra hạ bằng', question: 'Có bị hạ bằng không?', symbol: '%', color: '#1E8A55' },
];

const MORE_LINKS: MoreLink[] = [
  ...(SHOW_EXPERIENCE_PAGE ? [{ id: 'kinh-nghiem', label: 'Kinh nghiệm', icon: Star }] : []),
  { id: 'danh-ba', label: 'Danh bạ', icon: Contact },
  { id: 'huong-dan', label: 'Cách dùng web', icon: BookOpenCheck },
];

export function ToolsPage({ onNavigate }: ToolsPageProps) {
  const [storedPins, setStoredPins] = useLocalStorage<string[]>('hcmue-pinned-tools', []);
  const [storedRecent, setStoredRecent] = useLocalStorage<string | null>(RECENT_TOOL_KEY, null);
  const { pinned, groups } = arrangePinnedTools([{ title: 'Tính nhanh', tools: CALC_TOOLS }], storedPins);
  const quick = groups[0]?.tools ?? [];
  const recentId = readRecentTool(storedRecent);
  const recent = CALC_TOOLS.find((tool) => tool.id === recentId) ?? null;

  const openTool = (id: string) => {
    setStoredRecent(id);
    onNavigate(id);
  };

  const renderTile = (tool: ToolItem, isPinned: boolean) => {
    const PinIcon = isPinned ? PinOff : Pin;
    return (
      <div
        className={`tools-tile${isPinned ? ' pinned' : ''}`}
        style={{ '--c': tool.color } as React.CSSProperties}
        key={tool.id}
      >
        <button
          type="button"
          className="tools-tile-main"
          aria-label={`${tool.fullTitle}: ${tool.question}`}
          onClick={() => openTool(tool.id)}
        >
          <span className="tools-chip" aria-hidden="true">{tool.symbol}</span>
          <span className="tools-tile-text">
            <b>{tool.title}</b>
            <small>{tool.question}</small>
          </span>
        </button>
        {/* A sibling of the tile button, not a child: buttons cannot nest, and a tap here must not navigate. */}
        <button
          type="button"
          className={`tools-pin${isPinned ? ' on' : ''}`}
          aria-pressed={isPinned}
          aria-label={`${isPinned ? 'Bỏ ghim' : 'Ghim'} ${tool.fullTitle}`}
          title={isPinned ? 'Bỏ ghim' : 'Ghim lên đầu'}
          onClick={() => setStoredPins((current) => togglePinnedId(Array.isArray(current) ? current : [], tool.id))}
        >
          <PinIcon size={15} aria-hidden="true" />
        </button>
      </div>
    );
  };

  return (
    <div className="page-container tools-page">
      <div className="tools-shell">
        <header className="tools-head">
          <h1>Công cụ</h1>
          <p>6 công cụ tính theo Sổ tay sinh viên</p>
        </header>

        {recent && (
          <button
            type="button"
            className="tools-recent"
            style={{ '--c': recent.color } as React.CSSProperties}
            aria-label={`Gần nhất: ${recent.fullTitle}`}
            onClick={() => openTool(recent.id)}
          >
            <span className="tools-chip" aria-hidden="true">{recent.symbol}</span>
            <span className="tools-recent-text">
              <small>Gần nhất</small>
              <b>{recent.title}</b>
            </span>
            <ChevronRight size={18} aria-hidden="true" />
          </button>
        )}

        {pinned.length > 0 && (
          <section className="tools-section" aria-labelledby="tools-pinned">
            <div className="tools-sect">
              <h2 id="tools-pinned">Đã ghim</h2>
              <span>{pinned.length}</span>
            </div>
            <div className="tools-grid">{pinned.map((tool) => renderTile(tool, true))}</div>
          </section>
        )}

        {quick.length > 0 && (
          <section className="tools-section" aria-labelledby="tools-quick">
            <div className="tools-sect">
              <h2 id="tools-quick">Tính nhanh</h2>
              <span>{quick.length}</span>
            </div>
            <div className="tools-grid">{quick.map((tool) => renderTile(tool, false))}</div>
          </section>
        )}

        <section className="tools-section" aria-labelledby="tools-more">
          <div className="tools-sect">
            <h2 id="tools-more">Xem thêm</h2>
          </div>
          <div className="tools-more">
            {MORE_LINKS.map(({ id, label, icon: Icon }) => (
              <button type="button" key={id} onClick={() => onNavigate(id)}>
                <Icon size={20} aria-hidden="true" />
                <span>{label}</span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
