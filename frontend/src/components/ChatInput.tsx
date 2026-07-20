import { useState, useRef, useEffect } from 'react';
import { Send } from 'lucide-react';

const PLACEHOLDERS = [
  "Hỏi chi tiết về học bổng, điểm rèn luyện...",
  "Quy định xét vớt tốt nghiệp như thế nào?",
  "Sinh viên năm 4 cần lưu ý gì về chuẩn đầu ra?",
  "Mất thẻ sinh viên thì phải làm sao?"
];

const MAX_CHARS = 1000;

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
  hasError?: boolean;
}

export function ChatInput({ onSend, disabled, hasError = false }: ChatInputProps) {
  const [input, setInput] = useState('');
  const [queuedMessage, setQueuedMessage] = useState<string | null>(null);
  const [showLimitWarning, setShowLimitWarning] = useState(false);
  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isSubmittingRef = useRef(false);
  const hasFiredRef = useRef(false);
  
  const placeholder = PLACEHOLDERS[placeholderIdx];

  const charCount = input.length;
  const isNearLimit = charCount > MAX_CHARS * 0.8;
  const isOverLimit = charCount > MAX_CHARS;

  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderIdx(prev => (prev + 1) % PLACEHOLDERS.length);
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [input]);


  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isOverLimit || isSubmittingRef.current) return;
    
    // Nếu AI đang bận: Đưa vào hàng đợi
    if (disabled) {
      if (queuedMessage) {
        setShowLimitWarning(true);
        setTimeout(() => setShowLimitWarning(false), 2500);
        return; // Chỉ cho phép hàng đợi 1 tin
      }
      setQueuedMessage(input);
      setInput('');
      return;
    }

    isSubmittingRef.current = true;
    onSend(input);
    setInput('');
    
    // Debounce chống click đúp (Double-click guard)
    setTimeout(() => {
      isSubmittingRef.current = false;
    }, 500);
  };

  const handleCancelQueue = () => {
    if (queuedMessage) {
      const restoredText = queuedMessage + (input.trim() ? '\n' + input.trim() : '');
      setInput(restoredText);
      setQueuedMessage(null);
      // Tự focus lại
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  };

  // Logic Auto-Fire (Bóp cò tự động)
  useEffect(() => {
    // Nếu AI đã gõ xong, và không có lỗi, và có tin nhắn đang chờ, và chưa bắn
    if (!disabled && queuedMessage && !hasError && !hasFiredRef.current) {
      hasFiredRef.current = true;
      const msgToFire = queuedMessage;
      setQueuedMessage(null);
      isSubmittingRef.current = true;
      
      onSend(msgToFire);
      
      setTimeout(() => {
        isSubmittingRef.current = false;
      }, 500);
    }
    
    // Reset cờ fire khi AI chuyển sang trạng thái bận
    if (disabled) {
      hasFiredRef.current = false;
    }
  }, [disabled, queuedMessage, hasError, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (disabled && queuedMessage) {
        setShowLimitWarning(true);
        setTimeout(() => setShowLimitWarning(false), 2500);
        return;
      }
      if (isSubmittingRef.current) return;
      handleSubmit();
    }
  };

  // Có thể submit (Gửi thật hoặc Đưa vào queue) nếu input có giá trị và không vượt limit
  // Và: Nút chỉ hoàn toàn bị vô hiệu hóa khi (đang disabled VÀ đã có queuedMessage)
  const isSendDisabled = !input.trim() || isOverLimit || (disabled && queuedMessage !== null);

  return (
    <div className="chat-input-wrapper">
      {queuedMessage && (
        <div className="queued-message-banner" style={showLimitWarning ? { backgroundColor: '#fee2e2', borderColor: '#ef4444' } : {}}>
          <div className="queued-message-text" title={queuedMessage} style={showLimitWarning ? { color: '#b91c1c' } : {}}>
            {showLimitWarning ? '⚠️ Hàng đợi đã đầy:' : '⏳ Đang chờ gửi:'} "{queuedMessage.length > 40 ? queuedMessage.slice(0, 40) + '...' : queuedMessage}"
          </div>
          <button 
            type="button" 
            className="queued-message-cancel" 
            onClick={handleCancelQueue}
            title="Hủy tin nhắn này và trả về ô nhập"
          >
            Hủy
          </button>
        </div>
      )}
      
      <form onSubmit={handleSubmit} className="chat-input-container" aria-busy={disabled}>
        <div className="chat-input-box">
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            placeholder={placeholder}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={false} // Unblock input
            rows={1}
          />
          
          {isNearLimit && (
            <span className={`char-counter ${isOverLimit ? 'over' : ''}`}>
              {charCount}/{MAX_CHARS}
            </span>
          )}

          <button 
            type="submit" 
            className={`send-btn ${input.trim() && !isSendDisabled ? 'has-input' : ''}`} 
            disabled={isSendDisabled}
            aria-disabled={isSendDisabled}
            aria-label={disabled ? 'Đang chờ trợ lý trả lời' : 'Gửi câu hỏi'}
            title={disabled && queuedMessage ? 'Hàng đợi đã đầy. Vui lòng đợi' : 'Gửi câu hỏi'}
            style={isSendDisabled ? { opacity: 0.5, cursor: 'not-allowed' } : {}}
          >
            <Send size={18} className={input.trim() && !isSendDisabled ? 'send-icon-active' : ''} />
          </button>
        </div>
        <p className="disclaimer">
          Trợ lý AI có thể mắc lỗi. Vui lòng kiểm tra thông tin quan trọng.
        </p>
      </form>
    </div>
  );
}
