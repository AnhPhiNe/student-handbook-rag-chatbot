import { useState, useEffect } from 'react';
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
import { useMediaQuery } from './hooks/useMediaQuery';
import { useLocalStorage } from './hooks/useLocalStorage';
import { BugReportModal } from './components/BugReportModal';

function App() {
  const { messages, isTyping, progressMessage, sendMessage, sendHardcodedMessage, clearMessages, retryLastMessage, regenerateLastMessage } = useChat();
  const [theme, setTheme] = useLocalStorage<'light' | 'dark'>('hcmue-theme', 'light');
  const [activeTab, setActiveTab] = useState('home');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isBugModalOpen, setIsBugModalOpen] = useState(false);
  
  const isMobile = useMediaQuery('(max-width: 768px)');

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
          
          <div className="content-area">
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
              />
            )}
            {activeTab === 'bieu-mau' && <FormPage />}
            {activeTab === 'tools' && <ToolsPage onNavigate={setActiveTab} />}
            {activeTab === 'gpa' && <GpaPage />}
            {activeTab === 'target-gpa' && <TargetGpaPage />}
            {activeTab === 'course-target' && <CourseTargetPage />}
            {activeTab === 'scholarship' && <ScholarshipPage />}
            {activeTab === 'tuition' && <TuitionPage />}
            {activeTab === 'credits' && <CreditsPage />}
            {activeTab === 'huong-dan' && <GuidePage />}
          </div>

          {isMobile && (
            <BottomTabBar 
              activeTab={activeTab} 
              onTabChange={setActiveTab} 
            />
          )}

          <BugReportModal isOpen={isBugModalOpen} setIsOpen={setIsBugModalOpen} />
        </div>
      </ToastProvider>
    </ErrorBoundary>
  );
}

export default App;
