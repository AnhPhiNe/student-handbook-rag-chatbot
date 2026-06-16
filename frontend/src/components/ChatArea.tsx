import { useRef, useEffect, useState } from 'react';
import { Moon, Sun, GraduationCap, FileText, Gift, Home, Trash2, ArrowDown, Lock, Bug } from 'lucide-react';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import type { Message } from '../hooks/useChat';
import logoHcmue from '../assets/logo_hcmue.png';

const IS_MAINTENANCE_MODE = false;


interface ChatAreaProps {
  messages: Message[];
  isTyping: boolean;
  progressMessage?: string;
  onSendMessage: (text: string) => void;
  onSendHardcoded: (text: string, response: string, suggestions?: string[]) => void;
  onRetry?: () => void;
  onRegenerate?: () => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onNavigateTab?: (tabId: string) => void;
  onClearChat?: () => void;
}

const ACTION_CARDS = [
  { id: 'hoc-vu', label: 'Học vụ & Đào tạo', icon: GraduationCap, color: '#3b82f6', desc: 'Hỏi về điểm số, học vượt, bảo lưu...' },
  { id: 'hoc-bong', label: 'Học bổng & Học phí', icon: Gift, color: '#8b5cf6', desc: 'Điều kiện, thời hạn, chính sách...' },
  { id: 'ktx', label: 'Phòng ban & KTX', icon: Home, color: '#f59e0b', desc: 'Thông tin liên hệ, nội quy, giờ làm việc...' },
  { id: 'hanh-chinh', label: 'Quy trình Hành chính', icon: FileText, color: '#10b981', desc: 'Hỏi cách làm thủ tục, nộp đơn từ...' }
];

type QuickAccessResponse = {
  response: string;
  suggestions: string[];
};

// Local-only responses for quick access cards. These do not call the backend.
const HARDCODED_RESPONSES: Record<string, QuickAccessResponse> = {
  'hoc-vu': {
    response: "## Học vụ & Đào tạo\n\nBạn có thể hỏi các quy định học vụ có trong Sổ tay sinh viên, nhất là nội dung về điểm học phần và kết quả học tập.\n\n**Bạn có thể hỏi về:**\n\n- **Điểm học phần:** điểm quá trình, điểm thi kết thúc học phần, thang điểm 10.\n- **Xếp loại điểm chữ:** A, B+, B, C+, C, D+, D, F+, F và quy đổi hệ 4.\n- **Qua môn/học lại:** học phần đạt từ D trở lên; F+ và F là không đạt.\n- **Điểm rèn luyện:** phân loại theo thang điểm trong sổ tay.",
    suggestions: [
      "Mấy điểm thì qua môn?",
      "Mấy điểm thì được điểm A?",
      "Điểm B+ quy đổi sang hệ 4 bao nhiêu?",
      "Điểm rèn luyện 85 là loại gì?"
    ]
  },
  'hoc-bong': {
    response: "## Học bổng & Học phí\n\nBạn có thể hỏi các nội dung tài chính sinh viên được nêu trong Sổ tay sinh viên.\n\n**Bạn có thể hỏi về:**\n\n- **Học bổng khuyến khích học tập:** điều kiện xét, xếp loại và thông tin liên quan đến học tập/rèn luyện.\n- **Cách tính điểm học bổng:** công thức khi sổ tay có đủ dữ liệu cần thiết.\n- **Học phí:** quy định chung theo số tín chỉ đăng ký từng học kỳ.\n- **Miễn giảm, trợ cấp và hỗ trợ chi phí học tập:** thông tin chính sách khi sổ tay có đề cập.\n\nNếu bạn cần tải mẫu đơn, hãy dùng mục **Biểu mẫu** ở sidebar.",
    suggestions: [
      "Điều kiện xét học bổng khuyến khích học tập là gì?",
      "Cách tính điểm học bổng như thế nào?",
      "Học phí được quy định ra sao?",
      "Miễn giảm học phí áp dụng cho ai?"
    ]
  },
  'ktx': {
    response: "## Phòng ban & Ký túc xá\n\nBạn có thể hỏi thông tin liên hệ và một số nội dung KTX có trong Sổ tay sinh viên.\n\n**Bạn có thể hỏi về:**\n\n- **Phòng ban:** số điện thoại, email, website, địa chỉ/văn phòng làm việc và nhiệm vụ chính.\n- **Khoa/ngành:** thông tin liên hệ của khoa, văn phòng khoa và website khi sổ tay có dữ liệu.\n- **Ký túc xá:** đăng ký, điều kiện, nội quy hoặc thông tin liên quan được sổ tay đề cập.",
    suggestions: [
      "Phòng Đào tạo email là gì?",
      "Phòng CNTT ở đâu?",
      "Khoa Công nghệ Thông tin ở đâu?",
      "Điều kiện vào ký túc xá là gì?"
    ]
  },
  'hanh-chinh': {
    response: "## Quy trình Hành chính\n\nBạn có thể hỏi các nội dung giấy tờ và thủ tục mà Sổ tay sinh viên có đề cập rõ.\n\n**Bạn có thể hỏi về:**\n\n- **Thông tin giấy tờ/xác nhận:** thông tin hoặc đơn vị liên quan nếu sổ tay có nêu.\n- **Thủ tục học vụ có dữ liệu:** học lại, cải thiện điểm, bảo lưu/tạm nghỉ hoặc quy định liên quan.\n- **Đơn vị phụ trách:** phòng ban/khoa liên quan khi sổ tay có thông tin đủ rõ.\n\nNếu sổ tay không nêu rõ nơi nộp, thời hạn hoặc từng bước làm thủ tục, chatbot sẽ không tự đoán. Nếu bạn cần tìm hoặc tải mẫu đơn, hãy dùng mục **Biểu mẫu** ở sidebar.",
    suggestions: [
      "Muốn bảo lưu kết quả học tập thì quy định thế nào?",
      "Học lại và cải thiện điểm khác nhau thế nào?",
      "Xin giấy xác nhận sinh viên liên hệ đơn vị nào?",
      "Xin bảng điểm thì liên hệ phòng nào?"
    ]
  }
};

export function ChatArea({ messages, isTyping, progressMessage, onSendMessage, onSendHardcoded, onRetry, onRegenerate, theme, onToggleTheme, onNavigateTab, onClearChat }: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const hasMessages = messages.length > 0;
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [thinkingMessage, setThinkingMessage] = useState("");
  const coldStartTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleScroll = () => {
    if (!chatContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
    const isScrolledUp = scrollHeight - scrollTop - clientHeight > 100;
    setShowScrollButton(isScrolledUp);
  };

  const handleQuickAccess = (id: string) => {
    if (id === 'bieu-mau') {
      if (onNavigateTab) onNavigateTab('resources');
      return;
    }
    
    const titles: Record<string, string> = {
      'hoc-vu': 'Học vụ & Đào tạo',
      'hoc-bong': 'Học bổng & Học phí',
      'ktx': 'Phòng ban & Ký túc xá',
      'hanh-chinh': 'Quy trình Hành chính'
    };
    
    const userPrompt = `Cho tôi biết thông tin về ${titles[id]}`;
    
    const quickAccess = HARDCODED_RESPONSES[id];
    if (quickAccess) onSendHardcoded(userPrompt, quickAccess.response, quickAccess.suggestions);
  };

  // Keyboard shortcut '/' to focus textarea
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === '/' && document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault();
        const textarea = document.querySelector('.chat-textarea') as HTMLTextAreaElement;
        textarea?.focus();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Progressive thinking indicator based on real backend progress or simulated fallback
  useEffect(() => {
    if (isTyping) {
      if (progressMessage) {
        setThinkingMessage(progressMessage);
        clearInterval(coldStartTimer.current);
      } else {
        const messages = [
          "⏳ Đang phân tích câu hỏi của bạn...",
          "📖 Đang lục lọi trong Sổ tay sinh viên...",
          "🔍 Đang tìm kiếm các tài liệu liên quan...",
          "✨ Sắp xong rồi, đang tổng hợp câu trả lời..."
        ];
        if (!thinkingMessage) {
          setThinkingMessage(messages[0]);
        }
        
        let i = 0;
        clearInterval(coldStartTimer.current);
        coldStartTimer.current = setInterval(() => {
          i++;
          if (i < messages.length) {
            setThinkingMessage(messages[i]);
          }
        }, 5000) as any;
      }
    } else {
      setThinkingMessage("");
      clearInterval(coldStartTimer.current);
    }
    return () => clearInterval(coldStartTimer.current);
  }, [isTyping, progressMessage]);

  // ============ EMPTY STATE ============
  if (!hasMessages) {
    return (
      <main className="chat-area">
        {IS_MAINTENANCE_MODE && (
          <div className="maintenance-overlay">
            <div className="maintenance-card">
              <div className="maintenance-icon-wrap">
                <Lock size={32} />
              </div>
              <h3>Tính năng đang bảo trì</h3>
              <p>Trợ lý AI đang tạm nghỉ để nâng cấp dữ liệu. Trong lúc chờ đợi, bạn vẫn có thể dùng thả ga các công cụ <strong>Tính GPA, Mục tiêu GPA, Mục tiêu môn học, Tính học bổng, Ước tính học phí, Kiểm tra hạ bằng, Tra cứu biểu mẫu</strong> và xem <strong>Hướng dẫn</strong> ở menu bên cạnh nhé!</p>
            </div>
          </div>
        )}

        <header className="chat-header">
          <div style={{flex: 1}}></div>
          {hasMessages && (
            <button className="theme-toggle" onClick={onClearChat} title="Xóa lịch sử chat" style={{ marginRight: '0.5rem' }}>
              <Trash2 size={16} />
              <span>Xóa chat</span>
            </button>
          )}
          <button className="theme-toggle" onClick={onToggleTheme}>
            {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
            <span>{theme === 'light' ? 'Chế độ tối' : 'Chế độ sáng'}</span>
          </button>
        </header>

        {/* Scrollable content area that fills available space */}
        <div className="empty-state">
          <div className="empty-state-content">
            {/* Hero - compact */}
            <div className="empty-hero">
              <img src={logoHcmue} alt="HCMUE" className="hero-logo" />
              <p className="hero-subtitle" style={{ marginTop: '0.5rem', fontSize: '1.125rem' }}>Mình là trợ lý AI của Đại học Sư phạm TP.HCM</p>
              <p className="hero-desc">Bạn cần tìm gì trong sổ tay sinh viên hôm nay?</p>
            </div>

            {/* Action Cards Grid */}
            <div className="action-cards-grid">
              {ACTION_CARDS.map(item => (
                <button key={item.id} className="action-card" onClick={() => handleQuickAccess(item.id)}>
                  <div className="action-icon" style={{ backgroundColor: `${item.color}15`, color: item.color }}>
                    <item.icon size={20} />
                  </div>
                  <div className="action-text">
                    <h4>{item.label}</h4>
                    <p>{item.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Input pinned to bottom */}
        <div className="chat-input-pinned">
          {thinkingMessage && (
            <div className="cold-start-banner" style={{ margin: '0 auto 0.75rem', maxWidth: '780px' }}>
              <div className="cold-start-spinner" />
              <span>{thinkingMessage}</span>
            </div>
          )}
          <ChatInput onSend={onSendMessage} disabled={isTyping} />
        </div>
      </main>
    );
  }

  // ============ CONVERSATION STATE ============
  return (
    <main className="chat-area">
      {IS_MAINTENANCE_MODE && (
        <div className="maintenance-overlay">
          <div className="maintenance-card">
            <div className="maintenance-icon-wrap">
              <Lock size={32} />
            </div>
            <h3>Tính năng đang bảo trì</h3>
            <p>Trợ lý AI đang tạm nghỉ để nâng cấp dữ liệu. Trong lúc chờ đợi, bạn vẫn có thể dùng thả ga các công cụ <strong>Tính GPA, Mục tiêu GPA, Mục tiêu môn học, Tính học bổng, Ước tính học phí, Kiểm tra hạ bằng, Tra cứu biểu mẫu</strong> và xem <strong>Hướng dẫn</strong> ở menu bên cạnh nhé!</p>
          </div>
        </div>
      )}

      <header className="chat-header">
        <h2 className="chat-title">Hội thoại với HCMUE AI</h2>
        <div style={{display: 'flex', gap: '0.5rem'}}>
          <button className="theme-toggle" onClick={onClearChat} title="Xóa lịch sử chat">
            <Trash2 size={16} />
            <span>Xóa chat</span>
          </button>
          <button className="theme-toggle" onClick={onToggleTheme}>
            {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
            <span>{theme === 'light' ? 'Chế độ tối' : 'Chế độ sáng'}</span>
          </button>
        </div>
      </header>

      <div className="chat-messages" ref={chatContainerRef} onScroll={handleScroll}>
        {messages.map((msg) => (
          <ChatMessage 
            key={msg.id} 
            message={msg} 
            thinkingMessage={thinkingMessage}
            onRetry={onRetry}
            onRegenerate={onRegenerate}
          />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {showScrollButton && (
        <button className="scroll-to-bottom-btn" onClick={scrollToBottom} title="Cuộn xuống dưới">
          <ArrowDown size={20} />
        </button>
      )}

      <ChatInput onSend={onSendMessage} disabled={isTyping} />
    </main>
  );
}
