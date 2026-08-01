import { useEffect, useState, useSyncExternalStore } from 'react';
import './VisitorCounter.css';

const BASE_VISITS = 150;
const ROLL_START = 100;
const ROLL_DURATION_MS = 900;

type VisitorSnapshot = {
  count: number | null;
  isLoading: boolean;
};

const listeners = new Set<() => void>();

let visitorSnapshot: VisitorSnapshot = {
  count: null,
  isLoading: true,
};
let sharedFetchPromise: Promise<number | null> | null = null;

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

function ensureVisitorCountLoaded(): Promise<number | null> {
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
        return BASE_VISITS + data.count;
      }
      throw new Error('Invalid visitor counter payload');
    })
    .catch(err => {
      console.warn('Visitor counter fallback:', err);
      return null;
    })
    .finally(() => {
      window.clearTimeout(timeoutId);
    });

  sharedFetchPromise.then(total => {
    emitVisitorSnapshot({
      count: total,
      isLoading: false,
    });
  });

  return sharedFetchPromise;
}

function formatCounterChar(char: string) {
  return char === ' ' ? '\u00a0' : char;
}

function AnimatedDigit({ char }: { char: string }) {
  return (
    <span className="digit-container">
      <span className="digit-track">
        <span>{formatCounterChar(char)}</span>
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
  const [displayCount, setDisplayCount] = useState<number | null>(null);

  useEffect(() => {
    void ensureVisitorCountLoaded();
  }, []);

  useEffect(() => {
    if (count === null) return;

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReducedMotion || count <= ROLL_START) {
      const frame = window.requestAnimationFrame(() => setDisplayCount(count));
      return () => window.cancelAnimationFrame(frame);
    }

    let animationFrame = 0;
    let startTime: number | null = null;

    const animate = (timestamp: number) => {
      if (startTime === null) {
        startTime = timestamp;
      }

      const progress = Math.min((timestamp - startTime) / ROLL_DURATION_MS, 1);
      const easedProgress = 1 - Math.pow(1 - progress, 3);
      const nextCount = Math.round(ROLL_START + (count - ROLL_START) * easedProgress);
      setDisplayCount(nextCount);

      if (progress < 1) {
        animationFrame = window.requestAnimationFrame(animate);
      }
    };

    const startFrame = window.requestAnimationFrame(() => {
      setDisplayCount(ROLL_START);
      animationFrame = window.requestAnimationFrame(animate);
    });

    return () => {
      window.cancelAnimationFrame(startFrame);
      window.cancelAnimationFrame(animationFrame);
    };
  }, [count]);

  return (
    <div className="visitor-counter">
      <div className="visitor-label">Lượt truy cập</div>
      <div className="visitor-number">
        {!isLoading && displayCount !== null ? (
          displayCount.toLocaleString('vi-VN').split('').map((char, i) => (
            <AnimatedDigit key={`${displayCount}-${i}`} char={char} />
          ))
        ) : (
          <span style={{ opacity: 0.5, letterSpacing: '2px' }}>...</span>
        )}
      </div>
    </div>
  );
}
