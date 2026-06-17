import { useState } from 'react';
import { createPortal } from 'react-dom';
import { Bug, X, Send } from 'lucide-react';
import { useToast } from './Toast';

interface BugReportModalProps {
isOpen: boolean;
setIsOpen: (isOpen: boolean) => void;
}

export function BugReportModal({
isOpen,
setIsOpen,
}: BugReportModalProps) {
const [bugText, setBugText] = useState('');
const toast = useToast();

const handleSubmit = async () => {
if (!bugText.trim()) {
toast.show('Vui lòng nhập nội dung lỗi!', 'error');
return;
}

try {
  await fetch(
    'https://script.google.com/macros/s/AKfycbx3XMBqzTArTmlTc2KE7_twFepC5Bg9bqjIeWDAVT3fPv8s1OAlqRvXboMdLiZW2i8w/exec',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'text/plain',
      },
      body: JSON.stringify({
        message: bugText,
      }),
    }
  );

  toast.show(
    'Đã gửi phản hồi thành công!',
    'success'
  );

  setBugText('');
  setIsOpen(false);
} catch (error) {
  console.error(error);

  toast.show(
    'Không thể gửi phản hồi.',
    'error'
  );
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
onClick={(e) => e.stopPropagation()}
>
<div className="bug-header">
<h3>
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
        >
          <X size={20} />
        </button>
      </div>

      <div className="bug-body">
        <p>
          Hệ thống có chỗ nào chưa tốt hoặc bạn gặp lỗi gì,
          hãy mô tả bên dưới để gửi phản hồi cho nhóm phát triển.
        </p>

        <textarea
          value={bugText}
          onChange={(e) => setBugText(e.target.value)}
          placeholder="Ví dụ: Nút tính điểm học bổng không hoạt động, bot trả lời sai ở câu hỏi nào đó..."
          rows={5}
          autoFocus
        />
      </div>

      <div className="bug-actions">
        <button
          className="btn-secondary"
          onClick={() => setIsOpen(false)}
        >
          Hủy
        </button>

        <button
          className="btn-primary"
          onClick={handleSubmit}
        >
          <Send size={16} />
          Gửi báo lỗi
        </button>
      </div>
    </div>
  </div>
) : null,
document.body

);
}
