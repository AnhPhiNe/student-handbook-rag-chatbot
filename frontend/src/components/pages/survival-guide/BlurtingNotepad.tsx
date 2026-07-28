import { useState, useEffect, useRef } from 'react';
import { Play, Eye, EyeOff, RotateCcw } from 'lucide-react';
import { createAudioContext } from '../../../utils/audio';

const DURATION = 15 * 60; // 15 minutes

export function BlurtingNotepad() {
  const [text, setText] = useState('');
  const [secondsLeft, setSecondsLeft] = useState(DURATION);
  const [isRunning, setIsRunning] = useState(false);
  const [isDone, setIsDone] = useState(false);
  const [showText, setShowText] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!isRunning) return;
    intervalRef.current = setInterval(() => {
      setSecondsLeft(prev => {
        if (prev <= 1) {
          clearInterval(intervalRef.current!);
          setIsRunning(false);
          setIsDone(true);
          setShowText(false);
          try {
            const ctx = createAudioContext();
            if (!ctx) return 0;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.value = 523;
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 1);
            osc.start();
            osc.stop(ctx.currentTime + 1);
          } catch { /* ignore */ }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [isRunning]);

  const handleStart = () => {
    setIsRunning(true);
    setIsDone(false);
    setShowText(true);
    setTimeout(() => textareaRef.current?.focus(), 100);
  };

  const reset = () => {
    setText('');
    setSecondsLeft(DURATION);
    setIsRunning(false);
    setIsDone(false);
    setShowText(true);
    if (intervalRef.current) clearInterval(intervalRef.current);
  };

  const minutes = Math.floor(secondsLeft / 60).toString().padStart(2, '0');
  const seconds = (secondsLeft % 60).toString().padStart(2, '0');
  const progress = (DURATION - secondsLeft) / DURATION;
  const urgentColor = secondsLeft < 180 ? '#EF4444' : secondsLeft < 300 ? '#F59E0B' : '#10B981';
  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;

  return (
    <div className="blurting-notepad">
      <div className="blurting-header">
        <div className="blurting-timer-row">
          <div className="blurting-timer-display" style={{ color: urgentColor }}>
            ⏱ {minutes}:{seconds}
          </div>
          <div className="blurting-progress-bar">
            <div className="blurting-progress-fill" style={{ width: `${progress * 100}%`, background: urgentColor }} />
          </div>
          <span className="blurting-word-count">{wordCount} từ</span>
        </div>

        <div className="blurting-controls">
          {!isRunning && !isDone && (
            <button className="blurting-start-btn" onClick={handleStart}>
              <Play size={16} /> Bắt đầu xả lũ (15 phút)
            </button>
          )}
          {isRunning && (
            <span className="blurting-running-badge">🔥 Đang chạy – Ghi ra mọi thứ bạn nhớ!</span>
          )}
          {isDone && (
            <span className="blurting-done-badge">✅ Hết giờ! Bây giờ mở sách đối chiếu nhé.</span>
          )}
          {(isRunning || isDone) && (
            <button className="blurting-toggle-btn" onClick={() => setShowText(s => !s)} title={showText ? 'Ẩn nội dung' : 'Xem lại'}>
              {showText ? <EyeOff size={16} /> : <Eye size={16} />}
              {showText ? 'Ẩn' : 'Xem lại'}
            </button>
          )}
          <button className="blurting-reset-btn" onClick={reset} title="Làm lại">
            <RotateCcw size={16} />
          </button>
        </div>
      </div>

      <div className={`blurting-textarea-wrap ${!showText && (isRunning || isDone) ? 'blurred' : ''}`}>
        <textarea
          ref={textareaRef}
          className="blurting-textarea"
          placeholder={isRunning
            ? "Viết ra MỌI THỨ bạn nhớ được... Đừng lo về chính tả hay thứ tự!"
            : "Nhấn 'Bắt đầu xả lũ' rồi ghi ra toàn bộ kiến thức bạn nhớ được mà không cần mở tài liệu..."}
          value={text}
          onChange={e => setText(e.target.value)}
          disabled={!isRunning}
          rows={10}
        />
        {!showText && (isRunning || isDone) && (
          <div className="blurting-overlay">
            <button onClick={() => setShowText(true)}>
              <Eye size={20} /> Nhấn để xem lại
            </button>
          </div>
        )}
      </div>

      {isDone && (
        <div className="blurting-next-step">
          <h4>📖 Bước tiếp theo</h4>
          <ol>
            <li>Mở tài liệu / giáo trình ra đối chiếu với những gì bạn vừa viết.</li>
            <li>Dùng bút đỏ bổ sung thêm những <strong>ý còn thiếu</strong> vào tờ giấy nháp.</li>
            <li>Những chỗ bổ sung đó chính là phần bạn cần ôn lại kỹ nhất!</li>
          </ol>
        </div>
      )}
    </div>
  );
}
