import { useEffect, useState } from 'react';
import './VisitorCounter.css';

const BASE_VISITS = 1057490;
const FALLBACK_KEY = 'hcmue_visitor_count';

export function VisitorCounter() {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 4000);

    fetch('https://api.counterapi.dev/v1/hcmue-student-handbook/visits/up', { signal: controller.signal })
      .then(res => res.json())
      .then(data => {
        clearTimeout(timeoutId);
        if (data && typeof data.count === 'number') {
          const total = BASE_VISITS + data.count;
          setCount(total);
          localStorage.setItem(FALLBACK_KEY, total.toString());
        } else {
          throw new Error('Dữ liệu đếm không hợp lệ');
        }
      })
      .catch(err => {
        clearTimeout(timeoutId);
        console.warn('Sử dụng bộ đếm dự phòng:', err);
        const savedCount = parseInt(localStorage.getItem(FALLBACK_KEY) || '0', 10);
        const newCount = Math.max(savedCount + 1, BASE_VISITS + Math.floor(Math.random() * 5));
        setCount(newCount);
        localStorage.setItem(FALLBACK_KEY, newCount.toString());
      });
  }, []);

  return (
    <div className={`visitor-counter ${count === null ? 'loading' : ''}`} style={{ opacity: count === null ? 0.6 : 1 }}>
      <div className="visitor-label">LƯỢT TRUY CẬP</div>
      <div className="visitor-number">{count !== null ? count.toLocaleString('vi-VN') : '...'}</div>
    </div>
  );
}
