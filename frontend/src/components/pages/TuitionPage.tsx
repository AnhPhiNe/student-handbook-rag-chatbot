import { useState } from 'react';
import { Calculator, GraduationCap, MessageCircle, Minus, Plus } from 'lucide-react';
import {
  SCHOOL_YEARS,
  formatVnd,
  type SchoolYear,
  type TuitionProgram,
} from '../../data/tuitionRates';
import { estimateSemester, isTeacherTraining } from '../../utils/tuition';
import { sanitizeInteger } from '../../utils/numberInput';
import { ShareResultButton } from '../tool/ShareResultButton';
import { tuitionShareText } from '../../utils/shareText';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton } from '../tool/ToolSection';
import { ProgramSearch } from '../tool/ProgramSearch';

interface TuitionPageProps {
  onAskChat: (text: string) => void;
}

const DEFAULT_YEAR: SchoolYear = SCHOOL_YEARS[SCHOOL_YEARS.length - 1];
const MAX_RETAKE_CREDITS = 99;
const DECREE_116_QUESTION = 'Chính sách hỗ trợ học phí và sinh hoạt phí theo Nghị định 116 cho sinh viên sư phạm là gì?';

/** Amount without the trailing " đ" that formatVnd adds, so the unit can be styled apart. */
const plainAmount = (value: number) => formatVnd(value).replace(/\s*đ$/, '');

export function TuitionPage({ onAskChat }: TuitionPageProps) {
  const [query, setQuery] = useState('');
  const [selectedProgram, setSelectedProgram] = useState<TuitionProgram | null>(null);
  const [schoolYear, setSchoolYear] = useState<SchoolYear>(DEFAULT_YEAR);
  const [retake, setRetake] = useState('0');

  const retakeCredits = Number(retake) || 0;
  const estimate = selectedProgram ? estimateSemester(selectedProgram, schoolYear, retakeCredits) : null;
  const hasRetake = Boolean(estimate && estimate.extra > 0);
  const teacherTraining = Boolean(selectedProgram && isTeacherTraining(selectedProgram.code));

  const shareText =
    estimate && selectedProgram
      ? tuitionShareText({
          total: estimate.total,
          semester: estimate.semester,
          extra: estimate.extra,
          programName: selectedProgram.name,
          year: schoolYear.replace('-20', '–'),
        })
      : null;

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
    clearProgram();
    setSchoolYear(DEFAULT_YEAR);
    setRetake('0');
  };

  const stepRetake = (delta: number) => {
    setRetake(String(Math.min(MAX_RETAKE_CREDITS, Math.max(0, retakeCredits + delta))));
  };

  const setRetakeExact = (delta: number) => {
    setRetake(String(Math.min(MAX_RETAKE_CREDITS, Math.max(0, retakeCredits + delta))));
  };

  // Reusable Form Controls for Desktop & Mobile
  const renderFormInputs = (isMobile: boolean) => (
    <div className="tu-inputs-inner">
      <div className="tu-field-group">
        <label className="tu-field-label" htmlFor={isMobile ? 'tuition-program-m' : 'tuition-program'}>
          <span className="tu-step-badge">1</span>
          <span>Ngành đào tạo</span>
        </label>
        <ProgramSearch
          id={isMobile ? 'tuition-program-m' : 'tuition-program'}
          label=""
          query={query}
          selectedProgram={selectedProgram}
          onQueryChange={handleQueryChange}
          onSelect={selectProgram}
          onClear={clearProgram}
        />
      </div>

      <div className="tu-field-group">
        <div className="tu-field-label" id={isMobile ? 'tu-year-label-m' : 'tu-year-label'}>
          <span className="tu-step-badge">2</span>
          <span>Năm học áp dụng</span>
        </div>
        <div className="sc-years" role="group" aria-labelledby={isMobile ? 'tu-year-label-m' : 'tu-year-label'}>
          {SCHOOL_YEARS.map((year) => (
            <button key={year} type="button" aria-pressed={year === schoolYear} onClick={() => setSchoolYear(year)}>
              {year.replace('-20', '–')}
            </button>
          ))}
        </div>
      </div>

      <div className="tu-field-group">
        <div className="tu-field-label">
          <span className="tu-step-badge">3</span>
          <span>Tín chỉ học lại / cải thiện</span>
        </div>
        <div className="tu-retake-row">
          <div className="tu-retake-info">
            <label htmlFor={isMobile ? 'tuition-retake-m' : 'tuition-retake'} className="tu-retake-title">
              Số tín chỉ đăng ký học lại
            </label>
            <span className="tu-retake-sub">
              {estimate ? `Đơn giá: ${formatVnd(estimate.perCredit)} / TC` : 'Đơn giá tính theo tín chỉ'}
            </span>
          </div>
          <div className="tu-retake-controls">
            <div style={{ display: 'flex', gap: '6px' }}>
              <button type="button" className="tu-chip-btn" onClick={() => setRetakeExact(3)}>
                +3 TC
              </button>
              <button type="button" className="tu-chip-btn" onClick={() => setRetakeExact(6)}>
                +6 TC
              </button>
            </div>
            <div className="tu-compact-stepper">
              <button type="button" className="tu-step-btn" onClick={() => stepRetake(-1)} aria-label="Giảm số tín chỉ">
                <Minus size={14} aria-hidden="true" />
              </button>
              <input
                id={isMobile ? 'tuition-retake-m' : 'tuition-retake'}
                className="tu-step-input"
                type="text"
                inputMode="numeric"
                maxLength={2}
                value={retake}
                onChange={(e) => setRetake(sanitizeInteger(e.target.value))}
                onBlur={() => setRetake(String(retakeCredits))}
              />
              <button type="button" className="tu-step-btn" onClick={() => stepRetake(1)} aria-label="Tăng số tín chỉ">
                <Plus size={14} aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {teacherTraining && (
        <div className="tu-nd116-box">
          <GraduationCap size={18} aria-hidden="true" className="tu-nd116-icon" />
          <div>
            <div>
              🎓 <b>Lưu ý sinh viên Sư phạm:</b> Nếu được duyệt hưởng <b>Nghị định 116</b>, bạn sẽ được Nhà nước hỗ trợ 100% học phí chính thức và 3,63 triệu đồng/tháng sinh hoạt phí (có điều kiện bồi hoàn).
            </div>
            <button type="button" className="tu-nd116-ask" onClick={() => onAskChat(DECREE_116_QUESTION)}>
              <MessageCircle size={13} aria-hidden="true" />
              Hỏi chatbot về Nghị định 116
            </button>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="page-container tool-page simplified gpa-page-wrapper sc-page tu-page">
      <ToolPageHeader
        icon={Calculator}
        title="Ước tính học phí"
        description="Tra học phí học kỳ theo ngành và năm học, cộng thêm tín chỉ học lại nếu có."
      />

      {/* =========================================================================
          DESKTOP VIEW (.gpa-desktop-layout)
          ========================================================================= */}
      <div className="gpa-desktop-layout">
        {/* CỘT TRÁI: THIẾT LẬP */}
        <div className="gpa-d-table-card">
          <div className="gpa-d-toolbar">
            <div className="gpa-d-toolbar-title">
              <span className="gpa-d-table-heading">THIẾT LẬP HỌC PHÍ</span>
            </div>
            <ResetButton onClick={handleReset} />
          </div>
          <div className="tu-card-body">
            {renderFormInputs(false)}
          </div>
        </div>

        {/* CỘT PHẢI: KẾT QUẢ HERO & THỐNG KÊ */}
        <div className="gpa-d-sticky-col">
          <div className="gpa-d-result-card" id="tuition-result">
            <div className="gpa-d-result-header">
              <span className="gpa-d-result-title">KẾT QUẢ HỌC PHÍ</span>
              <span className={`gpa-d-result-badge ${estimate ? 'tier-success' : 'unranked'}`}>
                {estimate ? '• Đã tính' : '• Chờ chọn ngành'}
              </span>
            </div>

            {/* Hero Navy Display chuẩn 3 tầng */}
            <div className="gpa-d-hero-score-box" style={{ padding: '1.25rem 1rem 1rem' }}>
              <div className="gpa-d-hero-sub">
                {hasRetake ? 'TỔNG HỌC PHÍ HỌC KỲ' : 'HỌC PHÍ 1 HỌC KỲ CHÍNH'}
              </div>
              <div className="gpa-d-hero-score-row" style={{ alignItems: 'baseline', gap: '0.45rem', justifyContent: 'center' }}>
                {estimate ? (
                  <>
                    <span className="gpa-d-hero-score" style={{ fontSize: '2.1rem' }}>
                      {plainAmount(estimate.total)}
                    </span>
                    <span className="gpa-d-hero-score-unit" style={{ fontSize: '1.1rem', fontWeight: 700, color: '#94a3b8' }}>
                      đ
                    </span>
                  </>
                ) : (
                  <span className="gpa-d-hero-score" style={{ fontSize: '2.1rem', color: '#64748b' }}>
                    --
                  </span>
                )}
              </div>
              <div className="gpa-d-gpa10-pill">
                <span className="gpa-d-gpa10-label">
                  {estimate ? (
                    `Năm học ${schoolYear.replace('-20', '–')}`
                  ) : (
                    'Chọn ngành đào tạo bên trái để tính'
                  )}
                </span>
              </div>
            </div>

            {estimate && (
              <div className="tu-result-breakdown">
                {hasRetake && (
                  <div className="tool-result-detail-row">
                    <span>Học phí kỳ chính</span>
                    <strong>{formatVnd(estimate.semester)}</strong>
                  </div>
                )}
                {hasRetake && (
                  <div className="tool-result-detail-row">
                    <span>Học lại / cải thiện</span>
                    <strong>+ {formatVnd(estimate.extra)}</strong>
                  </div>
                )}
                <details className="tool-result-details">
                  <summary>Chi tiết học phí</summary>
                  <div className="tool-result-detail-row">
                    <span>Học phí cả năm</span>
                    <strong>{formatVnd(estimate.annual)}</strong>
                  </div>
                  <div className="tool-result-detail-row">
                    <span>Đơn giá học lại</span>
                    <strong>{formatVnd(estimate.perCredit)} / TC</strong>
                  </div>
                </details>
              </div>
            )}

            <p className="tu-foot">
              * Mức học phí thực tế theo thông báo từng học kỳ của trường. Chưa bao gồm các khoản thu khác (nếu có).
            </p>

            {shareText && (
              <div className="sc-foot tu-share-footer">
                <ShareResultButton text={shareText} className="sc-link" />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* =========================================================================
          MOBILE VIEW (.gpa-mobile-layout)
          ========================================================================= */}
      <div className="gpa-mobile-layout">
        <div className="gpa-m-page-header">
          <div className="gpa-m-title-wrap">
            <Calculator size={18} aria-hidden="true" className="gpa-m-title-icon" />
            <h1 className="gpa-m-page-title">Ước tính học phí</h1>
          </div>
        </div>

        {/* Mobile Hero Card: 3 Tầng Chuẩn Navy, đồng nhất với các công cụ khác */}
        <div className="gpa-mobile-hero-container">
          <div className="gpa-mobile-hero-card" aria-label="Kết quả học phí">
            <span className="gpa-m-hero-label">
              {hasRetake ? 'TỔNG HỌC PHÍ HỌC KỲ' : 'HỌC PHÍ 1 HỌC KỲ CHÍNH'}
            </span>
            <div className="gpa-m-score-row" style={{ justifyContent: 'center' }}>
              {estimate ? (
                <>
                  <span className="gpa-m-score-val" style={{ fontSize: '1.9rem' }}>{plainAmount(estimate.total)}</span>
                  <span className="gpa-m-score-scale" style={{ fontSize: '1rem', fontWeight: 600, color: '#94a3b8' }}>đ</span>
                </>
              ) : (
                <span className="gpa-m-score-val" style={{ fontSize: '1.9rem' }}>--</span>
              )}
            </div>
            <div className="gpa-m-capsule-wrap">
              {estimate ? (
                <div className="gpa-m-capsule" style={{ background: 'rgba(255, 255, 255, 0.12)', border: '1px solid rgba(255, 255, 255, 0.18)' }}>
                  <span className="gpa-m-stat-item">
                    {hasRetake
                      ? `Kỳ ${plainAmount(estimate.semester)} đ + học lại ${plainAmount(estimate.extra)} đ`
                      : `Năm học ${schoolYear.replace('-20', '–')}`}
                  </span>
                </div>
              ) : (
                <div className="gpa-m-capsule empty">
                  <span className="gpa-m-stat-item" style={{ color: 'rgba(255,255,255,0.75)' }}>
                    Chọn ngành đào tạo bên dưới
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Mobile Secondary Stats */}
        {estimate && (
          <div className="tu-stats-grid" style={{ margin: '10px 0 14px' }}>
            <div className="tu-stat-card">
              <span className="tu-stat-label">Học phí cả năm</span>
              <span className="tu-stat-val">{formatVnd(estimate.annual)}</span>
            </div>
            <div className="tu-stat-card">
              <span className="tu-stat-label">Học lại / TC</span>
              <span className="tu-stat-val">{formatVnd(estimate.perCredit)}</span>
            </div>
          </div>
        )}

        {/* Mobile Input Card */}
        <div className="scholarship-m-card tu-m-card" style={{ marginTop: '10px' }}>
          <div className="scholarship-m-card-header">
            <span className="scholarship-m-card-title">THIẾT LẬP HỌC PHÍ</span>
            <ResetButton onClick={handleReset} />
          </div>
          <div className="tu-card-body-mobile">
            {renderFormInputs(true)}
          </div>
        </div>

        <p className="tu-foot" style={{ marginTop: '10px', textAlign: 'center' }}>
          * Số thực tế theo thông báo chính thức của trường.
        </p>

        {shareText && (
          <div style={{ marginTop: '14px', display: 'flex', justifyContent: 'center' }}>
            <ShareResultButton text={shareText} className="sc-link" />
          </div>
        )}
      </div>
    </div>
  );
}
