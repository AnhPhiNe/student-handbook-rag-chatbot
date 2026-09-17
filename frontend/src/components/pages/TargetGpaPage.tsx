import { useMemo, useState } from 'react';
import { TrendingUp } from 'lucide-react';
import { type Cohort } from '../../utils/gradeScale';
import { sanitizeDecimal } from '../../utils/numberInput';
import { useAnimatedNumber } from '../../hooks/useAnimatedNumber';
import { GpaReferenceModal } from '../GpaReferenceModal';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton, ToolSection } from '../tool/ToolSection';
import { TextField } from '../tool/fields';
import { ResultCard, type ResultTone } from '../tool/ResultCard';
import { DetailsToggle } from '../tool/DetailsToggle';
import { ScoreBar } from '../tool/ScoreBar';
import { ResultFacts } from '../tool/ResultFacts';
import { ResultCallout } from '../tool/ResultCallout';

interface TargetGpaPageProps {
  cohort?: Cohort;
}

const TARGET_PRESETS = [
  { label: 'Xuất sắc', value: '3.60' },
  { label: 'Giỏi', value: '3.20' },
  { label: 'Khá', value: '2.50' },
];

const CREDIT_PRESETS = ['12', '15', '18', '21'];

function equivalentLetter(gpa: number) {
  if (gpa >= 3.6) return 'A (Xuất sắc)';
  if (gpa >= 3.2) return 'B+ (Giỏi)';
  if (gpa >= 2.5) return 'B (Khá)';
  return 'C+ đến B';
}

export function TargetGpaPage({ cohort = 'K51' }: TargetGpaPageProps) {
  const [currentGpa, setCurrentGpa] = useState('');
  const [currentCredits, setCurrentCredits] = useState('');
  const [targetGpa, setTargetGpa] = useState('');
  const [futureCredits, setFutureCredits] = useState('15');
  const [referenceModalTab, setReferenceModalTab] = useState<'scale' | 'rules' | null>(null);

  const calculation = useMemo(() => {
    const hasCGpa = currentGpa !== '';
    const hasCCreds = currentCredits !== '';
    const hasTGpa = targetGpa !== '';
    const hasFCreds = futureCredits !== '';

    const cGpa = Number(currentGpa);
    const cCreds = Number(currentCredits);
    const tGpa = Number(targetGpa);
    const fCreds = Number(futureCredits);

    const isCGpaInvalid = hasCGpa && (!Number.isFinite(cGpa) || cGpa < 0 || cGpa > 4.0);
    const isCCredsInvalid = hasCCreds && (!Number.isFinite(cCreds) || cCreds <= 0 || cCreds > 250);
    const isTGpaInvalid = hasTGpa && (!Number.isFinite(tGpa) || tGpa <= 0 || tGpa > 4.0);
    const isFCredsInvalid = hasFCreds && (!Number.isFinite(fCreds) || fCreds <= 0 || fCreds > 45);

    const hasAnyError = isCGpaInvalid || isCCredsInvalid || isTGpaInvalid || isFCredsInvalid;
    const isComplete = hasCGpa && hasCCreds && hasTGpa && hasFCreds && !hasAnyError;

    if (!isComplete) {
      return {
        isComplete: false as const,
        isCGpaInvalid,
        isCCredsInvalid,
        isTGpaInvalid,
        isFCredsInvalid,
        requiredGpa: 0,
        totalCreds: 0,
        status: 'empty' as const,
        minCreditsNeeded: null,
      };
    }

    const totalCreds = cCreds + fCreds;
    const requiredGpa = (tGpa * totalCreds - cGpa * cCreds) / fCreds;

    // When one term cannot reach the target even at 4.0, how many credits at 4.0 would.
    let minCreditsNeeded: number | null = null;
    if (requiredGpa > 4.0 && tGpa < 4.0) {
      const needed = ((tGpa - cGpa) * cCreds) / (4.0 - tGpa);
      if (needed > 0) minCreditsNeeded = Math.ceil(needed);
    }

    let status: 'achieved' | 'possible' | 'impossible' = 'possible';
    if (requiredGpa <= 0 || (tGpa <= cGpa && requiredGpa <= cGpa)) {
      status = 'achieved';
    } else if (requiredGpa > 4.0) {
      status = 'impossible';
    }

    return {
      isComplete: true as const,
      isCGpaInvalid: false,
      isCCredsInvalid: false,
      isTGpaInvalid: false,
      isFCredsInvalid: false,
      requiredGpa,
      totalCreds,
      status,
      minCreditsNeeded,
      cGpa,
      cCreds,
      tGpa,
      fCreds,
    };
  }, [currentGpa, currentCredits, targetGpa, futureCredits]);

  let tone: ResultTone | null = null;
  let chip: string | null = null;
  if (calculation.isComplete) {
    if (calculation.status === 'achieved') {
      tone = 'success';
      chip = 'Đã đạt mục tiêu';
    } else if (calculation.status === 'impossible') {
      tone = 'danger';
      chip = 'Không khả thi trong 1 kỳ';
    } else if (calculation.requiredGpa >= 3.6) {
      tone = 'warning';
      chip = 'Rất khó';
    } else {
      tone = 'success';
      chip = 'Khả thi';
    }
  }

  const animatedRequired = useAnimatedNumber(
    calculation.isComplete && calculation.status !== 'achieved' ? Math.round(calculation.requiredGpa * 100) / 100 : 0,
    2,
  );

  const handleReset = () => {
    if (currentGpa || currentCredits || targetGpa || (futureCredits && futureCredits !== '15')) {
      if (!window.confirm('Bạn có chắc chắn muốn xóa trắng các số liệu mục tiêu không?')) {
        return;
      }
    }
    setCurrentGpa('');
    setCurrentCredits('');
    setTargetGpa('');
    setFutureCredits('15');
  };

  return (
    <div className="page-container tool-page simplified">
      <ToolPageHeader
        icon={TrendingUp}
        title="Mục tiêu GPA"
        description="Tính GPA học kỳ tới cần đạt để kéo GPA tích lũy lên mức bạn muốn."
      />

      <div className="tool-grid">
        <div className="tool-main">
          <ToolSection id="target-gpa-input" title="Thông số" action={<ResetButton onClick={handleReset} />}>
            <div className="tool-group">
              <h3>Hiện tại</h3>
              <div className="tool-fields">
                <TextField
                  id="target-curr-gpa"
                  label="GPA tích lũy"
                  value={currentGpa}
                  onChange={(value) => setCurrentGpa(sanitizeDecimal(value))}
                  suffix="/ 4.00"
                  placeholder="VD: 2.85"
                  error={calculation.isCGpaInvalid ? 'GPA phải từ 0 đến 4.00.' : null}
                />
                <TextField
                  id="target-curr-creds"
                  label="Tín chỉ đã tích lũy"
                  value={currentCredits}
                  onChange={(value) => setCurrentCredits(sanitizeDecimal(value))}
                  suffix="TC"
                  placeholder="VD: 60"
                  error={calculation.isCCredsInvalid ? 'Số tín chỉ phải từ 1 đến 250.' : null}
                  hint="Các tín chỉ đang được tính trong GPA tích lũy."
                />
              </div>
            </div>

            <div className="tool-group">
              <h3>Học kỳ tới</h3>
              <div className="tool-fields">
                <TextField
                  id="target-goal-gpa"
                  label="GPA tích lũy muốn đạt"
                  value={targetGpa}
                  onChange={(value) => setTargetGpa(sanitizeDecimal(value))}
                  suffix="/ 4.00"
                  placeholder="VD: 3.20"
                  error={calculation.isTGpaInvalid ? 'Mục tiêu phải lớn hơn 0 và tối đa 4.00.' : null}
                >
                  <div className="tool-chips" role="group" aria-label="Chọn nhanh mục tiêu">
                    {TARGET_PRESETS.map((preset) => (
                      <button
                        key={preset.value}
                        type="button"
                        className="tool-chip"
                        aria-pressed={targetGpa === preset.value}
                        onClick={() => setTargetGpa(preset.value)}
                      >
                        {preset.label} {preset.value}
                      </button>
                    ))}
                  </div>
                </TextField>
                <TextField
                  id="target-future-creds"
                  label="Tín chỉ học kỳ tới"
                  value={futureCredits}
                  onChange={(value) => setFutureCredits(sanitizeDecimal(value))}
                  suffix="TC"
                  placeholder="VD: 15"
                  error={calculation.isFCredsInvalid ? 'Số tín chỉ học kỳ phải từ 1 đến 45.' : null}
                >
                  <div className="tool-chips" role="group" aria-label="Chọn nhanh số tín chỉ">
                    {CREDIT_PRESETS.map((value) => (
                      <button
                        key={value}
                        type="button"
                        className="tool-chip"
                        aria-pressed={futureCredits === value}
                        onClick={() => setFutureCredits(value)}
                      >
                        {value} TC
                      </button>
                    ))}
                  </div>
                </TextField>
              </div>
            </div>
          </ToolSection>
        </div>

        <ResultCard id="target-gpa-result" tone={tone} chip={chip}>
          {calculation.isComplete ? (
            calculation.status === 'achieved' ? (
              <>
                <div aria-live="polite">
                  <p className="tool-big-label">GPA tích lũy hiện tại</p>
                  <p className="tool-big">
                    <strong>{calculation.cGpa.toFixed(2)}</strong>
                    <span>/ 4.00</span>
                  </p>
                </div>
                <ResultFacts
                  facts={[
                    { label: 'Mục tiêu', value: calculation.tGpa.toFixed(2) },
                    { label: 'TC đã tích lũy', value: calculation.cCreds },
                  ]}
                />
                <ResultCallout tone="success">
                  GPA hiện tại đã đạt mục tiêu <strong>{calculation.tGpa.toFixed(2)}</strong>. Chỉ cần giữ phong độ ở học kỳ tới.
                </ResultCallout>
              </>
            ) : (
              <>
                <div aria-live="polite">
                  <p className="tool-big-label">GPA học kỳ tới cần đạt tối thiểu</p>
                  <p className={`tool-big ${calculation.status === 'impossible' ? 'danger' : ''}`}>
                    <strong>{animatedRequired.toFixed(2)}</strong>
                    <span>/ 4.00</span>
                  </p>
                </div>
                <ScoreBar value={calculation.requiredGpa} max={4} maxLabel="4.00" />
                <ResultFacts
                  facts={[
                    { label: 'TC kỳ tới', value: calculation.fCreds },
                    { label: 'Mục tiêu', value: calculation.tGpa.toFixed(2) },
                    { label: 'Tổng TC sau kỳ', value: calculation.totalCreds },
                  ]}
                />
                {calculation.status === 'impossible' ? (
                  <ResultCallout tone="danger">
                    Không thể đạt <strong>{calculation.tGpa.toFixed(2)}</strong> chỉ với{' '}
                    <strong>{calculation.fCreds} tín chỉ</strong> trong 1 kỳ.
                    {calculation.minCreditsNeeded ? (
                      <>
                        {' '}Cần học ít nhất <strong>{calculation.minCreditsNeeded} tín chỉ</strong> và đạt{' '}
                        <strong>4.00</strong> toàn bộ.
                      </>
                    ) : null}
                  </ResultCallout>
                ) : (
                  <ResultCallout tone={tone}>
                    Học kỳ tới cần trung bình khoảng điểm chữ <strong>{equivalentLetter(calculation.requiredGpa)}</strong>.
                  </ResultCallout>
                )}
              </>
            )
          ) : (
            <p className="tool-empty">
              Nhập GPA tích lũy, số tín chỉ đã học và mục tiêu để xem GPA học kỳ tới cần đạt.
            </p>
          )}

          {calculation.isComplete && (
            <DetailsToggle id="target-gpa-calc" label="Xem cách tính">
              <dl className="tool-calc">
                <dt>Tổng tín chỉ sau học kỳ tới</dt>
                <dd>{calculation.totalCreds} TC</dd>
                <dt>Chênh lệch mục tiêu</dt>
                <dd>
                  {calculation.tGpa >= calculation.cGpa ? '+' : ''}
                  {(calculation.tGpa - calculation.cGpa).toFixed(2)}
                </dd>
                <dt>GPA học kỳ tới cần đạt</dt>
                <dd>
                  ({calculation.tGpa.toFixed(2)} × {calculation.totalCreds} − {calculation.cGpa.toFixed(2)} × {calculation.cCreds}) ÷ {calculation.fCreds} ={' '}
                  {calculation.requiredGpa.toFixed(2)}
                </dd>
              </dl>
            </DetailsToggle>
          )}

          <div className="tool-source">
            <span>Kết quả chỉ để tham khảo.</span>
            <button type="button" className="tool-text-btn" onClick={() => setReferenceModalTab('rules')}>
              Quy chế điểm
            </button>
            <button type="button" className="tool-text-btn" onClick={() => setReferenceModalTab('scale')}>
              Bảng quy đổi điểm
            </button>
          </div>
        </ResultCard>
      </div>

      <GpaReferenceModal
        isOpen={referenceModalTab !== null}
        onClose={() => setReferenceModalTab(null)}
        cohort={cohort}
        initialTab={referenceModalTab ?? 'scale'}
      />
    </div>
  );
}
