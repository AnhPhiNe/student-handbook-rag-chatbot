import { useState } from 'react';
import { BookOpen, ShieldCheck } from 'lucide-react';
import {
  calculateCreditThreshold,
  type CreditThresholdStatus,
} from '../../utils/creditThreshold';
import { useAnimatedNumber } from '../../hooks/useAnimatedNumber';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton, ToolSection } from '../tool/ToolSection';
import { NumberStepper } from '../tool/NumberStepper';
import { ResultCard, type ResultTone } from '../tool/ResultCard';
import { DetailsToggle } from '../tool/DetailsToggle';
import { ResultFacts } from '../tool/ResultFacts';
import { ResultCallout } from '../tool/ResultCallout';

const DEFAULT_TOTAL_CREDITS = '130';
const DEFAULT_FAILED_CREDITS = '0';
// Above this many allowed credits the one-segment-per-credit meter gets too thin to read.
const MAX_METER_SEGMENTS = 40;

const STATUS_LABELS: Record<CreditThresholdStatus, string> = {
  safe: 'An toàn',
  near: 'Sát ngưỡng',
  exceeded: 'Đã vượt ngưỡng',
};

const STATUS_TONES: Record<CreditThresholdStatus, ResultTone> = {
  safe: 'success',
  near: 'warning',
  exceeded: 'danger',
};

function formatCredits(value: number) {
  return String(Math.round(value * 100) / 100);
}

interface CreditMeterProps {
  failed: number;
  maxCredits: number;
}

function CreditMeter({ failed, maxCredits }: CreditMeterProps) {
  const segmented = maxCredits >= 1 && maxCredits <= MAX_METER_SEGMENTS;
  const fillPercent = maxCredits > 0 ? Math.min(100, (failed / maxCredits) * 100) : failed > 0 ? 100 : 0;

  return (
    <div className="tool-bar" role="img" aria-label={`Đã rớt ${failed} trên tối đa ${maxCredits} tín chỉ`}>
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
        <div className="tool-bar-track">
          <div className="tool-bar-fill" style={{ width: `${fillPercent}%` }} />
        </div>
      )}
      <div className="tool-scale">
        <span>0</span>
        <span>Tối đa {maxCredits} TC</span>
      </div>
    </div>
  );
}

export function CreditsPage() {
  const [totalCredits, setTotalCredits] = useState(DEFAULT_TOTAL_CREDITS);
  const [failedCredits, setFailedCredits] = useState(DEFAULT_FAILED_CREDITS);

  const total = Number(totalCredits);
  const failed = Number(failedCredits || 0);
  const result = calculateCreditThreshold(total, failed);
  const exceeded = result?.status === 'exceeded';
  const animatedCreditsLeft = useAnimatedNumber(result ? Math.abs(result.creditsLeft) : 0);

  const handleReset = () => {
    setTotalCredits(DEFAULT_TOTAL_CREDITS);
    setFailedCredits(DEFAULT_FAILED_CREDITS);
  };

  return (
    <div className="page-container tool-page simplified">
      <ToolPageHeader
        icon={ShieldCheck}
        title="Kiểm tra điều kiện hạ bằng"
        description="Xem bạn còn được rớt bao nhiêu tín chỉ trước khi bị hạ bậc bằng tốt nghiệp."
      />

      <div className="tool-grid">
        <div className="tool-main">
          <ToolSection id="credits-input" title="Thông tin tín chỉ" action={<ResetButton onClick={handleReset} />}>
            <div className="tool-fields">
              <NumberStepper
                id="credits-total-input"
                label="Tổng tín chỉ toàn khóa"
                hint="Xem trong chương trình đào tạo của ngành, thường 120–150 TC."
                value={totalCredits}
                min={1}
                fallback={130}
                onChange={setTotalCredits}
              />
              <NumberStepper
                id="credits-failed-input"
                label="Tín chỉ đã rớt, phải học lại"
                hint="Chỉ tính học phần bị điểm F. Học cải thiện điểm D không tính."
                value={failedCredits}
                min={0}
                fallback={0}
                onChange={setFailedCredits}
              />
            </div>
          </ToolSection>

          <section className="tool-rules tool-secondary" aria-labelledby="credits-rules-title">
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

        <ResultCard
          id="credits-result"
          tone={result ? STATUS_TONES[result.status] : null}
          chip={result ? STATUS_LABELS[result.status] : null}
        >
          {result ? (
            <>
              <div aria-live="polite">
                <p className="tool-big-label">
                  {exceeded ? 'Số tín chỉ đã vượt mức tối đa' : 'Còn được rớt thêm tối đa'}
                </p>
                <p className={`tool-big ${exceeded ? 'danger' : ''}`}>
                  <strong>{animatedCreditsLeft}</strong>
                  <span>tín chỉ</span>
                </p>
              </div>
              {!Number.isInteger(result.threshold) && (
                <p className="tool-footnote">
                  5% của {total} TC là {formatCredits(result.threshold)} TC, làm tròn xuống thành {result.maxCredits} TC vì mỗi học phần có số tín chỉ nguyên.
                </p>
              )}
              <CreditMeter failed={failed} maxCredits={result.maxCredits} />

              <ResultFacts
                facts={[
                  {
                    label: 'Đã rớt',
                    value: `${failed} TC`,
                    tone: result.status === 'safe' ? null : STATUS_TONES[result.status],
                  },
                  { label: 'Tối đa được rớt', value: `${result.maxCredits} TC` },
                  { label: 'Ngưỡng 5%', value: `${formatCredits(result.threshold)} TC` },
                ]}
              />

              <ResultCallout tone={STATUS_TONES[result.status]}>{result.message}</ResultCallout>

              <DetailsToggle id="credits-calc" label="Xem cách tính">
                <dl className="tool-calc">
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
              </DetailsToggle>

              <p className="tool-source">
                <BookOpen size={14} aria-hidden="true" />
                Theo Khoản 3 Điều 15 Quy chế đào tạo. Kết quả chỉ để tham khảo.
              </p>
            </>
          ) : (
            <p className="tool-empty">Nhập tổng tín chỉ toàn khóa (lớn hơn 0) để xem kết quả.</p>
          )}
        </ResultCard>
      </div>
    </div>
  );
}
