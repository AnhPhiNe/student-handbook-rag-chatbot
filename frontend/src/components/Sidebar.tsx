import { Award, BookOpen, Calculator, ChevronLeft, ChevronRight, Contact, GraduationCap, Home, MessageSquare, ShieldCheck, Star, Target, TrendingUp, Wrench, type LucideIcon } from 'lucide-react';
import { VisitorCounter } from './VisitorCounter';
import { IS_CHAT_MAINTENANCE, SHOW_EXPERIENCE_PAGE } from '../config/features';

const logoHcmue = '/logo_hcmue.png?v=2';

interface SidebarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

interface NavEntry {
  id: string;
  label: string;
  icon: LucideIcon;
}

// Desktop has room for direct calculator links. Phones retain their five-tab navigation.
const NAV: NavEntry[] = [
  { id: 'home', label: 'Trang chủ', icon: Home },
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'tools', label: 'Công cụ', icon: Wrench },
  ...(SHOW_EXPERIENCE_PAGE ? [{ id: 'kinh-nghiem', label: 'Kinh nghiệm', icon: Star }] : []),
  { id: 'danh-ba', label: 'Danh bạ', icon: Contact },
];

const CALCULATORS: NavEntry[] = [
  { id: 'gpa', label: 'Tính GPA', icon: GraduationCap },
  { id: 'target-gpa', label: 'Mục tiêu GPA', icon: TrendingUp },
  { id: 'course-target', label: 'Mục tiêu môn', icon: Target },
  { id: 'scholarship', label: 'Học bổng', icon: Award },
  { id: 'tuition', label: 'Học phí', icon: Calculator },
  { id: 'credits', label: 'Hạ bằng', icon: ShieldCheck },
];

export function Sidebar({ activeTab, onTabChange, isCollapsed, onToggleCollapse }: SidebarProps) {
  const isActive = (id: string) => activeTab === id;

  const renderLink = ({ id, label, icon: Icon }: NavEntry, tool = false) => {
    const maintenance = id === 'chat' && IS_CHAT_MAINTENANCE;
    return (
      <button key={id} type="button"
        className={`nav-item${tool ? ' sidebar-tool-link' : ''}${isActive(id) ? ' active' : ''}`}
        onClick={() => onTabChange(id)} aria-current={isActive(id) ? 'page' : undefined}
        aria-label={maintenance ? `${label} (Đang bảo trì)` : label}
        title={isCollapsed ? label : undefined}>
        <Icon size={tool ? 16 : 18} aria-hidden="true" />
        <span>{label}</span>
        {maintenance && <span className="sidebar-maintenance-badge">Bảo trì</span>}
      </button>
    );
  };

  return (
    <aside className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-head">
        <button type="button" className="sidebar-logo" onClick={() => onTabChange('home')} title="Trang chủ">
          <img src={logoHcmue} alt="HCMUE" className="sidebar-logo-img" />
          <span className="sidebar-logo-text">
            HCMUE AI
            <small>beta</small>
          </span>
        </button>
        <button
          type="button"
          className="collapse-toggle"
          onClick={onToggleCollapse}
          aria-label={isCollapsed ? 'Mở rộng thanh bên' : 'Thu gọn thanh bên'}
          title={isCollapsed ? 'Mở rộng' : 'Thu gọn'}
        >
          {isCollapsed ? <ChevronRight size={16} aria-hidden="true" /> : <ChevronLeft size={16} aria-hidden="true" />}
        </button>
      </div>

      <nav className="sidebar-nav" aria-label="Điều hướng chính">
        {NAV.map((entry) => entry.id === 'tools' ? (
          <div className="sidebar-tools" key={entry.id}>
            {renderLink(entry)}
            <div className="sidebar-tool-list" role="group" aria-label="Công cụ tính toán">
              {CALCULATORS.map((tool) => renderLink(tool, true))}
            </div>
          </div>
        ) : renderLink(entry))}
      </nav>

      <div className="sidebar-footer">
        <button
          type="button"
          className={`nav-item sidebar-guide ${activeTab === 'huong-dan' ? 'active' : ''}`}
          onClick={() => onTabChange('huong-dan')}
          aria-current={activeTab === 'huong-dan' ? 'page' : undefined}
          title={isCollapsed ? 'Cách dùng web' : undefined}
        >
          <BookOpen size={18} aria-hidden="true" />
          <span>Cách dùng web</span>
        </button>
        <div className="sidebar-visitor-wrapper">
          <VisitorCounter />
        </div>
        <p>Dự án cá nhân vì sinh viên HCMUE · Phiên bản 1.0</p>
      </div>
    </aside>
  );
}
