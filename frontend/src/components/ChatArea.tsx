import { useRef, useEffect, useState } from 'react';
import { GraduationCap, Gift, ArrowDown, Lock, Medal, ArrowLeft, BookOpen, Phone, Shield } from 'lucide-react';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import type { Message } from '../hooks/useChat';
import type { Cohort } from '../utils/gradeScale';
const botAvatarImg = '/bot_avatar.png';

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
  { id: 'hoc-vu', label: 'Học tập & Điểm số', icon: BookOpen, color: '#3b82f6', desc: 'Đăng ký môn, tính GPA, học cải thiện...' },
  { id: 'bao-luu', label: 'Bảo lưu & Tốt nghiệp', icon: GraduationCap, color: '#0ea5e9', desc: 'Tạm nghỉ, thôi học, xét tốt nghiệp...' },
  { id: 'hoc-bong', label: 'Học bổng & Học phí', icon: Gift, color: '#8b5cf6', desc: 'Điều kiện xét, mức thưởng, miễn giảm...' },
  { id: 'ren-luyen', label: 'Rèn luyện & Khen thưởng', icon: Medal, color: '#ef4444', desc: 'Điểm rèn luyện, kỷ luật, danh hiệu...' },
  { id: 'lien-he', label: 'Phòng ban & Liên hệ', icon: Phone, color: '#f59e0b', desc: 'SĐT, email, KTX, hỗ trợ sinh viên...' },
  { id: 'noi-quy', label: 'Nội quy & Văn hóa', icon: Shield, color: '#0ea5e9', desc: 'Trang phục, thẻ SV, văn hóa ứng xử...' }
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
      'Học tập & Điểm số',
      'Dùng mục này khi bạn thắc mắc về quá trình học, lịch học, điểm số và thi cử:\n\n- **Học vụ:** quy định đăng ký tín chỉ, hủy môn, học lại, học cải thiện.\n- **Điểm số & Thi cử:** cách tính điểm trung bình (GPA), quy đổi điểm chữ, vắng thi, gian lận thi cử.\n- **Học vụ khác:** điều kiện chuyển ngành, chuyển trường, cảnh báo học vụ.'
    ),
    suggestions: [
      'Học cải thiện tính điểm thế nào?',
      'Thi rớt 3 môn có bị đuổi học?',
      'Đăng ký học vượt tín chỉ ra sao?',
      'Hoãn thi cuối kỳ cần điều kiện gì?'
    ]
  },
  'bao-luu': {
    response: buildQuickAccessResponse(
      'Bảo lưu & Tốt nghiệp',
      'Dùng mục này khi bạn quan tâm đến việc tạm dừng học hoặc thủ tục ra trường:\n\n- **Bảo lưu/Tạm nghỉ:** điều kiện bảo lưu kết quả, thời gian tối đa được bảo lưu, thủ tục xin học lại.\n- **Thôi học:** quy định buộc thôi học, tự nguyện xin thôi học.\n- **Tốt nghiệp:** điều kiện để được xét tốt nghiệp, quy trình đăng ký xét và nhận bằng.'
    ),
    suggestions: [
      'Năm nhất có được xin bảo lưu?',
      'Thời gian bảo lưu tối đa bao lâu?',
      'Bị cảnh báo học vụ mấy lần thì đuổi?',
      'Nợ môn Thể chất có xét tốt nghiệp?'
    ]
  },
  'hoc-bong': {
    response: buildQuickAccessResponse(
      'Học bổng & Học phí',
      'Dùng mục này khi bạn có thắc mắc về quyền lợi tài chính của sinh viên:\n\n- **Học bổng:** điều kiện xét học bổng, mức học bổng, trường hợp bị loại khỏi danh sách xét.\n- **Học phí:** quy định nộp học phí, xử lý khi trễ hạn nộp, các kênh thanh toán học phí hợp lệ.\n- **Miễn giảm/hỗ trợ:** ai được miễn giảm học phí, hỗ trợ chi phí học tập hoặc hỗ trợ sinh hoạt.'
    ),
    suggestions: [
      'Điều kiện để được xét học bổng KKHT là gì?',
      'Đóng học phí trễ bị cấm thi không?',
      'Mức học bổng Xuất sắc là bao nhiêu?',
      'Ai thuộc diện miễn giảm học phí?'
    ]
  },
  'ren-luyen': {
    response: buildQuickAccessResponse(
      'Rèn luyện & Khen thưởng',
      'Dùng mục này khi bạn muốn hỏi về quá trình rèn luyện và xử lý vi phạm:\n\n- **Điểm rèn luyện:** bao nhiêu điểm là tốt/xuất sắc, tiêu chí chấm điểm gồm những gì.\n- **Khen thưởng:** điều kiện được khen thưởng, danh hiệu hoặc các hình thức ghi nhận sinh viên.\n- **Kỷ luật/vi phạm:** vi phạm quy chế thi bị xử lý ra sao, khiển trách/cảnh cáo bao lâu được xóa.'
    ),
    suggestions: [
      'Điểm rèn luyện dưới 50 bị cảnh báo?',
      'Tiêu chí chấm điểm rèn luyện là gì?',
      'Nhờ người thi hộ bị xử lý ra sao?',
      'Kỷ luật Cảnh cáo bao lâu được xóa?'
    ]
  },
  'lien-he': {
    response: buildQuickAccessResponse(
      'Phòng ban & Liên hệ',
      'Dùng mục này khi bạn không biết nên liên hệ đơn vị nào trong trường:\n\n- **Phòng Đào tạo / CTSV:** hỏi về lịch học, bảng điểm, học bổng, giấy xác nhận, tạm nghỉ.\n- **Ký túc xá & Trạm y tế:** quy định, thủ tục đăng ký, giờ giấc hoạt động.\n- **Liên hệ khác:** số điện thoại, email, địa chỉ các Phòng, Khoa hoặc hỗ trợ tài khoản sinh viên.'
    ),
    suggestions: [
      'Số điện thoại của Phòng Đào tạo?',
      'Lỗi tài khoản SV liên hệ phòng nào?',
      'Phòng nào hỗ trợ in bảng điểm?',
      'Phòng CTCT-HSSV nằm ở đâu?'
    ]
  },
  'noi-quy': {
    response: buildQuickAccessResponse(
      'Nội quy & Văn hóa',
      'Dùng mục này khi bạn muốn hỏi về các quy định nội quy, văn hóa học đường của trường:\n\n- **Trang phục & Tác phong:** quy định về trang phục, đeo thẻ sinh viên khi đến lớp.\n- **Hành vi cấm:** những việc sinh viên không được làm trong khuôn viên trường (hút thuốc, uống rượu bia, gian lận...).\n- **Văn hóa ứng xử:** quy tắc giao tiếp với giảng viên, cán bộ và bạn bè.'
    ),
    suggestions: [
      'Không đeo thẻ SV có bị cấm thi?',
      'Sinh viên không được làm những gì?',
      'Hút thuốc trong trường phạt ra sao?',
      'Mặc quần đùi đến lớp được không?'
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
  
  const displayThinkingMessage = thinkingMessage;

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

  const handleQuickAccess = (id: string) => {
    if (id === 'bieu-mau') {
      if (onNavigateTab) onNavigateTab('bieu-mau');
      return;
    }
    
    const card = ACTION_CARDS.find(c => c.id === id);
    const title = card ? card.label : id;
    
    const userPrompt = `Cho tôi biết thông tin về ${title}`;
    
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
