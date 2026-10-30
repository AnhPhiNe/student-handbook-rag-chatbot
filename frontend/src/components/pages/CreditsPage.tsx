import { useRef, useState, useMemo, type KeyboardEvent, type ReactNode } from 'react';
import { MessageCircle, ShieldCheck } from 'lucide-react';
import {
  calculateCreditThreshold,
  getDowngradeVerdict,
  type CreditThresholdStatus,
  type GraduationClassification,
} from '../../utils/creditThreshold';
import { useStudentProfile } from '../../hooks/useStudentProfile';
import { integerCredits } from '../../utils/studentProfile';
import { sanitizeInteger } from '../../utils/numberInput';
import { ShareResultButton } from '../tool/ShareResultButton';
import { creditsShareText } from '../../utils/shareText';
import type { Cohort } from '../../utils/gradeScale';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton } from '../tool/ToolSection';

interface CreditsPageProps {
  cohort: Cohort;
  onAskChat: (text: string) => void;
}

// Above this many allowed credits the one-segment-per-credit meter gets too thin to read.
const MAX_METER_SEGMENTS = 40;
const DOWNGRADE_QUESTION = 'Điều kiện bị hạ bậc bằng tốt nghiệp là gì?';

const STATUS_LABELS: Record<CreditThresholdStatus, string> = {
  safe: 'An toàn',
  near: 'Sát ngưỡng',
  exceeded: 'Vượt ngưỡng',
};

const CLASSIFICATIONS: { value: GraduationClassification; label: string; star?: boolean }[] = [
  { value: 'excellent', label: 'Xuất sắc', star: true },
  { value: 'good', label: 'Giỏi' },
  { value: 'fair', label: 'Khá trở xuống' },
];

interface CreditMeterProps {
  failed: number;
  maxCredits: number;
  status?: CreditThresholdStatus;
}

function CreditMeter({ failed, maxCredits, status = 'safe' }: CreditMeterProps) {
  const segmented = maxCredits >= 1 && maxCredits <= MAX_METER_SEGMENTS;
  const fillPercent = maxCredits > 0 ? Math.min(100, (failed / maxCredits) * 100) : failed > 0 ? 100 : 0;

  return (
    <div
      className={`cr-meter status-${status}`}
      role="img"
      aria-label={`Đã không đạt ${failed} trên tối đa ${maxCredits} tín chỉ`}
    >
      {segmented ? (
        <div className="cr-segs">
          {Array.from({ length: maxCredits }, (_, index) => (
            <i key={index} className={index < failed ? 'on' : ''} />
          ))}
        </div>
      ) : (
        <div className="cr-bar">
          <i style={{ width: `${fillPercent}%` }} />
        </div>
      )}
      <div className="cr-scale">
        <span>0</span>
        <span>Tối đa {maxCredits} TC</span>
      </div>
    </div>
  );
}

export function CreditsPage({ cohort, onAskChat }: CreditsPageProps) {
  // The degree total is the student's own number: reuse the one saved by the GPA target page.
  const { profile, update: updateProfile } = useStudentProfile();
  const [totalCredits, setTotalCredits] = useState(() => integerCredits(profile.totalDegreeCredits));
  const [failedCredits, setFailedCredits] = useState('');
  const [classification, setClassification] = useState<GraduationClassification | null>(null);

  const failedRef = useRef<HTMLInputElement>(null);
  const mFailedRef = useRef<HTMLInputElement>(null);

  const total = Number(totalCredits);
  const failed = Number(failedCredits || 0);
  const result = totalCredits === '' ? null : calculateCreditThreshold(total, failed);
  const exceeded = result?.status === 'exceeded';
  const verdict = result ? getDowngradeVerdict(result.status, classification) : null;

  const shareText = result
    ? creditsShareText({
        status: result.status,
        failedCredits: failed,
        maxCredits: result.maxCredits,
        creditsLeft: result.creditsLeft,
        totalCredits: total,
        cohort,
      })
    : null;

  const handleReset = () => {
    setTotalCredits('');
    setFailedCredits('');
    setClassification(null);
  };

  const handleTotalKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      failedRef.current?.focus();
    }
  };

  const toggleClassification = (value: GraduationClassification) => {
    setClassification((current) => (current === value ? null : value));
  };

  const statusBadge = useMemo(() => {
    if (!result) {
      return <span className="gpa-d-result-badge unranked">• Chờ nhập liệu</span>;
    }
    if (result.status === 'safe') {
      return <span className="gpa-d-result-badge tier-success">★ An toàn</span>;
    }
    if (result.status === 'near') {
      return <span className="gpa-d-result-badge tier-warning">⚠️ Sát ngưỡng</span>;
    }
    return <span className="gpa-d-result-badge tier-danger">⛔ Vượt ngưỡng</span>;
  }, [result]);

  const renderConclusion = (isMobile: boolean) => {
    if (!result) {
      return (
        <span className="cr-conclusion-text">
          💡 Nhập tổng tín chỉ toàn khóa {isMobile ? 'bên dưới' : 'bên trái'} để kiểm tra
        </span>
      );
    }
    if (!verdict) return null;

    let textNode: ReactNode;
    switch (verdict.kind) {
      case 'fair-safe':
        textNode = <>Bằng Khá trở xuống <strong>không bị hạ bằng</strong> theo quy chế.</>;
        break;
      case 'downgrade':
        textNode = <>Bằng <strong>{verdict.from}</strong> sẽ bị hạ xuống <strong>{verdict.to}</strong>.</>;
        break;
      case 'kept':
        textNode = <>Bằng <strong>{verdict.from}</strong> được giữ nguyên nếu không bị kỷ luật từ mức cảnh cáo.</>;
        break;
      case 'may-downgrade':
        textNode = <>Nếu tốt nghiệp Giỏi/Xuất sắc, bằng sẽ <strong>bị hạ một mức</strong>.</>;
        break;
      default:
        textNode = <>Bằng Giỏi, Xuất sắc được giữ nguyên nếu không bị kỷ luật.</>;
        break;
    }

    return (
      <span className="cr-conclusion-text">
        🎯 <strong>Kết luận:</strong> {textNode}
      </span>
    );
  };

  return (
    <div className="page-container tool-page simplified gpa-page-wrapper cr-page">
      <ToolPageHeader
        icon={ShieldCheck}
        title="Kiểm tra hạ bằng"
        description="Xem bạn còn được không đạt bao nhiêu tín chỉ trước khi bằng Giỏi, Xuất sắc bị hạ một mức."
      />

      {/* ============================================================== */}
      {/* 1. BẢN DESKTOP 2 CỘT CÂN ĐỐI (7 CỘT : 5 CỘT)                   */}
      {/* ============================================================== */}
      <div className="gpa-desktop-layout">
        {/* CỘT TRÁI (7 Cols): THIẾT LẬP THÔNG TIN */}
        <div className="gpa-d-table-card">
          <div className="gpa-d-toolbar">
            <div className="gpa-d-toolbar-title">
              <span className="gpa-d-table-heading">THIẾT LẬP THÔNG TIN</span>
              <span className="gpa-d-count-badge">Quy tắc 5%</span>
            </div>
            <ResetButton onClick={handleReset} />
          </div>

          <div className="cr-inputs-body">
            {/* 2 ô nhập liệu chính */}
            <div className="cr-input-grid">
              <div className="cr-field">
                <label htmlFor="cr-total-input" className="tool-field-label"><span className="tool-step-badge">1</span><span>Tổng tín chỉ toàn khóa</span></label>
                <div className="cr-input-box">
                  <input
                    id="cr-total-input"
                    type="text"
                    inputMode="numeric"
                    enterKeyHint="next"
                    autoComplete="off"
                    placeholder="VD: 130"
                    value={totalCredits}
                    onChange={(e) => {
                      const next = sanitizeInteger(e.target.value);
                      setTotalCredits(next);
                      updateProfile({ totalDegreeCredits: next });
                    }}
                    onKeyDown={handleTotalKeyDown}
                    aria-describedby="cr-total-hint"
                  />
                  <span className="cr-input-unit">TC</span>
                </div>

              </div>

              <div className="cr-field">
                <label htmlFor="cr-failed-input" className="tool-field-label"><span className="tool-step-badge">2</span><span>Số tín chỉ từng bị điểm F</span></label>
                <div className="cr-input-box">
                  <input
                    id="cr-failed-input"
                    ref={failedRef}
                    type="text"
                    inputMode="numeric"
                    enterKeyHint="done"
                    autoComplete="off"
                    placeholder="VD: 0"
                    value={failedCredits}
                    onChange={(e) => setFailedCredits(sanitizeInteger(e.target.value))}
                    aria-describedby="cr-failed-hint"
                  />
                  <span className="cr-input-unit">TC</span>
                </div>

              </div>
            </div>

            {/* Chú thích nhỏ */}
            <p className="cr-explain-note">
              * Tính cả môn đã học lại và qua. Không tính học cải thiện.
            </p>

            {/* Bộ chọn xếp loại tốt nghiệp dự kiến (3 pills dạng viên thuốc cao cấp) */}
            <div className="cr-cls-section">
              <div className="cr-cls-head">
                <span className="tool-field-label"><span className="tool-step-badge">3</span><span>Xếp loại mục tiêu (tùy chọn)</span></span>
              </div>
              <div className="cr-cls-pills" role="group" aria-label="Xếp loại tốt nghiệp dự kiến">
                {CLASSIFICATIONS.map(({ value, label, star }) => (
                  <button
                    key={value}
                    type="button"
                    className={`cr-cls-pill ${classification === value ? 'active' : ''}`}
                    aria-pressed={classification === value}
                    onClick={() => toggleClassification(value)}
                  >
                    {star ? '★ ' : ''}{label}
                  </button>
                ))}
              </div>
            </div>

            {/* Hộp trích dẫn quy chế đào tạo */}
            <div className="cr-rule-box">
              <p>
                📖 <strong>Quy chế hạ bằng (Khoản 3 Điều 15):</strong> Nếu số tín chỉ từng bị điểm F vượt quá <strong>5%</strong> toàn khóa: bằng <strong>Xuất sắc</strong> sẽ hạ xuống <strong>Giỏi</strong>, bằng <strong>Giỏi</strong> hạ xuống <strong>Khá</strong>. <em>(Bằng Khá trở xuống không bị hạ bậc).</em>
              </p>
            </div>
          </div>
        </div>

        {/* CỘT PHẢI (5 Cols): TÌNH TRẠNG HẠ BẰNG */}
        <div className="gpa-d-sticky-col">
          <div className="gpa-d-result-card" id="credits-result">
            {/* Header card */}
            <div className="gpa-d-result-header">
              <span className="gpa-d-result-title">TÌNH TRẠNG HẠ BẰNG</span>
              {statusBadge}
            </div>

            {/* Hero Display trung tâm */}
            <div className="cr-hero-wrap gpa-d-hero-score-box">
              <div className="gpa-d-hero-sub">
                {exceeded ? 'ĐÃ VƯỢT MỨC CHO PHÉP' : 'CÒN ĐƯỢC RỚT TỐI ĐA'}
              </div>
              <div className="gpa-d-hero-score-row" style={{ alignItems: 'baseline', gap: '0.45rem' }}>
                <span className={`gpa-d-hero-score cr-hero-val ${exceeded ? 'neg' : ''}`}>
                  {result ? Math.abs(result.creditsLeft) : '--'}
                </span>
                <span className="gpa-d-hero-score-unit" style={{ fontSize: '1rem', fontWeight: 700, color: '#64748b' }}>
                  tín chỉ
                </span>
              </div>
              <div className="gpa-d-gpa10-pill">
                {result ? (
                  <>
                    <span className={`cr-capsule-badge ${result.status}`}>
                      {STATUS_LABELS[result.status].toUpperCase()}
                    </span>
                    <span className="gpa-d-gpa10-label" style={{ opacity: 0.4 }}>│</span>
                    <span className="gpa-d-gpa10-label">
                      Đã không đạt: <strong>{failed}</strong> / {result.maxCredits} TC
                    </span>
                  </>
                ) : (
                  <span className="gpa-d-gpa10-label">Nhập tổng tín chỉ toàn khóa bên trái để kiểm tra</span>
                )}
              </div>
            </div>

            {/* Thanh đo từng bậc CreditMeter */}
            {result && (
              <div className="cr-meter-section">
                <CreditMeter failed={failed} maxCredits={result.maxCredits} status={result.status} />
              </div>
            )}

            {/* Đúng 1 dòng kết luận thông minh */}
            <div className={`cr-conclusion-box ${verdict?.tone || ''}`}>
              {renderConclusion(false)}
            </div>

            {/* Chân trang Desktop */}
            <div className="gpa-d-result-footer">
              <button
                type="button"
                className="gpa-d-footer-link"
                onClick={() => onAskChat(DOWNGRADE_QUESTION)}
              >
                <MessageCircle size={14} aria-hidden="true" />
                <span>Hỏi chatbot về quy chế hạ bằng ↗</span>
              </button>
              <ShareResultButton text={shareText} className="cr-share-link" />
            </div>
          </div>
        </div>
      </div>

      {/* ============================================================== */}
      {/* 2. BẢN MOBILE NATIVE TINH GỌN                                  */}
      {/* ============================================================== */}
      <div className="gpa-mobile-layout">
        {/* Header Mobile */}
        <div className="gpa-m-page-header">
          <div className="gpa-m-title-wrap">
            <ShieldCheck size={20} className="gpa-m-title-icon" aria-hidden="true" />
            <h1 className="gpa-m-page-title">Kiểm tra hạ bằng</h1>
          </div>
          <ResetButton onClick={handleReset} />
        </div>

        {/* Thẻ Hero Navy (3 tầng + thanh từng bậc CreditMeter) */}
        <div className="gpa-mobile-hero-container">
          <div className="gpa-mobile-hero-card">
            <div className="gpa-m-hero-label">
              {exceeded ? 'ĐÃ VƯỢT MỨC CHO PHÉP' : 'CÒN ĐƯỢC RỚT TỐI ĐA'}
            </div>
            <div className="gpa-m-score-row" style={{ alignItems: 'baseline', gap: '0.45rem' }}>
              <span className="gpa-m-score-val" style={{ fontSize: '2.55rem' }}>
                {result ? Math.abs(result.creditsLeft) : '--'}
              </span>
              <span className="gpa-m-score-max">
                {result ? (exceeded ? 'tín chỉ quá mức' : 'tín chỉ') : 'tín chỉ'}
              </span>
            </div>
            <div className="gpa-m-capsule-wrap">
              <div className="gpa-m-capsule">
                {result ? (
                  <>
                    <span
                      className={`gpa-m-tier-text ${
                        result.status === 'exceeded'
                          ? 'tier-danger'
                          : result.status === 'near'
                            ? 'tier-warning'
                            : ''
                      }`}
                    >
                      {STATUS_LABELS[result.status].toUpperCase()}
                    </span>
                    <span className="gpa-m-sep">│</span>
                    <span className="gpa-m-stat-item">
                      Đã rớt: <strong>{failed}</strong> / {result.maxCredits} TC
                    </span>
                  </>
                ) : (
                  <span className="gpa-m-stat-item" style={{ color: 'rgba(255,255,255,0.75)' }}>
                    Nhập tổng tín chỉ toàn khóa bên dưới
                  </span>
                )}
              </div>
            </div>


          </div>
        </div>

        {/* 1 dòng kết luận thông minh trên Mobile (chỉ hiển thị khi đã có kết quả kiểm tra) */}
        {result && verdict && (
          <div className={`scholarship-m-prompt-box ${verdict.tone || ''}`}>
            {renderConclusion(true)}
          </div>
        )}

        {/* Thẻ nhập liệu Mobile phẳng (không lồng card) */}
        <div className="scholarship-m-card cr-m-card">
          <div className="scholarship-m-card-header">
            <span className="scholarship-m-card-title">THÔNG TIN ĐÀO TẠO</span>
            <span className="gpa-d-count-badge">Quy tắc 5%</span>
          </div>

          <div className="cr-inputs-body cr-m-inputs-body">
            <div className="cr-input-grid">
              <div className="cr-field">
                <label htmlFor="m-cr-total-input" className="tool-field-label"><span className="tool-step-badge">1</span><span>Tổng tín chỉ toàn khóa</span></label>
                <div className="cr-input-box">
                  <input
                    id="m-cr-total-input"
                    type="text"
                    inputMode="numeric"
                    enterKeyHint="next"
                    autoComplete="off"
                    placeholder="VD: 130"
                    value={totalCredits}
                    onChange={(e) => {
                      const next = sanitizeInteger(e.target.value);
                      setTotalCredits(next);
                      updateProfile({ totalDegreeCredits: next });
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        mFailedRef.current?.focus();
                      }
                    }}
                    aria-describedby="m-cr-total-hint"
                  />
                  <span className="cr-input-unit">TC</span>
                </div>

              </div>

              <div className="cr-field">
                <label htmlFor="m-cr-failed-input" className="tool-field-label"><span className="tool-step-badge">2</span><span>Số tín chỉ từng bị điểm F</span></label>
                <div className="cr-input-box">
                  <input
                    id="m-cr-failed-input"
                    ref={mFailedRef}
                    type="text"
                    inputMode="numeric"
                    enterKeyHint="done"
                    autoComplete="off"
                    placeholder="VD: 0"
                    value={failedCredits}
                    onChange={(e) => setFailedCredits(sanitizeInteger(e.target.value))}
                    aria-describedby="m-cr-failed-hint"
                  />
                  <span className="cr-input-unit">TC</span>
                </div>

              </div>
            </div>

            <p className="cr-explain-note">
              * Tính cả môn đã học lại và qua. Không tính học cải thiện.
            </p>

            <div className="cr-cls-section">
              <div className="cr-cls-head">
                <span className="tool-field-label"><span className="tool-step-badge">3</span><span>Xếp loại mục tiêu (tùy chọn)</span></span>
              </div>
              <div className="cr-cls-pills" role="group" aria-label="Xếp loại tốt nghiệp dự kiến">
                {CLASSIFICATIONS.map(({ value, label, star }) => (
                  <button
                    key={value}
                    type="button"
                    className={`cr-cls-pill ${classification === value ? 'active' : ''}`}
                    aria-pressed={classification === value}
                    onClick={() => toggleClassification(value)}
                  >
                    {star ? '★ ' : ''}{label}
                  </button>
                ))}
              </div>
            </div>

            <div className="cr-rule-box">
              <p>
                📖 <strong>Quy chế hạ bằng (Khoản 3 Điều 15):</strong> Nếu số tín chỉ từng bị điểm F vượt quá <strong>5%</strong> toàn khóa: bằng <strong>Xuất sắc</strong> sẽ hạ xuống <strong>Giỏi</strong>, bằng <strong>Giỏi</strong> hạ xuống <strong>Khá</strong>. <em>(Bằng Khá trở xuống không bị hạ bậc).</em>
              </p>
            </div>
          </div>
        </div>


      </div>
    </div>
  );
}
