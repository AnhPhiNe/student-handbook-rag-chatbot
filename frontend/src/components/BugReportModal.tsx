import { useState } from 'react';
import { createPortal } from 'react-dom';
import { Bug, X, Send } from 'lucide-react';
import { useToast } from './Toast';

interface BugReportModalProps {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
}

export function BugReportModal({ isOpen, setIsOpen }: BugReportModalProps) {
  const [bugText, setBugText] = useState("");
  const toast = useToast();

  const handleSubmit = () => {
    if (!bugText.trim()) {
      toast.show("Vui lòng nhập nội dung lỗi!", "error");
      return;
    }

    const email = "anhphine1011@gmail.com";
    const subject = encodeURIComponent("Báo lỗi hệ thống HCMUE Chatbot");
    const body = encodeURIComponent(
      `Chào nhóm phát triển,\n\nTôi muốn báo lỗi hoặc góp ý về hệ thống Chatbot với nội dung như sau:\n\n${bugText}\n\n---\nThời gian: ${new Date().toLocaleString('vi-VN')}`
    );

    window.open(`mailto:${email}?subject=${subject}&body=${body}`);
    setIsOpen(false);
    setBugText("");
    toast.show("Đã mở ứng dụng Email để gửi lỗi!", "success");
  };

  // Render the FAB and Modal directly into document.body to avoid stacking context issues
  return createPortal(
    <>
      <button 
        className="bug-fab-btn" 
        onClick={() => setIsOpen(true)}
        title="Báo lỗi / Góp ý"
      >
        <Bug size={24} />
      </button>

      {isOpen && (
        <div className="bug-modal-overlay" onClick={() => setIsOpen(false)}>
          <div className="bug-modal" onClick={e => e.stopPropagation()}>
            <div className="bug-header">
              <h3><Bug size={20} style={{marginRight: '8px', verticalAlign: 'bottom'}}/> Báo lỗi hệ thống</h3>
              <button className="close-btn" onClick={() => setIsOpen(false)}>
                <X size={20} />
              </button>
            </div>
            
            <div className="bug-body">
              <p>Hệ thống có chỗ nào chưa tốt hoặc bạn gặp lỗi gì, hãy mô tả bên dưới nhé. Sau khi bấm Gửi, trình duyệt sẽ tự động mở ứng dụng Email để gửi thẳng đến <strong style={{color: 'var(--primary)'}}>anhphine1011@gmail.com</strong>.</p>
              <textarea 
                value={bugText}
                onChange={e => setBugText(e.target.value)}
                placeholder="Ví dụ: Nút tính điểm học bổng không hoạt động, bot trả lời sai ở câu X..."
                rows={5}
                autoFocus
              />
            </div>

            <div className="bug-actions">
              <button className="btn-secondary" onClick={() => setIsOpen(false)}>Hủy</button>
              <button className="btn-primary" onClick={handleSubmit}>
                <Send size={16} /> Gửi báo lỗi
              </button>
            </div>
          </div>
        </div>
      )}
    </>,
    document.body
  );
}
