import { useMemo, useState } from 'react';
import {
  Minus,
  Plus,
  ShieldCheck,
  RotateCcw,
  BookOpen,
} from 'lucide-react';
import { calculateCreditThreshold } from '../../utils/creditThreshold';
import { PageContextBadges } from '../PageContextBadges';

export function CreditsPage() {
  const [totalCredits, setTotalCredits] = useState('130');
  const [checkedCredits, setCheckedCredits] = useState('0');

  const total = Number(totalCredits);
  const checked = Number(checkedCredits);

  const result = useMemo(() => {
    if (!Number.isFinite(total) || total <= 0) return null;
    if (!Number.isFinite(checked) || checked < 0) return null;
    return calculateCreditThreshold(total, checked);
  }, [total, checked]);

  const handleIncTotal = () => setTotalCredits((prev) => (Math.max(1, Number(prev || 130)) + 1).toString());
  const handleDecTotal = () => setTotalCredits((prev) => Math.max(1, Number(prev || 130) - 1).toString());

  const handleIncChecked = () => setCheckedCredits((prev) => (Math.max(0, Number(prev || 0)) + 1).toString());
  const handleDecChecked = () => setCheckedCredits((prev) => Math.max(0, Number(prev || 0) - 1).toString());

  const handleReset = () => {
    setTotalCredits('130');
    setCheckedCredits('0');
  };

  const ratioPercent =
    result && result.threshold > 0
      ? Math.min(100, Math.max(0, (checked / result.threshold) * 100))
      : 0;

  return (
    <div className="page-container tool-page">
      {/* Header */}
      <div className="page-header">
        <h1 className="page-title-with-icon">
          <ShieldCheck aria-hidden="true" />
          <span>Kiểm tra điều kiện hạ bằng</span>
        </h1>
        <p>Ước tính ngưỡng 5% tổng tín chỉ để theo dõi rủi ro bị hạ bậc bằng tốt nghiệp.</p>
        <PageContextBadges
          source="Khoản 3 Điều 15 Quy chế đào tạo"
          advisory
          advisoryLabel="Công cụ tham khảo"
        />
      </div>

      {/* Main Split Layout: Form -> Result Card -> Rules */}
      <div className="credits-split-layout">
        {/* Form Card (order: 1 on mobile, grid-area: form on desktop) */}
        <div className="credits-form-card">
          {/* Top Toolbar */}
          <div className="gpa-result-top scholarship-card-top">
            <div className="gpa-result-tag-wrap">
              <span className="gpa-live-dot" />
              <span className="gpa-result-tag">THÔNG TIN TÍN CHỈ CHƯƠNG TRÌNH</span>
            </div>
            <button
              type="button"
              className="tool-btn gpa-reset-btn gpa-btn-sm"
              onClick={handleReset}
              title="Khôi phục mặc định"
            >
              <RotateCcw size={13} />
              <span>Làm mới</span>
            </button>
          </div>

          {/* Inputs Grid */}
          <div className="scholarship-inputs-grid">
            {/* Tổng tín chỉ */}
            <div className="scholarship-input-group">
              <label className="scholarship-input-label">Tổng tín chỉ toàn khóa</label>
              <div className="number-input-group" style={{ height: '38px' }}>
                <button
                  type="button"
                  className="number-btn"
                  onClick={handleDecTotal}
                  aria-label="Giảm tổng tín chỉ"
                >
                  <Minus size={14} />
                </button>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={totalCredits}
                  onChange={(e) => setTotalCredits(e.target.value)}
                  placeholder="130"
                  style={{ fontSize: '0.88rem', padding: '0' }}
                />
                <button
                  type="button"
                  className="number-btn"
                  onClick={handleIncTotal}
                  aria-label="Tăng tổng tín chỉ"
                >
                  <Plus size={14} />
                </button>
              </div>
              <span className="scholarship-input-hint">Thường từ 120 - 150 tín chỉ tùy ngành</span>
            </div>

            {/* Số tín chỉ rớt */}
            <div className="scholarship-input-group">
              <label className="scholarship-input-label">Số tín chỉ đã rớt / học lại</label>
              <div className="number-input-group" style={{ height: '38px' }}>
                <button
                  type="button"
                  className="number-btn"
                  onClick={handleDecChecked}
                  aria-label="Giảm tín chỉ rớt"
                >
                  <Minus size={14} />
                </button>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={checkedCredits}
                  onChange={(e) => setCheckedCredits(e.target.value)}
                  placeholder="0"
                  style={{ fontSize: '0.88rem', padding: '0' }}
                />
                <button
                  type="button"
                  className="number-btn"
                  onClick={handleIncChecked}
                  aria-label="Tăng tín chỉ rớt"
                >
                  <Plus size={14} />
                </button>
              </div>
              <span className="scholarship-input-hint">Chỉ tính tín chỉ các môn điểm F phải học lại</span>
            </div>
          </div>

          <p className="tool-note" style={{ margin: 0 }}>
            💡 Công cụ tự động áp dụng công thức <strong>5% tổng số tín chỉ</strong> chương trình theo Quy chế Đào tạo ĐHQG-HCM.
          </p>
        </div>

        {/* Result Card (order: 2 on mobile, grid-area: result on desktop) */}
        <aside className="credits-summary-card">
          {/* Header & Symmetrical Stat Grid */}
          <div className="credits-summary-header-wrap">
            <div className="gpa-result-top">
              <div className="gpa-result-tag-wrap">
                <span className="gpa-live-dot" />
                <span className="gpa-result-tag">ĐÁNH GIÁ ĐIỀU KIỆN HẠ BẰNG</span>
              </div>
              {result && (
                <span className={`gpa-status-pill ${result.status}`}>
                  {result.status === 'safe' && '🟢 An toàn'}
                  {result.status === 'near' && '🟡 Gần ngưỡng'}
                  {result.status === 'exceeded' && '🔴 Vượt ngưỡng 5%'}
                </span>
              )}
            </div>

            {/* Symmetrical Stat Grid */}
            <div className="course-target-stats-grid">
              <div className="gpa-stat-box">
                <span className="gpa-stat-label">Ngưỡng 5% cho phép</span>
                <strong className="gpa-stat-val text-gradient">
                  {result ? `${result.threshold.toFixed(2)} TC` : '--'}
                </strong>
              </div>
              <div className="gpa-stat-box">
                <span className="gpa-stat-label">Số tín chỉ đã rớt</span>
                <strong
                  className="gpa-stat-val"
                  style={{
                    color:
                      result?.status === 'exceeded'
                        ? '#ef4444'
                        : result?.status === 'near'
                        ? '#d97706'
                        : 'var(--text-primary)',
                  }}
                >
                  {checked || 0} TC
                </strong>
              </div>
            </div>
          </div>

          {/* Dynamic Status Evaluation Banner (The card user loved in Image 3) */}
          {result && (
            <div className={`credits-status-banner ${result.status}`}>
              <span className="banner-label">TÌNH TRẠNG ĐÁNH GIÁ</span>
              <div className="banner-value">
                {result.status === 'safe' && 'Trong vùng an toàn'}
                {result.status === 'near' && 'Đang sát ngưỡng 5%'}
                {result.status === 'exceeded' && 'Đã vượt ngưỡng 5%'}
              </div>
              <span className="banner-desc">{result.message}</span>
            </div>
          )}

          {/* Ratio Meter Bar */}
          {result && (
            <div className="credits-meter-wrap">
              <div className="credits-meter-header">
                <span>Tỷ lệ tín chỉ rớt so với ngưỡng 5%:</span>
                <strong>{ratioPercent.toFixed(1)}%</strong>
              </div>
              <div className="credits-meter-track">
                <div
                  className={`credits-meter-fill ${result.status}`}
                  style={{ width: `${Math.min(100, ratioPercent)}%` }}
                />
              </div>
            </div>
          )}

          {/* Detailed Breakdown List */}
          {result && (
            <div className="tuition-breakdown-list">
              <div className="tuition-breakdown-item">
                <span className="label">Tổng tín chỉ toàn khóa</span>
                <span className="value">{total} tín chỉ</span>
              </div>
              <div className="tuition-breakdown-item">
                <span className="label">Mức trần cho phép (5%)</span>
                <span className="value">{result.threshold.toFixed(2)} tín chỉ</span>
              </div>
              <div className="tuition-breakdown-item">
                <span className="label">Số tín chỉ đã học lại</span>
                <span className="value">{checked} tín chỉ</span>
              </div>
              <div className="tuition-breakdown-item highlight">
                <span className="label">
                  {result.remaining >= 0 ? 'Còn cách ngưỡng an toàn' : 'Số tín chỉ vượt quá'}
                </span>
                <span
                  className="value"
                  style={{ color: result.remaining < 0 ? '#ef4444' : '#10b981' }}
                >
                  {Math.abs(result.remaining).toFixed(2)} tín chỉ
                </span>
              </div>
            </div>
          )}

          {/* Advice Box */}
          <div className="scholarship-advice-box">
            <div className="scholarship-advice-title">
              <ShieldCheck size={16} />
              <span>Gợi ý & Định hướng</span>
            </div>
            <p className="scholarship-advice-desc">
              {result?.status === 'safe'
                ? 'Số tín chỉ học lại đang nằm trong mức an toàn cho phép. Cứ yên tâm duy trì nhịp học ổn định để hướng tới tấm bằng loại Xuất sắc hoặc Giỏi!'
                : result?.status === 'near'
                ? 'Bạn chỉ còn cách ngưỡng tối đa vài tín chỉ (tương đương 1-2 môn). Hãy cân nhắc số lượng môn đăng ký vừa sức ở học kỳ tới để tránh rớt thêm môn.'
                : 'Bạn đã vượt quá 5% số tín chỉ của chương trình. Nếu điểm CPA của bạn xếp loại Xuất sắc sẽ nhận bằng Giỏi, hoặc Giỏi sẽ nhận bằng Khá. Bằng xếp loại Khá sẽ không bị ảnh hưởng.'}
            </p>
          </div>
        </aside>

        {/* Rules Card: Khoản 3 Điều 15 (order: 3 on mobile, grid-area: rule on desktop) */}
        <div className="credits-rule-card">
          <div className="credits-rule-title">
            <BookOpen size={16} style={{ color: 'var(--primary)' }} />
            <span>Quy định hạ bậc tốt nghiệp (Khoản 3 Điều 15)</span>
          </div>
          <ul className="credits-rule-list">
            <li>
              <span style={{ color: '#ef4444', fontWeight: 'bold' }}>⚠️</span>
              <div>
                <strong>Điều kiện bị giảm 1 mức xếp loại:</strong> Sinh viên thuộc một trong hai trường hợp: (1) Khối lượng tín chỉ học lại vượt quá <strong>5% tổng số tín chỉ</strong> toàn khóa; hoặc (2) Bị kỷ luật từ mức <strong>cảnh cáo</strong> trở lên trong thời gian học.
              </div>
            </li>
            <li>
              <span style={{ color: '#f59e0b', fontWeight: 'bold' }}>🎯</span>
              <div>
                <strong>Phạm vi áp dụng:</strong> Chỉ áp dụng đối với hạng <strong>Xuất sắc</strong> (hạ xuống Giỏi) và hạng <strong>Giỏi</strong> (hạ xuống Khá).
              </div>
            </li>
            <li>
              <span style={{ color: '#10b981', fontWeight: 'bold' }}>✅</span>
              <div>
                <strong>Ngoại lệ an toàn:</strong> Nếu điểm tốt nghiệp xếp loại <strong>Khá, Trung bình hoặc Yếu</strong> thì sẽ <strong>không bao giờ bị hạ bậc</strong> dù vượt quá 5% số tín chỉ học lại.
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
