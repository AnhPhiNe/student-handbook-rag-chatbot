import { Menu, Moon, Sun } from 'lucide-react';
import type { Cohort } from '../utils/gradeScale';

interface MobileHeaderProps {
  onMenuToggle: () => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  cohort: Cohort;
  onCohortChange: (cohort: Cohort) => void;
  showCohortSelector: boolean;
}

export function MobileHeader({ onMenuToggle, theme, onToggleTheme, cohort, onCohortChange, showCohortSelector }: MobileHeaderProps) {
  return (
    <header className="mobile-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button className="mobile-menu-btn" onClick={onMenuToggle} aria-label="Menu" style={{ padding: '4px' }}>
          <Menu size={26} />
        </button>
        
        <div className="mobile-header-title" style={{ display: 'flex', alignItems: 'center', gap: '6px', margin: 0 }}>
          <span style={{ fontSize: '1.05rem', fontWeight: 700 }}>HCMUE AI</span>
          <span style={{ backgroundColor: 'rgba(245, 158, 11, 0.2)', color: '#F59E0B', fontSize: '0.65rem', padding: '0.125rem 0.375rem', borderRadius: '4px', letterSpacing: '0.5px' }}>BETA</span>
        </div>
      </div>
      
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {showCohortSelector && (
          <select 
            className="mobile-cohort-selector"
            style={{ textAlignLast: 'center', paddingLeft: '8px', paddingRight: '8px' }}
            value={cohort} 
            onChange={(e) => onCohortChange(e.target.value as Cohort)}
            aria-label="Chọn khóa áp dụng"
          >
            <option value="K48-K49">Khóa 48 - 49</option>
            <option value="K50">Khóa 50</option>
            <option value="K51">Khóa 51</option>
          </select>
        )}
        <button className="mobile-theme-btn" onClick={onToggleTheme} aria-label="Toggle theme">
          {theme === 'light' ? <Moon size={22} /> : <Sun size={22} />}
        </button>
      </div>
    </header>
  );
}
