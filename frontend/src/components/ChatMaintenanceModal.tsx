import { X, Wrench, ArrowRight, CheckCircle2, LayoutGrid } from 'lucide-react';
import { useAccessibleDialog } from '../hooks/useAccessibleDialog';
import { OwlMascot } from './OwlMascot';

interface ChatMaintenanceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onExploreTools?: () => void;
}

export function ChatMaintenanceModal({
  isOpen,
  onClose,
  onExploreTools,
}: ChatMaintenanceModalProps) {
  const dialogRef = useAccessibleDialog<HTMLDivElement>({
    isOpen,
    onClose,
  });

  if (!isOpen) return null;

  return (
    <div className="maintenance-modal-overlay" onClick={onClose}>
      <div
        ref={dialogRef}
        className="maintenance-modal-content"
        role="dialog"
        aria-modal="true"
        aria-labelledby="maintenance-modal-title"
        aria-describedby="maintenance-modal-desc"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          className="maintenance-modal-close"
          onClick={onClose}
          aria-label="Đóng cửa sổ"
        >
          <X size={18} />
        </button>

        <div className="maintenance-modal-header">
          <div className="maintenance-mascot-wrap">
            <OwlMascot size={76} state="reading" showFrame={false} />
            <span className="maintenance-pill-badge">
              <Wrench size={13} aria-hidden="true" />
              Đang bảo trì & nâng cấp
            </span>
          </div>

          <h2 id="maintenance-modal-title">Chức năng Chat AI đang tạm bảo trì</h2>
          <p id="maintenance-modal-desc">
            Hệ thống trợ lý AI đang được nâng cấp mô hình và cập nhật dữ liệu Sổ tay sinh viên mới nhất. Chức năng sẽ sớm hoạt động trở lại, bạn vui lòng quay lại sau nhé!
          </p>
        </div>

        <div className="maintenance-modal-body">
          <div className="maintenance-tools-box">
            <div className="maintenance-tools-title">
              Trong lúc chờ đợi, bạn vẫn có thể sử dụng đầy đủ:
            </div>
            <ul className="maintenance-tools-list">
              <li>
                <CheckCircle2 size={16} className="tool-check-icon" aria-hidden="true" />
                <span><strong>Tính GPA</strong> học kỳ & quy đổi điểm hệ 10 / hệ 4</span>
              </li>
              <li>
                <CheckCircle2 size={16} className="tool-check-icon" aria-hidden="true" />
                <span><strong>Ước tính học phí</strong> & xét điều kiện <strong>Học bổng KKHT</strong></span>
              </li>
              <li>
                <CheckCircle2 size={16} className="tool-check-icon" aria-hidden="true" />
                <span><strong>Kiểm tra hạ bằng</strong> tốt nghiệp (tỷ lệ tín chỉ điểm F)</span>
              </li>
              <li>
                <CheckCircle2 size={16} className="tool-check-icon" aria-hidden="true" />
                <span><strong>Mục tiêu môn học</strong> & <strong>Mục tiêu GPA</strong> cần đạt</span>
              </li>
              <li>
                <CheckCircle2 size={16} className="tool-check-icon" aria-hidden="true" />
                <span>Tra cứu <strong>Biểu mẫu sinh viên</strong> & <strong>Phương pháp học tập</strong></span>
              </li>
            </ul>
          </div>
        </div>

        <div className="maintenance-modal-footer">
          {onExploreTools && (
            <button
              type="button"
              className="maintenance-btn-primary"
              onClick={() => {
                onExploreTools();
                onClose();
              }}
            >
              <LayoutGrid size={18} aria-hidden="true" />
              <span>Khám phá các công cụ sinh viên</span>
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          )}
          <button
            type="button"
            className="maintenance-btn-secondary"
            onClick={onClose}
          >
            Đã hiểu
          </button>
        </div>
      </div>
    </div>
  );
}
