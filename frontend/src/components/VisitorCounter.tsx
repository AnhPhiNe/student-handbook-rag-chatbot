import { useEffect, useState } from 'react';
import './VisitorCounter.css';

const BASE_VISITS = 150;
const FALLBACK_KEY = 'hcmue_visitor_count_v2';

// Shared promise to prevent multiple instances (Desktop & Mobile) from double-fetching
let sharedFetchPromise: Promise<number> | null = null;

export function VisitorCounter() {
  const [count, setCount] = useState<number>(() => {
    const saved = localStorage.getItem(FALLBACK_KEY);
    return saved ? parseInt(saved, 10) : BASE_VISITS;
  });

  useEffect(() => {
    // Only fetch once per page load (syncs Desktop and Mobile components)
    if (!sharedFetchPromise) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 4000);

      sharedFetchPromise = fetch('https://api.counterapi.dev/v1/hcmue-student-handbook/visits/up', { signal: controller.signal })
        .then(res => res.json())
        .then(data => {
          clearTimeout(timeoutId);
          if (data && typeof data.count === 'number') {
            const total = BASE_VISITS + data.count;
            localStorage.setItem(FALLBACK_KEY, total.toString());
            return total;
          } else {
            throw new Error('Dữ liệu đếm không hợp lệ');
          }
        })
        .catch(err => {
          clearTimeout(timeoutId);
          console.warn('Sử dụng bộ đếm dự phòng:', err);
          const savedCount = parseInt(localStorage.getItem(FALLBACK_KEY) || '0', 10);
          const newCount = Math.max(savedCount + 1, BASE_VISITS);
          localStorage.setItem(FALLBACK_KEY, newCount.toString());
          return newCount;
        });
    }

    // All instances will resolve the exact same number from the shared promise
    let isMounted = true;
    sharedFetchPromise.then(total => {
      if (isMounted) {
        setCount(total);
      }
    });

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="visitor-counter">
      <div className="visitor-label">Lượt truy cập</div>
      <div className="visitor-number">{count.toLocaleString('vi-VN')}</div>
    </div>
  );
}
