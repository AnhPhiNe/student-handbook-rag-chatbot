import React, { useState, useEffect, useRef, Suspense } from 'react';
import { Sun, Moon, Trash2, Loader2 } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { useChat } from './hooks/useChat';
const HomePage = React.lazy(() => import('./components/pages/HomePage').then(module => ({ default: module.HomePage })));
const FormPage = React.lazy(() => import('./components/pages/FormPage').then(module => ({ default: module.FormPage })));
const GuidePage = React.lazy(() => import('./components/pages/GuidePage').then(module => ({ default: module.GuidePage })));
const GpaPage = React.lazy(() => import('./components/pages/GpaPage').then(module => ({ default: module.GpaPage })));
const TargetGpaPage = React.lazy(() => import('./components/pages/TargetGpaPage').then(module => ({ default: module.TargetGpaPage })));
const CourseTargetPage = React.lazy(() => import('./components/pages/CourseTargetPage').then(module => ({ default: module.CourseTargetPage })));
const ScholarshipPage = React.lazy(() => import('./components/pages/ScholarshipPage').then(module => ({ default: module.ScholarshipPage })));
const ToolsPage = React.lazy(() => import('./components/pages/ToolsPage').then(module => ({ default: module.ToolsPage })));
const TuitionPage = React.lazy(() => import('./components/pages/TuitionPage').then(module => ({ default: module.TuitionPage })));
const SurvivalGuidePage = React.lazy(() => import('./components/pages/SurvivalGuidePage').then(module => ({ default: module.SurvivalGuidePage })));
const CreditsPage = React.lazy(() => import('./components/pages/CreditsPage').then(module => ({ default: module.CreditsPage })));

import { ErrorBoundary } from './components/ErrorBoundary';
import { MobileHeader } from './components/MobileHeader';
import { BottomTabBar } from './components/BottomTabBar';
import { ToastProvider } from './components/Toast';
import { useMediaQuery } from './hooks/useMediaQuery';
import { useLocalStorage } from './hooks/useLocalStorage';
import { VisitorCounter } from './components/VisitorCounter';
import { CohortSelectionModal } from './components/CohortSelectionModal';
import { SystemStatusBadge } from './components/SystemStatusBadge';
import { MobileScrollAffordance } from './components/MobileScrollAffordance';
import { normalizeFrontendCohort, type Cohort } from './utils/gradeScale';

const COHORT_SELECTOR_TABS = new Set([
  'home',
  'chat',
  'gpa',
  'target-gpa',
  'course-target',
  'scholarship',
  'tuition',
  'credits',
]);

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
  const [isCohortModalDismissed, setIsCohortModalDismissed] = useState(false);
  const contentAreaRef = useRef<HTMLDivElement>(null);
  
  const isMobile = useMediaQuery('(max-width: 900px)');
  const shouldShowCohortSelector = COHORT_SELECTOR_TABS.has(activeTab);

  // Sync theme with HTML data attribute
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  const handleNavigate = (nextTab: string) => {
    setActiveTab(nextTab);
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
              cohort={cohort}
              onCohortChange={setCohort}
              showCohortSelector={shouldShowCohortSelector}
            />
          )}
          
          <Sidebar 
            activeTab={activeTab}
            onTabChange={handleNavigate}
            isCollapsed={sidebarCollapsed}
            isMobileOpen={isMobileMenuOpen}
            onClose={() => setIsMobileMenuOpen(false)}
            onToggleCollapse={() => setSidebarCollapsed(prev => !prev)}
            showVisitorCounter={isMobile}
          />
          
          <div ref={contentAreaRef} className="content-area" style={{ position: 'relative' }}>
            {/* Global Controls */}
            {!isMobile && (
              <>
                <div className="header-left-controls">
                  <VisitorCounter />
                </div>
                <div className={`global-controls ${shouldShowCohortSelector ? '' : 'compact'}`}>
                <SystemStatusBadge />
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
                  <span>Chế độ {theme === 'light' ? 'tối' : 'sáng'}</span>
                </button>
              </div>
              </>
            )}
            
            <Suspense fallback={
              <div className="page-container" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: '60vh', gap: '1rem', color: 'var(--text-secondary)' }}>
                <Loader2 size={40} style={{ color: 'var(--primary)', animation: 'spin 1s linear infinite' }} />
                <p style={{ fontSize: '1.1rem', animation: 'pulse-opacity 2s ease-in-out infinite' }}>Đang tải nội dung...</p>
              </div>
            }>
              {activeTab === 'home' && <HomePage onNavigate={handleNavigate} />}
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
                  onNavigateTab={handleNavigate}
                  onClearChat={clearMessages}
                  cohort={cohort}
                />
              )}
              {activeTab === 'bieu-mau' && <FormPage />}
              {activeTab === 'tools' && <ToolsPage onNavigate={handleNavigate} />}
              {activeTab === 'gpa' && <GpaPage key={cohort} cohort={cohort} />}
              {activeTab === 'target-gpa' && <TargetGpaPage />}
              {activeTab === 'course-target' && <CourseTargetPage key={cohort} cohort={cohort} />}
              {activeTab === 'scholarship' && <ScholarshipPage />}
              {activeTab === 'tuition' && <TuitionPage />}
              {activeTab === 'credits' && <CreditsPage />}
              {activeTab === 'survival-guide' && <SurvivalGuidePage />}
              {activeTab === 'huong-dan' && <GuidePage onNavigate={handleNavigate} />}

            </Suspense>
            {isMobile && (
              <MobileScrollAffordance
                activeKey={activeTab}
                containerRef={contentAreaRef}
                disabled={activeTab === 'chat'}
              />
            )}
          </div>

          {isMobile && (
            <BottomTabBar 
              activeTab={activeTab} 
              onTabChange={handleNavigate}
            />
          )}

          {!storedCohort && !isCohortModalDismissed && (
            <CohortSelectionModal
              onSelect={setCohort}
              onDismiss={() => setIsCohortModalDismissed(true)}
            />
          )}
        </div>
      </ToastProvider>
    </ErrorBoundary>
  );
}

export default App;
