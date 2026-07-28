import { useState, useEffect, useRef } from 'react';
import { Play, Pause, RotateCcw, Zap } from 'lucide-react';
import { createAudioContext } from '../../../utils/audio';

const DURATION = 120;

export function TwoMinuteTimer() {
  const [task, setTask] = useState('');
  const [secondsLeft, setSecondsLeft] = useState(DURATION);
  const [isRunning, setIsRunning] = useState(false);
  const [isDone, setIsDone] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!isRunning) return;
    intervalRef.current = setInterval(() => {
      setSecondsLeft(prev => {
        if (prev <= 1) {
          clearInterval(intervalRef.current!);
          setIsRunning(false);
          setIsDone(true);
          try {
            const ctx = createAudioContext();
            if (!ctx) return 0;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain); gain.connect(ctx.destination);
            osc.frequency.value = 660;
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);
            osc.start(); osc.stop(ctx.currentTime + 0.8);
          } catch { /* ignore */ }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [isRunning]);

  const reset = () => { setSecondsLeft(DURATION); setIsRunning(false); setIsDone(false); };

  const minutes = Math.floor(secondsLeft / 60).toString().padStart(2, '0');
  const seconds = (secondsLeft % 60).toString().padStart(2, '0');
  const progress = (DURATION - secondsLeft) / DURATION;
  const circumference = 2 * Math.PI * 34;

  if (isDone) {
    return (
      <div className="two-min-timer done-state">
        <div className="two-min-done-icon">🎉</div>
        <h3>Bạn đã bắt đầu!</h3>
        <p>"{task || 'Nhiệm vụ của bạn'}" đã được khởi động. Não bạn đã vào guồng — đừng dừng lại!</p>
        <button className="two-min-reset-btn" onClick={reset}>
          <RotateCcw size={16} /> Thử task khác
        </button>
      </div>
    );
  }

  const canStart = task.trim() !== '' || secondsLeft < DURATION;

  return (
    <div className="two-min-timer">
      {/* Task input */}
      <div className="two-min-input-wrap">
        <Zap size={16} className="two-min-input-icon" />
        <input
          className="two-min-input"
          placeholder="Gõ task bạn đang né tránh..."
          value={task}
          onChange={e => setTask(e.target.value)}
          disabled={isRunning}
        />
      </div>

      {/* Task display badge when running */}
      {isRunning && task && (
        <div className="two-min-task-badge">
          ⚡ Đang thực hiện: <strong>{task}</strong>
        </div>
      )}

      {/* Clock */}
      <div className="two-min-clock">
        <div className="two-min-progress-ring">
          <svg viewBox="0 0 80 80" className="two-min-svg">
            <circle cx="40" cy="40" r="34" className="two-min-track" />
            <circle
              cx="40" cy="40" r="34"
              className="two-min-fill"
              style={{ strokeDasharray: circumference, strokeDashoffset: circumference * (1 - progress) }}
            />
          </svg>
          <span className="two-min-time">{minutes}:{seconds}</span>
        </div>
      </div>

      {/* Controls — always fixed layout */}
      <div className="two-min-controls">
        <button
          className={`two-min-start-btn ${isRunning ? 'paused' : ''}`}
          onClick={() => setIsRunning(r => !r)}
          disabled={!canStart && !isRunning}
        >
          {isRunning
            ? <><Pause size={17} /> Tạm dừng</>
            : <><Play size={17} /> {secondsLeft < DURATION ? 'Tiếp tục' : 'Bắt đầu 2 phút'}</>
          }
        </button>
        <button className="two-min-reset-btn small" onClick={reset} title="Đặt lại">
          <RotateCcw size={14} />
        </button>
      </div>

      {!isRunning && secondsLeft === DURATION && (
        <p className="two-min-hint">💡 Gõ tên task vào ô trên rồi bấm Bắt đầu!</p>
      )}
    </div>
  );
}
