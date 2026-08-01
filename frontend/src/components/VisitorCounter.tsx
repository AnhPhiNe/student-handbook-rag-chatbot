import { useEffect, useSyncExternalStore } from 'react';
import './VisitorCounter.css';

const BASE_VISITS = 150;
const FALLBACK_KEY = 'hcmue_visitor_count_v2';

type VisitorSnapshot = {
  count: number | null;
  isLoading: boolean;
};

const listeners = new Set<() => void>();

function getStoredCount(): number | null {
  try {
    const saved = localStorage.getItem(FALLBACK_KEY);
    if (!saved) return null;
    const value = Number.parseInt(saved, 10);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

function setStoredCount(count: number) {
  try {
    localStorage.setItem(FALLBACK_KEY, count.toString());
  } catch {
    // Storage may be unavailable in private browsing modes.
  }
}

let visitorSnapshot: VisitorSnapshot = {
  count: getStoredCount(),
  isLoading: true,
};
let sharedFetchPromise: Promise<number> | null = null;

function emitVisitorSnapshot(next: VisitorSnapshot) {
  visitorSnapshot = next;
  listeners.forEach(listener => listener());
}

function subscribeVisitorStore(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getVisitorSnapshot() {
  return visitorSnapshot;
}

function ensureVisitorCountLoaded(): Promise<number> {
  if (sharedFetchPromise) return sharedFetchPromise;

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 4000);

  sharedFetchPromise = fetch('/api/visits?mode=up', {
    signal: controller.signal,
    cache: 'no-store',
  })
    .then(res => {
      if (!res.ok) throw new Error('Network response was not ok');
      return res.json();
    })
    .then(data => {
      if (data && typeof data.count === 'number') {
        const total = BASE_VISITS + data.count;
        setStoredCount(total);
        return total;
      }
      throw new Error('Invalid visitor counter payload');
    })
    .catch(err => {
      console.warn('Visitor counter fallback:', err);
      return getStoredCount() ?? BASE_VISITS;
    })
    .finally(() => {
      window.clearTimeout(timeoutId);
    });

  sharedFetchPromise.then(total => {
    emitVisitorSnapshot({ count: total, isLoading: false });
  });

  return sharedFetchPromise;
}

function AnimatedDigit({ char }: { char: string }) {
  return (
    <span className="digit-container">
      <span className="digit-track">
        <span>{char}</span>
      </span>
    </span>
  );
}

export function VisitorCounter() {
  const { count, isLoading } = useSyncExternalStore(
    subscribeVisitorStore,
    getVisitorSnapshot,
    getVisitorSnapshot,
  );

  useEffect(() => {
    void ensureVisitorCountLoaded();
  }, []);

  return (
    <div className="visitor-counter">
      <div className="visitor-label">Lượt truy cập</div>
      <div className="visitor-number">
        {!isLoading && count !== null ? (
          count.toLocaleString('vi-VN').split('').map((char, i) => (
            <AnimatedDigit key={`${count}-${i}`} char={char} />
          ))
        ) : (
          <span style={{ opacity: 0.5, letterSpacing: '2px' }}>...</span>
        )}
      </div>
    </div>
  );
}
