import { useRef, useEffect, useState } from 'react';
import { ArrowDown } from 'lucide-react';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import type { Message } from '../hooks/useChat';
import type { Cohort } from '../utils/gradeScale';
import { ChatEmptyState } from './ChatEmptyState';
import './ChatPage.css';


interface ChatAreaProps {
  messages: Message[];
  isTyping: boolean;
  onSendMessage: (text: string) => void;
  onRetry?: () => void;
  onRegenerate?: () => void;
  onNavigateTab?: (tabId: string) => void;
  cohort: Cohort;
  draft?: { id: number; text: string } | null;
}

export function ChatArea({ messages, isTyping, onSendMessage, onRetry, onRegenerate, cohort, draft, onNavigateTab }: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const hasMessages = messages.length > 0;

  const [topic, setTopic] = useState<string | null>(null);

  const [showScrollButton, setShowScrollButton] = useState(false);

  const lastMsg = messages[messages.length - 1];
  const hasError = !isTyping && lastMsg?.role === 'bot' && (lastMsg.content.includes("Xin lỗi, đã có lỗi") || lastMsg.content.includes("Hệ thống AI hiện đang quá tải"));

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    // Tránh tự động cuộn xuống đáy ở lượt hội thoại đầu tiên 
    // để người dùng luôn nhìn thấy câu hỏi của mình ở trên cùng
    if (messages.length > 2) {
      scrollToBottom();
    }
  }, [messages, isTyping]);

  const handleScroll = () => {
    if (!chatContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
    const isScrolledUp = scrollHeight - scrollTop - clientHeight > 100;
    setShowScrollButton(isScrolledUp);
  };

  // Keyboard shortcut '/' to focus textarea
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === '/' && !['TEXTAREA', 'INPUT', 'SELECT'].includes(document.activeElement?.tagName ?? '') && !document.activeElement?.hasAttribute('contenteditable')) {
        e.preventDefault();
        const textarea = document.querySelector('.chat-textarea') as HTMLTextAreaElement;
        textarea?.focus();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);


  return (
    <main className={`chat-area chat-page${hasMessages ? ' chat-page-conversation' : ' chat-page-empty'}`}>
      <header className="cc-header"><span>Sổ tay HCMUE · Khóa {cohort.replace('K', '')}</span></header>
      {!hasMessages ? (
        <ChatEmptyState cohort={cohort} topic={topic} onTopicChange={setTopic}
          onAsk={onSendMessage} onNavigate={onNavigateTab} draft={draft}
          isTyping={isTyping} hasError={hasError} />
      ) : (
      <>
      <div className="chat-messages" ref={chatContainerRef} onScroll={handleScroll}>
        {messages.map((msg, index) => {
          const prevMsg = index > 0 ? messages[index - 1] : null;
          const query = msg.role === 'bot' && prevMsg?.role === 'user' ? prevMsg.content : undefined;
          return (
            <ChatMessage
              key={msg.id}
              message={msg}
              onRetry={onRetry}
              onRegenerate={onRegenerate}
              query={query}
              onSuggestionClick={onSendMessage}
              cohort={cohort}
            />
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {showScrollButton && (
        <button className="scroll-to-bottom-btn" onClick={scrollToBottom} title="Cuộn xuống dưới">
          <ArrowDown size={20} />
        </button>
      )}

      <ChatInput key={draft?.id ?? 'composer'} initialText={draft?.text} placeholderText="Hỏi tiếp…" onSend={onSendMessage} disabled={isTyping} hasError={hasError} />
      </>
      )}
    </main>
  );
}
