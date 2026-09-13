import { useEffect, useRef, useState } from 'react';
import { BookOpen, ChevronDown, Minus, Plus, RotateCcw, ShieldCheck } from 'lucide-react';
import {
  calculateCreditThreshold,
  type CreditThresholdStatus,
} from '../../utils/creditThreshold';

const DEFAULT_TOTAL_CREDITS = '130';
const DEFAULT_FAILED_CREDITS = '0';
// Above this many allowed credits the one-segment-per-credit meter gets too thin to read.
const MAX_METER_SEGMENTS = 40;

const STATUS_LABELS: Record<CreditThresholdStatus, string> = {
  safe: 'An toàn',
  near: 'Sát ngưỡng',
  exceeded: 'Đã vượt ngưỡng',
};

function formatCredits(value: number) {
  return String(Math.round(value * 100) / 100);
}

/** Eases the displayed integer toward `target` so a changed result is noticed. */
function useAnimatedInteger(target: number) {
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
      const value = Math.round(from + (target - from) * eased);
      displayRef.current = value;
      setDisplay(value);
      if (progress < 1) frame = window.requestAnimationFrame(step);
    };

    frame = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(frame);
  }, [target]);

  return display;
}

interface CreditStepperProps {
  id: string;
  label: string;
  hint: string;
  value: string;
  min: number;
  fallback: number;
  onChange: (value: string) => void;
}

function CreditStepper({ id, label, hint, value, min, fallback, onChange }: CreditStepperProps) {
  const current = Number(value || fallback);
  const hintId = `${id}-hint`;

  return (
    <div className="credits-field">
      <label htmlFor={id}>{label}</label>
      <div className="credits-stepper">
        <button
          type="button"
          onClick={() => onChange(String(Math.max(min, current - 1)))}
          aria-label={`Giảm ${label.toLowerCase()}`}
        >
          <Minus size={15} aria-hidden="true" />
        </button>
        <input
          id={id}
          type="text"
          inputMode="numeric"
          maxLength={3}
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, ''))}
          aria-describedby={hintId}
        />
        <button
          type="button"
          onClick={() => onChange(String(Math.max(min, current) + 1))}
          aria-label={`Tăng ${label.toLowerCase()}`}
        >
          <Plus size={15} aria-hidden="true" />
        </button>
      </div>
      <p id={hintId} className="credits-hint">{hint}</p>
    </div>
  );
}

interface CreditMeterProps {
  failed: number;
  maxCredits: number;
}

function CreditMeter({ failed, maxCredits }: CreditMeterProps) {
  const segmented = maxCredits >= 1 && maxCredits <= MAX_METER_SEGMENTS;
  const fillPercent = maxCredits > 0 ? Math.min(100, (failed / maxCredits) * 100) : failed > 0 ? 100 : 0;

  return (
    <div className="credits-meter" role="img" aria-label={`Đã rớt ${failed} trên tối đa ${maxCredits} tín chỉ`}>
      {segmented ? (
        <div className="credits-segments">
          {Array.from({ length: maxCredits }, (_, index) => (
            <span
              key={index}
              className={`credits-segment ${index < failed ? 'on' : ''}`}
              style={{ transitionDelay: `${index * 25}ms` }}
            />
          ))}
        </div>
      ) : (
        <div className="credits-track">
          <div className="credits-fill" style={{ width: `${fillPercent}%` }} />
        </div>
      )}
      <div className="credits-scale">
        <span>0</span>
        <span>Tối đa {maxCredits} TC</span>
      </div>
    </div>
  );
}

export function CreditsPage() {
  const [totalCredits, setTotalCredits] = useState(DEFAULT_TOTAL_CREDITS);
  const [failedCredits, setFailedCredits] = useState(DEFAULT_FAILED_CREDITS);
  const [showCalculation, setShowCalculation] = useState(false);

  const total = Number(totalCredits);
  const failed = Number(failedCredits || 0);
  const result = calculateCreditThreshold(total, failed);
  const exceeded = result?.status === 'exceeded';

  // The status chip pulses only when the status changes between two results, not on first render.
  const status = result?.status ?? null;
  const [lastStatus, setLastStatus] = useState(status);
  const [statusChanges, setStatusChanges] = useState(0);
  if (status !== lastStatus) {
    setLastStatus(status);
    if (lastStatus && status) setStatusChanges((count) => count + 1);
  }

  const animatedCreditsLeft = useAnimatedInteger(result ? Math.abs(result.creditsLeft) : 0);

  const handleReset = () => {
    setTotalCredits(DEFAULT_TOTAL_CREDITS);
    setFailedCredits(DEFAULT_FAILED_CREDITS);
  };

  return (
    <div className="page-container tool-page credits-page">
      <div className="page-header compact">
        <h1 className="page-title-with-icon">
          <ShieldCheck aria-hidden="true" />
          <span>Kiểm tra điều kiện hạ bằng</span>
        </h1>
        <p>Xem bạn còn được rớt bao nhiêu tín chỉ trước khi bị hạ bậc bằng tốt nghiệp.</p>
      </div>

      <div className="credits-layout">
        <div className="credits-main">
          <section className="credits-card" aria-labelledby="credits-input-title">
            <div className="credits-section-head">
              <h2 id="credits-input-title">Thông tin tín chỉ</h2>
              <button type="button" className="credits-text-btn" onClick={handleReset}>
                <RotateCcw size={14} aria-hidden="true" />
                Đặt lại
              </button>
            </div>
            <div className="credits-fields">
              <CreditStepper
                id="credits-total-input"
                label="Tổng tín chỉ toàn khóa"
                hint="Xem trong chương trình đào tạo của ngành, thường 120–150 TC."
                value={totalCredits}
                min={1}
                fallback={130}
                onChange={setTotalCredits}
              />
              <CreditStepper
                id="credits-failed-input"
                label="Tín chỉ đã rớt, phải học lại"
                hint="Chỉ tính học phần bị điểm F. Học cải thiện điểm D không tính."
                value={failedCredits}
                min={0}
                fallback={0}
                onChange={setFailedCredits}
              />
            </div>
          </section>

          <section className="credits-rules" aria-labelledby="credits-rules-title">
            <h2 id="credits-rules-title">Quy định hạ bậc tốt nghiệp</h2>
            <dl>
              <div>
                <dt>Bị hạ 1 mức khi</dt>
                <dd>Tín chỉ học lại vượt 5% tổng tín chỉ toàn khóa, hoặc bị kỷ luật từ mức cảnh cáo trở lên trong thời gian học.</dd>
              </div>
              <div>
                <dt>Chỉ áp dụng cho</dt>
                <dd>Bằng Xuất sắc (hạ xuống Giỏi) và bằng Giỏi (hạ xuống Khá).</dd>
              </div>
              <div>
                <dt>Không bị hạ nếu</dt>
                <dd>Xếp loại tốt nghiệp là Khá, Trung bình hoặc Yếu, kể cả khi vượt 5%.</dd>
              </div>
            </dl>
          </section>
        </div>

        <aside className={`credits-result ${result ? result.status : ''}`} aria-labelledby="credits-result-title">
          {result ? (
            <>
              <div className="credits-result-top">
                <span id="credits-result-title">Kết quả</span>
                <span
                  key={statusChanges}
                  className={`credits-chip ${statusChanges > 0 ? 'pulse' : ''}`}
                >
                  {STATUS_LABELS[result.status]}
                </span>
              </div>

              <div aria-live="polite">
                <p className="credits-big-label">
                  {exceeded ? 'Số tín chỉ đã vượt mức tối đa' : 'Còn được rớt thêm tối đa'}
                </p>
                <p className={`credits-big ${exceeded ? 'exceeded' : ''}`}>
                  <strong>{animatedCreditsLeft}</strong>
                  <span>tín chỉ</span>
                </p>
              </div>
              {!Number.isInteger(result.threshold) && (
                <p className="credits-note">
                  5% của {total} TC là {formatCredits(result.threshold)} TC, làm tròn xuống thành {result.maxCredits} TC vì mỗi học phần có số tín chỉ nguyên.
                </p>
              )}
              <p className="credits-sub">
                Đã rớt <strong>{failed} TC</strong> trên mức tối đa <strong>{result.maxCredits} TC</strong>.
              </p>

              <CreditMeter failed={failed} maxCredits={result.maxCredits} />

              <p className="credits-message">{result.message}</p>

              <div className="credits-calc-wrap">
                <button
                  type="button"
                  className="credits-calc-toggle"
                  aria-expanded={showCalculation}
                  aria-controls="credits-calc"
                  onClick={() => setShowCalculation((open) => !open)}
                >
                  <ChevronDown size={15} aria-hidden="true" />
                  Xem cách tính
                </button>
                <div id="credits-calc" className={`credits-calc ${showCalculation ? 'open' : ''}`} inert={!showCalculation}>
                  <div>
                    <dl>
                      <dt>Tổng tín chỉ toàn khóa</dt>
                      <dd>{total} TC</dd>
                      <dt>Ngưỡng 5%</dt>
                      <dd>{total} × 5% = {formatCredits(result.threshold)} TC</dd>
                      <dt>Mức tối đa (làm tròn xuống)</dt>
                      <dd>{result.maxCredits} TC</dd>
                      <dt>Đã rớt, phải học lại</dt>
                      <dd>{failed} TC</dd>
                      <dt>{exceeded ? 'Vượt mức tối đa' : 'Còn được rớt thêm'}</dt>
                      <dd>{Math.abs(result.creditsLeft)} TC</dd>
                    </dl>
                  </div>
                </div>
              </div>

              <p className="credits-source">
                <BookOpen size={14} aria-hidden="true" />
                Theo Khoản 3 Điều 15 Quy chế đào tạo. Kết quả chỉ để tham khảo.
              </p>
            </>
          ) : (
            <p className="credits-empty" id="credits-result-title">
              Nhập tổng tín chỉ toàn khóa (lớn hơn 0) để xem kết quả.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
