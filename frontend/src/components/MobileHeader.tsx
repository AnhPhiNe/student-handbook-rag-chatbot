import { ChevronDown, Moon, Plus, Sun } from 'lucide-react';
import type { Cohort } from '../utils/gradeScale';

const logoHcmue = '/logo_hcmue.png?v=2';

interface MobileHeaderProps {
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  cohort: Cohort;
  onOpenCohort: () => void;
  showCohortSelector: boolean;
  /** Shown on the chat tab only, where a fresh conversation is the common next step. */
  onNewChat?: () => void;
}

// Every page is one tap away in the tab bar, so the header keeps only what applies to the
// page itself: the cohort, a new conversation in chat, and the theme.
export function MobileHeader({ theme, onToggleTheme, cohort, onOpenCohort, showCohortSelector, onNewChat }: MobileHeaderProps) {
  return (
    <header className="mobile-header">
      <span className="mobile-brand">
        <img src={logoHcmue} alt="" className="mobile-brand-logo" />
        <span className="mobile-brand-name">HCMUE AI</span>
        <small>beta</small>
      </span>
      <span className="mobile-header-actions">
        {showCohortSelector && (
          <button type="button" className="mobile-cohort-pill" onClick={onOpenCohort} aria-label={`Đổi khóa, đang chọn ${cohort}`}>
            {cohort}
            <ChevronDown size={14} aria-hidden="true" />
          </button>
        )}
        {onNewChat && (
          <button type="button" className="mobile-icon-btn solid" onClick={onNewChat} aria-label="Cuộc trò chuyện mới" title="Cuộc trò chuyện mới">
            <Plus size={20} aria-hidden="true" />
          </button>
        )}
        <button
          type="button"
          className="mobile-icon-btn"
          onClick={onToggleTheme}
          aria-label={`Bật chế độ ${theme === 'light' ? 'tối' : 'sáng'}`}
        >
          {theme === 'light' ? <Moon size={20} aria-hidden="true" /> : <Sun size={20} aria-hidden="true" />}
        </button>
      </span>
    </header>
  );
}
