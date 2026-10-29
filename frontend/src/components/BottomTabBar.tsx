import { useEffect, useState } from 'react';
import { BookOpen, Contact, Home, MessageSquare, Star, Wrench } from 'lucide-react';
import { IS_CHAT_MAINTENANCE, SHOW_EXPERIENCE_PAGE } from '../config/features';

interface BottomTabBarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const TOOL_TABS = new Set(['gpa', 'target-gpa', 'course-target', 'scholarship', 'tuition', 'credits']);

// Phones shrink the visual viewport when the keyboard opens; the bar then hides so the
// chat input keeps its room.
function useKeyboardOpen(): boolean {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const update = () => setOpen(viewport.height < window.innerHeight * 0.75);
    viewport.addEventListener('resize', update);
    return () => viewport.removeEventListener('resize', update);
  }, []);
  return open;
}

// Chat sits in the middle as a raised round button. While the experience page is off,
// the usage guide takes its slot so there are always five tabs and chat stays centred.
export function BottomTabBar({ activeTab, onTabChange }: BottomTabBarProps) {
  const keyboardOpen = useKeyboardOpen();
  const tabs = [
    { id: 'home', icon: Home, label: 'Trang chủ' },
    { id: 'tools', icon: Wrench, label: 'Công cụ' },
    { id: 'chat', icon: MessageSquare, label: 'Chat' },
    SHOW_EXPERIENCE_PAGE
      ? { id: 'kinh-nghiem', icon: Star, label: 'Kinh nghiệm' }
      : { id: 'huong-dan', icon: BookOpen, label: 'Cách dùng web' },
    { id: 'danh-ba', icon: Contact, label: 'Danh bạ' },
  ];

  return (
    <nav className={`bottom-tab-bar${keyboardOpen ? ' keyboard-open' : ''}`} aria-label="Điều hướng chính">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id || (tab.id === 'tools' && TOOL_TABS.has(activeTab));
        const isChat = tab.id === 'chat';
        return (
          <button
            key={tab.id}
            type="button"
            data-tab={tab.id}
            className={`tab-btn${isChat ? ' chat' : ''}${isActive ? ' active' : ''}`}
            onClick={() => onTabChange(tab.id)}
            aria-current={isActive ? 'page' : undefined}
            aria-label={isChat && IS_CHAT_MAINTENANCE ? `${tab.label} (Đang bảo trì)` : tab.label}
            title={isChat && IS_CHAT_MAINTENANCE ? 'Chức năng này đang bảo trì, vui lòng thử lại sau' : undefined}
          >
            <span className="tab-icon" aria-hidden="true">
              <Icon size={isChat ? 22 : 21} />
            </span>
            <span className="tab-label">{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
