import { Menu, Moon, Sun, Bug } from 'lucide-react';

interface MobileHeaderProps {
  onMenuToggle: () => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onOpenBugReport: () => void;
}

export function MobileHeader({ onMenuToggle, theme, onToggleTheme, onOpenBugReport }: MobileHeaderProps) {
  return (
    <header className="mobile-header">
      <button className="mobile-menu-btn" onClick={onMenuToggle} aria-label="Menu">
        <Menu size={24} />
      </button>
      
      <div className="mobile-header-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        HCMUE AI
        <span style={{ backgroundColor: 'rgba(245, 158, 11, 0.2)', color: '#F59E0B', fontSize: '0.65rem', padding: '0.125rem 0.375rem', borderRadius: '4px', letterSpacing: '0.5px' }}>BETA</span>
      </div>
      
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button 
          className="mobile-theme-btn" 
          onClick={onOpenBugReport} 
          aria-label="Báo lỗi"
          style={{ color: 'var(--danger)' }}
        >
          <Bug size={22} />
        </button>
        <button className="mobile-theme-btn" onClick={onToggleTheme} aria-label="Toggle theme">
          {theme === 'light' ? <Moon size={22} /> : <Sun size={22} />}
        </button>
      </div>
    </header>
  );
}
