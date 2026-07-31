import { useEffect, useState, useRef } from 'react';
import './VisitorCounter.css';

const BASE_VISITS = 150;
const FALLBACK_KEY = 'hcmue_visitor_count_v2';

export function VisitorCounter() {
  // Bắt đầu hiển thị ngay số đã lưu thay vì '...' để tránh nhấp nháy
  const [count, setCount] = useState<number>(() => {
    const saved = localStorage.getItem(FALLBACK_KEY);
    return saved ? parseInt(saved, 10) : BASE_VISITS;
  });
  const hasFetched = useRef(false);

  useEffect(() => {
    // Ngăn chặn React Strict Mode gọi API 2 lần khi dev trên localhost
    if (hasFetched.current) return;
    hasFetched.current = true;

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
        const newCount = Math.max(savedCount + 1, BASE_VISITS);
        setCount(newCount);
        localStorage.setItem(FALLBACK_KEY, newCount.toString());
      });
  }, []);

  return (
    <div className="visitor-counter">
      <div className="visitor-label">Lượt truy cập</div>
      <div className="visitor-number">{count.toLocaleString('vi-VN')}</div>
    </div>
  );
}
