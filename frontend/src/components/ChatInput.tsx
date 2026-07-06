import { useState, useRef, useEffect } from 'react';
import { Send } from 'lucide-react';

const MAX_CHARS = 500;
const PLACEHOLDERS = [
  "Nhập câu hỏi của bạn...",
  "Nhập câu hỏi về điều kiện bảo lưu...",
  "Hỗ trợ cả tiếng Việt không dấu ✨",
  "Nhập câu hỏi về bảng điểm hoặc phòng ban...",
];

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [input, setInput] = useState('');
  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isSubmittingRef = useRef(false);
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
    if (!input.trim() || disabled || isOverLimit || isSubmittingRef.current) return;
    
    isSubmittingRef.current = true;
    onSend(input);
    setInput('');
    
    // Debounce chống click đúp (Double-click guard)
    setTimeout(() => {
      isSubmittingRef.current = false;
    }, 500);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (disabled || isSubmittingRef.current) return;
      handleSubmit();
    }
  };

  return (
    <div className="chat-input-wrapper">
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
            className={`send-btn ${input.trim() ? 'has-input' : ''}`} 
            disabled={!input.trim() || disabled || isOverLimit}
            aria-disabled={disabled}
            aria-label={disabled ? 'Đang chờ trợ lý trả lời' : 'Gửi câu hỏi'}
            title={disabled ? 'Vui lòng chờ trợ lý trả lời xong' : 'Gửi câu hỏi'}
            style={disabled ? { opacity: 0.5, cursor: 'not-allowed' } : {}}
          >
            <Send size={18} className={input.trim() ? 'send-icon-active' : ''} />
          </button>
        </div>
        <p className="disclaimer">
          Trợ lý AI có thể mắc lỗi. Vui lòng kiểm tra thông tin quan trọng.
        </p>
      </form>
    </div>
  );
}
