import { useMemo, useState } from 'react';
import { Minus, Plus, Calculator, Search } from 'lucide-react';
import { SCHOOL_YEARS, formatVnd, searchTuitionPrograms, type SchoolYear, type TuitionProgram } from '../../data/tuitionRates';
import { PageContextBadges } from '../PageContextBadges';

export function TuitionPage() {
  const [query, setQuery] = useState('');
  const [selectedProgram, setSelectedProgram] = useState<TuitionProgram | null>(null);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [schoolYear, setSchoolYear] = useState<SchoolYear | ''>('');
  const [credits, setCredits] = useState('');

  const suggestions = useMemo(() => searchTuitionPrograms(query), [query]);
  const creditCount = Number(credits);
  const hasValidCredits = Number.isFinite(creditCount) && creditCount > 0;

  const handleIncrement = () => setCredits((prev) => (Number(prev || 0) + 1).toString());
  const handleDecrement = () => setCredits((prev) => Math.max(0, Number(prev || 0) - 1).toString());

  const handleQueryChange = (value: string) => {
    setQuery(value);
    if (selectedProgram && `${selectedProgram.code} ${selectedProgram.name}` !== value) {
      setSelectedProgram(null);
    }
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
      if (focusedIndex >= 0 && focusedIndex < suggestions.length) {
        selectProgram(suggestions[focusedIndex]);
      }
    }
  };

  const annual = schoolYear ? selectedProgram?.annual[schoolYear] ?? 0 : 0;
  const semester = annual / 2;
  const perCredit = schoolYear ? selectedProgram?.perCredit[schoolYear] ?? 0 : 0;
  const creditEstimate = hasValidCredits ? perCredit * creditCount : 0;

  return (
    <div className="page-container tool-page">
      <div className="page-header">
        <h1 className="page-title-with-icon">
          <Calculator aria-hidden="true" />
          <span>Ước tính học phí</span>
        </h1>
        <p>Tra theo bảng học phí theo ngành và năm học, sau đó ước tính học kỳ hoặc số tín chỉ đăng ký.</p>
        <PageContextBadges schoolYear={schoolYear || undefined} source="Bảng học phí theo ngành" advisory />
      </div>

      <div className="tool-layout">
        <section className="tool-panel">
          <h2>Chọn thông tin</h2>
          <label className="tool-field">
            <span>Tìm ngành theo mã hoặc tên</span>
            <div className="autocomplete-box">
              <Search size={18} className="search-icon" />
              <input
                className="tool-input"
                value={query}
                onChange={(event) => {
                  handleQueryChange(event.target.value);
                  setFocusedIndex(-1);
                }}
                onKeyDown={handleKeyDown}
                placeholder="VD: Công nghệ thông tin hoặc 7480201"
              />
            </div>
          </label>

          {query && !selectedProgram && (
            <div className="autocomplete-list">
              {suggestions.length > 0 ? suggestions.map((program, index) => (
                <button
                  key={`${program.code}-${program.name}`}
                  onClick={() => selectProgram(program)}
                  style={index === focusedIndex ? { background: 'rgba(59, 130, 246, 0.1)' } : undefined}
                  className={index === focusedIndex ? 'focused' : ''}
                >
                  <strong>{program.name}</strong>
                  <span>{program.code}</span>
                </button>
              )) : (
                <p>Không tìm thấy ngành phù hợp. Vui lòng chọn ngành trong danh sách gợi ý.</p>
              )}
            </div>
          )}

          <div className="tool-form-grid">
            <label className="tool-field">
              <span>Năm học</span>
              <select className="tool-select" value={schoolYear} onChange={(event) => setSchoolYear(event.target.value as SchoolYear | '')}>
                <option value="" disabled>Chọn năm học</option>
                {SCHOOL_YEARS.map((year) => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </label>
            <label className="tool-field">
              <span>Số tín chỉ học kỳ (tùy chọn)</span>
              <div className="number-input-group">
                <button type="button" className="number-btn" onClick={handleDecrement} aria-label="Giảm"><Minus size={16} /></button>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={credits}
                  onChange={(event) => setCredits(event.target.value)}
                  placeholder="VD: 18"
                />
                <button type="button" className="number-btn" onClick={handleIncrement} aria-label="Tăng"><Plus size={16} /></button>
              </div>
            </label>
          </div>
        </section>

        <aside className="tool-result-card">
          <Calculator size={28} className="result-icon" />
          <p className="result-label">Kết quả học phí</p>
          {selectedProgram && schoolYear ? (
            <>
              <h3 className="result-title">{selectedProgram.name}</h3>
              <p className="result-subtitle">{selectedProgram.code} · Năm học {schoolYear}</p>
              <div className="result-list">
                <div><span>Học phí năm</span><strong className="text-gradient">{formatVnd(annual)}</strong></div>
                <div><span>Ước tính học kỳ</span><strong className="text-gradient">{formatVnd(semester)}</strong></div>
                <div><span>Học phí 1 tín chỉ</span><strong className="text-gradient">{formatVnd(perCredit)}</strong></div>
                {hasValidCredits && <div><span>{creditCount} tín chỉ</span><strong className="text-gradient">{formatVnd(creditEstimate)}</strong></div>}
              </div>
            </>
          ) : (
            <p className="tool-note">
              {selectedProgram
                ? 'Hãy chọn năm học để xem kết quả.'
                : 'Hãy chọn một ngành từ danh sách gợi ý để xem kết quả.'}
            </p>
          )}
        </aside>
      </div>

      <section className="tool-callout info">
        <h2>📌 Lưu ý quan trọng</h2>
        <p>
          Học phí học kỳ là ước tính bằng học phí năm chia 2. Số tiền thực tế có thể thay đổi theo số tín chỉ đăng ký,
          học phần cụ thể và thông báo chính thức của Trường.
        </p>
      </section>
    </div>
  );
}
