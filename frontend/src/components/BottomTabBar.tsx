import { MessageSquare, FileText, BookOpen, Wrench, Home } from 'lucide-react';

interface BottomTabBarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

export function BottomTabBar({ activeTab, onTabChange }: BottomTabBarProps) {
  const toolTabs = new Set(['gpa', 'target-gpa', 'course-target', 'scholarship', 'tuition', 'credits', 'faq']);
  const tabs = [
    { id: 'home', icon: Home, label: 'Trang chủ' },
    { id: 'chat', icon: MessageSquare, label: 'Chat' },
    { id: 'bieu-mau', icon: FileText, label: 'Biểu mẫu' },
    { id: 'tools', icon: Wrench, label: 'Công cụ' },
    { id: 'huong-dan', icon: BookOpen, label: 'Hướng dẫn' }
  ];

  return (
    <nav className="bottom-tab-bar">
      {tabs.map(tab => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id || (tab.id === 'tools' && toolTabs.has(activeTab));
        return (
          <button
            key={tab.id}
            className={`tab-btn ${isActive ? 'active' : ''}`}
            onClick={() => onTabChange(tab.id)}
            aria-label={tab.label}
          >
            <Icon size={22} />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
