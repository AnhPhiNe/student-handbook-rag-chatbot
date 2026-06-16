import { Award, Calculator, FileText, GraduationCap, HelpCircle, MessageSquare, Plus, ShieldCheck, ChevronLeft, ChevronRight, TrendingUp, Target, Home } from 'lucide-react';
import logoHcmue from '../assets/logo_hcmue.png';

interface SidebarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  onNewChat: () => void;
  isCollapsed: boolean;
  isMobileOpen: boolean;
  onClose: () => void;
  onToggleCollapse: () => void;
}

export function Sidebar({ activeTab, onTabChange, onNewChat, isCollapsed, isMobileOpen, onClose, onToggleCollapse }: SidebarProps) {
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

        <div 
          className="sidebar-logo" 
          onClick={() => { onNewChat(); handleTabClick('chat'); }}
          title="Trang chủ"
        >
          <img src={logoHcmue} alt="HCMUE" className="sidebar-logo-img" />
          <div className="sidebar-logo-text">
            <h2 style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              HCMUE
              <span style={{ backgroundColor: 'rgba(245, 158, 11, 0.2)', color: '#F59E0B', fontSize: '0.65rem', padding: '0.125rem 0.375rem', borderRadius: '4px', letterSpacing: '0.5px' }}>BETA</span>
            </h2>
            <p>AI Assistant</p>
          </div>
        </div>

        <button className="new-chat-btn" onClick={() => { onNewChat(); handleTabClick('chat'); }}>
          <Plus size={18} />
          <span>Chat mới</span>
        </button>

        <nav className="sidebar-nav">
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
          <button className={`nav-item ${activeTab === 'bieu-mau' ? 'active' : ''}`} onClick={() => handleTabClick('bieu-mau')} aria-label="Biểu mẫu">
            {activeTab === 'bieu-mau' && <div className="active-indicator" />}
            <FileText size={18} />
            <span>Biểu mẫu</span>
          </button>
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
          <button className={`nav-item ${activeTab === 'scholarship' ? 'active' : ''}`} onClick={() => handleTabClick('scholarship')} aria-label="Tính học bổng">
            {activeTab === 'scholarship' && <div className="active-indicator" />}
            <Award size={18} />
            <span>Tính học bổng</span>
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
          <button className={`nav-item ${activeTab === 'huong-dan' ? 'active' : ''}`} onClick={() => handleTabClick('huong-dan')} aria-label="Hướng dẫn">
            {activeTab === 'huong-dan' && <div className="active-indicator" />}
            <HelpCircle size={18} />
            <span>Hướng dẫn</span>
          </button>
        </nav>

        <div className="sidebar-links">
          <div className="sidebar-links-title">Liên kết ngoài</div>
          <a href="https://online.hcmue.edu.vn/" target="_blank" rel="noreferrer" className="quick-link-item">
            🌐 Trang chủ HCMUE
          </a>
          <a href="http://thuvien.hcmue.edu.vn" target="_blank" rel="noreferrer" className="quick-link-item">
            📖 Thư viện trường
          </a>
          <a href="https://ctsv.hcmue.edu.vn/storage/files/so-tay-sinh-vien-khoa-48.pdf" target="_blank" rel="noreferrer" className="quick-link-item">
            🔖 Sổ tay K48-49
          </a>
          <a href="mailto:khoacntt@hcmue.edu.vn?subject=Báo%20lỗi%20HCMUE%20Chatbot" className="quick-link-item" style={{ color: '#EF4444', fontWeight: 500, marginTop: '0.5rem' }}>
            🐞 Góp ý / Báo lỗi
          </a>
        </div>

        <div className="sidebar-footer">
          <p>Phiên bản 1.0.0 · © 2026 HCMUE</p>
        </div>
      </aside>
    </>
  );
}
