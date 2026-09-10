import { useMemo, useState } from 'react';
import {
  Award,
  RotateCcw,
  Search,
  X,
  Check,
  Sparkles,
} from 'lucide-react';
import {
  calculateScholarshipScore,
  getScholarshipTierDetails,
} from '../../utils/scholarship';
import {
  SCHOOL_YEARS,
  searchTuitionPrograms,
  type SchoolYear,
  type TuitionProgram,
} from '../../data/tuitionRates';
import { PageContextBadges } from '../PageContextBadges';

const PRESETS: Array<{ label: string; academic: string; conduct: string }> = [
  { label: 'Xuất sắc (3.70 / 92)', academic: '3.70', conduct: '92' },
  { label: 'Giỏi (3.35 / 85)', academic: '3.35', conduct: '85' },
  { label: 'Khá (2.85 / 75)', academic: '2.85', conduct: '75' },
];

export function ScholarshipPage() {
  const [academicScore, setAcademicScore] = useState('');
  const [conductScore, setConductScore] = useState('');
  const [credits, setCredits] = useState('15');

  const [query, setQuery] = useState('');
  const [selectedProgram, setSelectedProgram] = useState<TuitionProgram | null>(null);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [schoolYear, setSchoolYear] = useState<SchoolYear | ''>('2024-2025');

  const suggestions = useMemo(() => searchTuitionPrograms(query), [query]);

  const handleQueryChange = (value: string) => {
    setQuery(value);
    if (selectedProgram && `${selectedProgram.code} - ${selectedProgram.name}` !== value) {
      setSelectedProgram(null);
    }
  };

  const selectProgram = (program: TuitionProgram) => {
    setSelectedProgram(program);
    setQuery(`${program.code} - ${program.name}`);
    setFocusedIndex(-1);
  };

  const clearProgram = () => {
    setSelectedProgram(null);
    setQuery('');
    setFocusedIndex(-1);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!query || selectedProgram || suggestions.length === 0) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setFocusedIndex((prev) => (prev < suggestions.length - 1 ? prev + 1 : prev));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setFocusedIndex((prev) => (prev > 0 ? prev - 1 : prev));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (focusedIndex >= 0 && focusedIndex < suggestions.length) {
        selectProgram(suggestions[focusedIndex]);
      }
    }
  };

  const tuitionFee = schoolYear && selectedProgram ? selectedProgram.perCredit[schoolYear] ?? 0 : 0;

  const numAcademic = academicScore !== '' ? Number(academicScore) : null;
  const numConduct = conductScore !== '' ? Number(conductScore) : null;

  const isAcademicInvalid =
    numAcademic !== null && (!Number.isFinite(numAcademic) || numAcademic < 0 || numAcademic > 4);
  const isConductInvalid =
    numConduct !== null && (!Number.isFinite(numConduct) || numConduct < 0 || numConduct > 100);
  const isCreditsInvalid =
    credits !== '' && (!Number.isFinite(Number(credits)) || Number(credits) <= 0);
  const isCreditsBelowMinimum =
    credits !== '' && Number(credits) > 0 && Number(credits) < 15;

  const result = useMemo(() => {
    if (numAcademic === null || numConduct === null || isAcademicInvalid || isConductInvalid) {
      return null;
    }
    return calculateScholarshipScore(numAcademic, numConduct);
  }, [numAcademic, numConduct, isAcademicInvalid, isConductInvalid]);

  const tierDetails = useMemo(() => {
    return getScholarshipTierDetails(
      !isAcademicInvalid ? numAcademic : null,
      !isConductInvalid ? numConduct : null,
      result?.score ?? null
    );
  }, [numAcademic, numConduct, result, isAcademicInvalid, isConductInvalid]);

  const scholarshipAmount = useMemo(() => {
    if (
      !result?.classification ||
      !credits ||
      tuitionFee === 0 ||
      isCreditsInvalid ||
      isCreditsBelowMinimum
    ) {
      return null;
    }
    return Number(credits) * tuitionFee * result.multiplier;
  }, [result, credits, tuitionFee, isCreditsInvalid, isCreditsBelowMinimum]);

  const handleReset = () => {
    setAcademicScore('');
    setConductScore('');
    setCredits('15');
    setSelectedProgram(null);
    setQuery('');
  };

  const applyPreset = (academic: string, conduct: string) => {
    setAcademicScore(academic);
    setConductScore(conduct);
  };

  // Smart suggestion for next tier
  const nextTierAdvice = useMemo(() => {
    if (!result) return null;
    if (result.classification === 'Xuất sắc') {
      return '🎉 Bạn đã đạt mức học bổng cao nhất (Xuất sắc - Hệ số 1.5x)!';
    }

    if (result.classification === 'Giỏi') {
      const neededScore = 3.6;
      const neededConduct = 90;
      const curScore = result.score;
      const curConduct = numConduct ?? 0;
      const reasons: string[] = [];
      if (curScore < neededScore) reasons.push(`điểm xét ≥ 3.60 (hiện tại: ${curScore.toFixed(2)})`);
      if (curConduct < neededConduct) reasons.push(`điểm rèn luyện ≥ 90 (hiện tại: ${curConduct})`);
      return `💡 Để nâng lên mức Xuất sắc (1.5x), bạn cần: ${reasons.join(' và ')}.`;
    }

    if (result.classification === 'Khá') {
      const neededScore = 3.2;
      const neededConduct = 80;
      const curScore = result.score;
      const curConduct = numConduct ?? 0;
      const reasons: string[] = [];
      if (curScore < neededScore) reasons.push(`điểm xét ≥ 3.20 (hiện tại: ${curScore.toFixed(2)})`);
      if (curConduct < neededConduct) reasons.push(`điểm rèn luyện ≥ 80 (hiện tại: ${curConduct})`);
      return `💡 Để nâng lên mức Giỏi (1.25x), bạn cần: ${reasons.join(' và ')}.`;
    }

    // Chưa đạt
    return '💡 Cần đạt tối thiểu Điểm xét ≥ 2.56, Học tập ≥ 2.50 và Rèn luyện ≥ 70 để đạt học bổng Khá.';
  }, [result, numConduct]);

  return (
    <div className="page-container tool-page">
      {/* Page Header */}
      <header className="gpa-page-header">
        <div className="gpa-page-header-text">
          <h1 className="gpa-page-title">
            <Award className="gpa-page-title-icon" size={32} />
            Tính điểm học bổng
          </h1>
          <p className="gpa-page-subtitle">
            Tính điểm xét học bổng khuyến khích học tập và ước tính số tiền theo quy chế HCMUE.
          </p>
          <PageContextBadges
            schoolYear={schoolYear || undefined}
            source="Công thức học bổng và bảng học phí"
            advisory
          />
        </div>
      </header>

      {/* Main Split Layout */}
      <div className="scholarship-split-layout">
        {/* Left Column: Input Form */}
        <section className="scholarship-main-column">
          {/* Top Toolbar */}
          <div className="gpa-toolbar">
            <div className="gpa-mode-control">
              <span className="gpa-mode-label">Thông tin xét tuyển:</span>
              <div className="scholarship-preset-chips">
                <span className="scholarship-preset-icon"><Sparkles size={13} /> Mẫu:</span>
                {PRESETS.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    className="scholarship-preset-chip"
                    onClick={() => applyPreset(p.academic, p.conduct)}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="gpa-action-buttons">
              <button
                type="button"
                className="tool-btn gpa-reset-btn gpa-btn-sm"
                onClick={handleReset}
                title="Khôi phục mặc định"
              >
                <RotateCcw size={14} />
                <span>Làm mới</span>
              </button>
            </div>
          </div>

          {/* Card 1: Điểm học tập & Rèn luyện */}
          <div className="scholarship-form-card">
            <div className="scholarship-card-title-row">
              <span className="scholarship-step-num">1</span>
              <div>
                <h2 className="scholarship-card-title">Điểm xét học bổng</h2>
                <p className="scholarship-card-subtitle">
                  Tỷ lệ: 80% Điểm học tập + 20% Điểm rèn luyện quy đổi
                </p>
              </div>
            </div>

            <div className="scholarship-inputs-grid">
              {/* Điểm học tập */}
              <div className="scholarship-input-group">
                <label className="scholarship-input-label">
                  Điểm học tập (GPA)
                  <span className="scholarship-sub-label weight-tag">80%</span>
                </label>
                <div className="course-target-input-wrap">
                  <input
                    type="text"
                    inputMode="decimal"
                    value={academicScore}
                    onChange={(e) => {
                      const val = e.target.value.replace(',', '.');
                      if (val === '' || /^[0-9.]*$/.test(val)) setAcademicScore(val);
                    }}
                    className={`course-target-input ${isAcademicInvalid ? 'input-error' : ''}`}
                    placeholder="VD: 3.50"
                  />
                  <span className="course-target-affix">/ 4.0</span>
                </div>
                {isAcademicInvalid && (
                  <span className="scholarship-field-error">Điểm phải từ 0.0 đến 4.0</span>
                )}
              </div>

              {/* Điểm rèn luyện */}
              <div className="scholarship-input-group">
                <label className="scholarship-input-label">
                  Điểm rèn luyện (ĐRL)
                  <span className="scholarship-sub-label weight-tag">20%</span>
                </label>
                <div className="course-target-input-wrap">
                  <input
                    type="text"
                    inputMode="numeric"
                    value={conductScore}
                    onChange={(e) => {
                      const val = e.target.value.replace(',', '.');
                      if (val === '' || /^[0-9]*$/.test(val)) setConductScore(val);
                    }}
                    className={`course-target-input ${isConductInvalid ? 'input-error' : ''}`}
                    placeholder="VD: 85"
                  />
                  <span className="course-target-affix">/ 100</span>
                </div>
                {isConductInvalid && (
                  <span className="scholarship-field-error">Điểm rèn luyện từ 0 đến 100</span>
                )}
              </div>
            </div>
          </div>

          {/* Card 2: Giá trị học bổng (Ngành học & Tín chỉ) */}
          <div className="scholarship-form-card">
            <div className="scholarship-card-title-row">
              <span className="scholarship-step-num">2</span>
              <div>
                <h2 className="scholarship-card-title">Ước tính số tiền học bổng</h2>
                <p className="scholarship-card-subtitle">
                  Học bổng = Đơn giá tín chỉ × Số tín chỉ × Hệ số mức thưởng
                </p>
              </div>
            </div>

            {/* Autocomplete ngành học */}
            <div className="scholarship-input-group">
              <label className="scholarship-input-label">
                Tìm ngành học để tra đơn giá tín chỉ
              </label>
              <div className="scholarship-search-box">
                <Search size={16} className="scholarship-search-icon" />
                <input
                  type="text"
                  className="scholarship-search-input"
                  value={query}
                  onChange={(e) => {
                    handleQueryChange(e.target.value);
                    setFocusedIndex(-1);
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="Nhập tên ngành hoặc mã ngành (VD: Sư phạm Toán, CNTT)..."
                />
                {query && (
                  <button
                    type="button"
                    className="scholarship-clear-btn"
                    onClick={clearProgram}
                    aria-label="Xóa tìm kiếm"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>

              {query && !selectedProgram && (
                <div className="scholarship-autocomplete-dropdown">
                  {suggestions.length > 0 ? (
                    suggestions.map((prog, idx) => (
                      <button
                        key={`${prog.code}-${prog.name}`}
                        type="button"
                        className={`scholarship-suggestion-item ${
                          idx === focusedIndex ? 'focused' : ''
                        }`}
                        onClick={() => selectProgram(prog)}
                      >
                        <span className="prog-name">{prog.name}</span>
                        <span className="prog-code">{prog.code}</span>
                      </button>
                    ))
                  ) : (
                    <div className="scholarship-suggestion-empty">
                      Không tìm thấy ngành phù hợp. Vui lòng chọn ngành trong danh sách gợi ý.
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Form grid: Năm học & Tín chỉ */}
            <div className="scholarship-inputs-grid">
              <div className="scholarship-input-group">
                <label className="scholarship-input-label">Năm học áp dụng</label>
                <select
                  className="course-target-select"
                  value={schoolYear}
                  onChange={(e) => setSchoolYear(e.target.value as SchoolYear)}
                >
                  {SCHOOL_YEARS.map((y) => (
                    <option key={y} value={y}>
                      Năm học {y}
                    </option>
                  ))}
                </select>
              </div>

              <div className="scholarship-input-group">
                <label className="scholarship-input-label">
                  Số tín chỉ học kỳ
                  <span className="scholarship-highlight-badge">
                    ⚡ Tối thiểu 15 TC
                  </span>
                </label>
                <div className="course-target-input-wrap">
                  <input
                    type="number"
                    min="1"
                    value={credits}
                    onChange={(e) => setCredits(e.target.value)}
                    className={`course-target-input ${
                      isCreditsInvalid || isCreditsBelowMinimum ? 'input-warning' : ''
                    }`}
                    placeholder="15"
                  />
                  <span className="course-target-affix">TC</span>
                </div>
                {isCreditsBelowMinimum ? (
                  <span className="scholarship-field-warning">
                    ⚠️ Dưới 15 tín chỉ: Không đủ điều kiện xét học bổng (trừ HK tốt nghiệp tối thiểu 6 TC).
                  </span>
                ) : (
                  <span className="scholarship-field-hint-text">
                    Đăng ký tối thiểu 15 TC/kỳ (HK cuối: 6 TC) & không có môn điểm F.
                  </span>
                )}
              </div>
            </div>

            {/* Tuition Rate Display Strip */}
            {selectedProgram && schoolYear && (
              <div className="scholarship-tuition-strip">
                <span className="strip-label">Đơn giá 1 tín chỉ ({schoolYear}):</span>
                <strong className="strip-value">
                  {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(
                    tuitionFee
                  )}
                </strong>
              </div>
            )}
          </div>
        </section>

        {/* Right Column: Sticky Scholarship Result Card */}
        <aside className="scholarship-summary-card">
          {/* Header */}
          <div className="gpa-result-top">
            <div className="gpa-result-tag-wrap">
              <span className="gpa-live-dot" />
              <span className="gpa-result-tag">KẾT QUẢ XÉT HỌC BỔNG</span>
            </div>
            <span
              className={`gpa-cohort-pill ${
                result?.classification ? 'scholarship-badge-active' : ''
              }`}
            >
              {result?.multiplier ? `Hệ số: ${result.multiplier}x` : 'Chưa xếp loại'}
            </span>
          </div>

          {/* Symmetrical Stat Grid */}
          <div className="course-target-stats-grid">
            <div className="gpa-stat-box">
              <span className="gpa-stat-label">Điểm xét học bổng</span>
              <strong className="gpa-stat-val">
                {result ? result.score.toFixed(3) : '--'}
              </strong>
            </div>
            <div className="gpa-stat-box">
              <span className="gpa-stat-label">Xếp loại dự kiến</span>
              <strong
                className="gpa-stat-val"
                style={{
                  color:
                    result?.classification === 'Xuất sắc'
                      ? '#ec4899'
                      : result?.classification === 'Giỏi'
                      ? '#8b5cf6'
                      : result?.classification === 'Khá'
                      ? '#3b82f6'
                      : undefined,
                }}
              >
                {result?.classification ? `Loại ${result.classification}` : 'Chưa đạt'}
              </strong>
            </div>
          </div>

          {/* Amount Estimated Banner */}
          {isCreditsBelowMinimum && result?.classification ? (
            <div className="scholarship-amount-card warning">
              <span className="amount-label">Số tiền học bổng</span>
              <strong className="amount-warning-text">Chưa đủ 15 tín chỉ</strong>
              <span className="amount-formula">
                Quy chế HCMUE yêu cầu tối thiểu 15 TC trong học kỳ xét (trừ HK cuối: 6 TC)
              </span>
            </div>
          ) : scholarshipAmount !== null ? (
            <div className="scholarship-amount-card">
              <span className="amount-label">Số tiền học bổng dự kiến</span>
              <strong className="amount-value">
                {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(
                  scholarshipAmount
                )}
              </strong>
              <span className="amount-formula">
                {credits} TC ×{' '}
                {new Intl.NumberFormat('vi-VN').format(tuitionFee)} đ × {result?.multiplier}x
              </span>
            </div>
          ) : (
            selectedProgram &&
            schoolYear &&
            result?.classification && (
              <div className="scholarship-amount-placeholder">
                <span>Nhập số tín chỉ để tính số tiền dự kiến.</span>
              </div>
            )
          )}

          {/* Criteria Checklist Matrix Table */}
          <div className="scholarship-matrix-wrapper">
            <div className="scholarship-matrix-header">
              <span className="matrix-title">TIÊU CHUẨN XÉT THEO QUY CHẾ</span>
            </div>
            <div className="scholarship-table-container">
              <div className="scholarship-table-head">
                <span className="th-tier">Mức</span>
                <span className="th-stat">Đ.Xét</span>
                <span className="th-stat">GPA</span>
                <span className="th-stat">ĐRL</span>
                <span className="th-status">Kết quả</span>
              </div>
              <div className="scholarship-table-body">
                {tierDetails.map((tier) => (
                  <div
                    key={tier.label}
                    className={`scholarship-table-row ${
                      result?.classification === tier.label ? 'achieved' : ''
                    }`}
                  >
                    <div className="td-tier">
                      <span
                        className="tier-mini-badge"
                        style={{ backgroundColor: tier.badgeColor }}
                      >
                        {tier.label.charAt(0)}
                      </span>
                      <div className="tier-meta">
                        <strong className="tier-name">{tier.label}</strong>
                        <span className="tier-mult">{tier.multiplier}x</span>
                      </div>
                    </div>

                    <div className={`td-stat ${tier.isScoreMet ? 'met' : ''}`}>
                      {tier.isScoreMet ? (
                        <span className="stat-met">
                          <Check size={10} /> {tier.minScholarshipScore.toFixed(2)}
                        </span>
                      ) : (
                        <span className="stat-req">≥ {tier.minScholarshipScore.toFixed(2)}</span>
                      )}
                    </div>

                    <div className={`td-stat ${tier.isAcademicMet ? 'met' : ''}`}>
                      {tier.isAcademicMet ? (
                        <span className="stat-met">
                          <Check size={10} /> {tier.minAcademicScore.toFixed(2)}
                        </span>
                      ) : (
                        <span className="stat-req">≥ {tier.minAcademicScore.toFixed(2)}</span>
                      )}
                    </div>

                    <div className={`td-stat ${tier.isConductMet ? 'met' : ''}`}>
                      {tier.isConductMet ? (
                        <span className="stat-met">
                          <Check size={10} /> {tier.minConductScore}
                        </span>
                      ) : (
                        <span className="stat-req">≥ {tier.minConductScore}</span>
                      )}
                    </div>

                    <div className="td-status">
                      {tier.isFullyMet ? (
                        <span className="tier-tag achieved">ĐẠT 🎉</span>
                      ) : (
                        <span className="tier-tag unmet">Chưa đủ</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Actionable Advice Message */}
          {nextTierAdvice && (
            <div className="scholarship-advice-box">
              <span className="advice-text">{nextTierAdvice}</span>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

