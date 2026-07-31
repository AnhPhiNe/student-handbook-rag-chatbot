import { useEffect, useState } from 'react';
import './VisitorCounter.css';

const BASE_VISITS = 150;
const FALLBACK_KEY = 'hcmue_visitor_count_v2';

// Shared promise to prevent multiple instances (Desktop & Mobile) from double-fetching
let sharedFetchPromise: Promise<number> | null = null;

function AnimatedDigit({ char }: { char: string }) {
  const [oldChar, setOldChar] = useState(char);
  const [newChar, setNewChar] = useState(char);
  const [isRolling, setIsRolling] = useState(false);

  useEffect(() => {
    if (char !== newChar) {
      // Start rolling!
      setOldChar(newChar);
      setNewChar(char);
      setIsRolling(true);

      const timer = setTimeout(() => {
        setIsRolling(false);
        setOldChar(char); // Snap back to top seamlessly
      }, 600); // matches CSS animation duration
      
      return () => clearTimeout(timer);
    }
  }, [char, newChar]);

  return (
    <span className="digit-container">
      <span className={`digit-track ${isRolling ? 'rolling' : ''}`}>
        <span>{oldChar}</span>
        <span>{newChar}</span>
      </span>
    </span>
  );
}

export function VisitorCounter() {
  const [displayCount, setDisplayCount] = useState<number | null>(() => {
    const saved = localStorage.getItem(FALLBACK_KEY);
    return saved ? parseInt(saved, 10) : null;
  });

  // Effect to handle data fetching (only once)
  useEffect(() => {
    let isMounted = true;

    if (!sharedFetchPromise) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 4000);

      sharedFetchPromise = fetch('/api/visits', { 
        signal: controller.signal,
        cache: 'no-store' 
      })
        .then(res => {
          if (!res.ok) throw new Error('Network response was not ok');
          return res.json();
        })
        .then(data => {
          clearTimeout(timeoutId);
          if (data && typeof data.count === 'number') {
            return BASE_VISITS + data.count;
          }
          throw new Error('Invalid data format');
        })
        .catch(err => {
          console.warn('Visitor counter fallback:', err);
          const savedCount = parseInt(localStorage.getItem(FALLBACK_KEY) || '0', 10);
          return Math.max(savedCount + 1, BASE_VISITS);
        });
    }

    sharedFetchPromise.then(total => {
      if (isMounted) {
        localStorage.setItem(FALLBACK_KEY, total.toString());
        // User requested to always show "..." first, then show (total - 1), then roll to total
        setDisplayCount(total - 1);
        setTimeout(() => {
          if (isMounted) setDisplayCount(total);
        }, 500);
      }
    });

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="visitor-counter">
      <div className="visitor-label">Lượt truy cập</div>
      <div className="visitor-number">
        {displayCount !== null ? (
          displayCount.toLocaleString('vi-VN').split('').map((char, i) => (
            <AnimatedDigit key={displayCount.toString().length - i} char={char} />
          ))
        ) : (
          <span style={{ opacity: 0.5, letterSpacing: '2px' }}>...</span>
        )}
      </div>
    </div>
  );
}
