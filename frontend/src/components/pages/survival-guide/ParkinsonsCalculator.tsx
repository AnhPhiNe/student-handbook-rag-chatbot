import { useState, useEffect } from 'react';
import { ExternalLink, RotateCcw, Zap } from 'lucide-react';

function formatCountdown(ms: number) {
  if (ms <= 0) return { days: 0, hours: 0, minutes: 0, label: 'Đã hết hạn!' };
  const totalSeconds = Math.floor(ms / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return { days, hours, minutes, label: null };
}

// Pre-built time options: every 30 min from 06:00 to 23:30
const TIME_OPTIONS = Array.from({ length: 36 }, (_, i) => {
  const h = Math.floor(i / 2) + 6;
  const m = i % 2 === 0 ? '00' : '30';
  return `${String(h).padStart(2, '0')}:${m}`;
});

/** Parse date+time string as LOCAL time (avoid UTC offset issues) */
function parseLocalDateTime(dateStr: string, timeStr: string): number {
  const [year, month, day] = dateStr.split('-').map(Number);
  const [hour, min] = timeStr.split(':').map(Number);
  return new Date(year, month - 1, day, hour, min, 0).getTime();
}

export function ParkinsonsCalculator() {
  const [date, setDate] = useState('');
  const [time, setTime] = useState('23:00');
  const [fakeDeadline, setFakeDeadline] = useState<Date | null>(null);
  const [countdown, setCountdown] = useState<ReturnType<typeof formatCountdown> | null>(null);
  const [error, setError] = useState('');

  // Min date = today (local)
  const todayLocal = (() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  })();

  useEffect(() => {
    if (!fakeDeadline) return;
    const tick = () => setCountdown(formatCountdown(fakeDeadline.getTime() - Date.now()));
    tick();
    const id = setInterval(tick, 60000);
    return () => clearInterval(id);
  }, [fakeDeadline]);

  const calculate = () => {
    setError('');
    if (!date) {
      setError('Vui lòng chọn ngày deadline thật trước!');
      return;
    }
    const real = parseLocalDateTime(date, time);
    const now = Date.now();
    const remaining = real - now;
    if (remaining <= 0) {
      setError('Deadline đã qua rồi! Hãy chọn ngày trong tương lai.');
      return;
    }
    setFakeDeadline(new Date(now + remaining * 0.7));
  };

  const reset = () => {
    setFakeDeadline(null);
    setDate('');
    setTime('23:00');
    setError('');
  };

  const googleCalLink = fakeDeadline
    ? `https://calendar.google.com/calendar/render?action=TEMPLATE&text=Fake+Deadline+(70%25)&dates=${fakeDeadline.toISOString().replace(/[-:]/g, '').split('.')[0]}Z/${fakeDeadline.toISOString().replace(/[-:]/g, '').split('.')[0]}Z`
    : '';

  return (
    <div className="parkinson-calc">
      {!fakeDeadline ? (
        <>
          {/* Date + Time side by side */}
          <div className="pk-row">
            <div className="pk-input-group" style={{ flex: 2 }}>
              <label className="pk-label">📅 Ngày deadline thật</label>
              <input
                type="date"
                className="pk-date-input"
                value={date}
                min={todayLocal}
                onChange={e => { setDate(e.target.value); setError(''); }}
              />
            </div>
            <div className="pk-input-group" style={{ flex: 1 }}>
              <label className="pk-label">🕐 Giờ nộp</label>
              <select
                className="pk-time-select"
                value={time}
                onChange={e => setTime(e.target.value)}
              >
                {TIME_OPTIONS.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Error message */}
          {error && <p className="pk-error">⚠️ {error}</p>}

          <button className="pk-calc-btn" onClick={calculate}>
            <Zap size={16} /> Tính Fake Deadline (70%)
          </button>

          <p className="pk-hint">💡 Nhập deadline thật → công cụ tự tính deadline ảo sớm hơn 30%</p>
        </>
      ) : (
        <div className="pk-result">
          <div className="pk-result-header">
            <span className="pk-badge">⚡ Fake Deadline của bạn</span>
            <button className="pk-reset-btn" onClick={reset}><RotateCcw size={14} /></button>
          </div>

          <div className="pk-fake-date">
            {fakeDeadline.toLocaleDateString('vi-VN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
            &nbsp;lúc&nbsp;
            {fakeDeadline.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}
          </div>

          {countdown && (
            countdown.label ? (
              <div className="pk-expired">{countdown.label}</div>
            ) : (
              <div className="pk-countdown">
                <div className="pk-unit"><span>{countdown.days}</span><small>ngày</small></div>
                <div className="pk-sep">:</div>
                <div className="pk-unit"><span>{countdown.hours}</span><small>giờ</small></div>
                <div className="pk-sep">:</div>
                <div className="pk-unit"><span>{countdown.minutes}</span><small>phút</small></div>
              </div>
            )
          )}

          <a className="pk-calendar-btn" href={googleCalLink} target="_blank" rel="noopener noreferrer">
            <ExternalLink size={15} /> Lưu vào Google Calendar
          </a>
          <p className="pk-tip">💡 Hãy cam kết với nhóm về Fake Deadline này để tăng trách nhiệm tập thể!</p>
        </div>
      )}
    </div>
  );
}
