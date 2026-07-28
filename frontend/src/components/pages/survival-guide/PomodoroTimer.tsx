import { useState, useEffect, useRef, useCallback } from 'react';
import { Play, Pause, RotateCcw, Settings } from 'lucide-react';
import { HorizontalScrollHint } from '../../HorizontalScrollHint';
import { createAudioContext } from '../../../utils/audio';

type TimerMode = 'focus' | 'short-break' | 'long-break';

const DEFAULT_TIMES = { focus: 25, 'short-break': 5, 'long-break': 15 };
const LABELS: Record<TimerMode, string> = {
  focus: '🍅 Học tập',
  'short-break': '☕ Nghỉ ngắn',
  'long-break': '🌿 Nghỉ dài',
};

function beep(type: 'end' | 'start') {
  try {
    const ctx = createAudioContext();
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = type === 'end' ? 880 : 440;
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.6);
  } catch { /* ignore audio errors */ }
}

export function PomodoroTimer() {
  const [mode, setMode] = useState<TimerMode>('focus');
  const [customMinutes, setCustomMinutes] = useState(DEFAULT_TIMES);
  const [secondsLeft, setSecondsLeft] = useState(DEFAULT_TIMES.focus * 60);
  const [isRunning, setIsRunning] = useState(false);
  const [rounds, setRounds] = useState(0);
  const [showSettings, setShowSettings] = useState(false);
  const modeTabsRef = useRef<HTMLDivElement | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const totalSeconds = customMinutes[mode] * 60;
  const progress = secondsLeft / totalSeconds;

  const switchMode = useCallback((newMode: TimerMode) => {
    setMode(newMode);
    setSecondsLeft(customMinutes[newMode] * 60);
    setIsRunning(false);
    if (intervalRef.current) clearInterval(intervalRef.current);
  }, [customMinutes]);

  useEffect(() => {
    if (!isRunning) return;
    intervalRef.current = setInterval(() => {
      setSecondsLeft(prev => {
        if (prev <= 1) {
          clearInterval(intervalRef.current!);
          setIsRunning(false);
          beep('end');
          if (mode === 'focus') {
            setRounds(r => r + 1);
            setMode('short-break');
            setSecondsLeft(customMinutes['short-break'] * 60);
          } else {
            setMode('focus');
            setSecondsLeft(customMinutes.focus * 60);
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [isRunning, mode, customMinutes]);

  const minutes = Math.floor(secondsLeft / 60).toString().padStart(2, '0');
  const seconds = (secondsLeft % 60).toString().padStart(2, '0');

  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - progress);

  const handleStart = () => {
    beep('start');
    setIsRunning(true);
  };

  return (
    <div className="pomodoro-timer">
      <div className="pom-mode-tabs" ref={modeTabsRef}>
        {(Object.keys(LABELS) as TimerMode[]).map(m => (
          <button
            key={m}
            className={`pom-tab ${mode === m ? 'active' : ''}`}
            onClick={() => switchMode(m)}
          >
            {LABELS[m]}
          </button>
        ))}
      </div>
      <HorizontalScrollHint targetRef={modeTabsRef} className="compact" />

      <div className="pom-clock-wrap">
        <svg className="pom-svg" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r={radius} className="pom-track" />
          <circle
            cx="60" cy="60" r={radius}
            className="pom-progress"
            style={{
              strokeDasharray: circumference,
              strokeDashoffset,
              stroke: mode === 'focus' ? '#EF4444' : mode === 'short-break' ? '#10B981' : '#3B82F6',
            }}
          />
        </svg>
        <div className="pom-time-display">
          <span className="pom-digits">{minutes}:{seconds}</span>
          <span className="pom-mode-label">{LABELS[mode]}</span>
        </div>
      </div>

      <div className="pom-controls">
        <button className="pom-btn reset" onClick={() => { setSecondsLeft(customMinutes[mode] * 60); setIsRunning(false); }}>
          <RotateCcw size={18} />
        </button>
        <button className="pom-btn main" onClick={isRunning ? () => setIsRunning(false) : handleStart}>
          {isRunning ? <Pause size={22} /> : <Play size={22} />}
        </button>
        <button className="pom-btn settings" onClick={() => setShowSettings(s => !s)}>
          <Settings size={18} />
        </button>
      </div>

      <div className="pom-rounds">
        {Array.from({ length: Math.max(4, rounds + 1) }).map((_, i) => (
          <span key={i} className={`pom-tomato ${i < rounds ? 'done' : ''}`}>🍅</span>
        ))}
        <span className="pom-rounds-label">{rounds} vòng hoàn thành</span>
      </div>

      {showSettings && (
        <div className="pom-settings-panel">
          <h4>⚙️ Tùy chỉnh thời gian (phút)</h4>
          {(Object.keys(DEFAULT_TIMES) as TimerMode[]).map(m => (
            <div key={m} className="pom-setting-row">
              <label>{LABELS[m]}</label>
              <input
                type="number" min={1} max={60}
                value={customMinutes[m]}
                onChange={e => {
                  const val = Math.max(1, Math.min(60, +e.target.value));
                  setCustomMinutes(prev => ({ ...prev, [m]: val }));
                  if (mode === m) setSecondsLeft(val * 60);
                }}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
