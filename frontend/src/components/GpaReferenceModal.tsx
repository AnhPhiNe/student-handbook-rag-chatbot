import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, GraduationCap, Info, Award, AlertTriangle, BookOpen } from 'lucide-react';
import type { Cohort } from '../utils/gradeScale';
import { getGradeScales } from '../utils/gradeScale';
import { useAccessibleDialog } from '../hooks/useAccessibleDialog';

interface GpaReferenceModalProps {
  isOpen: boolean;
  onClose: () => void;
  cohort: Cohort;
  initialTab?: 'scale' | 'rules';
}

export function GpaReferenceModal({
  isOpen,
  onClose,
  cohort,
  initialTab = 'scale',
}: GpaReferenceModalProps) {
  const [activeTab, setActiveTab] = useState<'scale' | 'rules'>(initialTab);

  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab);
    }
  }, [isOpen, initialTab]);

  const dialogRef = useAccessibleDialog<HTMLDivElement>({
    isOpen,
    onClose,
  });

  if (!isOpen) return null;

  const gradeScales = getGradeScales(cohort);
  const showCourseGroup = gradeScales.length > 1;

  return createPortal(
    <div className="gpa-modal-overlay" onClick={onClose}>
      <div
        ref={dialogRef}
        className="gpa-modal-container"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="gpa-modal-title"
        tabIndex={-1}
      >
        {/* Modal Header */}
        <div className="gpa-modal-header">
          <div className="gpa-modal-title-wrap">
            <div className="gpa-modal-icon-badge">
              <GraduationCap size={20} />
            </div>
            <div>
              <h2 id="gpa-modal-title" className="gpa-modal-title">
                Tra cứu Quy chế & Bảng điểm ({cohort})
              </h2>
              <p className="gpa-modal-subtitle">
                Quy định thang điểm và điều kiện học vụ chính thức của trường.
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

        {/* Modal Tabs */}
        <div className="gpa-modal-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'scale'}
            className={`gpa-modal-tab ${activeTab === 'scale' ? 'active' : ''}`}
            onClick={() => setActiveTab('scale')}
          >
            <GraduationCap size={16} />
            <span>Bảng quy đổi điểm ({cohort})</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'rules'}
            className={`gpa-modal-tab ${activeTab === 'rules' ? 'active' : ''}`}
            onClick={() => setActiveTab('rules')}
          >
            <Info size={16} />
            <span>Quy chế & Lưu ý học vụ</span>
          </button>
        </div>

        {/* Modal Content */}
        <div className="gpa-modal-body">
          {activeTab === 'scale' ? (
            <div className="gpa-modal-scale-panel animate-fade-in">
              <div className="gpa-scale-blocks">
                {gradeScales.map((scale) => {
                  const passedRows = scale.rows.filter((row) => row.status !== 'Không đạt');
                  const failedRows = scale.rows.filter((row) => row.status === 'Không đạt');

                  return (
                    <div key={scale.id} className="gpa-scale-block">
                      {showCourseGroup && (
                        <div className="gpa-scale-block-header">
                          <h4>{scale.label}</h4>
                          <span>{scale.applicability}</span>
                        </div>
                      )}
                      <div className="gpa-scale-rows-container">
                        {/* Row 1: Passed Grades */}
                        <div className="gpa-scale-row-group">
                          <div className="gpa-scale-row-label passed">
                            <span>✓ Điểm đạt học phần:</span>
                          </div>
                          <div className="gpa-scale-full-grid">
                            {passedRows.map((row) => (
                              <div
                                key={`${scale.id}-${row.letter}`}
                                className="gpa-scale-chip passed"
                              >
                                <div className="gpa-chip-top">
                                  <span className="gpa-chip-letter">{row.letter}</span>
                                  <span className="gpa-chip-score4">{row.score4.toFixed(1)}</span>
                                </div>
                                <div className="gpa-chip-range">
                                  {row.min10} - {row.max10}
                                </div>
                                <span className="gpa-chip-status success">{row.status}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Row 2: Failed Grades (Red) */}
                        {failedRows.length > 0 && (
                          <div className="gpa-scale-row-group failed-group">
                            <div className="gpa-scale-row-label failed">
                              <span>✕ Điểm chưa đạt (Không đạt):</span>
                            </div>
                            <div className="gpa-scale-full-grid failed-grid">
                              {failedRows.map((row) => (
                                <div
                                  key={`${scale.id}-${row.letter}`}
                                  className="gpa-scale-chip failed"
                                >
                                  <div className="gpa-chip-top">
                                    <span className="gpa-chip-letter">{row.letter}</span>
                                    <span className="gpa-chip-score4">{row.score4.toFixed(1)}</span>
                                  </div>
                                  <div className="gpa-chip-range">
                                    {row.min10} - {row.max10}
                                  </div>
                                  <span className="gpa-chip-status danger">{row.status}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="gpa-modal-rules-panel animate-fade-in">
              {/* Section 1: Important Notes */}
              <div className="gpa-rules-section">
                <div className="gpa-rules-section-title">
                  <BookOpen size={16} />
                  <h3>Lưu ý quan trọng khi tính GPA</h3>
                </div>
                <ul className="gpa-rules-list">
                  <li>
                    <strong>Giáo dục thể chất (GDTC)</strong> và{' '}
                    <strong>Giáo dục quốc phòng (GDQP)</strong> là các học phần điều kiện,{' '}
                    <u>không tính</u> vào điểm GPA trung bình chung tích lũy.
                  </li>
                  <li>
                    Các môn <strong>học lại / học cải thiện</strong> vẫn được tính vào điểm GPA học kỳ, nhưng{' '}
                    <strong>không được tính số tín chỉ đó khi xét học bổng khuyến khích học tập</strong>.
                  </li>
                  <li>
                    Điểm trung bình hệ 4 được làm tròn theo quy định chuẩn đến{' '}
                    <strong>2 chữ số thập phân</strong>.
                  </li>
                </ul>
              </div>

              {/* Section 2: Scholarship & Academic Standing Tiers */}
              <div className="gpa-rules-section">
                <div className="gpa-rules-section-title">
                  <Award size={16} />
                  <h3>Tiêu chuẩn Xếp loại học lực & Xét Học bổng</h3>
                </div>
                <div className="gpa-tiers-table-wrap">
                  <table className="gpa-tiers-table">
                    <thead>
                      <tr>
                        <th>Xếp loại</th>
                        <th>Điểm GPA (Hệ 4)</th>
                        <th>Điều kiện xét học bổng (ĐRL)</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="tier-row-excellent">
                        <td>
                          <strong>⭐ Xuất sắc</strong>
                        </td>
                        <td>3.60 - 4.00</td>
                        <td>ĐRL &ge; 90 (Tích lũy đủ số TC theo quy định)</td>
                      </tr>
                      <tr className="tier-row-good">
                        <td>
                          <strong>🏆 Giỏi</strong>
                        </td>
                        <td>3.20 - 3.59</td>
                        <td>ĐRL &ge; 80 (Tích lũy đủ số TC theo quy định)</td>
                      </tr>
                      <tr className="tier-row-fair">
                        <td>
                          <strong>📈 Khá</strong>
                        </td>
                        <td>2.50 - 3.19</td>
                        <td>ĐRL &ge; 70 (Tích lũy đủ số TC theo quy định)</td>
                      </tr>
                      <tr className="tier-row-average">
                        <td>
                          <strong>⚖️ Trung bình</strong>
                        </td>
                        <td>2.00 - 2.49</td>
                        <td>Không đủ chuẩn xét học bổng</td>
                      </tr>
                      <tr className="tier-row-weak">
                        <td>
                          <strong>⚠️ Yếu</strong>
                        </td>
                        <td>Dưới 2.00</td>
                        <td>
                          <span className="text-danger">Cần cải thiện để tránh cảnh báo học vụ</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Warning note */}
              <div className="gpa-rules-alert">
                <AlertTriangle size={16} className="text-warning" />
                <p>
                  Tiêu chuẩn xét học bổng có thể thay đổi tùy thuộc vào chỉ tiêu ngân sách và quy định
                  cụ thể của từng Khoa/Viện trong mỗi học kỳ.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="gpa-modal-footer">
          <button type="button" className="tool-btn secondary gpa-btn-sm" onClick={onClose}>
            Đóng
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
