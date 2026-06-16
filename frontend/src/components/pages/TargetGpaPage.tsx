import { useMemo, useState } from 'react';
import { Target, AlertTriangle } from 'lucide-react';

export function TargetGpaPage() {
  const [currentGpa, setCurrentGpa] = useState('');
  const [currentCredits, setCurrentCredits] = useState('');
  const [targetGpa, setTargetGpa] = useState('');
  const [futureCredits, setFutureCredits] = useState('15');

  const result = useMemo(() => {
    const cGpa = Number(currentGpa);
    const cCreds = Number(currentCredits);
    const tGpa = Number(targetGpa);
    const fCreds = Number(futureCredits);

    if (!currentGpa || !currentCredits || !targetGpa || !futureCredits || fCreds <= 0 || cCreds <= 0) {
      return null;
    }

    const totalCreds = cCreds + fCreds;
    const targetPoints = tGpa * totalCreds;
    const currentPoints = cGpa * cCreds;
    const requiredPoints = targetPoints - currentPoints;
    const requiredGpa = requiredPoints / fCreds;

    return {
      requiredGpa,
      totalCreds,
      isPossible: requiredGpa <= 4.0,
      isAlreadyAchieved: requiredGpa <= 0,
    };
  }, [currentGpa, currentCredits, targetGpa, futureCredits]);

  return (
    <div className="page-container tool-page">
      <div className="page-header">
        <h1>Mục tiêu GPA</h1>
        <p>Tính điểm trung bình học kỳ cần đạt để kéo GPA tích lũy lên mức mong muốn.</p>
      </div>

      <div className="tool-layout split">
        <div className="tool-input-section" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <section className="tool-panel">
            <h2 className="section-title">Hiện tại của bạn</h2>
            <div className="tool-form-grid" style={{ marginBottom: '2rem' }}>
              <label className="tool-field">
                <span>GPA tích lũy hiện tại (Hệ 4)</span>
                <input
                  type="number"
                  min="0"
                  max="4"
                  step="0.01"
                  value={currentGpa}
                  onChange={(e) => setCurrentGpa(e.target.value)}
                  className="tool-input"
                  placeholder="Ví dụ: 2.50"
                />
              </label>
              <label className="tool-field">
                <span>Số tín chỉ tích lũy</span>
                <input
                  type="number"
                  min="1"
                  value={currentCredits}
                  onChange={(e) => setCurrentCredits(e.target.value)}
                  className="tool-input"
                  placeholder="Ví dụ: 100"
                />
              </label>
            </div>

            <h2 className="section-title">Mục tiêu sắp tới</h2>
            <div className="tool-form-grid">
              <label className="tool-field">
                <span>GPA mục tiêu muốn đạt</span>
                <input
                  type="number"
                  min="0"
                  max="4"
                  step="0.01"
                  value={targetGpa}
                  onChange={(e) => setTargetGpa(e.target.value)}
                  className="tool-input"
                  placeholder="Ví dụ: 3.20"
                />
              </label>
              <label className="tool-field">
                <span>Số tín chỉ dự kiến học kỳ tới</span>
                <input
                  type="number"
                  min="1"
                  value={futureCredits}
                  onChange={(e) => setFutureCredits(e.target.value)}
                  className="tool-input"
                  placeholder="Ví dụ: 15"
                />
              </label>
            </div>
          </section>
          
          <section className="tool-callout info" style={{ margin: 0, maxWidth: 'none' }}>
            <h2>💡 Mẹo nhỏ</h2>
            <p>
              Bạn có thể điều chỉnh <strong>số tín chỉ dự kiến</strong> để xem mình cần học nhiều hay ít môn để dễ dàng đạt được GPA mục tiêu.
            </p>
            <div className="formula-box">
              <strong>Công thức:</strong> GPA học kỳ = [(GPA mục tiêu × Tổng tín chỉ) - (GPA hiện tại × Tín chỉ hiện tại)] / Tín chỉ học kỳ tới
            </div>
          </section>
        </div>

        <aside className="tool-result-card">
          <Target size={28} className="result-icon" />
          <p className="result-label">GPA học kỳ tới cần đạt</p>
          
          {result ? (
            <>
              {result.isAlreadyAchieved ? (
                <div style={{ marginTop: '1rem', textAlign: 'center' }}>
                  <div className="result-number text-gradient" style={{ color: 'var(--success)' }}>Đã đạt</div>
                  <p className="tool-note" style={{ marginTop: '1rem', color: 'var(--success)' }}>
                    Bạn đã vượt mục tiêu này rồi! Hãy đặt một mục tiêu cao hơn nhé.
                  </p>
                </div>
              ) : result.isPossible ? (
                <div style={{ marginTop: '1rem', textAlign: 'center' }}>
                  <div className="result-number text-gradient">{result.requiredGpa.toFixed(2)}</div>
                  <p className="result-pill success" style={{ margin: '0 auto' }}>Khả thi</p>
                  <p className="tool-note" style={{ marginTop: '1rem' }}>
                    Bạn cần đạt trung bình <strong>{result.requiredGpa.toFixed(2)}</strong> cho <strong>{futureCredits}</strong> tín chỉ sắp tới để kéo điểm lên <strong>{Number(targetGpa).toFixed(2)}</strong>.
                  </p>
                </div>
              ) : (
                <div style={{ marginTop: '1rem', textAlign: 'center' }}>
                  <div className="result-number" style={{ color: 'var(--danger)', fontSize: '2.5rem' }}>Bất khả thi</div>
                  <p className="result-pill danger" style={{ background: 'rgba(239, 68, 68, 0.1)', color: 'var(--danger)', margin: '0 auto' }}>
                    <AlertTriangle size={14} style={{ display: 'inline', marginRight: '4px' }} />
                    Yêu cầu GPA &gt; 4.0
                  </p>
                  <p className="tool-note" style={{ marginTop: '1rem', color: 'var(--danger)' }}>
                    Bạn cần đạt {result.requiredGpa.toFixed(2)} điểm, điều này vượt quá thang điểm tối đa 4.0. Bạn cần phải đăng ký nhiều tín chỉ hơn hoặc hạ mục tiêu xuống.
                  </p>
                </div>
              )}
            </>
          ) : (
             <div style={{ marginTop: '1rem', textAlign: 'center' }}>
               <div className="result-number text-gradient">--</div>
               <p className="tool-note" style={{ marginTop: '1rem' }}>
                 Nhập đầy đủ thông tin để tính điểm GPA cần đạt ở học kỳ tới.
               </p>
             </div>
          )}
        </aside>
      </div>
    </div>
  );
}
