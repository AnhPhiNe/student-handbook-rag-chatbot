import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Copy, ChevronDown, ChevronRight, Check, ThumbsUp, ThumbsDown, RotateCcw, Share2, FileText } from 'lucide-react';
import type { Message } from '../hooks/useChat';
import { useToast } from './Toast';
import logoHcmue from '../assets/logo_hcmue.png';

interface ChatMessageProps {
  message: Message;
  thinkingMessage?: string;
  onRegenerate?: () => void;
  onRetry?: () => void;
}


function getRelativeTime(timestamp: string): string {
  // Simple implementation since timestamp is just HH:MM
  return timestamp;
}

export function ChatMessage({ message, thinkingMessage = "", onRegenerate, onRetry }: ChatMessageProps) {
  const [showSources, setShowSources] = useState(false);
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<'like'|'dislike'|null>(null);
  const toast = useToast();

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    toast.show("Đã sao chép nội dung!", "success");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleShare = () => {
    const text = `📚 HCMUE AI Assistant\n\n💬 ${message.content}\n\n🔗 https://student-handbook-rag-chatbot.vercel.app`;
    navigator.clipboard.writeText(text);
    toast.show("Đã sao chép nội dung để chia sẻ!", "success");
  };

  const handleFeedback = (type: 'like' | 'dislike') => {
    setFeedback(type);
    toast.show("Cảm ơn bạn đã đánh giá!", "success");
  };

  if (message.role === 'user') {
    return (
      <div className="message-wrapper user">
        <div className="avatar user">{message.content[0]?.toUpperCase() || 'U'}</div>
        <div className="message-content">
          <div className="message-header">
            <span className="message-time">{getRelativeTime(message.timestamp)}</span>
          </div>
          <div className="message-bubble">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  const isErrorMsg = !message.isStreaming && message.content.includes("Xin lỗi, đã có lỗi");

  return (
    <div className="message-wrapper bot">
      <img src={logoHcmue} alt="HCMUE AI" className="avatar bot" />
      <div className="message-content">
        <div className={`${thinkingMessage && message.isStreaming && !message.content ? 'cold-start-bubble' : 'message-bubble'} ${message.isStreaming && !message.content && !thinkingMessage ? 'typing-indicator' : ''}`}>
          {message.isStreaming && !message.content ? (
            thinkingMessage ? (
              <div className="cold-start-content">
                <div className="cold-start-spinner" />
                <span>{thinkingMessage}</span>
              </div>
            ) : (
              <>
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
              </>
            )
          ) : (
            <ReactMarkdown>{message.content}</ReactMarkdown>
          )}
          
          {message.isStreaming && message.content && (
            <span style={{ display: 'inline-block', width: '8px', height: '16px', background: 'var(--accent-color)', animation: 'blink 1s step-end infinite', marginLeft: '4px', verticalAlign: 'middle' }}></span>
          )}

          {!message.isStreaming && message.citations && message.citations.length > 0 && (
            <div className="citation-container">
              <div 
                className="citation-header" 
                onClick={() => setShowSources(!showSources)}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)' }}
              >
                <span>Nguồn tham khảo ({message.citations.length})</span>
                {showSources ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </div>
              
              {showSources && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
                  {message.citations.map((cit, idx) => (
                    <div key={idx} className="citation-card">
                      <div className="citation-card-icon"><FileText size={16} /></div>
                      <div className="citation-card-body">
                        <span className="citation-title">{cit.title || cit.chunk_id}</span>
                        <span className="citation-pages">Trang {cit.source_pages?.length ? cit.source_pages.join(', ') : 'N/A'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {isErrorMsg && (
          <button className="retry-btn" onClick={() => onRetry?.()}>
            <RotateCcw size={14} /> Thử lại
          </button>
        )}



        {!message.isStreaming && !isErrorMsg && (
          <div className="message-metadata">
            <div className="meta-actions">
              <button className="action-btn" title="Chia sẻ" onClick={handleShare}>
                <Share2 size={16} />
              </button>
              <button className={`action-btn ${feedback === 'like' ? 'active' : ''}`} title="Hữu ích" onClick={() => handleFeedback('like')}>
                <ThumbsUp size={16} />
              </button>
              <button className={`action-btn ${feedback === 'dislike' ? 'active' : ''}`} title="Chưa chính xác" onClick={() => handleFeedback('dislike')}>
                <ThumbsDown size={16} />
              </button>
              <button className="action-btn" title="Copy" onClick={handleCopy}>
                {copied ? <Check size={16} style={{color: 'var(--success)'}}/> : <Copy size={16} />}
              </button>
              <button className="action-btn" title="Tạo lại" onClick={() => onRegenerate?.()}>
                <RotateCcw size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
