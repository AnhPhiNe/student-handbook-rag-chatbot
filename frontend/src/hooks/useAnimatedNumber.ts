import { useEffect, useRef, useState } from 'react';

/**
 * Eases the displayed value toward `target` so a changed result is noticed.
 * Snaps straight to the target when the user prefers reduced motion.
 */
export function useAnimatedNumber(target: number, decimals = 0) {
  const factor = 10 ** decimals;
  const [display, setDisplay] = useState(target);
  const displayRef = useRef(target);

  useEffect(() => {
    const from = displayRef.current;
    if (from === target) return;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const start = performance.now();
    let frame = 0;

    const step = (now: number) => {
      const progress = reduceMotion ? 1 : Math.min(1, (now - start) / 220);
      const eased = 1 - Math.pow(1 - progress, 3);
      const value = progress === 1 ? target : Math.round((from + (target - from) * eased) * factor) / factor;
      displayRef.current = value;
      setDisplay(value);
      if (progress < 1) frame = window.requestAnimationFrame(step);
    };

    frame = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(frame);
  }, [target, factor]);

  return display;
}
