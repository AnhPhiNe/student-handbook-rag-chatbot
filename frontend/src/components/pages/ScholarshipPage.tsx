import { useMemo, useState } from 'react';
import { Minus, Plus, Award, Info, Search } from 'lucide-react';
import { calculateScholarshipScore } from '../../utils/scholarship';
import { SCHOOL_YEARS, searchTuitionPrograms, type SchoolYear, type TuitionProgram } from '../../data/tuitionRates';

export function ScholarshipPage() {
  const [academicScore, setAcademicScore] = useState('');
  const [conductScore, setConductScore] = useState('');
  const [credits, setCredits] = useState('15');
  
  const [query, setQuery] = useState('');
  const [selectedProgram, setSelectedProgram] = useState<TuitionProgram | null>(null);
  const [schoolYear, setSchoolYear] = useState<SchoolYear>('2025-2026');

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
  };

  const tuitionFee = selectedProgram?.perCredit[schoolYear] ?? 0;

  const result = useMemo(() => {
    if (!academicScore || !conductScore) return null;
    return calculateScholarshipScore(Number(academicScore), Number(conductScore));
  }, [academicScore, conductScore]);

  const scholarshipAmount = useMemo(() => {
    if (!result?.classification || !credits || tuitionFee === 0) return null;
    const multiplier = result.classification === 'Xuất sắc' ? 1.5 : result.classification === 'Giỏi' ? 1.25 : 1.0;
    return Number(credits) * tuitionFee * multiplier;
  }, [result, credits, tuitionFee]);

  const handleIncAcademic = () => setAcademicScore((prev) => Math.min(4, Number(prev || 0) + 0.1).toFixed(2).replace(/\.00$/, ''));
  const handleDecAcademic = () => setAcademicScore((prev) => Math.max(0, Number(prev || 0) - 0.1).toFixed(2).replace(/\.00$/, ''));

  const handleIncConduct = () => setConductScore((prev) => Math.min(100, Number(prev || 0) + 1).toString());
  const handleDecConduct = () => setConductScore((prev) => Math.max(0, Number(prev || 0) - 1).toString());

  return (
    <div className="page-container tool-page">
      <div className="page-header">
        <h1>Tính học bổng</h1>
        <p>Tính điểm học bổng khuyến khích học tập tham khảo theo công thức trong Sổ tay sinh viên.</p>
      </div>

      <div className="tool-layout split">
        <div className="tool-input-section" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <section className="tool-panel">
            <h2>Thông tin điểm</h2>
            <div className="tool-form-grid">
              <label className="tool-field">
                <span>Điểm học tập thang 4</span>
                <div className="number-input-group">
                  <button type="button" className="number-btn" onClick={handleDecAcademic} aria-label="Giảm"><Minus size={16} /></button>
                  <input
                    type="number"
                    min="0"
                    max="4"
                    step="0.01"
                    value={academicScore}
                    onChange={(event) => setAcademicScore(event.target.value)}
                    placeholder="Nhập điểm học tập"
                  />
                  <button type="button" className="number-btn" onClick={handleIncAcademic} aria-label="Tăng"><Plus size={16} /></button>
                </div>
              </label>
              <label className="tool-field">
                <span>Điểm rèn luyện thang 100</span>
                <div className="number-input-group">
                  <button type="button" className="number-btn" onClick={handleDecConduct} aria-label="Giảm"><Minus size={16} /></button>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    step="1"
                    value={conductScore}
                    onChange={(event) => setConductScore(event.target.value)}
                    placeholder="Nhập điểm rèn luyện"
                  />
                  <button type="button" className="number-btn" onClick={handleIncConduct} aria-label="Tăng"><Plus size={16} /></button>
                </div>
              </label>
            </div>
            <p className="tool-note">Công thức điểm: (Điểm học tập x 80 + Điểm rèn luyện / 25 x 20) / 100.</p>

            <h2 style={{ marginTop: '2rem' }}>Giá trị học bổng</h2>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1.5rem' }}>
              <label className="tool-field">
                <span>Tìm ngành để tra học phí 1 tín chỉ</span>
                <div className="autocomplete-box">
                  <Search size={18} className="search-icon" />
                  <input
                    className="tool-input"
                    value={query}
                    onChange={(event) => handleQueryChange(event.target.value)}
                    placeholder="Nhập mã ngành hoặc tên ngành"
                  />
                </div>
              </label>

              {query && !selectedProgram && (
                <div className="autocomplete-list">
                  {suggestions.length > 0 ? suggestions.map((program) => (
                    <button key={`${program.code}-${program.name}`} onClick={() => selectProgram(program)}>
                      <strong>{program.name}</strong>
                      <span>{program.code}</span>
                    </button>
                  )) : (
                    <p>Không tìm thấy ngành phù hợp. Vui lòng chọn ngành trong danh sách gợi ý.</p>
                  )}
                </div>
              )}

              <div className="tool-form-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
                <label className="tool-field">
                  <span>Năm học</span>
                  <select className="tool-select" value={schoolYear} onChange={(event) => setSchoolYear(event.target.value as SchoolYear)}>
                    {SCHOOL_YEARS.map((year) => (
                      <option key={year} value={year}>{year}</option>
                    ))}
                  </select>
                </label>
                <label className="tool-field">
                  <span>Số tín chỉ học kỳ</span>
                  <input
                    className="tool-input"
                    type="number"
                    min="15"
                    value={credits}
                    onChange={(event) => setCredits(event.target.value)}
                    placeholder="Tối thiểu 15"
                  />
                </label>
              </div>

              {selectedProgram && (
                <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', padding: '0.75rem', background: 'rgba(59, 130, 246, 0.05)', borderRadius: '6px', border: '1px solid rgba(59, 130, 246, 0.1)' }}>
                  Học phí 1 tín chỉ ({schoolYear}): <strong>{new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(tuitionFee)}</strong>
                </div>
              )}
            </div>

            <div style={{ marginTop: '2.5rem', background: 'var(--bg-secondary)', padding: '1.5rem', borderRadius: '12px' }}>
              <h3 style={{ fontSize: '1rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Info size={18} /> Các mức học bổng
              </h3>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.9rem' }}>
                <li><strong>Xuất sắc (Hệ số 1.5):</strong> Điểm xét ≥ 3.60 | Học tập ≥ 3.60 | Rèn luyện ≥ 90</li>
                <li><strong>Giỏi (Hệ số 1.25):</strong> Điểm xét ≥ 3.20 | Học tập ≥ 3.20 | Rèn luyện ≥ 80</li>
                <li><strong>Khá (Hệ số 1.0):</strong> Điểm xét ≥ 2.56 | Học tập ≥ 2.50 | Rèn luyện ≥ 70</li>
              </ul>
            </div>
          </section>
          
          <section className="tool-callout info" style={{ margin: 0, width: '100%' }}>
            <h2>📌 Lưu ý quan trọng</h2>
            <p>
              <strong>1. Quy định tín chỉ:</strong> Tối thiểu <strong>15 tín chỉ/kỳ</strong> (học kỳ cuối tối thiểu <strong>6 tín chỉ</strong>).
              Số tín chỉ xét học bổng <strong>KHÔNG</strong> bao gồm các môn: Giáo dục Thể chất, Giáo dục Quốc phòng, học cải thiện, học lại...
            </p>
            <p>
              <strong>2. Tính tham khảo:</strong> Việc xét học bổng thực tế còn phụ thuộc điều kiện tín chỉ,
              hệ đào tạo, thời gian học, kỷ luật và quỹ học bổng từng kỳ. Số tiền dự kiến chưa trừ các khoản bù đắp nếu có.
            </p>
            <div className="formula-box">
              <strong>Công thức:</strong> Mức tiền = (Số tín chỉ) × (Học phí 1 tín chỉ) × (Hệ số)
            </div>
          </section>
        </div>

        <aside className="tool-result-card">
          <Award size={28} className="result-icon" />
          <p className="result-label">Mức học bổng dự kiến</p>
          <div className="result-number text-gradient">{result ? result.score.toFixed(3) : '--'}</div>
          <p className={`result-pill ${result?.classification ? 'success' : ''}`}>
            {result?.classification ? `Loại ${result.classification}` : 'Chưa có kết quả'}
          </p>
          <p className="tool-note">
            {result?.message ?? 'Nhập điểm học tập và điểm rèn luyện để xem kết quả tham khảo.'}
          </p>

          {scholarshipAmount !== null && (
            <div style={{ marginTop: '2rem', paddingTop: '1.5rem', borderTop: '1px solid rgba(59, 130, 246, 0.2)' }}>
              <p className="result-label" style={{ marginBottom: '0.5rem' }}>Số tiền dự kiến</p>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--primary)' }}>
                {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(scholarshipAmount)}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
