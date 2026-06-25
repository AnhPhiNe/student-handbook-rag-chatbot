import { useRef, useEffect, useState } from 'react';
import { Moon, Sun, GraduationCap, Gift, Home, Trash2, ArrowDown, Lock, Calculator, Medal, ClipboardList } from 'lucide-react';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import type { Message } from '../hooks/useChat';
import botAvatarImg from '../assets/bot_avatar.png';

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
  { id: 'hoc-vu', label: 'Học vụ & Đào tạo', icon: GraduationCap, color: '#3b82f6', desc: 'Điểm số, qua môn, học lại, bảo lưu...' },
  { id: 'tinh-toan', label: 'Tính điểm & Công cụ', icon: Calculator, color: '#ec4899', desc: 'Tính GPA, rèn luyện, học bổng...' },
  { id: 'hoc-bong', label: 'Học bổng & Học phí', icon: Gift, color: '#8b5cf6', desc: 'Điều kiện xét, mức thưởng, miễn giảm...' },
  { id: 'ren-luyen', label: 'Rèn luyện & Khen thưởng', icon: Medal, color: '#ef4444', desc: 'Điểm rèn luyện, kỷ luật, danh hiệu...' },
  { id: 'ktx', label: 'Phòng ban & Liên hệ', icon: Home, color: '#f59e0b', desc: 'SĐT, email, địa chỉ, KTX...' },
  { id: 'hanh-chinh', label: 'Quy trình Hành chính', icon: ClipboardList, color: '#10b981', desc: 'Thủ tục, nộp đơn, mẫu biểu...' }
];

type QuickAccessResponse = {
  response: string;
  suggestions: string[];
};

// Local-only responses for quick access cards. These do not call the backend.
const HARDCODED_RESPONSES: Record<string, QuickAccessResponse> = {
  'hoc-vu': {
    response: "## Học vụ & Đào tạo\n\nBạn có thể hỏi các quy định học vụ có trong Sổ tay sinh viên, nhất là nội dung về điểm học phần và kết quả học tập.\n\n**Bạn có thể hỏi về:**\n\n- **Điểm học phần:** điểm quá trình, điểm thi, thang điểm 10.\n- **Xếp loại điểm chữ:** A, B+, B, C+, C, D+, D, F+, F và quy đổi hệ 4.\n- **Qua môn/học lại:** học phần đạt từ D trở lên; F+ và F là không đạt.\n- **Nghỉ học tạm thời:** quy định và điều kiện bảo lưu kết quả.",
    suggestions: [
      "Mấy điểm thì qua môn?",
      "Mấy điểm thì được điểm A?",
      "Điểm B+ quy đổi sang hệ 4 bao nhiêu?",
      "Xin bảo lưu kết quả thì cần điều kiện gì?"
    ]
  },
  'tinh-toan': {
    response: "## Tính điểm & Công cụ\n\nHệ thống được tích hợp các công cụ tính toán tự động dựa trên quy định của trường. Chatbot có thể tính nhẩm hoặc tính chính xác nếu bạn cung cấp đủ số liệu.\n\n**Bạn có thể yêu cầu:**\n\n- **Tính GPA:** Nhập danh sách điểm chữ hoặc điểm số, chatbot sẽ tính ra GPA hệ 4.\n- **Tính điểm rèn luyện:** Cung cấp tổng điểm, chatbot sẽ phân loại (Xuất sắc, Tốt, Khá...).\n- **Tính học bổng:** So sánh điểm học tập và rèn luyện của bạn với mức chuẩn học bổng.\n\nThử ngay bằng cách chọn các câu hỏi gợi ý bên dưới!",
    suggestions: [
      "Tính giúp tôi điểm trung bình nếu có 3 điểm A và 2 điểm B+",
      "Điểm rèn luyện 85 là loại gì?",
      "Học kỳ này mình được 3.2 GPA và 90 rèn luyện thì có được học bổng không?",
      "Muốn đạt học bổng loại Xuất sắc cần điều kiện gì?"
    ]
  },
  'hoc-bong': {
    response: "## Học bổng & Học phí\n\nBạn có thể hỏi các nội dung tài chính sinh viên được nêu trong Sổ tay sinh viên.\n\n**Bạn có thể hỏi về:**\n\n- **Học bổng khuyến khích học tập:** điều kiện xét, mức thưởng và cách phân loại.\n- **Học phí:** quy định chung, phương thức và thời hạn đóng học phí.\n- **Miễn giảm học phí:** các đối tượng được miễn, giảm hoặc hỗ trợ chi phí học tập.\n- **Vay vốn:** hướng dẫn làm thủ tục vay vốn sinh viên.",
    suggestions: [
      "Điều kiện xét học bổng khuyến khích học tập là gì?",
      "Học bổng loại Giỏi được bao nhiêu tiền?",
      "Đối tượng nào được miễn học phí?",
      "Sinh viên sư phạm có được hỗ trợ chi phí học tập không?"
    ]
  },
  'ren-luyen': {
    response: "## Rèn luyện & Khen thưởng\n\nBạn có thể hỏi về các quy định đánh giá rèn luyện, khen thưởng và xử lý kỷ luật.\n\n**Bạn có thể hỏi về:**\n\n- **Đánh giá rèn luyện:** các tiêu chí, thang điểm, và cách xếp loại kết quả rèn luyện.\n- **Khen thưởng:** các danh hiệu (Sinh viên 5 tốt, Sao tháng Giêng) và quy định tuyên dương.\n- **Kỷ luật:** các mức kỷ luật (khiển trách, cảnh cáo, buộc thôi học) và cách thức xóa kỷ luật.",
    suggestions: [
      "Tiêu chí đánh giá kết quả rèn luyện gồm những gì?",
      "Làm sao để đạt danh hiệu Sinh viên 5 tốt?",
      "Bị kỷ luật khiển trách thì bao lâu được xóa?",
      "Quay cóp trong phòng thi bị xử lý thế nào?"
    ]
  },
  'ktx': {
    response: "## Phòng ban & Liên hệ\n\nBạn có thể hỏi thông tin liên hệ của các đơn vị chức năng và Ký túc xá.\n\n**Bạn có thể hỏi về:**\n\n- **Phòng ban chức năng:** số điện thoại, email, địa chỉ của Phòng Đào tạo, Phòng CTCT-HSSV, Trạm y tế...\n- **Ký túc xá:** thông tin liên hệ, điều kiện đăng ký, nội quy sinh hoạt tại KTX.\n- **Đoàn - Hội:** liên hệ Đoàn Thanh niên, Hội Sinh viên trường.",
    suggestions: [
      "Cho mình xin số điện thoại Phòng Đào tạo",
      "Trạm y tế của trường nằm ở đâu?",
      "Ai được ưu tiên xếp vào Ký túc xá?",
      "Email của Phòng Công tác Chính trị là gì?"
    ]
  },
  'hanh-chinh': {
    response: "## Quy trình Hành chính\n\nBạn có thể hỏi các quy trình nộp đơn, xin giấy xác nhận hoặc làm thủ tục hành chính.\n\n**Bạn có thể hỏi về:**\n\n- **Giấy xác nhận:** xin giấy xác nhận sinh viên, vay vốn, tạm hoãn nghĩa vụ quân sự.\n- **Thủ tục học vụ:** đăng ký học lại, học vượt, chuyển ngành, xin bảng điểm.\n- **Quy trình:** các bước thực hiện và đơn vị tiếp nhận hồ sơ.\n\nNếu bạn cần mẫu đơn, hãy dùng mục **Biểu mẫu** ở thanh công cụ bên trái.",
    suggestions: [
      "Quy trình xin giấy xác nhận sinh viên như thế nào?",
      "Làm thủ tục xin bảng điểm ở đâu?",
      "Cách làm thẻ sinh viên bị mất",
      "Quy trình phúc khảo điểm thi"
    ]
  }
};

export function ChatArea({ messages, isTyping, progressMessage, onSendMessage, onSendHardcoded, onRetry, onRegenerate, theme, onToggleTheme, onNavigateTab, onClearChat }: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const hasMessages = messages.length > 0;

  const handleClearChat = () => {
    if (onClearChat && window.confirm("Bạn có chắc chắn muốn xóa toàn bộ lịch sử trò chuyện không?")) {
      onClearChat();
    }
  };

  const hour = new Date().getHours();
  let greeting = "Xin chào 👋";
  if (hour < 12) greeting = "Chào buổi sáng 🌅";
  else if (hour < 18) greeting = "Chào buổi chiều ☀️";
  else greeting = "Chào buổi tối 🌙";
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
          "Đang phân tích câu hỏi của bạn...",
          "Đang lục lọi trong Sổ tay sinh viên...",
          "Đang tìm kiếm các tài liệu liên quan...",
          "Sắp xong rồi, đang tổng hợp câu trả lời..."
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
        }, 1200) as any;
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
            <button className="theme-toggle" onClick={handleClearChat} title="Xóa lịch sử chat" style={{ marginRight: '0.5rem' }}>
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
            <div className="empty-hero" style={{ marginTop: '1rem', marginBottom: '2rem' }}>
              <img src={botAvatarImg} alt="HCMUE AI" className="bot-avatar-animated" />
              <h2 className="hero-title" style={{ fontSize: '1.75rem', marginTop: '1.5rem', color: 'var(--primary)' }}>{greeting}</h2>
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
          <button className="theme-toggle" onClick={handleClearChat} title="Xóa lịch sử chat">
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
        {messages.map((msg, index) => {
          const prevMsg = index > 0 ? messages[index - 1] : null;
          const query = msg.role === 'bot' && prevMsg?.role === 'user' ? prevMsg.content : undefined;
          return (
            <ChatMessage 
              key={msg.id} 
              message={msg} 
              thinkingMessage={thinkingMessage}
              onRetry={onRetry}
              onRegenerate={onRegenerate}
              query={query}
              onSuggestionClick={onSendMessage}
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

      <ChatInput onSend={onSendMessage} disabled={isTyping} />
    </main>
  );
}
