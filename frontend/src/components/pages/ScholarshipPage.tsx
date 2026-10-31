import { useRef, useState, useMemo, useEffect, useId, type KeyboardEvent } from 'react';
import { Award, Minus, Plus, MessageCircle, RotateCcw, Info } from 'lucide-react';
import {
  calculateScholarshipScore,
  getFinalSemesterMinCredits,
  SCHOLARSHIP_RULES,
} from '../../utils/scholarship';
import {
  formatVnd,
  type SchoolYear,
  type TuitionProgram,
} from '../../data/tuitionRates';
import type { Cohort } from '../../utils/gradeScale';
import { sanitizeDecimal, sanitizeInteger } from '../../utils/numberInput';
import { ShareResultButton } from '../tool/ShareResultButton';
import { scholarshipShareText } from '../../utils/shareText';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ProgramSearch } from '../tool/ProgramSearch';

interface ScholarshipPageProps {
  cohort: Cohort;
  onAskChat: (text: string) => void;
}

const MIN_SCHOLARSHIP_CREDITS = 15;
const DEFAULT_CREDITS = '15';
const DEFAULT_YEAR: SchoolYear = '2025-2026';
const PROGRAM_INPUT_ID = 'scholarship-program';
const PROGRAM_INPUT_MOBILE_ID = 'scholarship-program-mobile';

const SCHOLARSHIP_YEARS: { id: SchoolYear; label: string }[] = [
  { id: '2025-2026', label: '2025–26' },
  { id: '2026-2027', label: '2026–27' },
];

function ScholarshipConditions({ finalSemesterMin }: { finalSemesterMin: number }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    };
    const dismissOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('keydown', dismissOnEscape);
    return () => {
      document.removeEventListener('pointerdown', dismiss);
      document.removeEventListener('keydown', dismissOnEscape);
    };
  }, [open]);

  return (
    <div
      className="scholarship-conditions"
      ref={root}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => {
        if (!root.current?.contains(document.activeElement)) setOpen(false);
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.stopPropagation();
          setOpen(false);
        }
      }}
    >
      <button
        type="button"
        className="scholarship-conditions-trigger"
        aria-expanded={open}
        aria-controls={panelId}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
      >
        Điều kiện học bổng <Info size={16} aria-hidden="true" />
      </button>
      <div id={panelId} className="scholarship-conditions-panel" hidden={!open} role="region" aria-label="Điều kiện GPA và rèn luyện">
        <div className="scholarship-thresholds">
          {[...SCHOLARSHIP_RULES].reverse().map((rule) => (
            <div className="scholarship-threshold" key={rule.label}>
              <strong className={`scholarship-threshold-title ${rule.label === 'Khá' ? 'level-fair' : rule.label === 'Giỏi' ? 'level-good' : 'level-excellent'}`}>
                {rule.label}
              </strong>
              <span>GPA ≥ {rule.minAcademicScore.toFixed(2).replace('.', ',')}</span>
              <span>RL ≥ {rule.minConductScore}</span>
            </div>
          ))}
        </div>
        <p>Tín chỉ đăng ký: tối thiểu 15 TC. Học kỳ tốt nghiệp: tối thiểu {finalSemesterMin} TC.</p>
        <p>RL: điểm rèn luyện. Cần đồng thời đạt các ngưỡng trên, điểm xét và điều kiện tín chỉ.</p>
      </div>
    </div>
  );
}

export function ScholarshipPage({ cohort, onAskChat }: ScholarshipPageProps) {
  const [academicScore, setAcademicScore] = useState('');
  const [conductScore, setConductScore] = useState('');
  const [credits, setCredits] = useState(DEFAULT_CREDITS);
  const [query, setQuery] = useState('');
  const [selectedProgram, setSelectedProgram] = useState<TuitionProgram | null>(null);
  const [schoolYear, setSchoolYear] = useState<SchoolYear>(DEFAULT_YEAR);

  const conductRef = useRef<HTMLInputElement | null>(null);

  const gpa = academicScore !== '' ? Number(academicScore) : null;
  const conduct = conductScore !== '' ? Number(conductScore) : null;
  const academicError =
    gpa !== null && (!Number.isFinite(gpa) || gpa < 0 || gpa > 4) ? 'GPA từ 0 đến 4.' : null;
  const conductError =
    conduct !== null && (!Number.isFinite(conduct) || conduct < 0 || conduct > 100)
      ? 'Rèn luyện từ 0 đến 100.'
      : null;

  // Calculate scholarship evaluation
  const result =
    gpa !== null && conduct !== null && !academicError && !conductError
      ? calculateScholarshipScore(gpa, conduct)
      : null;

  const creditCount = Number(credits);
  const hasCredits = credits !== '' && creditCount > 0;
  const isBelowMinimum = hasCredits && creditCount < MIN_SCHOLARSHIP_CREDITS;
  const finalSemesterMin = getFinalSemesterMinCredits(cohort);
  const perCredit = selectedProgram?.perCredit[schoolYear] ?? 0;
  const amount =
    result?.classification && perCredit > 0 && hasCredits && !isBelowMinimum
      ? creditCount * perCredit * result.multiplier
      : null;

  const tierLevel = useMemo(() => {
    if (!result?.classification) return 0;
    if (result.classification === 'Xuất sắc') return 3;
    if (result.classification === 'Giỏi') return 2;
    if (result.classification === 'Khá') return 1;
    return 0;
  }, [result?.classification]);

  const handleQueryChange = (value: string) => {
    setQuery(value);
    if (selectedProgram && `${selectedProgram.code} - ${selectedProgram.name}` !== value) {
      setSelectedProgram(null);
    }
  };

  const selectProgram = (program: TuitionProgram) => {
    setSelectedProgram(program);
    setQuery(`${program.code} - ${program.name}`);
  };

  const clearProgram = () => {
    setSelectedProgram(null);
    setQuery('');
  };

  const handleReset = () => {
    setAcademicScore('');
    setConductScore('');
    setCredits(DEFAULT_CREDITS);
    setSchoolYear(DEFAULT_YEAR);
    clearProgram();
  };

  const stepCredits = (delta: number) => {
    const current = Number(credits || DEFAULT_CREDITS);
    setCredits(String(Math.max(1, current + delta)));
  };

  const handleGpaKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    conductRef.current?.focus();
  };

  const handleConductKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    event.currentTarget.blur();
  };

  const shareText = result
    ? scholarshipShareText({
        classification: result.classification,
        multiplier: result.multiplier,
        score: result.score,
        amount,
        cohort,
      })
    : null;

  // Status badge for desktop right card header
  const statusBadge = useMemo(() => {
    if (!result || gpa === null || conduct === null) {
      return <span className="gpa-d-result-badge unranked">• Chờ nhập liệu</span>;
    }
    if (!result.classification) {
      return <span className="gpa-d-result-badge tier-danger">• Chưa đạt</span>;
    }
    if (result.classification === 'Xuất sắc') {
      return <span className="gpa-d-result-badge tier-warning">★ Đạt loại Xuất sắc</span>;
    }
    if (result.classification === 'Giỏi') {
      return <span className="gpa-d-result-badge tier-success">★ Đạt loại Giỏi</span>;
    }
    return <span className="gpa-d-result-badge tier-info">★ Đạt loại Khá</span>;
  }, [result, gpa, conduct]);

  // Unified smart tip generator
  const renderSmartTip = (isMobile: boolean) => {
    if (!result || gpa === null || conduct === null) {
      return (
        <span className="scholarship-smart-tip">
          💡 Nhập GPA và điểm rèn luyện {isMobile ? 'để xem gợi ý' : 'bên trái để xem gợi ý'}
        </span>
      );
    }

    if (isBelowMinimum) {
      return (
        <span className="scholarship-smart-tip">
          ⚠️ Cần tối thiểu {MIN_SCHOLARSHIP_CREDITS} TC để đủ điều kiện xét học bổng
        </span>
      );
    }

    if (result.classification === 'Xuất sắc') {
      return (
        <span className="scholarship-smart-tip">
          🎉 Bạn đã đạt mức học bổng khuyến khích cao nhất
        </span>
      );
    }

    const nextTier =
      result.classification === 'Giỏi'
        ? SCHOLARSHIP_RULES.find((r) => r.label === 'Xuất sắc')!
        : result.classification === 'Khá'
          ? SCHOLARSHIP_RULES.find((r) => r.label === 'Giỏi')!
          : SCHOLARSHIP_RULES.find((r) => r.label === 'Khá')!;

    if (!result.classification) {
      return (
        <span className="scholarship-smart-tip">
          ⚠️ Cần tối thiểu GPA ≥ 2.50 và 70 điểm RL để xét học bổng
        </span>
      );
    }

    const gpaGap = Math.max(0, Math.round((nextTier.minAcademicScore - gpa) * 100) / 100);
    const conductGap = Math.max(0, nextTier.minConductScore - conduct);

    if (gpaGap > 0 && conductGap > 0) {
      return (
        <span className="scholarship-smart-tip">
          🎯 Cần thêm <strong className="gpa-motivate-highlight">{gpaGap.toFixed(2)} GPA</strong> và{' '}
          <strong className="gpa-motivate-highlight">{conductGap} điểm RL</strong> để đạt{' '}
          <strong>{nextTier.label} (× {nextTier.multiplier})</strong>
        </span>
      );
    }

    if (conductGap > 0) {
      return (
        <span className="scholarship-smart-tip">
          🎯 Cần thêm <strong className="gpa-motivate-highlight">{conductGap} điểm {isMobile ? 'RL' : 'rèn luyện'}</strong> để đạt{' '}
          <strong>{nextTier.label} (× {nextTier.multiplier})</strong>
        </span>
      );
    }

    if (gpaGap > 0) {
      return (
        <span className="scholarship-smart-tip">
          🎯 Cần thêm <strong className="gpa-motivate-highlight">{gpaGap.toFixed(2)} GPA</strong> để đạt{' '}
          <strong>{nextTier.label} (× {nextTier.multiplier})</strong>
        </span>
      );
    }

    const scoreGap = Math.max(0, Math.round((nextTier.minScholarshipScore - result.score) * 1000) / 1000);
    if (scoreGap > 0) {
      return (
        <span className="scholarship-smart-tip">
          🎯 Cần thêm <strong className="gpa-motivate-highlight">{scoreGap.toFixed(3)} điểm xét</strong> để đạt{' '}
          <strong>{nextTier.label} (× {nextTier.multiplier})</strong>
        </span>
      );
    }

    return (
      <span className="scholarship-smart-tip">
        🎯 Phấn đấu duy trì kết quả để đạt <strong>{nextTier.label} (× {nextTier.multiplier})</strong>
      </span>
    );
  };

  return (
    <div className="page-container tool-page simplified gpa-page-wrapper scholarship-page">
      <ToolPageHeader
        icon={Award}
        title="Tính điểm học bổng"
        description={
          <>
            Xem bạn đạt học bổng khuyến khích học tập mức nào và ước tính số tiền nhận được theo quy chế{' '}
            <strong>{cohort}</strong>.
          </>
        }
      />

      {/* ============================================================== */}
      {/* 1. BẢN DESKTOP 2 CỘT CÂN ĐỐI (7 CỘT : 5 CỘT)                   */}
      {/* ============================================================== */}
      <div className="gpa-desktop-layout">
        {/* CỘT TRÁI (7 Cols): THÔNG TIN XÉT HỌC BỔNG */}
        <div className="gpa-d-table-card">
          <div className="gpa-d-toolbar">
            <div className="gpa-d-toolbar-title">
              <span className="gpa-d-table-heading">THÔNG TIN XÉT HỌC BỔNG</span>
              <span className="gpa-d-table-badge">Tối thiểu 15 TC</span>
            </div>
            <button
              type="button"
              className="gpa-d-reset-btn"
              onClick={handleReset}
              title="Đặt lại thông số"
            >
              <RotateCcw size={14} />
              <span>Đặt lại</span>
            </button>
          </div>

          <div className="scholarship-d-content">
            {/* Nhóm Điểm số chính (Phẳng hoàn toàn trên nền thẻ trắng, KHÔNG card lồng card) */}
            <div className="scholarship-input-grid scholarship-eligibility-grid">
              <div>
                <div className="scholarship-input-label-row">
                  <label htmlFor="scholarship-gpa" className="scholarship-input-label">
                    <span className="tool-step-badge">1</span>
                    <span>GPA học kỳ</span>
                  </label>
                </div>
                <div className={`scholarship-input-box ${academicError ? 'bad' : ''}`}>
                  <input
                    id="scholarship-gpa"
                    type="text"
                    inputMode="decimal"
                    placeholder="VD: 3.50"
                    value={academicScore}
                    onChange={(e) => setAcademicScore(sanitizeDecimal(e.target.value))}
                    onKeyDown={handleGpaKeyDown}
                    className="scholarship-val-input"
                  />
                  <span className="scholarship-input-max">/ 4.00</span>
                </div>
                {academicError && <span className="scholarship-field-err">{academicError}</span>}
              </div>

              <div>
                <div className="scholarship-input-label-row">
                  <label htmlFor="scholarship-conduct" className="scholarship-input-label">
                    <span className="tool-step-badge">2</span>
                    <span>Điểm rèn luyện</span>
                  </label>
                </div>
                <div className={`scholarship-input-box ${conductError ? 'bad' : ''}`}>
                  <input
                    id="scholarship-conduct"
                    ref={conductRef}
                    type="text"
                    inputMode="numeric"
                    placeholder="VD: 85"
                    value={conductScore}
                    onChange={(e) => setConductScore(sanitizeInteger(e.target.value))}
                    onKeyDown={handleConductKeyDown}
                    className="scholarship-val-input"
                  />
                  <span className="scholarship-input-max">/ 100</span>
                </div>
                {conductError && <span className="scholarship-field-err">{conductError}</span>}
              </div>
              <div className="scholarship-credit-field">
                <label className="scholarship-input-label" htmlFor="scholarship-credits">
                  <span className="tool-step-badge">3</span><span>Tín chỉ đăng ký</span>
                </label>
              <div className="stepper-capsule">
                <button
                  type="button"
                  className="stepper-btn"
                  onClick={() => stepCredits(-1)}
                  aria-label="Giảm 1 tín chỉ"
                >
                  <Minus size={15} />
                </button>
                <input
                  id="scholarship-credits"
                  className="stepper-input"
                  value={credits}
                  onChange={(e) => setCredits(sanitizeInteger(e.target.value))}
                  aria-label="Số tín chỉ đăng ký"
                />
                <button
                  type="button"
                  className="stepper-btn"
                  onClick={() => stepCredits(1)}
                  aria-label="Tăng 1 tín chỉ"
                >
                  <Plus size={15} />
                </button>
              </div>
              </div>
            </div>
            <p className="scholarship-credit-note">Tối thiểu 15 TC · Học kỳ tốt nghiệp: {finalSemesterMin} TC</p>
            {isBelowMinimum && (
              <p className="scholarship-credits-warn" role="status">
                Cần tối thiểu {MIN_SCHOLARSHIP_CREDITS} TC để đủ điều kiện xét học bổng (học kỳ tốt nghiệp: {finalSemesterMin} TC).
              </p>
            )}

            {/* Ước tính số tiền nhận được */}
            <div className="scholarship-tuition-section">
              <div className="scholarship-tuition-head">
                <div>
                  <div className="scholarship-optional-heading"><span className="scholarship-tuition-title">Ước tính số tiền</span><span className="scholarship-optional-tag">Tùy chọn</span></div>
                  <span className="scholarship-tuition-sub">
                    Chọn ngành và năm học áp dụng.
                  </span>
                </div>
                <div className="scholarship-year-selector" role="group" aria-label="Năm học">
                  {SCHOLARSHIP_YEARS.map((y) => (
                    <button
                      key={y.id}
                      type="button"
                      className={`scholarship-year-btn ${schoolYear === y.id ? 'active' : ''}`}
                      onClick={() => setSchoolYear(y.id)}
                    >
                      {y.label}
                    </button>
                  ))}
                </div>
              </div>
              <ProgramSearch
                id={PROGRAM_INPUT_ID}
                label="Ngành đào tạo"
                query={query}
                selectedProgram={selectedProgram}
                onQueryChange={handleQueryChange}
                onSelect={selectProgram}
                onClear={clearProgram}
              />
            </div>
          </div>
        </div>

        {/* CỘT PHẢI (5 Cols): KẾT QUẢ XÉT HỌC BỔNG */}
        <div className="gpa-d-sticky-col">
          <div className="gpa-d-result-card" id="scholarship-result">
            {/* Header */}
            <div className="gpa-d-result-header">
              <span className="gpa-d-result-title">KẾT QUẢ XÉT HỌC BỔNG</span>
              {statusBadge}
            </div>

            {/* Hero Display trung tâm */}
            <div className="gpa-d-hero-score-box">
              <div className="gpa-d-hero-sub">HỌC BỔNG KHUYẾN KHÍCH DỰ KIẾN</div>
              <div className="gpa-d-hero-score-row" style={{ alignItems: 'baseline', gap: '0.5rem' }}>
                <span className="gpa-d-hero-score">
                  {result ? (result.classification ? `Loại ${result.classification}` : 'Chưa đạt') : '--'}
                </span>
                {result?.classification && (
                  <span className="scholarship-multiplier-tag">
                    × {result.multiplier === 1 ? '1.00' : result.multiplier}
                  </span>
                )}
              </div>
              <div className="gpa-d-gpa10-pill">
                {result ? (
                  <>
                    <span className="gpa-d-gpa10-label">Điểm xét học bổng:</span>
                    <span className="gpa-d-gpa10-val">{result.score.toFixed(3)} / 4.00</span>
                  </>
                ) : (
                  <span className="gpa-d-gpa10-label">Nhập GPA và điểm rèn luyện bên trái để xét</span>
                )}
              </div>
            </div>

            {/* Milestone Progress Bar + Gợi ý liền khối */}
            <div className="gpa-d-milestone-box">
              <ScholarshipConditions finalSemesterMin={finalSemesterMin} />
              <div className="scholarship-tier-names" aria-hidden="true">
                <span className="gpa-milestone-blue">Khá</span>
                <span className="gpa-milestone-green">Giỏi</span>
                <span className="gpa-milestone-amber">Xuất sắc</span>
              </div>
              <div className="scholarship-milestone-track" aria-hidden="true">
                <div className="gpa-d-milestone-bar-fill" style={{ width: `${(tierLevel / 3) * 100}%` }} />
                <span className="gpa-d-milestone-tick" style={{ left: '33.333%' }} />
                <span className="gpa-d-milestone-tick" style={{ left: '66.667%' }} />
              </div>
              <div className="gpa-d-milestone-prompt scholarship-smart-prompt">
                {renderSmartTip(false)}
              </div>
            </div>

            <div className="scholarship-amount-row">
              <div className="tool-result-detail-row">
                <span>Số tiền dự kiến</span>
                {amount !== null ? (
                  <span
                    className="gpa-d-stat-val"
                    style={{ fontSize: '0.86rem', color: '#059669' }}
                    title={`${creditCount} TC × ${formatVnd(perCredit)} × ${result?.multiplier}`}
                  >
                    {formatVnd(amount)}
                  </span>
                ) : selectedProgram ? (
                  <span className="gpa-d-stat-val" style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                    --
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => document.getElementById(PROGRAM_INPUT_ID)?.focus()}
                    className="scholarship-pick-program-link"
                  >
                    Chọn ngành
                  </button>
                )}
              </div>
            </div>

            {/* 1-Line Footer */}
            <div className="gpa-d-result-footer">
              <button
                type="button"
                className="gpa-d-footer-link"
                onClick={() => onAskChat(`Điều kiện xét học bổng khuyến khích học tập của ${cohort} là gì?`)}
              >
                <MessageCircle size={14} aria-hidden="true" />
                <span>Hỏi chatbot về quy chế học bổng</span>
              </button>
              <ShareResultButton text={shareText} className="gpa-d-footer-link" />
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
            <Award size={20} className="gpa-m-title-icon" aria-hidden="true" />
            <h1 className="gpa-m-page-title">Tính điểm học bổng</h1>
          </div>
          <button
            type="button"
            className="gpa-d-reset-btn"
            onClick={handleReset}
            title="Đặt lại thông số"
          >
            <RotateCcw size={12} />
            <span>Đặt lại</span>
          </button>
        </div>

        {/* Thẻ Hero Navy (3 tầng) */}
        <div className="gpa-mobile-hero-container">
          <div className="gpa-mobile-hero-card">
            <div className="gpa-m-hero-label">HỌC BỔNG KHUYẾN KHÍCH DỰ KIẾN</div>
            <div className="gpa-m-score-row" style={{ alignItems: 'baseline', gap: '0.45rem' }}>
              <span className="gpa-m-score-val" style={{ fontSize: '2.4rem' }}>
                {result ? (result.classification ? `Loại ${result.classification}` : 'Chưa đạt') : '--'}
              </span>
              {result?.classification && (
                <span style={{ fontSize: '1.1rem', fontWeight: 800, color: '#34d399' }}>
                  × {result.multiplier === 1 ? '1.00' : result.multiplier}
                </span>
              )}
            </div>
            <div className="gpa-m-capsule-wrap">
              <div className="gpa-m-capsule">
                {result ? (
                  <>
                    <span className="gpa-m-stat-item">
                      Điểm xét: <strong style={{ color: '#38bdf8' }}>{result.score.toFixed(3)}</strong>
                    </span>
                    <span className="gpa-m-bullet">•</span>
                    <span className="gpa-m-stat-item">
                      <strong style={{ color: '#ffffff' }}>{hasCredits ? creditCount : 0}</strong> TC
                    </span>
                  </>
                ) : (
                  <span className="gpa-m-stat-item" style={{ color: 'rgba(255,255,255,0.75)' }}>
                    Nhập GPA & điểm rèn luyện bên dưới
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="scholarship-mobile-conditions"><ScholarshipConditions finalSemesterMin={finalSemesterMin} /></div>

        {/* Gợi ý 1 dòng thông minh trên Mobile (chỉ hiển thị khi đã có kết quả tính toán) */}
        {result && (
          <div className="scholarship-m-prompt-box">
            {renderSmartTip(true)}
          </div>
        )}

        {/* Thẻ nhập liệu Mobile (Phẳng hoàn toàn, không card lồng card) */}
        <div className="scholarship-m-card scholarship-mobile-form">
          <div className="scholarship-m-card-header">
            <span className="scholarship-m-card-title">THÔNG TIN XÉT</span>
          </div>

          <div className="scholarship-input-grid">
            <div>
              <label className="scholarship-m-field-label" htmlFor="m-scholarship-gpa">
                <span className="tool-step-badge">1</span>
                <span>GPA học kỳ</span>
              </label>
              <div className={`scholarship-input-box ${academicError ? 'bad' : ''}`}>
                <input
                  id="m-scholarship-gpa"
                  type="text"
                  inputMode="decimal"
                  placeholder="VD: 3.50"
                  value={academicScore}
                  onChange={(e) => setAcademicScore(sanitizeDecimal(e.target.value))}
                  className="scholarship-val-input"
                />
                <span className="scholarship-input-max">/ 4.0</span>
              </div>
              {academicError && <span className="scholarship-field-err">{academicError}</span>}
            </div>

            <div>
              <label className="scholarship-m-field-label" htmlFor="m-scholarship-conduct">
                <span className="tool-step-badge">2</span>
                <span>Điểm rèn luyện</span>
              </label>
              <div className={`scholarship-input-box ${conductError ? 'bad' : ''}`}>
                <input
                  id="m-scholarship-conduct"
                  type="text"
                  inputMode="numeric"
                  placeholder="VD: 85"
                  value={conductScore}
                  onChange={(e) => setConductScore(sanitizeInteger(e.target.value))}
                  className="scholarship-val-input"
                />
                <span className="scholarship-input-max">/ 100</span>
              </div>
              {conductError && <span className="scholarship-field-err">{conductError}</span>}
            </div>
          </div>

          <div className="scholarship-m-credits-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="tool-step-badge">3</span>
              <div>
                <span className="scholarship-m-credits-title">Tín chỉ</span>
              </div>
            </div>
            <div className="stepper-capsule" >
              <button
                type="button"
                className="stepper-btn"

                onClick={() => stepCredits(-1)}
                aria-label="Giảm 1 tín chỉ"
              >
                <Minus size={14} />
              </button>
              <input
                className="stepper-input"

                value={credits}
                onChange={(e) => setCredits(sanitizeInteger(e.target.value))}
                aria-label="Số tín chỉ"
              />
              <button
                type="button"
                className="stepper-btn"

                onClick={() => stepCredits(1)}
                aria-label="Tăng 1 tín chỉ"
              >
                <Plus size={14} />
              </button>
            </div>
          </div>
          {isBelowMinimum && (
            <p className="scholarship-credits-warn" role="status">
              Cần tối thiểu {MIN_SCHOLARSHIP_CREDITS} TC để đủ điều kiện xét học bổng (học kỳ cuối: {finalSemesterMin} TC).
            </p>
          )}

          {/* Ước tính số tiền trên Mobile */}
          <div className="scholarship-m-tuition-section" aria-label="Ước tính số tiền học bổng, tùy chọn">
            <div className="scholarship-tuition-head">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="scholarship-m-tuition-title">Ước tính số tiền <span className="scholarship-optional-tag">· Tùy chọn</span></span>
              </div>
            </div>
            <div className="scholarship-mobile-year-row">
              <span className="scholarship-m-tuition-title">Năm học</span>
              <div className="scholarship-year-selector" role="group" aria-label="Năm học">
                {SCHOLARSHIP_YEARS.map((y) => (
                  <button
                    key={y.id}
                    type="button"
                    className={`scholarship-year-btn ${schoolYear === y.id ? 'active' : ''}`}
                    onClick={() => setSchoolYear(y.id)}
                  >
                    {y.label}
                  </button>
                ))}
              </div>
            </div>
            <ProgramSearch
              id={PROGRAM_INPUT_MOBILE_ID}
              placeholder="Tìm ngành hoặc mã ngành"
              label="Ngành đào tạo"
              query={query}
              selectedProgram={selectedProgram}
              onQueryChange={handleQueryChange}
              onSelect={selectProgram}
              onClear={clearProgram}
            />

            {/* Khi tính được tiền, hiển thị dòng tiền dự kiến ngay tại đây */}
            {amount !== null && (
              <div className="scholarship-m-money-badge">
                <div className="scholarship-m-money-row">
                  <span className="scholarship-m-money-label">Số tiền dự kiến:</span>
                  <strong className="scholarship-m-money-val">{formatVnd(amount)}</strong>
                </div>
                <div className="scholarship-m-money-formula">
                  {creditCount} TC × {formatVnd(perCredit)} × {result?.multiplier}
                </div>
              </div>
            )}
          </div>
        </div>


      </div>
    </div>
  );
}
