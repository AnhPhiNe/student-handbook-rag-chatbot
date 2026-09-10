import { createPortal } from 'react-dom';
import {
  X,
  Award,
  BookOpen,
  Calculator,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { useAccessibleDialog } from '../hooks/useAccessibleDialog';

interface ScholarshipRulesModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ScholarshipRulesModal({ isOpen, onClose }: ScholarshipRulesModalProps) {
  const dialogRef = useAccessibleDialog<HTMLDivElement>({
    isOpen,
    onClose,
  });

  if (!isOpen) return null;

  return createPortal(
    <div className="gpa-modal-overlay" onClick={onClose}>
      <div
        ref={dialogRef}
        className="gpa-modal-container scholarship-rules-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="scholarship-modal-title"
        tabIndex={-1}
      >
        {/* Header */}
        <div className="gpa-modal-header">
          <div className="gpa-modal-title-wrap">
            <div className="gpa-modal-icon-badge">
              <Award size={22} />
            </div>
            <div>
              <h2 id="scholarship-modal-title" className="gpa-modal-title">
                Quy chế xét Học bổng Khuyến khích Học tập
              </h2>
              <p className="gpa-modal-subtitle">
                Trường Đại học Sư phạm TP.HCM (HCMUE) — Tiêu chuẩn & Nguyên tắc xét cấp
              </p>
            </div>
          </div>
          <button
            type="button"
            className="gpa-modal-close-btn"
            onClick={onClose}
            aria-label="Đóng hộp thoại"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="gpa-modal-body">
          {/* Section 1: Số tín chỉ */}
          <div className="gpa-rules-section">
            <div className="gpa-rules-section-title">
              <BookOpen size={16} className="text-primary" />
              <h3>1. Quy định về số tín chỉ (Điều kiện cần)</h3>
            </div>
            <ul className="gpa-rules-list">
              <li>
                <strong>Học kỳ chính:</strong> Sinh viên phải đăng ký và hoàn thành tối thiểu{' '}
                <strong className="text-primary">15 tín chỉ</strong> trong học kỳ xét học bổng.
              </li>
              <li>
                <strong>Học kỳ tốt nghiệp:</strong> Riêng học kỳ cuối khóa (học kỳ làm khóa luận hoặc thực tập tốt nghiệp), số tín chỉ tối thiểu là{' '}
                <strong className="text-primary">6 tín chỉ</strong>.
              </li>
            </ul>

            <div className="scholarship-modal-subbox">
              <span className="subbox-title">📌 Phân loại học phần khi tính tín chỉ xét học bổng:</span>
              <div className="scholarship-rules-tags-grid">
                <div className="scholarship-rule-tag excluded">
                  <XCircle size={14} className="rule-tag-icon" />
                  <div>
                    <strong>Giáo dục Thể chất (GDTC)</strong>
                    <span>Không tính vào số TC xét học bổng</span>
                  </div>
                </div>
                <div className="scholarship-rule-tag excluded">
                  <XCircle size={14} className="rule-tag-icon" />
                  <div>
                    <strong>Giáo dục Quốc phòng - An ninh</strong>
                    <span>Không tính vào số TC xét học bổng</span>
                  </div>
                </div>
                <div className="scholarship-rule-tag excluded">
                  <XCircle size={14} className="rule-tag-icon" />
                  <div>
                    <strong>Môn học lại / Cải thiện điểm</strong>
                    <span>Chỉ tính môn đăng ký học lần đầu</span>
                  </div>
                </div>
                <div className="scholarship-rule-tag included">
                  <CheckCircle2 size={14} className="rule-tag-icon" />
                  <div>
                    <strong>Học phần chuyên môn tích lũy</strong>
                    <span>Tính vào tín chỉ & GPA xét HB</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Section 2: Tiêu chuẩn xếp loại */}
          <div className="gpa-rules-section">
            <div className="gpa-rules-section-title">
              <Award size={16} className="text-primary" />
              <h3>2. Tiêu chuẩn kết quả học tập & rèn luyện</h3>
            </div>
            <ul className="gpa-rules-list">
              <li>
                <strong>Không có điểm F / F+:</strong> Không có bất kỳ học phần nào bị điểm F hoặc F+ trong học kỳ xét (kể cả môn tự chọn).
              </li>
              <li>
                <strong>Kỷ luật:</strong> Không bị xử lý kỷ luật từ mức <strong>Khiển trách</strong> trở lên trong học kỳ xét.
              </li>
              <li>
                <strong>Thỏa mãn đồng thời cả 3 tiêu chí:</strong> Điểm xét học bổng, Điểm học tập (GPA) và Điểm rèn luyện (ĐRL).
              </li>
            </ul>

            <div className="gpa-tiers-table-wrap" style={{ marginTop: '0.65rem' }}>
              <table className="gpa-tiers-table">
                <thead>
                  <tr>
                    <th>Mức học bổng</th>
                    <th>Điểm xét</th>
                    <th>Điểm GPA</th>
                    <th>Điểm ĐRL</th>
                    <th>Hệ số thưởng</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="tier-row-excellent">
                    <td><strong>⭐ Xuất sắc</strong></td>
                    <td>&ge; 3.60</td>
                    <td>&ge; 3.60</td>
                    <td>&ge; 90 (Xuất sắc)</td>
                    <td><strong>1.50x</strong></td>
                  </tr>
                  <tr className="tier-row-good">
                    <td><strong>🏆 Giỏi</strong></td>
                    <td>&ge; 3.20</td>
                    <td>&ge; 3.20</td>
                    <td>&ge; 80 (Tốt)</td>
                    <td><strong>1.25x</strong></td>
                  </tr>
                  <tr className="tier-row-fair">
                    <td><strong>📈 Khá</strong></td>
                    <td>&ge; 2.56</td>
                    <td>&ge; 2.50</td>
                    <td>&ge; 70 (Khá)</td>
                    <td><strong>1.00x</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 3: Công thức tính */}
          <div className="gpa-rules-section">
            <div className="gpa-rules-section-title">
              <Calculator size={16} className="text-primary" />
              <h3>3. Công thức tính điểm & ước tính số tiền</h3>
            </div>
            <ul className="gpa-rules-list">
              <li>
                <strong>Điểm xét học bổng:</strong>{' '}
                <code>Điểm xét = (GPA × 0.8) + ((ĐRL / 25) × 0.2)</code>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                  (Trong đó ĐRL quy đổi = ĐRL / 25 về hệ 4, chiếm 20% tổng trọng số).
                </div>
              </li>
              <li>
                <strong>Số tiền học bổng:</strong>{' '}
                <code>Tiền HB = Đơn giá 1 TC × Số TC học kỳ × Hệ số mức thưởng</code>
              </li>
            </ul>
          </div>

          {/* Section 4: Nguyên tắc xét cấp */}
          <div className="gpa-rules-section">
            <div className="gpa-rules-section-title">
              <ShieldCheck size={16} className="text-primary" />
              <h3>4. Nguyên tắc xét cấp & cạnh tranh chỉ tiêu</h3>
            </div>
            <ul className="gpa-rules-list">
              <li>
                Học bổng được xét và trao theo từng học kỳ dựa trên ngân sách phân bổ cho từng Khoa/Ngành.
              </li>
              <li>
                Hội đồng xét cấp theo thứ tự <strong>từ Điểm xét học bổng cao nhất trở xuống</strong> cho đến khi hết quỹ học bổng.
              </li>
              <li>
                Trường hợp ở cuối danh sách có nhiều sinh viên cùng Điểm xét, thứ tự ưu tiên: <strong>Điểm GPA học tập cao hơn</strong> → <strong>Điểm rèn luyện cao hơn</strong>.
              </li>
            </ul>
          </div>

          {/* Advisory Alert */}
          <div className="gpa-rules-alert">
            <AlertTriangle size={16} className="text-warning" />
            <p>
              <strong>Lưu ý:</strong> Kết quả trên công cụ là dự báo đối chiếu theo quy chế hiện hành. Kết quả xét cấp chính thức sẽ do Nhà trường và Hội đồng Học bổng công bố sau khi đối chiếu ngân sách và danh sách sinh viên toàn ngành.
            </p>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="gpa-modal-footer">
          <button type="button" className="tool-btn primary gpa-btn-sm" onClick={onClose}>
            Đã hiểu
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
