import { useRef, useEffect, useState } from 'react';
import { GraduationCap, Gift, Home, ArrowDown, Lock, Calculator, Medal, ClipboardList, ArrowLeft } from 'lucide-react';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import type { Message } from '../hooks/useChat';
import type { Cohort } from '../utils/gradeScale';
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
  cohort: Cohort;
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

function buildQuickAccessResponse(title: string, hint: string): string {
  return `## ${title}

${hint}

**Chọn một câu bên dưới hoặc gõ câu tương tự để hỏi AI ngay:**`;
}

// Local-only responses for quick access cards. These do not call the backend.
const HARDCODED_RESPONSES: Record<string, QuickAccessResponse> = {
  'hoc-vu': {
    response: buildQuickAccessResponse(
      'Học vụ & Đào tạo',
      'Dùng mục này khi bạn đang thắc mắc về các vấn đề học tập thường gặp:\n\n- **Điểm và qua môn:** mấy điểm thì đạt, D/D+ có qua môn không, điểm chữ/hệ 4 quy đổi ra sao.\n- **Học lại/cải thiện:** bị F thì học lại thế nào, học cải thiện có được không, điểm học lại được tính ra sao.\n- **Tiến độ học tập:** khi nào bị cảnh báo học vụ, bị buộc thôi học, được học vượt hoặc cần bảo lưu/tạm nghỉ.'
    ),
    suggestions: [
      'Mấy điểm thì qua môn?',
      'Điểm B+ quy đổi sang hệ 4 là bao nhiêu?',
      'K50-K51 điểm D+ có qua môn không?',
      'Bị điểm F thì học lại như thế nào?',
      'Khi nào sinh viên bị cảnh báo học vụ?',
      'Xin bảo lưu kết quả cần điều kiện gì?'
    ]
  },
  'tinh-toan': {
    response: buildQuickAccessResponse(
      'Tính điểm & Công cụ',
      'Dùng mục này khi bạn cần hiểu cách tính điểm hoặc cách xếp loại:\n\n- **GPA và điểm trung bình:** cách tính điểm trung bình học kỳ/tích lũy, GPA bao nhiêu thì thuộc loại nào.\n- **Quy đổi điểm:** điểm chữ A, B+, C, D quy đổi sang hệ 4 hoặc thang 10 như thế nào.\n- **Công cụ liên quan:** cần tính GPA, điểm học bổng, điểm rèn luyện hoặc kiểm tra nguy cơ hạ bằng.'
    ),
    suggestions: [
      'GPA 3.2 thì xếp loại học lực gì?',
      'Điểm rèn luyện 85 là loại gì?',
      'Điểm C quy đổi sang hệ 4 là bao nhiêu?',
      'Công thức tính điểm trung bình học kỳ như thế nào?',
      'Điều kiện để xếp loại học lực Xuất sắc là gì?',
      'Tính điểm học bổng cần những thông tin nào?'
    ]
  },
  'hoc-bong': {
    response: buildQuickAccessResponse(
      'Học bổng & Học phí',
      'Dùng mục này khi bạn có thắc mắc về quyền lợi tài chính của sinh viên:\n\n- **Học bổng:** điều kiện xét học bổng, mức học bổng, trường hợp bị loại khỏi danh sách xét.\n- **Học phí:** học phí/tài chính liên hệ ở đâu, cần hỏi phòng nào khi có vấn đề đóng học phí.\n- **Miễn giảm/hỗ trợ:** ai được miễn giảm học phí, hỗ trợ chi phí học tập hoặc hỗ trợ sinh hoạt.'
    ),
    suggestions: [
      'Điều kiện xét học bổng khuyến khích học tập là gì?',
      'Sinh viên bị kỷ luật có được xét học bổng không?',
      'Mức học bổng được tính như thế nào?',
      'Đối tượng nào được miễn học phí?',
      'Sinh viên sư phạm có được hỗ trợ chi phí sinh hoạt không?',
      'Học phí hoặc tài chính thì liên hệ phòng nào?'
    ]
  },
  'ren-luyen': {
    response: buildQuickAccessResponse(
      'Rèn luyện & Khen thưởng',
      'Dùng mục này khi bạn muốn hỏi về quá trình rèn luyện và xử lý vi phạm:\n\n- **Điểm rèn luyện:** bao nhiêu điểm là tốt/xuất sắc, tiêu chí chấm điểm gồm những gì.\n- **Khen thưởng:** điều kiện được khen thưởng, danh hiệu hoặc các hình thức ghi nhận sinh viên.\n- **Kỷ luật/vi phạm:** vi phạm quy chế thi bị xử lý ra sao, khiển trách/cảnh cáo bao lâu được xóa.'
    ),
    suggestions: [
      'Điểm rèn luyện bao nhiêu là tốt/xuất sắc?',
      'Tiêu chí đánh giá kết quả rèn luyện gồm những gì?',
      'Sinh viên vi phạm quy chế thi bị xử lý như thế nào?',
      'Bị kỷ luật khiển trách thì bao lâu được xóa?',
      'Quay cóp trong phòng thi bị xử lý thế nào?',
      'Điều kiện để được khen thưởng là gì?'
    ]
  },
  'ktx': {
    response: buildQuickAccessResponse(
      'Phòng ban & Liên hệ',
      'Dùng mục này khi bạn không biết nên liên hệ đơn vị nào trong trường:\n\n- **Học vụ/đào tạo:** hỏi về chương trình đào tạo, học phần, bảng điểm, tốt nghiệp hoặc đăng ký học.\n- **Công tác sinh viên:** hỏi học bổng, miễn giảm học phí, giấy xác nhận, tạm nghỉ, học lại hoặc hỗ trợ sinh viên.\n- **Dịch vụ và đơn vị khác:** hỏi học phí/tài chính, ký túc xá, trạm y tế, thư viện, khoa hoặc thông tin email/số điện thoại.'
    ),
    suggestions: [
      'Vấn đề tài khoản sinh viên thì liên hệ ở đâu?',
      'Cho mình xin số điện thoại Phòng Đào tạo',
      'Email Phòng CTCT&HSSV là gì?',
      'Học phí và tài chính thì liên hệ phòng nào?',
      'Ai được ưu tiên xếp vào Ký túc xá?',
      'Trạm y tế của trường nằm ở đâu?'
    ]
  },
  'hanh-chinh': {
    response: buildQuickAccessResponse(
      'Quy trình Hành chính',
      'Dùng mục này khi bạn cần biết thủ tục phải làm, giấy tờ cần chuẩn bị hoặc nơi nộp hồ sơ:\n\n- **Giấy tờ sinh viên:** xin giấy xác nhận sinh viên, bảng điểm, làm lại thẻ sinh viên hoặc giấy tờ liên quan.\n- **Thủ tục học vụ:** phúc khảo điểm thi, tạm nghỉ học, quay lại học, học lại hoặc học cải thiện.\n- **Biểu mẫu/hồ sơ:** cần mẫu đơn nào, nộp ở đâu, quy trình gồm những bước nào.'
    ),
    suggestions: [
      'Quy trình xin giấy xác nhận sinh viên như thế nào?',
      'Muốn phúc khảo điểm thi thì làm thế nào?',
      'Làm thủ tục xin bảng điểm ở đâu?',
      'Cách làm thẻ sinh viên bị mất',
      'Muốn tạm nghỉ học thì cần làm gì?',
      'Cần mẫu đơn thì tìm ở đâu trong web?'
    ]
  }
};

export function ChatArea({ messages, isTyping, progressMessage, onSendMessage, onSendHardcoded, onRetry, onRegenerate, onNavigateTab, onClearChat }: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const hasMessages = messages.length > 0;

  const hour = new Date().getHours();
  let greeting: string;
  if (hour < 12) greeting = "Chào buổi sáng 🌅";
  else if (hour < 18) greeting = "Chào buổi chiều ☀️";
  else greeting = "Chào buổi tối 🌙";

  const [showScrollButton, setShowScrollButton] = useState(false);
  const [thinkingMessage, setThinkingMessage] = useState("");
  const coldStartTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  
  const [loadingSeconds, setLoadingSeconds] = useState(0);
  const loadingTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const displayThinkingMessage = thinkingMessage ? `${thinkingMessage} (${loadingSeconds}s)` : "";

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

  useEffect(() => {
    if (isTyping) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoadingSeconds(0);
      loadingTimer.current = setInterval(() => {
        setLoadingSeconds(prev => prev + 1);
      }, 1000) as ReturnType<typeof setInterval>;
    } else {
      setLoadingSeconds(0);
      clearInterval(loadingTimer.current);
    }
    return () => clearInterval(loadingTimer.current);
  }, [isTyping]);

  const handleScroll = () => {
    if (!chatContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
    const isScrolledUp = scrollHeight - scrollTop - clientHeight > 100;
    setShowScrollButton(isScrolledUp);
  };

  const handleQuickAccess = (id: string) => {
    if (id === 'bieu-mau') {
      if (onNavigateTab) onNavigateTab('bieu-mau');
      return;
    }
    
    const titles: Record<string, string> = {
      'hoc-vu': 'Học vụ & Đào tạo',
      'hoc-bong': 'Học bổng & Học phí',
      'ktx': 'Phòng ban & Ký túc xá',
      'hanh-chinh': 'Quy trình Hành chính',
      'tinh-toan': 'Tính điểm & Đánh giá',
      'ren-luyen': 'Rèn luyện & Khen thưởng'
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

  const handleBackToTopics = () => {
    if (messages.length <= 2) {
      if (onClearChat) onClearChat();
    } else {
      if (window.confirm("Quay lại màn hình chính sẽ làm mới đoạn chat hiện tại. Bạn có chắc chắn không?")) {
        if (onClearChat) onClearChat();
      }
    }
  };

  // Progressive thinking indicator based on real backend progress or simulated fallback
  useEffect(() => {
    if (isTyping) {
      if (progressMessage) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
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
        }, 1200) as ReturnType<typeof setInterval>;
      }
    } else {
      setThinkingMessage("");
      clearInterval(coldStartTimer.current);
    }
    return () => clearInterval(coldStartTimer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
              <p>Trợ lý AI đang tạm nghỉ để nâng cấp dữ liệu. Trong lúc chờ đợi, bạn vẫn có thể dùng thả ga các công cụ <strong>Tính GPA, Mục tiêu GPA, Mục tiêu môn học, Tính điểm học bổng, Ước tính học phí, Kiểm tra hạ bằng, Tra cứu biểu mẫu</strong> và xem <strong>Hướng dẫn</strong> ở menu bên cạnh nhé!</p>
            </div>
          </div>
        )}

        <header className="chat-header">
          <div style={{flex: 1}}></div>
        </header>

        {/* Scrollable content area that fills available space */}
        <div className="empty-state">
          <div className="empty-state-content">
            {/* Hero - compact */}
            <div className="empty-hero" style={{ marginTop: '0.5rem', marginBottom: '1rem' }}>
              <img src={botAvatarImg} alt="HCMUE AI" className="bot-avatar-animated" style={{ width: '80px', height: '80px', objectFit: 'contain', flexShrink: 0, borderRadius: '50%' }} />
              <h2 className="hero-title" style={{ fontSize: '1.5rem', marginTop: '1rem', color: 'var(--primary)' }}>{greeting}</h2>
              <p className="hero-subtitle" style={{ marginTop: '0.5rem', fontSize: '1.125rem' }}>Mình là trợ lý AI của Đại học Sư phạm TP.HCM</p>
              <p className="hero-desc">Bạn cần tìm gì trong sổ tay sinh viên hôm nay?</p>
              <p className="hero-tip">Bấm một chủ đề bên dưới để xem các câu hỏi mẫu có thể hỏi ngay.</p>
            </div>

            {/* Action Cards Grid */}
            <div className="chat-action-cards-grid">
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
          {displayThinkingMessage && (
            <div className="cold-start-banner" style={{ margin: '0 auto 0.75rem', maxWidth: '780px' }}>
              <div className="cold-start-spinner" />
              <span>{displayThinkingMessage}</span>
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
            <p>Trợ lý AI đang tạm nghỉ để nâng cấp dữ liệu. Trong lúc chờ đợi, bạn vẫn có thể dùng thả ga các công cụ <strong>Tính GPA, Mục tiêu GPA, Mục tiêu môn học, Tính điểm học bổng, Ước tính học phí, Kiểm tra hạ bằng, Tra cứu biểu mẫu</strong> và xem <strong>Hướng dẫn</strong> ở menu bên cạnh nhé!</p>
          </div>
        </div>
      )}

      <header className="chat-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button 
            className="back-btn" 
            onClick={handleBackToTopics} 
            title="Quay lại danh sách thẻ gợi ý"
          >
            <ArrowLeft size={16} />
            <span>Quay lại</span>
          </button>
          <h2 className="chat-title" style={{ margin: 0 }}>Hội thoại với HCMUE AI</h2>
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
              thinkingMessage={displayThinkingMessage}
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
