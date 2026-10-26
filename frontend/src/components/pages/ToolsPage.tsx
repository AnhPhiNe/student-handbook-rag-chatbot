import {
  Award,
  BookOpenCheck,
  Calculator,
  FileText,
  GraduationCap,
  LayoutGrid,
  Pin,
  PinOff,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react';
import { useLocalStorage } from '../../hooks/useLocalStorage';
import { arrangePinnedTools, togglePinnedId } from '../../utils/pinnedTools';

interface ToolsPageProps {
  onNavigate: (tab: string) => void;
}

interface ToolItem {
  id: string;
  title: string;
  description: string;
  icon: LucideIcon;
  tone: 'blue' | 'rose' | 'cyan' | 'violet' | 'orange' | 'green';
}

interface ToolGroup {
  title: string;
  tools: ToolItem[];
}

const TOOL_GROUPS: ToolGroup[] = [
  {
    title: 'Tính toán',
    tools: [
      {
        id: 'gpa',
        title: 'Tính GPA',
        description: 'Tính GPA học kỳ theo tín chỉ và điểm.',
        icon: GraduationCap,
        tone: 'blue',
      },
      {
        id: 'target-gpa',
        title: 'Mục tiêu GPA',
        description: 'Ước tính GPA cần đạt cho mục tiêu tích lũy.',
        icon: TrendingUp,
        tone: 'rose',
      },
      {
        id: 'course-target',
        title: 'Mục tiêu môn học',
        description: 'Tính điểm cuối kỳ cần đạt.',
        icon: Target,
        tone: 'cyan',
      },
      {
        id: 'scholarship',
        title: 'Tính điểm học bổng',
        description: 'Ước tính điểm xét học bổng.',
        icon: Award,
        tone: 'violet',
      },
      {
        id: 'tuition',
        title: 'Ước tính học phí',
        description: 'Ước tính theo ngành và số tín chỉ.',
        icon: Calculator,
        tone: 'orange',
      },
      {
        id: 'credits',
        title: 'Kiểm tra hạ bằng',
        description: 'Kiểm tra điều kiện hạ mức bằng.',
        icon: ShieldCheck,
        tone: 'green',
      },
    ],
  },
  {
    title: 'Tài nguyên',
    tools: [
      {
        id: 'survival-guide',
        title: 'Phương pháp học tập',
        description: 'Gợi ý cách ghi nhớ và tập trung.',
        icon: Sparkles,
        tone: 'violet',
      },
      {
        id: 'bieu-mau',
        title: 'Biểu mẫu',
        description: 'Tìm và tải biểu mẫu sinh viên.',
        icon: FileText,
        tone: 'green',
      },
      {
        id: 'huong-dan',
        title: 'Hướng dẫn sử dụng',
        description: 'Xem cách sử dụng hệ thống.',
        icon: BookOpenCheck,
        tone: 'blue',
      },
    ],
  },
];

const PINNED_GROUP_TITLE = 'Đã ghim';

export function ToolsPage({ onNavigate }: ToolsPageProps) {
  const [storedPins, setStoredPins] = useLocalStorage<string[]>('hcmue-pinned-tools', []);
  const { pinned, groups } = arrangePinnedTools(TOOL_GROUPS, storedPins);
  const visibleGroups: ToolGroup[] = pinned.length > 0 ? [{ title: PINNED_GROUP_TITLE, tools: pinned }, ...groups] : groups;

  const renderCard = (tool: ToolItem, idx: number, isPinned: boolean) => {
    const Icon = tool.icon;
    const PinIcon = isPinned ? PinOff : Pin;
    return (
      <div className="tool-card-wrap" key={tool.id}>
        <button
          type="button"
          className={`category-card tool-card tone-${tool.tone}`}
          style={{ '--shimmer-delay': `${idx * 0.15}s` } as React.CSSProperties}
          onClick={() => onNavigate(tool.id)}
        >
          <span className="category-icon">
            <Icon size={24} aria-hidden="true" />
          </span>
          <span className="category-title">{tool.title}</span>
          <span className="category-desc">{tool.description}</span>
        </button>
        {/* A sibling of the card button, not a child: buttons cannot nest, and a tap here must not navigate. */}
        <button
          type="button"
          className={`tool-pin${isPinned ? ' pinned' : ''}`}
          aria-pressed={isPinned}
          aria-label={`${isPinned ? 'Bỏ ghim' : 'Ghim'} ${tool.title}`}
          title={isPinned ? 'Bỏ ghim' : 'Ghim lên đầu'}
          onClick={(event) => {
            event.stopPropagation();
            setStoredPins((current) => togglePinnedId(Array.isArray(current) ? current : [], tool.id));
          }}
        >
          <PinIcon size={15} aria-hidden="true" />
        </button>
      </div>
    );
  };

  return (
    <div className="page-container tools-page">
      <div className="tools-shell">
        <div className="page-header tools-page-header">
          <h1 className="page-title-with-icon">
            <LayoutGrid aria-hidden="true" />
            <span>Công cụ sinh viên</span>
          </h1>
          <p>Chọn công cụ bạn cần.</p>
          <div className="page-context-badges tools-summary-badges" aria-label="Tổng quan danh mục công cụ">
            <span className="page-context-badge primary">
              <Calculator size={14} aria-hidden="true" />
              6 công cụ tính toán
            </span>
            <span className="page-context-badge">
              <Search size={14} aria-hidden="true" />
              3 tài nguyên
            </span>
          </div>
        </div>

        {visibleGroups.map((group, groupIndex) => (
          <section className="tool-group" key={group.title} aria-labelledby={`tool-group-${groupIndex}`}>
            <div className="tool-group-heading">
              <h2 id={`tool-group-${groupIndex}`}>{group.title}</h2>
            </div>
            <div className="category-grid">
              {group.tools.map((tool, idx) => renderCard(tool, idx, group.title === PINNED_GROUP_TITLE))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
