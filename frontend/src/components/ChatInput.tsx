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

  useEffect(() => {
    if (!disabled && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [disabled]);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || disabled || isOverLimit) return;
    onSend(input);
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="chat-input-wrapper">
      <form onSubmit={handleSubmit} className="chat-input-container">
        <div className="chat-input-box">
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            placeholder={PLACEHOLDERS[placeholderIdx]}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            rows={1}
          />
          
          {isNearLimit && (
            <span className={`char-counter ${isOverLimit ? 'over' : ''}`}>
              {charCount}/{MAX_CHARS}
            </span>
          )}

          <button 
            type="submit" 
            className="send-btn" 
            disabled={!input.trim() || disabled || isOverLimit}
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
