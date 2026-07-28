import { useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Bug, X, Send } from 'lucide-react';
import { useToast } from './Toast';
import type { Message } from '../hooks/useChat';
import { useAccessibleDialog } from '../hooks/useAccessibleDialog';

interface BugReportModalProps {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
  messages?: Message[];
}

export function BugReportModal({
  isOpen,
  setIsOpen,
  messages,
}: BugReportModalProps) {
  const [bugText, setBugText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const toast = useToast();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useAccessibleDialog<HTMLDivElement>({
    isOpen,
    onClose: () => setIsOpen(false),
    initialFocusRef: textareaRef,
  });

  const handleSubmit = async () => {
    if (!bugText.trim()) {
      toast.show('Vui lòng nhập nội dung lỗi!', 'error');
      return;
    }

    setIsSubmitting(true);

    let chatHistory = '';
    if (messages && messages.length > 0) {
      const lastMessages = messages.filter(m => !m.isStreaming).slice(-6);
      chatHistory = lastMessages
        .map(m => `[${m.role === 'user' ? 'Sinh viên' : 'Bot'}] ${m.content}`)
        .join('\n\n');
    }

    try {
      const response = await fetch(
        'https://script.google.com/macros/s/AKfycbx3XMBqzTArTmlTc2KE7_twFepC5Bg9bqjIeWDAVT3fPv8s1OAlqRvXboMdLiZW2i8w/exec',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'text/plain;charset=utf-8',
          },
          body: JSON.stringify({
            message: bugText,
            history: chatHistory
          }),
        }
      );

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  toast.show(
    'Đã gửi phản hồi thành công!',
    'success'
  );

  setBugText('');
  setIsOpen(false);
    } catch (error) {
      console.error('Feedback submit error:', error);

      toast.show(
        'Không thể gửi phản hồi.',
        'error'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

return createPortal(
isOpen ? (
<div
className="bug-modal-overlay"
onClick={() => setIsOpen(false)}
>
<div
className="bug-modal"
ref={dialogRef}
role="dialog"
aria-modal="true"
aria-labelledby="bug-modal-title"
tabIndex={-1}
onClick={(e) => e.stopPropagation()}
>
<div className="bug-header">
<h3 id="bug-modal-title">
<Bug
size={20}
style={{
marginRight: '8px',
verticalAlign: 'bottom',
}}
/>
Báo lỗi hệ thống
</h3>

        <button
          className="close-btn"
          onClick={() => setIsOpen(false)}
          aria-label="Đóng hộp thoại báo lỗi"
        >
          <X size={20} />
        </button>
      </div>

      <div className="bug-body">
        <p>
          Hệ thống có chỗ nào chưa tốt hoặc bạn gặp lỗi gì,
          hãy mô tả bên dưới để gửi phản hồi cho nhóm phát triển.
          Lịch sử chat sẽ được tự động đính kèm để hỗ trợ kiểm tra.
        </p>

        <label className="bug-field-label" htmlFor="bug-description">
          Mô tả vấn đề
        </label>
        <textarea
          id="bug-description"
          ref={textareaRef}
          value={bugText}
          onChange={(e) => setBugText(e.target.value)}
          placeholder="VD: Bot trích sai điều kiện học bổng K51."
          rows={5}
        />
      </div>

      <div className="bug-actions">
        <button
          className="btn-secondary"
          onClick={() => setIsOpen(false)}
          disabled={isSubmitting}
          style={{ opacity: isSubmitting ? 0.7 : 1, cursor: isSubmitting ? 'not-allowed' : 'pointer' }}
        >
          Hủy
        </button>

        <button
          className="btn-primary"
          onClick={handleSubmit}
          disabled={isSubmitting}
          style={{ opacity: isSubmitting ? 0.7 : 1, cursor: isSubmitting ? 'not-allowed' : 'pointer' }}
        >
          <Send size={16} className={isSubmitting ? "animate-pulse" : ""} />
          {isSubmitting ? 'Đang gửi...' : 'Gửi báo lỗi'}
        </button>
      </div>
    </div>
  </div>
) : null,
document.body

);
}
