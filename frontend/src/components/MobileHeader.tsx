import { Menu, Moon, Sun } from 'lucide-react';

interface MobileHeaderProps {
  onMenuToggle: () => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
}

export function MobileHeader({ onMenuToggle, theme, onToggleTheme }: MobileHeaderProps) {
  return (
    <header className="mobile-header">
      <button className="mobile-menu-btn" onClick={onMenuToggle} aria-label="Menu">
        <Menu size={24} />
      </button>
      
      <div className="mobile-header-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        HCMUE AI
        <span style={{ backgroundColor: 'rgba(245, 158, 11, 0.2)', color: '#F59E0B', fontSize: '0.65rem', padding: '0.125rem 0.375rem', borderRadius: '4px', letterSpacing: '0.5px' }}>BETA</span>
      </div>
      
      <button className="mobile-theme-btn" onClick={onToggleTheme} aria-label="Toggle theme">
        {theme === 'light' ? <Moon size={22} /> : <Sun size={22} />}
      </button>
    </header>
  );
}
