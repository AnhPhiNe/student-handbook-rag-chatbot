import { useRef, useState, type KeyboardEvent } from 'react';
import { MessageCircle, ShieldCheck } from 'lucide-react';
import {
  calculateCreditThreshold,
  getDowngradeVerdict,
  type CreditThresholdStatus,
  type GraduationClassification,
} from '../../utils/creditThreshold';
import { useStudentProfile } from '../../hooks/useStudentProfile';
import { integerCredits } from '../../utils/studentProfile';
import { sanitizeInteger } from '../../utils/numberInput';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton } from '../tool/ToolSection';

interface CreditsPageProps {
  onAskChat: (text: string) => void;
}

// Above this many allowed credits the one-segment-per-credit meter gets too thin to read.
const MAX_METER_SEGMENTS = 40;
const DOWNGRADE_QUESTION = 'Điều kiện bị hạ bậc bằng tốt nghiệp là gì?';

const STATUS_LABELS: Record<CreditThresholdStatus, string> = {
  safe: 'An toàn',
  near: 'Sát ngưỡng',
  exceeded: 'Vượt ngưỡng',
};

const STATUS_SKIN: Record<CreditThresholdStatus, string> = {
  safe: 'sc-s-ok',
  near: 'sc-s-warn',
  exceeded: 'sc-s-bad',
};

const STATUS_BADGE: Record<CreditThresholdStatus, string> = {
  safe: '',
  near: ' warn',
  exceeded: ' bad',
};

const CLASSIFICATIONS: { value: GraduationClassification; label: string }[] = [
  { value: 'excellent', label: 'Xuất sắc' },
  { value: 'good', label: 'Giỏi' },
  { value: 'fair', label: 'Khá trở xuống' },
];

const formatDecimal = (value: number) => String(value).replace('.', ',');

interface CreditMeterProps {
  failed: number;
  maxCredits: number;
}

function CreditMeter({ failed, maxCredits }: CreditMeterProps) {
  const segmented = maxCredits >= 1 && maxCredits <= MAX_METER_SEGMENTS;
  const fillPercent = maxCredits > 0 ? Math.min(100, (failed / maxCredits) * 100) : failed > 0 ? 100 : 0;

  return (
    <div className="cr-meter" role="img" aria-label={`Đã không đạt ${failed} trên tối đa ${maxCredits} tín chỉ`}>
      {segmented ? (
        <div className="cr-segs">
          {Array.from({ length: maxCredits }, (_, index) => (
            <i key={index} className={index < failed ? 'on' : ''} />
          ))}
        </div>
      ) : (
        <div className="cr-bar">
          <i style={{ width: `${fillPercent}%` }} />
        </div>
      )}
      <div className="cr-scale">
        <span>0</span>
        <span>Tối đa {maxCredits} TC</span>
      </div>
    </div>
  );
}

export function CreditsPage({ onAskChat }: CreditsPageProps) {
  // The degree total is the student's own number: reuse the one saved by the GPA target page.
  const { profile, update: updateProfile } = useStudentProfile();
  const [totalCredits, setTotalCredits] = useState(() => integerCredits(profile.totalDegreeCredits));
  const [failedCredits, setFailedCredits] = useState('');
  const [classification, setClassification] = useState<GraduationClassification | null>(null);
  const failedRef = useRef<HTMLInputElement>(null);

  const total = Number(totalCredits);
  const failed = Number(failedCredits || 0);
  const result = totalCredits === '' ? null : calculateCreditThreshold(total, failed);
  const exceeded = result?.status === 'exceeded';
  const verdict = result ? getDowngradeVerdict(result.status, classification) : null;

  const handleReset = () => {
    setTotalCredits('');
    setFailedCredits('');
    setClassification(null);
  };

  const handleTotalKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      failedRef.current?.focus();
    }
  };

  const toggleClassification = (value: GraduationClassification) => {
    setClassification((current) => (current === value ? null : value));
  };

  const renderVerdict = () => {
    if (!verdict) return null;
    switch (verdict.kind) {
      case 'fair-safe':
        return <>Xếp loại Khá trở xuống <b>không bị hạ bằng</b> theo quy định này.</>;
      case 'downgrade':
        return <>Bằng <b>{verdict.from}</b> sẽ bị hạ xuống <b>{verdict.to}</b>.</>;
      case 'kept':
        return <>Bằng <b>{verdict.from}</b> giữ nguyên, nếu không bị kỷ luật từ mức cảnh cáo.</>;
      case 'may-downgrade':
        return <>Nếu xếp loại Giỏi hoặc Xuất sắc, bằng sẽ <b>bị hạ một mức</b>.</>;
      default:
        return <>Bị kỷ luật từ mức cảnh cáo cũng làm bằng Giỏi, Xuất sắc bị hạ một mức.</>;
    }
  };

  return (
    <div className="page-container tool-page simplified sc-page cr-page">
      <ToolPageHeader
        icon={ShieldCheck}
        title="Kiểm tra hạ bằng"
        description="Xem bạn còn được không đạt bao nhiêu tín chỉ trước khi bằng Giỏi, Xuất sắc bị hạ một mức."
      />

      <div className="gpa-m-page-header sc-m-header">
        <div className="gpa-m-title-wrap">
          <ShieldCheck size={18} aria-hidden="true" className="sc-m-title-icon" />
          <h1 className="gpa-m-page-title">Kiểm tra hạ bằng</h1>
        </div>
      </div>

      <div className="sc-grid">
        <section className={`sc-result ${result ? STATUS_SKIN[result.status] : ''}`} aria-label="Kết quả">
          <div aria-live="polite">
            <div className="sc-label">{exceeded ? 'Đã vượt mức tối đa' : 'Còn được không đạt tối đa'}</div>
            <div className="sc-num">
              {result ? (
                <>
                  <b className={exceeded ? 'neg' : ''}>{Math.abs(result.creditsLeft)}</b>
                  <span>tín chỉ</span>
                </>
              ) : (
                <b className="none">--</b>
              )}
            </div>
            <div className="sc-cap-wrap">
              {result ? (
                <span className="sc-cap">
                  <span className={`sc-badge${STATUS_BADGE[result.status]}`}>{STATUS_LABELS[result.status]}</span>
                  <span className="sc-sep">│</span>
                  Đã không đạt {failed} / tối đa {result.maxCredits} TC
                </span>
              ) : (
                <span className="sc-cap empty">Nhập tổng tín chỉ toàn khóa bên dưới</span>
              )}
            </div>
          </div>

          {result && verdict && (
            <>
              <CreditMeter failed={failed} maxCredits={result.maxCredits} />
              <p className="cr-why">
                5% × {total} TC = {formatDecimal(result.threshold)} TC
                {Number.isInteger(result.threshold) ? '.' : `, làm tròn xuống ${result.maxCredits} TC.`}
              </p>
              <div className={`cr-verdict ${verdict.tone}`}>{renderVerdict()}</div>
            </>
          )}

          <div className="cr-foot">
            <span>Khoản 3 Điều 15 Quy chế đào tạo</span>
            <button type="button" className="sc-link" onClick={() => onAskChat(DOWNGRADE_QUESTION)}>
              <MessageCircle size={14} aria-hidden="true" />
              Hỏi chatbot
            </button>
          </div>
        </section>

        <section className="sc-sheet" aria-labelledby="cr-sheet-title">
          <div className="sc-sheet-head">
            <h2 id="cr-sheet-title">Thông tin</h2>
            <ResetButton onClick={handleReset} />
          </div>

          <div className="sc-pair">
            <div className="sc-field">
              <label htmlFor="credits-total-input">Tổng tín chỉ toàn khóa</label>
              <div className="sc-box">
                <input
                  id="credits-total-input"
                  type="text"
                  inputMode="numeric"
                  enterKeyHint="next"
                  autoComplete="off"
                  placeholder="VD: 130"
                  value={totalCredits}
                  onChange={(e) => {
                    const next = sanitizeInteger(e.target.value);
                    setTotalCredits(next);
                    updateProfile({ totalDegreeCredits: next });
                  }}
                  onKeyDown={handleTotalKeyDown}
                  aria-describedby="credits-total-hint"
                />
                <i>TC</i>
              </div>
              <span id="credits-total-hint" className="cr-hint">
                Theo chương trình đào tạo
              </span>
            </div>
            <div className="sc-field">
              <label htmlFor="credits-failed-input">Tín chỉ từng không đạt</label>
              <div className="sc-box">
                <input
                  id="credits-failed-input"
                  ref={failedRef}
                  type="text"
                  inputMode="numeric"
                  enterKeyHint="done"
                  autoComplete="off"
                  placeholder="0"
                  value={failedCredits}
                  onChange={(e) => setFailedCredits(sanitizeInteger(e.target.value))}
                  aria-describedby="credits-failed-hint"
                />
                <i>TC</i>
              </div>
              <span id="credits-failed-hint" className="cr-hint">
                Tính cả môn đã học lại và qua. Không tính học cải thiện.
              </span>
            </div>
          </div>

          <div className="cr-cls">
            <div className="sc-sub" id="cr-cls-label">
              Xếp loại tốt nghiệp dự kiến <small>(tùy chọn)</small>
            </div>
            <div className="sc-years" role="group" aria-labelledby="cr-cls-label">
              {CLASSIFICATIONS.map(({ value, label }) => (
                <button key={value} type="button" aria-pressed={classification === value} onClick={() => toggleClassification(value)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
