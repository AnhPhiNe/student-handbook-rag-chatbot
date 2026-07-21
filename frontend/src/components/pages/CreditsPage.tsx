import { useMemo, useState } from 'react';
import { Minus, Plus, ShieldCheck } from 'lucide-react';
import { calculateCreditThreshold } from '../../utils/creditThreshold';

export function CreditsPage() {
  const [totalCredits, setTotalCredits] = useState('');
  const [checkedCredits, setCheckedCredits] = useState('');

  const result = useMemo(() => {
    if (!totalCredits || !checkedCredits) return null;
    return calculateCreditThreshold(Number(totalCredits), Number(checkedCredits));
  }, [totalCredits, checkedCredits]);

  const handleIncTotal = () => setTotalCredits((prev) => (Number(prev || 130) + 1).toString());
  const handleDecTotal = () => setTotalCredits((prev) => Math.max(1, Number(prev || 130) - 1).toString());

  const handleIncChecked = () => setCheckedCredits((prev) => (Number(prev || 0) + 1).toString());
  const handleDecChecked = () => setCheckedCredits((prev) => Math.max(0, Number(prev || 0) - 1).toString());

  return (
    <div className="page-container tool-page">
      <div className="page-header">
        <h1>Kiểm tra điều kiện hạ bằng</h1>
        <p>Ước tính ngưỡng 5% tổng tín chỉ để theo dõi rủi ro bị hạ bậc bằng tốt nghiệp.</p>
      </div>

      <div className="tool-layout">
        <section className="tool-panel">
          <h2>Thông tin tín chỉ</h2>
          <div className="tool-form-grid">
            <label className="tool-field">
              <span>Tổng tín chỉ chương trình</span>
              <div className="number-input-group">
                <button type="button" className="number-btn" onClick={handleDecTotal} aria-label="Giảm" tabIndex={-1}><Minus size={16} /></button>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={totalCredits}
                  onChange={(event) => setTotalCredits(event.target.value)}
                  placeholder="Nhập tổng tín chỉ"
                />
                <button type="button" className="number-btn" onClick={handleIncTotal} aria-label="Tăng" tabIndex={-1}><Plus size={16} /></button>
              </div>
            </label>
            <label className="tool-field">
              <span>Số tín chỉ đã rớt</span>
              <div className="number-input-group">
                <button type="button" className="number-btn" onClick={handleDecChecked} aria-label="Giảm" tabIndex={-1}><Minus size={16} /></button>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={checkedCredits}
                  onChange={(event) => setCheckedCredits(event.target.value)}
                  placeholder="Nhập số tín chỉ đã rớt"
                />
                <button type="button" className="number-btn" onClick={handleIncChecked} aria-label="Tăng" tabIndex={-1}><Plus size={16} /></button>
              </div>
            </label>
          </div>
          <p className="tool-note">Công cụ dùng ngưỡng tham khảo 5% tổng số tín chỉ chương trình để theo dõi số tín chỉ đã rớt.</p>
        </section>

        <aside className={`tool-result-card status-${result?.status ?? 'empty'}`}>
          <ShieldCheck size={28} className="result-icon" />
          <p className="result-label">Ngưỡng tham khảo</p>
          <div className="result-number text-gradient">{result ? result.threshold.toFixed(2) : '--'}</div>
          {result ? (
            <>
              <p className={`result-pill ${result.status}`}>{getStatusText(result.status)}</p>
              <div className="result-list">
                <div>
                  <span>{result.remaining >= 0 ? 'Còn cách ngưỡng' : 'Vượt ngưỡng'}</span>
                  <strong className={result.remaining < 0 ? 'text-danger' : ''}>{Math.abs(result.remaining).toFixed(2)} tín chỉ</strong>
                </div>
              </div>
              <p className="tool-note">{result.message}</p>
            </>
          ) : (
            <p className="tool-note">Nhập tổng tín chỉ và số tín chỉ đã rớt để xem kết quả.</p>
          )}
        </aside>
      </div>

      <section className="tool-callout info">
        <h2>📌 Lưu ý quan trọng</h2>
        <ul>
          <li>Công cụ này chỉ tính toán ngưỡng giới hạn 5% số tín chỉ học lại so với tổng chương trình đào tạo.</li>
          <li>Bạn sẽ bị <strong>giảm đi một mức xếp loại tốt nghiệp</strong> nếu thuộc một trong hai trường hợp (Theo khoản 3 Điều 15 Quy chế Đào tạo):
            <ol style={{ paddingLeft: '1.2rem', marginTop: '0.25rem' }}>
              <li>Khối lượng tín chỉ phải học lại vượt quá 5% tổng số tín chỉ toàn chương trình.</li>
              <li>Bị kỷ luật từ mức <strong>cảnh cáo</strong> trở lên trong thời gian học.</li>
            </ol>
          </li>
          <li><strong>Quan trọng:</strong> Việc hạ mức xếp loại tốt nghiệp <strong>chỉ áp dụng đối với hạng Xuất sắc và Giỏi</strong>. Nếu điểm của bạn tương đương xếp loại Khá, Trung bình hoặc Yếu thì sẽ <strong>không bị hạ bậc</strong> dù vi phạm các điều kiện trên.</li>
        </ul>
      </section>
    </div>
  );
}

function getStatusText(status: string): string {
  if (status === 'safe') return 'Trong vùng an toàn';
  if (status === 'near') return 'Gần ngưỡng';
  return 'Vượt ngưỡng';
}
