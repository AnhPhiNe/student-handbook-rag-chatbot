import { useState, useEffect } from 'react';
import { Sun, Moon, Trash2 } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { useChat } from './hooks/useChat';
import { HomePage } from './components/pages/HomePage';
import { FormPage } from './components/pages/FormPage';
import { GuidePage } from './components/pages/GuidePage';
import { CreditsPage } from './components/pages/CreditsPage';
import { GpaPage } from './components/pages/GpaPage';
import { TargetGpaPage } from './components/pages/TargetGpaPage';
import { CourseTargetPage } from './components/pages/CourseTargetPage';
import { ScholarshipPage } from './components/pages/ScholarshipPage';
import { ToolsPage } from './components/pages/ToolsPage';
import { TuitionPage } from './components/pages/TuitionPage';
import { ErrorBoundary } from './components/ErrorBoundary';
import { MobileHeader } from './components/MobileHeader';
import { BottomTabBar } from './components/BottomTabBar';
import { ToastProvider } from './components/Toast';
import { ScrollCue } from './components/ScrollCue';
import { useMediaQuery } from './hooks/useMediaQuery';
import { useLocalStorage } from './hooks/useLocalStorage';
import { BugReportModal } from './components/BugReportModal';
import { CohortSelectionModal } from './components/CohortSelectionModal';
import { ActiveUsersBadge } from './components/ActiveUsersBadge';
import { normalizeFrontendCohort, type Cohort } from './utils/gradeScale';

const COHORT_AWARE_TABS = new Set(['home', 'chat', 'gpa', 'course-target']);

function App() {
  const defaultTheme = (new Date().getHours() >= 18 || new Date().getHours() < 6) ? 'dark' : 'light';
  const [theme, setTheme] = useLocalStorage<'light' | 'dark'>('hcmue-theme', defaultTheme);
  const [storedCohort, setStoredCohort] = useLocalStorage<Cohort | null>('hcmue-cohort', null);
  const cohort = storedCohort ? normalizeFrontendCohort(storedCohort) : 'K48-K49'; // Fallback an toàn cho utils
  const setCohort = (nextCohort: Cohort) => setStoredCohort(nextCohort);
  
  const { messages, isTyping, progressMessage, sendMessage, sendHardcodedMessage, clearMessages, retryLastMessage, regenerateLastMessage } = useChat(cohort);

  const [activeTab, setActiveTab] = useState('home');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isBugModalOpen, setIsBugModalOpen] = useState(false);
  
  const isMobile = useMediaQuery('(max-width: 900px)');
  const shouldShowCohortSelector = COHORT_AWARE_TABS.has(activeTab);

  // Sync theme with HTML data attribute
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  return (
    <ErrorBoundary>
      <ToastProvider>
        <div className="app-container">
          {isMobile && (
            <MobileHeader 
              onMenuToggle={() => setIsMobileMenuOpen(true)} 
              theme={theme} 
              onToggleTheme={toggleTheme} 
              onOpenBugReport={() => setIsBugModalOpen(true)}
              cohort={cohort}
              onCohortChange={setCohort}
              showCohortSelector={shouldShowCohortSelector}
            />
          )}
          
          <Sidebar 
            activeTab={activeTab}
            onTabChange={setActiveTab}
            onNewChat={clearMessages}
            isCollapsed={sidebarCollapsed}
            isMobileOpen={isMobileMenuOpen}
            onClose={() => setIsMobileMenuOpen(false)}
            onToggleCollapse={() => setSidebarCollapsed(prev => !prev)}
            onOpenBugReport={() => setIsBugModalOpen(true)}
          />
          
          <div className="content-area" style={{ position: 'relative' }}>
            {/* Global Controls */}
            {!isMobile && (
              <div className={`global-controls ${shouldShowCohortSelector ? '' : 'compact'}`}>
                <ActiveUsersBadge />
                {activeTab === 'chat' && messages.length > 0 && (
                  <button className="theme-toggle" onClick={() => {
                    if (window.confirm("Bạn có chắc chắn muốn xóa toàn bộ lịch sử chat không?")) {
                      clearMessages();
                    }
                  }} title="Xóa lịch sử chat">
                    <Trash2 size={16} />
                    <span>Xóa chat</span>
                  </button>
                )}
                {shouldShowCohortSelector && (
                <select 
                  className="theme-toggle cohort-selector" 
                  value={cohort} 
                  onChange={(e) => setCohort(e.target.value as Cohort)}
                  style={{ cursor: 'pointer', outline: 'none' }}
                >
                  <option value="K48-K49">Khóa 48 - 49</option>
                  <option value="K50">Khóa 50</option>
                  <option value="K51">Khóa 51</option>
                </select>
                )}
                <button className="theme-toggle" onClick={toggleTheme}>
                  {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
                  <span>{theme === 'light' ? 'Chế độ tối' : 'Chế độ sáng'}</span>
                </button>
              </div>
            )}
            
            {activeTab === 'home' && <HomePage onNavigate={setActiveTab} />}
            {activeTab === 'chat' && (
              <ChatArea 
                messages={messages}
                isTyping={isTyping}
                progressMessage={progressMessage}
                onSendMessage={sendMessage}
                onSendHardcoded={sendHardcodedMessage}
                onRetry={retryLastMessage}
                onRegenerate={regenerateLastMessage}
                theme={theme}
                onToggleTheme={toggleTheme}
                onNavigateTab={setActiveTab}
                onClearChat={clearMessages}
                cohort={cohort}
              />
            )}
            {activeTab === 'bieu-mau' && <FormPage />}
            {activeTab === 'tools' && <ToolsPage onNavigate={setActiveTab} />}
            {activeTab === 'gpa' && <GpaPage key={cohort} cohort={cohort} />}
            {activeTab === 'target-gpa' && <TargetGpaPage />}
            {activeTab === 'course-target' && <CourseTargetPage key={cohort} cohort={cohort} />}
            {activeTab === 'scholarship' && <ScholarshipPage />}
            {activeTab === 'tuition' && <TuitionPage />}
            {activeTab === 'credits' && <CreditsPage />}
            {activeTab === 'huong-dan' && <GuidePage />}
            <ScrollCue activeTab={activeTab} />
          </div>

          {isMobile && (
            <BottomTabBar 
              activeTab={activeTab} 
              onTabChange={setActiveTab} 
            />
          )}

          <BugReportModal isOpen={isBugModalOpen} setIsOpen={setIsBugModalOpen} messages={messages} />
          
          {!storedCohort && <CohortSelectionModal onSelect={setCohort} />}
        </div>
      </ToastProvider>
    </ErrorBoundary>
  );
}

export default App;
