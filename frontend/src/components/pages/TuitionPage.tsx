import { useMemo, useState } from 'react';
import {
  Minus,
  Plus,
  Calculator,
  Search,
  RotateCcw,
  X,
} from 'lucide-react';
import {
  SCHOOL_YEARS,
  formatVnd,
  searchTuitionPrograms,
  type SchoolYear,
  type TuitionProgram,
} from '../../data/tuitionRates';
import { PageContextBadges } from '../PageContextBadges';

export function TuitionPage() {
  const [query, setQuery] = useState('');
  const [selectedProgram, setSelectedProgram] = useState<TuitionProgram | null>(null);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [schoolYear, setSchoolYear] = useState<SchoolYear | ''>('2024-2025');
  const [credits, setCredits] = useState('15');

  const suggestions = useMemo(() => searchTuitionPrograms(query), [query]);
  const creditCount = Number(credits);
  const hasValidCredits = Number.isFinite(creditCount) && creditCount > 0;

  const handleIncrement = () => setCredits((prev) => (Math.max(0, Number(prev || 0)) + 1).toString());
  const handleDecrement = () => setCredits((prev) => Math.max(0, Number(prev || 0) - 1).toString());

  const handleReset = () => {
    setQuery('');
    setSelectedProgram(null);
    setFocusedIndex(-1);
    setSchoolYear('2024-2025');
    setCredits('15');
  };

  const handleQueryChange = (val: string) => {
    setQuery(val);
    if (selectedProgram && `${selectedProgram.code} - ${selectedProgram.name}` !== val) {
      setSelectedProgram(null);
    }
  };

  const clearQuery = () => {
    setQuery('');
    setSelectedProgram(null);
    setFocusedIndex(-1);
  };

  const selectProgram = (program: TuitionProgram) => {
    setSelectedProgram(program);
    setQuery(`${program.code} - ${program.name}`);
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
      if (focusedIndex >= 0 && suggestions.length > 0 && focusedIndex < suggestions.length) {
        selectProgram(suggestions[focusedIndex]);
      }
    }
  };

  const annual = schoolYear && selectedProgram ? selectedProgram.annual[schoolYear] ?? 0 : 0;
  const semester = annual / 2;
  const perCredit = schoolYear && selectedProgram ? selectedProgram.perCredit[schoolYear] ?? 0 : 0;
  const creditEstimate = hasValidCredits ? perCredit * creditCount : 0;

  return (
    <div className="page-container tool-page">
      {/* Header */}
      <div className="page-header">
        <h1 className="page-title-with-icon">
          <Calculator aria-hidden="true" />
          <span>Ước tính học phí</span>
        </h1>
        <p>Tra theo bảng học phí theo ngành và năm học, sau đó ước tính học kỳ hoặc số tín chỉ đăng ký.</p>
        <PageContextBadges schoolYear={schoolYear || undefined} source="Bảng học phí theo ngành" advisory />
      </div>

      {/* Main Split Layout: Form -> Result Card -> Notes */}
      <div className="tuition-split-layout">
        {/* Form Card (order: 1 on mobile, grid-area: form on desktop) */}
        <div className="tuition-form-card">
          {/* Top Toolbar */}
          <div className="gpa-result-top scholarship-card-top">
            <div className="gpa-result-tag-wrap">
              <span className="gpa-live-dot" />
              <span className="gpa-result-tag">CHỌN THÔNG TIN TRA CỨU</span>
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

          {/* Step 1: Ngành đào tạo */}
          <div className="scholarship-section-block">
            <div className="scholarship-block-title-row">
              <span className="scholarship-step-num">1</span>
              <div>
                <h2 className="scholarship-block-title">Ngành đào tạo</h2>
                <p className="scholarship-block-subtitle">Tìm kiếm theo tên ngành hoặc mã ngành đào tạo</p>
              </div>
            </div>

            <div className="scholarship-search-box">
              <Search size={16} className="scholarship-search-icon" />
              <input
                type="text"
                value={query}
                onChange={(e) => {
                  handleQueryChange(e.target.value);
                  setFocusedIndex(-1);
                }}
                onKeyDown={handleKeyDown}
                className="scholarship-search-input"
                placeholder="VD: Công nghệ thông tin hoặc 7480201..."
              />
              {query && (
                <button
                  type="button"
                  onClick={clearQuery}
                  className="scholarship-clear-btn"
                  title="Xóa tìm kiếm"
                >
                  <X size={14} />
                </button>
              )}

              {query && !selectedProgram && (
                <div className="scholarship-autocomplete-dropdown">
                  {suggestions.length > 0 ? (
                    suggestions.map((program, index) => (
                      <button
                        key={`${program.code}-${program.name}`}
                        type="button"
                        onClick={() => selectProgram(program)}
                        className={`scholarship-suggestion-item ${
                          index === focusedIndex ? 'focused' : ''
                        }`}
                      >
                        <span className="prog-name">{program.name}</span>
                        <span className="prog-code">{program.code}</span>
                      </button>
                    ))
                  ) : (
                    <div className="scholarship-suggestion-empty">
                      Không tìm thấy ngành phù hợp. Vui lòng chọn ngành trong danh sách.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          <hr className="scholarship-section-divider" />

          {/* Step 2: Năm học & Số tín chỉ */}
          <div className="scholarship-section-block">
            <div className="scholarship-block-title-row">
              <span className="scholarship-step-num">2</span>
              <div>
                <h2 className="scholarship-block-title">Năm học & Số tín chỉ</h2>
                <p className="scholarship-block-subtitle">Chọn niên khóa và số tín chỉ dự kiến đăng ký trong học kỳ</p>
              </div>
            </div>

            <div className="scholarship-inputs-grid">
              {/* Năm học */}
              <div className="scholarship-input-group">
                <label className="scholarship-input-label">Năm học áp dụng</label>
                <select
                  className="tool-select"
                  value={schoolYear}
                  onChange={(e) => setSchoolYear(e.target.value as SchoolYear | '')}
                  style={{ height: '38px', padding: '0 0.75rem', borderRadius: '8px', fontSize: '0.84rem' }}
                >
                  <option value="" disabled>Chọn năm học</option>
                  {SCHOOL_YEARS.map((year) => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </select>
              </div>

              {/* Số tín chỉ */}
              <div className="scholarship-input-group">
                <label className="scholarship-input-label">Số tín chỉ học kỳ</label>
                <div className="number-input-group" style={{ height: '38px' }}>
                  <button type="button" className="number-btn" onClick={handleDecrement} aria-label="Giảm">
                    <Minus size={14} />
                  </button>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={credits}
                    onChange={(e) => setCredits(e.target.value)}
                    placeholder="15"
                    style={{ fontSize: '0.88rem', padding: '0' }}
                  />
                  <button type="button" className="number-btn" onClick={handleIncrement} aria-label="Tăng">
                    <Plus size={14} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Result Card (order: 2 on mobile, grid-area: result on desktop) */}
        <aside className="tuition-summary-card">
          {/* Header & Symmetrical Stat Grid */}
          <div className="tuition-summary-header-wrap">
            <div className="gpa-result-top">
              <div className="gpa-result-tag-wrap">
                <span className="gpa-live-dot" />
                <span className="gpa-result-tag">KẾT QUẢ HỌC PHÍ</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <span className="gpa-cohort-pill">
                  {schoolYear ? `Năm ${schoolYear}` : 'Chưa chọn năm'}
                </span>
              </div>
            </div>

            {/* Symmetrical Stat Grid */}
            <div className="course-target-stats-grid">
              <div className="gpa-stat-box">
                <span className="gpa-stat-label">Đơn giá 1 tín chỉ</span>
                <strong className="gpa-stat-val">
                  {perCredit ? formatVnd(perCredit) : '--'}
                </strong>
              </div>
              <div className="gpa-stat-box">
                <span className="gpa-stat-label">Ước tính học kỳ</span>
                <strong className="gpa-stat-val">
                  {semester ? formatVnd(semester) : '--'}
                </strong>
              </div>
            </div>
          </div>

          {/* Primary Amount Card (Formatted specifically for VND with no line wrapping) */}
          {selectedProgram && schoolYear ? (
            hasValidCredits ? (
              <div className="scholarship-amount-card">
                <span className="amount-label">Học phí theo tín chỉ ({creditCount} TC)</span>
                <strong className="amount-value">{formatVnd(creditEstimate)}</strong>
                <span className="amount-formula">
                  {creditCount} TC × {formatVnd(perCredit)}/TC
                </span>
              </div>
            ) : (
              <div className="scholarship-amount-card">
                <span className="amount-label">Học phí cả năm ({schoolYear})</span>
                <strong className="amount-value">{formatVnd(annual)}</strong>
                <span className="amount-formula">
                  Ước tính ~{formatVnd(semester)} / học kỳ
                </span>
              </div>
            )
          ) : (
            <div className="scholarship-amount-placeholder">
              <span>Hãy chọn ngành đào tạo và năm học để xem bảng tính học phí.</span>
            </div>
          )}

          {/* Detailed Breakdown List */}
          {selectedProgram && schoolYear && (
            <div className="tuition-breakdown-list">
              <div className="tuition-breakdown-item">
                <span className="label">Ngành học</span>
                <span className="value" style={{ textAlign: 'right', maxWidth: '60%' }}>
                  {selectedProgram.name} ({selectedProgram.code})
                </span>
              </div>
              <div className="tuition-breakdown-item">
                <span className="label">Năm học áp dụng</span>
                <span className="value">{schoolYear}</span>
              </div>
              <div className="tuition-breakdown-item">
                <span className="label">Học phí cả năm</span>
                <span className="value">{formatVnd(annual)}</span>
              </div>
              <div className="tuition-breakdown-item">
                <span className="label">Ước tính 1 học kỳ (chia 2)</span>
                <span className="value">{formatVnd(semester)}</span>
              </div>
              <div className="tuition-breakdown-item">
                <span className="label">Đơn giá 1 tín chỉ</span>
                <span className="value">{formatVnd(perCredit)}</span>
              </div>
              {hasValidCredits && (
                <div className="tuition-breakdown-item highlight">
                  <span className="label">Tổng tiền ({creditCount} tín chỉ)</span>
                  <span className="value">{formatVnd(creditEstimate)}</span>
                </div>
              )}
            </div>
          )}
        </aside>

        {/* Important Note Card (order: 3 on mobile, grid-area: note on desktop) */}
        <div className="tuition-note-card">
          <div className="tuition-note-title">
            <span>📌 Lưu ý quan trọng về học phí</span>
          </div>
          <div>
            Học phí học kỳ ước tính bằng học phí năm chia 2. Số tiền thực tế có thể thay đổi theo số tín chỉ đăng ký,
            học phần cụ thể và thông báo thu học phí chính thức từ Nhà trường trong từng học kỳ.
          </div>
        </div>
      </div>
    </div>
  );
}
