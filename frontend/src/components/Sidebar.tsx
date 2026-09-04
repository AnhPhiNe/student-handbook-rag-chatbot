import { Award, Calculator, FileText, GraduationCap, HelpCircle, MessageSquare, ShieldCheck, ChevronLeft, ChevronRight, TrendingUp, Target, Home, Sparkles } from 'lucide-react';
const logoHcmue = '/logo_hcmue.png?v=2';
import { VisitorCounter } from './VisitorCounter';

interface SidebarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  isCollapsed: boolean;
  isMobileOpen: boolean;
  onClose: () => void;
  onToggleCollapse: () => void;
  showVisitorCounter?: boolean;
}

export function Sidebar({ activeTab, onTabChange, isCollapsed, isMobileOpen, onClose, onToggleCollapse, showVisitorCounter }: SidebarProps) {
  const handleTabClick = (tab: string) => {
    onTabChange(tab);
    onClose(); // close mobile menu on selection
  };

  return (
    <>
      {isMobileOpen && <div className="sidebar-backdrop" onClick={onClose} />}
      
      <aside className={`sidebar ${isCollapsed ? 'collapsed' : ''} ${isMobileOpen ? 'mobile-open' : ''}`}>
        <button className="collapse-toggle" onClick={onToggleCollapse} aria-label="Thu gọn">
          {isCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>

        <button
          type="button"
          className="sidebar-logo" 
          onClick={() => handleTabClick('home')}
          title="Trang chủ"
        >
          <img src={logoHcmue} alt="HCMUE" className="sidebar-logo-img" />
          <div className="sidebar-logo-text">
            <h2 style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              HCMUE
              <span className="sidebar-beta-badge">BETA</span>
            </h2>
            <p>AI Assistant</p>
          </div>
        </button>
        <nav className="sidebar-nav">
          <div className="sidebar-nav-section">
            <div className="sidebar-nav-title">Hỏi đáp</div>
            <button className={`nav-item ${activeTab === 'home' ? 'active' : ''}`} onClick={() => handleTabClick('home')} aria-label="Trang chủ">
              {activeTab === 'home' && <div className="active-indicator" />}
              <Home size={18} />
              <span>Trang chủ</span>
            </button>
            <button className={`nav-item ${activeTab === 'chat' ? 'active' : ''}`} onClick={() => handleTabClick('chat')} aria-label="Chat">
              {activeTab === 'chat' && <div className="active-indicator" />}
              <MessageSquare size={18} />
              <span>Chat</span>
            </button>
          </div>

          <div className="sidebar-nav-section">
            <div className="sidebar-nav-title">Công cụ</div>
            <button className={`nav-item ${activeTab === 'gpa' ? 'active' : ''}`} onClick={() => handleTabClick('gpa')} aria-label="Tính GPA">
              {activeTab === 'gpa' && <div className="active-indicator" />}
              <GraduationCap size={18} />
              <span>Tính GPA</span>
            </button>
            <button className={`nav-item ${activeTab === 'target-gpa' ? 'active' : ''}`} onClick={() => handleTabClick('target-gpa')} aria-label="Mục tiêu GPA">
              {activeTab === 'target-gpa' && <div className="active-indicator" />}
              <TrendingUp size={18} />
              <span>Mục tiêu GPA</span>
            </button>
            <button className={`nav-item ${activeTab === 'course-target' ? 'active' : ''}`} onClick={() => handleTabClick('course-target')} aria-label="Mục tiêu môn học">
              {activeTab === 'course-target' && <div className="active-indicator" />}
              <Target size={18} />
              <span>Mục tiêu môn học</span>
            </button>
            <button className={`nav-item ${activeTab === 'scholarship' ? 'active' : ''}`} onClick={() => handleTabClick('scholarship')} aria-label="Tính điểm học bổng">
              {activeTab === 'scholarship' && <div className="active-indicator" />}
              <Award size={18} />
              <span>Tính điểm học bổng</span>
            </button>
            <button className={`nav-item ${activeTab === 'tuition' ? 'active' : ''}`} onClick={() => handleTabClick('tuition')} aria-label="Ước tính học phí">
              {activeTab === 'tuition' && <div className="active-indicator" />}
              <Calculator size={18} />
              <span>Ước tính học phí</span>
            </button>
            <button className={`nav-item ${activeTab === 'credits' ? 'active' : ''}`} onClick={() => handleTabClick('credits')} aria-label="Kiểm tra hạ bằng">
              {activeTab === 'credits' && <div className="active-indicator" />}
              <ShieldCheck size={18} />
              <span>Kiểm tra hạ bằng</span>
            </button>
          </div>

          <div className="sidebar-nav-section">
            <div className="sidebar-nav-title">Tài nguyên</div>
            <button className={`nav-item ${activeTab === 'survival-guide' ? 'active' : ''}`} onClick={() => handleTabClick('survival-guide')} aria-label="Phương pháp học tập">
              {activeTab === 'survival-guide' && <div className="active-indicator" />}
              <Sparkles size={18} />
              <span>Phương pháp học tập</span>
            </button>
            <button className={`nav-item ${activeTab === 'bieu-mau' ? 'active' : ''}`} onClick={() => handleTabClick('bieu-mau')} aria-label="Biểu mẫu">
              {activeTab === 'bieu-mau' && <div className="active-indicator" />}
              <FileText size={18} />
              <span>Biểu mẫu</span>
            </button>
            <button className={`nav-item ${activeTab === 'huong-dan' ? 'active' : ''}`} onClick={() => handleTabClick('huong-dan')} aria-label="Hướng dẫn">
              {activeTab === 'huong-dan' && <div className="active-indicator" />}
              <HelpCircle size={18} />
              <span>Hướng dẫn</span>
            </button>
          </div>
        </nav>

        <div className="sidebar-footer">
          {showVisitorCounter && (
            <div className="sidebar-visitor-wrapper" style={{ marginBottom: '12px' }}>
              <VisitorCounter />
            </div>
          )}
          <p>Dự án cá nhân vì sinh viên HCMUE · Phiên bản 1.0</p>
        </div>
      </aside>
    </>
  );
}
