import { useMemo, useState } from 'react';
import {
  TrendingUp,
  RotateCcw,
  Sparkles,
  Info,
  GraduationCap,
  HelpCircle,
  BookOpen,
} from 'lucide-react';
import { type Cohort } from '../../utils/gradeScale';
import { PageContextBadges } from '../PageContextBadges';
import { GpaReferenceModal } from '../GpaReferenceModal';

interface TargetGpaPageProps {
  cohort?: Cohort;
}

interface TargetPreset {
  label: string;
  targetGpa: string;
  badge: string;
  icon: string;
}

const TARGET_PRESETS: TargetPreset[] = [
  { label: 'Xuất sắc (3.60)', targetGpa: '3.60', badge: 'tier-excellent', icon: '⭐' },
  { label: 'Giỏi (3.20)', targetGpa: '3.20', badge: 'tier-good', icon: '🏆' },
  { label: 'Khá (2.50)', targetGpa: '2.50', badge: 'tier-fair', icon: '📈' },
];

const CREDIT_PRESETS = ['12', '15', '18', '21'];

export function TargetGpaPage({ cohort = 'K51' }: TargetGpaPageProps) {
  const [currentGpa, setCurrentGpa] = useState('');
  const [currentCredits, setCurrentCredits] = useState('');
  const [targetGpa, setTargetGpa] = useState('');
  const [futureCredits, setFutureCredits] = useState('15');
  const [referenceModalTab, setReferenceModalTab] = useState<'scale' | 'rules' | null>(null);

  // Parse and calculate target GPA requirement
  const calculation = useMemo(() => {
    const rawCGpa = currentGpa.trim().replace(',', '.');
    const rawCCreds = currentCredits.trim().replace(',', '.');
    const rawTGpa = targetGpa.trim().replace(',', '.');
    const rawFCreds = futureCredits.trim().replace(',', '.');

    const hasCGpa = rawCGpa !== '';
    const hasCCreds = rawCCreds !== '';
    const hasTGpa = rawTGpa !== '';
    const hasFCreds = rawFCreds !== '';

    const cGpa = Number(rawCGpa);
    const cCreds = Number(rawCCreds);
    const tGpa = Number(rawTGpa);
    const fCreds = Number(rawFCreds);

    const isCGpaInvalid = hasCGpa && (!Number.isFinite(cGpa) || cGpa < 0 || cGpa > 4.0);
    const isCCredsInvalid = hasCCreds && (!Number.isFinite(cCreds) || cCreds <= 0 || cCreds > 250);
    const isTGpaInvalid = hasTGpa && (!Number.isFinite(tGpa) || tGpa <= 0 || tGpa > 4.0);
    const isFCredsInvalid = hasFCreds && (!Number.isFinite(fCreds) || fCreds <= 0 || fCreds > 45);

    const hasAnyError = isCGpaInvalid || isCCredsInvalid || isTGpaInvalid || isFCredsInvalid;
    const isComplete = hasCGpa && hasCCreds && hasTGpa && hasFCreds && !hasAnyError;

    if (!isComplete) {
      return {
        isComplete: false,
        hasAnyError,
        isCGpaInvalid,
        isCCredsInvalid,
        isTGpaInvalid,
        isFCredsInvalid,
        requiredGpa: 0,
        totalCreds: 0,
        deltaGpa: 0,
        status: 'empty' as const,
        minCreditsNeeded: null,
      };
    }

    const totalCreds = cCreds + fCreds;
    const targetPoints = tGpa * totalCreds;
    const currentPoints = cGpa * cCreds;
    const requiredPoints = targetPoints - currentPoints;
    const requiredGpa = requiredPoints / fCreds;
    const deltaGpa = tGpa - cGpa;

    // Check minimum credits needed if impossible
    let minCreditsNeeded: number | null = null;
    if (requiredGpa > 4.0 && tGpa < 4.0) {
      const needed = ((tGpa - cGpa) * cCreds) / (4.0 - tGpa);
      if (needed > 0) {
        minCreditsNeeded = Math.ceil(needed);
      }
    }

    let status: 'achieved' | 'possible' | 'impossible' = 'possible';
    if (requiredGpa <= 0 || (tGpa <= cGpa && requiredGpa <= cGpa)) {
      status = 'achieved';
    } else if (requiredGpa > 4.0) {
      status = 'impossible';
    }

    return {
      isComplete: true,
      hasAnyError: false,
      isCGpaInvalid: false,
      isCCredsInvalid: false,
      isTGpaInvalid: false,
      isFCredsInvalid: false,
      requiredGpa,
      totalCreds,
      deltaGpa,
      status,
      minCreditsNeeded,
      cGpa,
      cCreds,
      tGpa,
      fCreds,
    };
  }, [currentGpa, currentCredits, targetGpa, futureCredits]);

  // Reset all inputs
  const handleReset = () => {
    if (currentGpa || currentCredits || targetGpa || (futureCredits && futureCredits !== '15')) {
      if (!window.confirm('Bạn có chắc chắn muốn xóa trắng các số liệu mục tiêu không?')) {
        return;
      }
    }
    setCurrentGpa('');
    setCurrentCredits('');
    setTargetGpa('');
    setFutureCredits('15');
  };

  // Fill sample data
  const handleSample = () => {
    setCurrentGpa('2.85');
    setCurrentCredits('60');
    setTargetGpa('3.20');
    setFutureCredits('15');
  };

  // Determine tier & progress bar width
  const tierInfo = useMemo(() => {
    if (!calculation.isComplete) return null;
    if (calculation.status === 'achieved') {
      return {
        label: 'Đã đạt mục tiêu',
        badgeClass: 'tier-excellent',
        icon: '🎉',
        progress: 100,
      };
    }
    if (calculation.status === 'impossible') {
      return {
        label: 'Bất khả thi (> 4.0)',
        badgeClass: 'tier-weak',
        icon: '⚠️',
        progress: 100,
      };
    }
    const gpa = calculation.requiredGpa;
    const progress = Math.min(100, Math.max(0, (gpa / 4.0) * 100));
    if (gpa >= 3.6) {
      return { label: 'Xuất sắc (A)', badgeClass: 'tier-excellent', icon: '⭐', progress };
    }
    if (gpa >= 3.2) {
      return { label: 'Giỏi (B+)', badgeClass: 'tier-good', icon: '🏆', progress };
    }
    if (gpa >= 2.5) {
      return { label: 'Khá (B)', badgeClass: 'tier-fair', icon: '📈', progress };
    }
    if (gpa >= 2.0) {
      return { label: 'Trung bình', badgeClass: 'tier-average', icon: '⚖️', progress };
    }
    return { label: 'Cần nỗ lực', badgeClass: 'tier-weak', icon: '🎯', progress };
  }, [calculation]);

  return (
    <div className="page-container tool-page target-gpa-page-wrapper">
      {/* Header */}
      <div className="page-header gpa-header">
        <h1 className="page-title-with-icon">
          <TrendingUp aria-hidden="true" />
          <span>Mục tiêu GPA</span>
        </h1>
        <p>Tính điểm trung bình học kỳ cần đạt để kéo GPA tích lũy lên mức mong muốn.</p>
        <PageContextBadges cohort={cohort} source="Quy chế đào tạo theo tín chỉ" />
      </div>

      {/* Top Mobile Hero Card (Pinned to top, zero bottom-bar overlap) */}
      <section className="gpa-mobile-hero-card target-gpa-mobile-hero" aria-label="Kết quả mục tiêu GPA">
        <div className="gpa-mobile-hero-top">
          <div className="gpa-result-tag-wrap">
            <span className="gpa-live-dot" aria-hidden="true" />
            <span className="gpa-hero-tag">MỤC TIÊU GPA • {cohort}</span>
          </div>
          {tierInfo && (
            <span className={`gpa-tier-pill ${tierInfo.badgeClass}`}>
              {tierInfo.icon} {tierInfo.label}
            </span>
          )}
        </div>

        <div className="gpa-mobile-hero-middle">
          <div className="gpa-hero-score">
            <span className="gpa-score-num text-gradient">
              {!calculation.isComplete
                ? '--'
                : calculation.status === 'achieved'
                ? 'Đạt'
                : calculation.status === 'impossible'
                ? '> 4.0'
                : calculation.requiredGpa.toFixed(2)}
            </span>
            <span className="gpa-score-den">/ 4.00</span>
          </div>

          <div className="gpa-mobile-stats-chips">
            <span className="gpa-stat-chip">
              <strong>{calculation.isComplete ? calculation.totalCreds : '--'}</strong> Tổng TC
            </span>
            <span className="gpa-stat-chip">
              <strong>{calculation.isComplete ? `${calculation.deltaGpa >= 0 ? '+' : ''}${calculation.deltaGpa.toFixed(2)}` : '--'}</strong> Chênh lệch
            </span>
            <span className="gpa-stat-chip">
              <strong>{futureCredits || '--'}</strong> TC kỳ tới
            </span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="gpa-progress-track">
          <div
            className={`gpa-progress-fill ${tierInfo ? tierInfo.badgeClass : ''}`}
            style={{ width: `${tierInfo ? tierInfo.progress : 0}%` }}
          />
        </div>

        {/* Validation error notice on Mobile */}
        {calculation.hasAnyError && (
          <div className="gpa-validation-error-notice" role="alert">
            <span>⚠️</span>
            <span>
              {calculation.isCGpaInvalid || calculation.isTGpaInvalid
                ? 'Điểm GPA phải nằm trong khoảng 0.00 đến 4.00.'
                : 'Số tín chỉ phải lớn hơn 0.'}
            </span>
          </div>
        )}
      </section>

      {/* Main 2-Column Split Layout */}
      <div className="gpa-split-layout target-gpa-split-layout">
        {/* Left Column: Input Sections & Guidance */}
        <section className="gpa-main-column target-gpa-main-column">
          {/* Controls Bar: Clean title & action buttons */}
          <div className="gpa-toolbar target-gpa-toolbar">
            <div className="target-gpa-toolbar-heading">
              <span className="target-gpa-toolbar-title">Thiết lập mục tiêu</span>
              <span className="target-gpa-toolbar-sub">Dự tính điểm trung bình học kỳ cần đạt</span>
            </div>

            <div className="gpa-action-buttons">
              <button
                type="button"
                className="tool-btn ghost gpa-btn-sm"
                onClick={handleReset}
                title="Xóa trắng các thông tin đã nhập"
              >
                <RotateCcw size={14} />
                <span>Làm mới</span>
              </button>
              <button
                type="button"
                className="tool-btn primary gpa-btn-sm gpa-btn-highlight"
                onClick={handleSample}
                title="Điền dữ liệu mẫu để thử tính toán"
              >
                <Sparkles size={14} />
                <span>Dữ liệu mẫu</span>
              </button>
            </div>
          </div>

          {/* Form Card with Distinct Styled Panels */}
          <div className="target-gpa-cards-stack">
            <div className="target-gpa-form-card">
              {/* Panel 1: Tích lũy hiện tại */}
              <div className="target-gpa-panel current-panel">
                <div className="target-gpa-panel-header">
                  <div className="target-gpa-panel-title">
                    <span className="target-gpa-panel-num current">1</span>
                    <h3>Kết quả tích lũy hiện tại</h3>
                  </div>
                  <span className="target-gpa-panel-hint">Tính đến hết học kỳ gần nhất</span>
                </div>

                <div className="target-gpa-grid-2col">
                  <div className="target-gpa-field-group">
                    <label htmlFor="target-curr-gpa" className="target-gpa-label">
                      GPA tích lũy hiện tại (Thang 4)
                    </label>
                    <div className="target-gpa-input-wrap">
                      <input
                        id="target-curr-gpa"
                        type="text"
                        inputMode="decimal"
                        className={`target-gpa-input ${calculation.isCGpaInvalid ? 'input-error' : ''}`}
                        value={currentGpa}
                        onChange={(e) => {
                          const val = e.target.value;
                          if (val === '' || /^[0-9.,]*$/.test(val)) setCurrentGpa(val);
                        }}
                        placeholder="VD: 2.85"
                      />
                      <span className="target-gpa-affix">/ 4.00</span>
                    </div>
                    {calculation.isCGpaInvalid && (
                      <span className="target-gpa-field-error">GPA phải từ 0.00 đến 4.00</span>
                    )}
                  </div>

                  <div className="target-gpa-field-group">
                    <label htmlFor="target-curr-creds" className="target-gpa-label">
                      Số tín chỉ đã tích lũy
                    </label>
                    <div className="target-gpa-input-wrap">
                      <input
                        id="target-curr-creds"
                        type="text"
                        inputMode="decimal"
                        className={`target-gpa-input ${calculation.isCCredsInvalid ? 'input-error' : ''}`}
                        value={currentCredits}
                        onChange={(e) => {
                          const val = e.target.value;
                          if (val === '' || /^[0-9.,]*$/.test(val)) setCurrentCredits(val);
                        }}
                        placeholder="VD: 60"
                      />
                      <span className="target-gpa-affix">Tín chỉ</span>
                    </div>
                    {calculation.isCCredsInvalid && (
                      <span className="target-gpa-field-error">Số tín chỉ phải &gt; 0</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Panel 2: Kế hoạch học kỳ tới */}
              <div className="target-gpa-panel target-panel">
                <div className="target-gpa-panel-header">
                  <div className="target-gpa-panel-title">
                    <span className="target-gpa-panel-num target">2</span>
                    <h3>Kế hoạch học kỳ tới</h3>
                  </div>
                  <span className="target-gpa-panel-hint">Mục tiêu phấn đấu & tín chỉ đăng ký</span>
                </div>

                <div className="target-gpa-grid-2col">
                  <div className="target-gpa-field-group">
                    <label htmlFor="target-goal-gpa" className="target-gpa-label">
                      GPA mục tiêu muốn đạt (Thang 4)
                    </label>
                    <div className="target-gpa-input-wrap">
                      <input
                        id="target-goal-gpa"
                        type="text"
                        inputMode="decimal"
                        className={`target-gpa-input ${calculation.isTGpaInvalid ? 'input-error' : ''}`}
                        value={targetGpa}
                        onChange={(e) => {
                          const val = e.target.value;
                          if (val === '' || /^[0-9.,]*$/.test(val)) setTargetGpa(val);
                        }}
                        placeholder="VD: 3.20"
                      />
                      <span className="target-gpa-affix">/ 4.00</span>
                    </div>
                    {calculation.isTGpaInvalid && (
                      <span className="target-gpa-field-error">Mục tiêu phải từ 0.00 đến 4.00</span>
                    )}

                    {/* Quick target presets right under the target input */}
                    <div className="target-gpa-quick-chips">
                      {TARGET_PRESETS.map((p) => (
                        <button
                          key={p.targetGpa}
                          type="button"
                          className={`target-gpa-tc-chip ${targetGpa === p.targetGpa ? 'active' : ''}`}
                          onClick={() => setTargetGpa(p.targetGpa)}
                        >
                          <span>{p.icon}</span>
                          <span>{p.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="target-gpa-field-group">
                    <label htmlFor="target-future-creds" className="target-gpa-label">
                      Số tín chỉ dự kiến học kỳ tới
                    </label>
                    <div className="target-gpa-input-wrap">
                      <input
                        id="target-future-creds"
                        type="text"
                        inputMode="decimal"
                        className={`target-gpa-input ${calculation.isFCredsInvalid ? 'input-error' : ''}`}
                        value={futureCredits}
                        onChange={(e) => {
                          const val = e.target.value;
                          if (val === '' || /^[0-9.,]*$/.test(val)) setFutureCredits(val);
                        }}
                        placeholder="VD: 15"
                      />
                      <span className="target-gpa-affix">Tín chỉ</span>
                    </div>
                    {calculation.isFCredsInvalid && (
                      <span className="target-gpa-field-error">Tín chỉ học kỳ phải &gt; 0</span>
                    )}

                    {/* Quick credit chips */}
                    <div className="target-gpa-quick-chips">
                      {CREDIT_PRESETS.map((tc) => (
                        <button
                          key={tc}
                          type="button"
                          className={`target-gpa-tc-chip ${futureCredits === tc ? 'active' : ''}`}
                          onClick={() => setFutureCredits(tc)}
                        >
                          {tc} TC
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Collapsible Formula & Guidance Card */}
            <details className="target-gpa-formula-details">
              <summary className="target-gpa-formula-summary">
                <div className="target-gpa-formula-sum-left">
                  <BookOpen size={16} />
                  <span>Xem công thức tính điểm & mẹo tối ưu kế hoạch</span>
                </div>
                <span className="target-gpa-formula-sum-toggle">Chi tiết ▾</span>
              </summary>
              <div className="target-gpa-formula-body">
                <div className="target-gpa-formula-display">
                  <div className="target-gpa-formula-lhs">
                    <span>Điểm kỳ tới</span>
                    <strong>=</strong>
                  </div>
                  <div className="target-gpa-fraction">
                    <div className="target-gpa-numerator">
                      <span>(GPA mục tiêu × Tổng TC sau kỳ)</span>
                      <span className="target-gpa-minus">−</span>
                      <span>(GPA hiện tại × TC hiện tại)</span>
                    </div>
                    <div className="target-gpa-fraction-line" />
                    <div className="target-gpa-denominator">
                      <span>Số tín chỉ học kỳ tới</span>
                    </div>
                  </div>
                </div>
                <div className="target-gpa-formula-tip">
                  <HelpCircle size={14} />
                  <span>
                    <strong>Mẹo:</strong> Nếu điểm yêu cầu quá cao, bạn có thể <strong>tăng số tín chỉ kỳ tới</strong> để dàn trải và giảm áp lực điểm trung bình cần đạt.
                  </span>
                </div>
              </div>
            </details>
          </div>
        </section>

        {/* Right Column: Sticky Sidebar Card (Desktop) */}
        <aside className="gpa-sidebar-column target-gpa-sidebar">
          <div className="gpa-sticky-card">
            <div className="gpa-card-inner">
              {/* Header Tag */}
              <div className="gpa-result-top">
                <div className="gpa-result-tag-wrap">
                  <span className="gpa-live-dot" aria-hidden="true" />
                  <span className="gpa-result-tag">MỤC TIÊU GPA</span>
                </div>
                <span className="gpa-cohort-pill">{cohort}</span>
              </div>

              {/* Dedicated Tier Row (Prevents text wrapping and header cramming) */}
              {tierInfo && (
                <div className="target-gpa-tier-row">
                  <span className={`gpa-tier-pill ${tierInfo.badgeClass}`}>
                    {tierInfo.icon} {tierInfo.label}
                  </span>
                </div>
              )}

              {/* Hero GPA Score Display */}
              <div className="gpa-hero-score">
                <span className="gpa-score-num text-gradient">
                  {!calculation.isComplete
                    ? '--'
                    : calculation.status === 'achieved'
                    ? 'Đạt'
                    : calculation.status === 'impossible'
                    ? '> 4.0'
                    : calculation.requiredGpa.toFixed(2)}
                </span>
                <span className="gpa-score-den">/ 4.00</span>
              </div>

              {/* Progress Bar (0 to 4.0) */}
              <div className="gpa-progress-track">
                <div
                  className={`gpa-progress-fill ${tierInfo ? tierInfo.badgeClass : ''}`}
                  style={{ width: `${tierInfo ? tierInfo.progress : 0}%` }}
                />
              </div>

              {/* Summary Stats Grid (3 Equal, Symmetrical Cards) */}
              <div className="gpa-stats-grid">
                <div className="gpa-stat-box">
                  <span className="gpa-stat-label">Tổng TC</span>
                  <strong className="gpa-stat-val">
                    {calculation.isComplete ? calculation.totalCreds : '--'}
                  </strong>
                </div>
                <div className="gpa-stat-box">
                  <span className="gpa-stat-label">Chênh lệch</span>
                  <strong className="gpa-stat-val">
                    {calculation.isComplete
                      ? `${calculation.deltaGpa >= 0 ? '+' : ''}${calculation.deltaGpa.toFixed(2)}`
                      : '--'}
                  </strong>
                </div>
                <div className="gpa-stat-box">
                  <span className="gpa-stat-label">TC kỳ tới</span>
                  <strong className="gpa-stat-val">
                    {futureCredits || '--'}
                  </strong>
                </div>
              </div>

              {/* Detailed Strategic Insight Card */}
              {calculation.isComplete ? (
                <>
                  {calculation.status === 'achieved' ? (
                    <div className="gpa-notice-card tier-excellent">
                      <span className="gpa-notice-icon">🎉</span>
                      <div className="gpa-notice-text">
                        <strong>Chúc mừng!</strong> GPA hiện tại ({calculation.cGpa.toFixed(2)}) của bạn đã đạt hoặc vượt mục tiêu ({calculation.tGpa.toFixed(2)}). Bạn chỉ cần duy trì phong độ học tập!
                      </div>
                    </div>
                  ) : calculation.status === 'possible' ? (
                    <div className={`gpa-notice-card ${tierInfo?.badgeClass || 'tier-good'}`}>
                      <span className="gpa-notice-icon">🎯</span>
                      <div className="gpa-notice-text">
                        Bạn cần đạt trung bình tối thiểu <strong>{calculation.requiredGpa.toFixed(2)}</strong> cho <strong>{calculation.fCreds} tín chỉ</strong> kỳ tới để kéo GPA tích lũy lên <strong>{calculation.tGpa.toFixed(2)}</strong>.
                        <div style={{ marginTop: '0.35rem', opacity: 0.9, fontSize: '0.74rem' }}>
                          👉 <em>Tương đương mức điểm chữ trung bình {calculation.requiredGpa >= 3.6 ? 'A (Xuất sắc)' : calculation.requiredGpa >= 3.2 ? 'B+ (Giỏi)' : calculation.requiredGpa >= 2.5 ? 'B (Khá)' : 'C+ đến B'}.</em>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="gpa-notice-card tier-weak">
                      <span className="gpa-notice-icon">⚠️</span>
                      <div className="gpa-notice-text">
                        <strong>Mục tiêu bất khả thi trong 1 kỳ!</strong> Điểm cần đạt là <strong>{calculation.requiredGpa.toFixed(2)}</strong>, vượt quá thang điểm tối đa 4.00.
                        {calculation.minCreditsNeeded && (
                          <div style={{ marginTop: '0.35rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                            💡 <em>Gợi ý: Cần đăng ký tối thiểu <strong>{calculation.minCreditsNeeded} tín chỉ</strong> (và đạt 4.0/4.0 toàn bộ) để đạt được mục tiêu này.</em>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="gpa-empty-state-card">
                  <div className="gpa-empty-state-icon">🎯</div>
                  <div className="gpa-empty-state-body">
                    <span className="gpa-empty-state-title">Chờ nhập dữ liệu</span>
                    <p className="gpa-empty-state-desc">
                      Nhập điểm tích lũy hiện tại và mục tiêu kỳ vọng để tính toán số điểm học kỳ cần đạt.
                    </p>
                  </div>
                </div>
              )}

              {/* Validation error notice on Desktop */}
              {calculation.hasAnyError && (
                <div className="gpa-validation-error-notice" role="alert">
                  <span>⚠️</span>
                  <span>Vui lòng kiểm tra lại các ô báo đỏ để hệ thống tính toán chính xác.</span>
                </div>
              )}

              {/* Footer Actions: 2 Stacked Reference Buttons */}
              <div className="gpa-card-footer">
                <div className="gpa-action-pills-row">
                  <button
                    type="button"
                    className="gpa-footer-pill-btn"
                    onClick={() => setReferenceModalTab('rules')}
                    title="Xem quy chế tính GPA và tiêu chuẩn học bổng"
                  >
                    <Info size={14} />
                    <span>Quy chế điểm</span>
                  </button>
                  <button
                    type="button"
                    className="gpa-footer-pill-btn"
                    onClick={() => setReferenceModalTab('scale')}
                    title={`Tra cứu bảng quy đổi điểm (${cohort})`}
                  >
                    <GraduationCap size={15} />
                    <span>Bảng quy đổi điểm</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* Reference Modal */}
      <GpaReferenceModal
        isOpen={referenceModalTab !== null}
        onClose={() => setReferenceModalTab(null)}
        cohort={cohort}
        initialTab={referenceModalTab ?? 'scale'}
      />
    </div>
  );
}
