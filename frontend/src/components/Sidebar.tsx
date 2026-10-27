import { BookOpen, ChevronLeft, ChevronRight, Contact, Home, MessageSquare, Star, Wrench, type LucideIcon } from 'lucide-react';
import { VisitorCounter } from './VisitorCounter';
import { IS_CHAT_MAINTENANCE, SHOW_EXPERIENCE_PAGE } from '../config/features';

const logoHcmue = '/logo_hcmue.png?v=2';
const TOOL_TABS = new Set(['tools', 'gpa', 'target-gpa', 'course-target', 'scholarship', 'tuition', 'credits']);

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

// The same five destinations as the phone tab bar; the six tools live on the tools page.
const NAV: NavEntry[] = [
  { id: 'home', label: 'Trang chủ', icon: Home },
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'tools', label: 'Công cụ', icon: Wrench },
  ...(SHOW_EXPERIENCE_PAGE ? [{ id: 'kinh-nghiem', label: 'Kinh nghiệm', icon: Star }] : []),
  { id: 'danh-ba', label: 'Danh bạ', icon: Contact },
];

export function Sidebar({ activeTab, onTabChange, isCollapsed, onToggleCollapse }: SidebarProps) {
  const isActive = (id: string) => activeTab === id || (id === 'tools' && TOOL_TABS.has(activeTab));

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
        {NAV.map(({ id, label, icon: Icon }) => {
          const maintenance = id === 'chat' && IS_CHAT_MAINTENANCE;
          return (
            <button
              key={id}
              type="button"
              className={`nav-item ${isActive(id) ? 'active' : ''}`}
              onClick={() => onTabChange(id)}
              aria-current={isActive(id) ? 'page' : undefined}
              aria-label={maintenance ? `${label} (Đang bảo trì)` : label}
              title={isCollapsed ? label : undefined}
            >
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
              {maintenance && <span className="sidebar-maintenance-badge">Bảo trì</span>}
            </button>
          );
        })}
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
