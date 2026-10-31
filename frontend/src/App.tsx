import React, { useState, useEffect, useRef, Suspense } from 'react';
import { Sun, Moon, Plus, Loader2 } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { CHAT_DRAFT_KEY } from './components/ChatInput';
import { useChat } from './hooks/useChat';
const HomePage = React.lazy(() => import('./components/pages/HomePage').then(module => ({ default: module.HomePage })));
const GuidePage = React.lazy(() => import('./components/pages/GuidePage').then(module => ({ default: module.GuidePage })));
const GpaPage = React.lazy(() => import('./components/pages/GpaPage').then(module => ({ default: module.GpaPage })));
const TargetGpaPage = React.lazy(() => import('./components/pages/TargetGpaPage').then(module => ({ default: module.TargetGpaPage })));
const CourseTargetPage = React.lazy(() => import('./components/pages/CourseTargetPage').then(module => ({ default: module.CourseTargetPage })));
const ScholarshipPage = React.lazy(() => import('./components/pages/ScholarshipPage').then(module => ({ default: module.ScholarshipPage })));
const ToolsPage = React.lazy(() => import('./components/pages/ToolsPage').then(module => ({ default: module.ToolsPage })));
const TuitionPage = React.lazy(() => import('./components/pages/TuitionPage').then(module => ({ default: module.TuitionPage })));
const CreditsPage = React.lazy(() => import('./components/pages/CreditsPage').then(module => ({ default: module.CreditsPage })));
const ExperiencePage = React.lazy(() => import('./components/pages/ExperiencePage').then(module => ({ default: module.ExperiencePage })));
const DirectoryPage = React.lazy(() => import('./components/pages/DirectoryPage').then(module => ({ default: module.DirectoryPage })));

import { ErrorBoundary } from './components/ErrorBoundary';
import { MobileHeader } from './components/MobileHeader';
import { BottomTabBar } from './components/BottomTabBar';
import { useMediaQuery } from './hooks/useMediaQuery';
import { useLocalStorage } from './hooks/useLocalStorage';
import { CohortSelectionModal } from './components/CohortSelectionModal';
import { WelcomeCurtain } from './components/WelcomeCurtain';
import { WELCOME_ENTRANCE_STORAGE_KEY, shouldShowWelcomeEntrance } from './utils/welcomeEntrance';
import { CohortSheet } from './components/CohortSheet';
import { ChatMaintenanceModal } from './components/ChatMaintenanceModal';
import { SystemStatusBadge } from './components/SystemStatusBadge';
import { MobileScrollAffordance } from './components/MobileScrollAffordance';
import { normalizeFrontendCohort, type Cohort } from './utils/gradeScale';
import { IS_CHAT_MAINTENANCE, SHOW_EXPERIENCE_PAGE } from './config/features';
import { useToast } from './components/Toast';
import { KEPT_DATA_NOTES, cohortChangeMessage, shouldNotifyCohortChange } from './utils/cohortNotice';
import { RECENT_TOOL_KEY, readRecentTool } from './utils/recentTool';

const COHORT_SELECTOR_TABS = new Set([
  'home',
  'chat',
  'tools',
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
  const cohort = storedCohort ? normalizeFrontendCohort(storedCohort) : 'K49'; // Fallback an toàn cho utils
  const toast = useToast();
  const [activeTab, setActiveTab] = useState('home');
  const [chatDraft, setChatDraft] = useState<{ id: number; text: string } | null>(null);
  const draftSequence = useRef(0);
  const setCohort = (nextCohort: Cohort) => {
    // Tool pages are keyed by cohort and reset, so say what changed for grading.
    if (shouldNotifyCohortChange(storedCohort ? cohort : null, nextCohort, activeTab)) {
      toast.show(cohortChangeMessage(nextCohort, KEPT_DATA_NOTES[activeTab]), 'info');
    }
    setStoredCohort(nextCohort);
  };
  
  const { messages, isTyping, sendMessage, clearMessages, retryLastMessage, regenerateLastMessage } = useChat(cohort);

  const [isCohortSheetOpen, setIsCohortSheetOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isCohortModalDismissed, setIsCohortModalDismissed] = useState(false);
  const [hasSeenWelcome, setHasSeenWelcome] = useLocalStorage<boolean>(WELCOME_ENTRANCE_STORAGE_KEY, false);
  const [isWelcomeActive, setIsWelcomeActive] = useState(() => shouldShowWelcomeEntrance(hasSeenWelcome));
  const handleWelcomeComplete = () => {
    setHasSeenWelcome(true);
    setIsWelcomeActive(false);
  };
  const [isMaintenanceModalOpen, setIsMaintenanceModalOpen] = useState(false);
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
    if (IS_CHAT_MAINTENANCE && nextTab === 'chat') {
      setIsMaintenanceModalOpen(true);
      return;
    }
    if (nextTab === 'kinh-nghiem' && !SHOW_EXPERIENCE_PAGE) return;
    // Home pins and in-chat links open tools too, so "Gần nhất" must follow
    // navigation from every entry point, not just clicks on the tools hub.
    const recentTool = readRecentTool(nextTab);
    if (recentTool) {
      try { window.localStorage.setItem(RECENT_TOOL_KEY, JSON.stringify(recentTool)); }
      catch { /* Navigation still works when browser storage is unavailable. */ }
    }
    setActiveTab(nextTab);
  };

  const startNewChat = () => {
    if (messages.length === 0) return;
    if (window.confirm('Bắt đầu cuộc trò chuyện mới? Cuộc trò chuyện hiện tại sẽ bị xóa.')) {
      try { sessionStorage.removeItem(CHAT_DRAFT_KEY); } catch { /* Storage may be unavailable. */ }
      setChatDraft(null);
      clearMessages();
    }
  };

  // Jump to the chat tab and ask a question there (same maintenance guard as navigating to chat).
  const askChat = (text: string) => {
    if (IS_CHAT_MAINTENANCE) {
      setIsMaintenanceModalOpen(true);
      return;
    }
    setActiveTab('chat');
    if (isTyping) {
      setChatDraft({ id: ++draftSequence.current, text });
      toast.show('Câu hỏi đã được điền vào ô nhập. Bạn có thể gửi khi sẵn sàng.', 'info');
      return;
    }
    setChatDraft(null);
    void sendMessage(text);
  };

  const sendChatMessage = React.useCallback((text: string) => {
    setChatDraft(null);
    void sendMessage(text);
  }, [sendMessage]);

  const desktopControls = (
    <>
      {/* Only show a health notice when chat needs attention. */}
      <SystemStatusBadge hideWhenOnline />
      {activeTab === 'chat' && messages.length > 0 && (
        <button type="button" className="control-pill" onClick={startNewChat}>
          <Plus size={15} aria-hidden="true" />
          <span>Cuộc trò chuyện mới</span>
        </button>
      )}
      <span className="control-cluster">
        {shouldShowCohortSelector && (
          <>
            <select
              value={cohort}
              onChange={(e) => setCohort(e.target.value as Cohort)}
              aria-label="Chọn khóa áp dụng"
            >
              <option value="K49">Khóa 49</option>
              <option value="K50">Khóa 50</option>
              <option value="K51">Khóa 51</option>
              <option value="K52" disabled>Khóa 52 (sắp có)</option>
            </select>
            <span className="control-cluster-divider" aria-hidden="true" />
          </>
        )}
        <button
          type="button"
          className="control-icon"
          onClick={toggleTheme}
          aria-label={`Bật chế độ ${theme === 'light' ? 'tối' : 'sáng'}`}
          title={`Chế độ ${theme === 'light' ? 'tối' : 'sáng'}`}
        >
          {theme === 'light' ? <Moon size={16} aria-hidden="true" /> : <Sun size={16} aria-hidden="true" />}
        </button>
      </span>
    </>
  );

  return (
    <ErrorBoundary>
      <div className="app-container">
          {isMobile && (
            <>
              <MobileHeader
                theme={theme}
                onToggleTheme={toggleTheme}
                cohort={cohort}
                onOpenCohort={() => setIsCohortSheetOpen(true)}
                showCohortSelector={shouldShowCohortSelector}
                onNewChat={activeTab === 'chat' && messages.length > 0 ? startNewChat : undefined}
              />
              <SystemStatusBadge hideWhenOnline variant="strip" />
            </>
          )}
          
          {!isMobile && (
            <Sidebar
              activeTab={activeTab}
              onTabChange={handleNavigate}
              isCollapsed={sidebarCollapsed}
              onToggleCollapse={() => setSidebarCollapsed(prev => !prev)}
            />
          )}
          
          <div ref={contentAreaRef} className="content-area" style={{ position: 'relative' }}>
            {/* Global Controls */}
            {!isMobile && activeTab !== 'tools' && (
              <div className="global-controls">{desktopControls}</div>
            )}
            
            <Suspense fallback={
              <div className="page-container" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: '60vh', gap: '1rem', color: 'var(--text-secondary)' }}>
                <Loader2 size={40} style={{ color: 'var(--primary)', animation: 'spin 1s linear infinite' }} />
                <p style={{ fontSize: '1.1rem', animation: 'pulse-opacity 2s ease-in-out infinite' }}>Đang tải nội dung...</p>
              </div>
            }>
              {activeTab === 'home' && <HomePage onNavigate={handleNavigate} onAskChat={askChat} cohort={storedCohort ? cohort : undefined} />}
              {activeTab === 'chat' && (
                <ChatArea 
                  messages={messages}
                  isTyping={isTyping}
                  onSendMessage={sendChatMessage}
                  draft={chatDraft}
                  onRetry={retryLastMessage}
                  onRegenerate={regenerateLastMessage}
                  onNavigateTab={handleNavigate}
                  cohort={cohort}
                />
              )}
              {activeTab === 'tools' && <ToolsPage onNavigate={handleNavigate} headerActions={!isMobile ? desktopControls : undefined} />}
              {activeTab === 'gpa' && <GpaPage key={cohort} cohort={cohort} onNavigate={handleNavigate} />}
              {activeTab === 'target-gpa' && <TargetGpaPage key={cohort} cohort={cohort} />}
              {activeTab === 'course-target' && <CourseTargetPage key={cohort} cohort={cohort} />}
              {activeTab === 'scholarship' && <ScholarshipPage key={cohort} cohort={cohort} onAskChat={askChat} />}
              {activeTab === 'tuition' && <TuitionPage key={cohort} onAskChat={askChat} />}
              {activeTab === 'credits' && <CreditsPage key={cohort} cohort={cohort} onAskChat={askChat} />}
              {SHOW_EXPERIENCE_PAGE && activeTab === 'kinh-nghiem' && <ExperiencePage onAskChat={askChat} onNavigate={handleNavigate} />}
              {activeTab === 'danh-ba' && <DirectoryPage onAskChat={askChat} />}
              {activeTab === 'huong-dan' && <GuidePage onNavigate={handleNavigate} />}

            </Suspense>
            {isMobile && (
              <MobileScrollAffordance
                activeKey={activeTab}
                containerRef={contentAreaRef}
                disabled={
                  activeTab === 'chat' ||
                  activeTab === 'gpa' ||
                  activeTab === 'target-gpa' ||
                  activeTab === 'course-target' ||
                  activeTab === 'credits' ||
                  activeTab === 'tuition' ||
                  activeTab === 'scholarship'
                }
              />
            )}
          </div>

          {isMobile && (
            <BottomTabBar 
              activeTab={activeTab} 
              onTabChange={handleNavigate}
            />
          )}

          {isWelcomeActive && (
            <WelcomeCurtain onComplete={handleWelcomeComplete} />
          )}

          {!isWelcomeActive && !storedCohort && !isCohortModalDismissed && (
            <CohortSelectionModal
              onSelect={setCohort}
              onDismiss={() => setIsCohortModalDismissed(true)}
            />
          )}

          {isCohortSheetOpen && (
            <CohortSheet
              cohort={cohort}
              onSelect={setCohort}
              onClose={() => setIsCohortSheetOpen(false)}
            />
          )}

          <ChatMaintenanceModal
            isOpen={isMaintenanceModalOpen}
            onClose={() => setIsMaintenanceModalOpen(false)}
            onExploreTools={() => {
              setIsMaintenanceModalOpen(false);
              setActiveTab('tools');
            }}
          />
        </div>
    </ErrorBoundary>
  );
}

export default App;
