import { useState } from 'react';
import { AlertTriangle, Award } from 'lucide-react';
import {
  calculateScholarshipScore,
  type ScholarshipClassification,
  type ScholarshipTierDetail,
} from '../../utils/scholarship';
import {
  SCHOOL_YEARS,
  formatVnd,
  type SchoolYear,
  type TuitionProgram,
} from '../../data/tuitionRates';
import type { GradeTone } from '../../utils/gradeTone';
import { sanitizeDecimal, sanitizeInteger } from '../../utils/numberInput';
import { ScholarshipRulesModal } from '../ScholarshipRulesModal';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton, ToolSection } from '../tool/ToolSection';
import { SelectField, TextField } from '../tool/fields';
import { NumberStepper } from '../tool/NumberStepper';
import { ProgramSearch } from '../tool/ProgramSearch';
import { ResultCard } from '../tool/ResultCard';

const MIN_SCHOLARSHIP_CREDITS = 15;
const DEFAULT_CREDITS = '15';
const DEFAULT_YEAR: SchoolYear = '2024-2025';
const YEAR_OPTIONS = SCHOOL_YEARS.map((year) => ({ value: year, label: `Năm học ${year}` }));

// Scholarship tiers reuse the letter-grade colour bands, so "Xuất sắc" reads like an A.
const TIER_TONES: Record<ScholarshipClassification, GradeTone> = {
  'Xuất sắc': 'excellent',
  Giỏi: 'good',
  Khá: 'fair',
};

interface TierLadderProps {
  tiers: ScholarshipTierDetail[];
  current: ScholarshipClassification | null;
}

/**
 * A slim three-segment progress bar from the lowest tier to the highest. Reached segments share
 * the student's tier colour; only the current tier's label is emphasised.
 */
function TierLadder({ tiers, current }: TierLadderProps) {
  return (
    <ol
      className={['tier-ladder', current && `grade-tone-${TIER_TONES[current]}`].filter(Boolean).join(' ')}
      aria-label="Các mức học bổng, từ thấp đến cao"
    >
      {[...tiers].reverse().map((tier) => {
        const classes = [tier.isFullyMet && 'reached', tier.label === current && 'current'].filter(Boolean).join(' ');
        return (
          <li key={tier.label} className={classes || undefined}>
            <span className="tier-ladder-label">
              <span className="tier-ladder-name">{tier.label}</span>
              <span className="tier-ladder-mult">× {tier.multiplier}</span>
            </span>
            <span className="sr-only">{tier.isFullyMet ? ', đã đạt' : ', chưa đạt'}</span>
          </li>
        );
      })}
    </ol>
  );
}

interface CriteriaProgressProps {
  tier: ScholarshipTierDetail;
  heading: string;
  score: number;
  gpa: number;
  conduct: number;
}

/** Each criterion as value, bar with the tier's threshold marked, and the remaining gap. */
function CriteriaProgress({ tier, heading, score, gpa, conduct }: CriteriaProgressProps) {
  const rows = [
    { label: 'Điểm xét', value: score, valueDecimals: 3, target: tier.minScholarshipScore, max: 4, decimals: 2, met: tier.isScoreMet },
    { label: 'GPA', value: gpa, valueDecimals: 2, target: tier.minAcademicScore, max: 4, decimals: 2, met: tier.isAcademicMet },
    { label: 'Rèn luyện', value: conduct, valueDecimals: 0, target: tier.minConductScore, max: 100, decimals: 0, met: tier.isConductMet },
  ];

  return (
    <div className="criteria-progress">
      <p className="criteria-progress-title">{heading}</p>
      <ul>
        {rows.map((row) => {
          const factor = 10 ** row.decimals;
          // Round the gap up (after trimming float noise) so "thiếu" never understates what is still needed.
          const gap = Math.ceil(Math.round((row.target - row.value) * factor * 1000) / 1000) / factor;
          return (
            <li key={row.label} className={row.met ? 'met' : 'unmet'}>
              <span className="criteria-label">{row.label}</span>
              <strong className="criteria-value">{row.value.toFixed(row.valueDecimals)}</strong>
              <span className="criteria-track" aria-hidden="true">
                <span className="criteria-fill" style={{ width: `${Math.min(100, (row.value / row.max) * 100)}%` }} />
                <span className="criteria-target" style={{ left: `${(row.target / row.max) * 100}%` }} />
              </span>
              <span className="criteria-gap">
                <b>{row.met ? 'Đạt' : `thiếu ${gap.toFixed(row.decimals)}`}</b>
                <small>cần {row.target.toFixed(row.decimals)}</small>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function ScholarshipPage() {
  const [academicScore, setAcademicScore] = useState('');
  const [conductScore, setConductScore] = useState('');
  const [credits, setCredits] = useState(DEFAULT_CREDITS);
  const [query, setQuery] = useState('');
  const [selectedProgram, setSelectedProgram] = useState<TuitionProgram | null>(null);
  const [schoolYear, setSchoolYear] = useState<SchoolYear>(DEFAULT_YEAR);
  const [showRulesModal, setShowRulesModal] = useState(false);

  const gpa = academicScore !== '' ? Number(academicScore) : null;
  const conduct = conductScore !== '' ? Number(conductScore) : null;
  const academicError =
    gpa !== null && (!Number.isFinite(gpa) || gpa < 0 || gpa > 4) ? 'GPA phải từ 0 đến 4.0.' : null;
  const conductError =
    conduct !== null && (!Number.isFinite(conduct) || conduct < 0 || conduct > 100)
      ? 'Điểm rèn luyện phải từ 0 đến 100.'
      : null;

  // No result until both scores are entered and valid, so nothing reads "Chưa đạt" before any input.
  const result =
    gpa !== null && conduct !== null && !academicError && !conductError
      ? calculateScholarshipScore(gpa, conduct)
      : null;
  const classified = Boolean(result?.classification);

  const creditCount = Number(credits);
  const hasCredits = credits !== '' && creditCount > 0;
  const isBelowMinimum = hasCredits && creditCount < MIN_SCHOLARSHIP_CREDITS;
  const perCredit = selectedProgram?.perCredit[schoolYear] ?? 0;
  const amount =
    result?.classification && perCredit > 0 && hasCredits && !isBelowMinimum
      ? creditCount * perCredit * result.multiplier
      : null;

  // Tiers are ordered highest first. Compare against the next tier up, or the top tier once it is reached.
  let targetTier: ScholarshipTierDetail | null = null;
  let criteriaHeading = '';
  if (result) {
    const currentIndex = result.classification
      ? result.tierDetails.findIndex((tier) => tier.label === result.classification)
      : result.tierDetails.length;
    if (currentIndex === 0) {
      targetTier = result.tierDetails[0];
      criteriaHeading = `Đạt đủ điều kiện mức ${targetTier.label}`;
    } else {
      targetTier = result.tierDetails[currentIndex - 1];
      criteriaHeading = `${classified ? 'Để lên' : 'Để đạt'} mức ${targetTier.label} (× ${targetTier.multiplier})`;
    }
  }

  const handleQueryChange = (value: string) => {
    setQuery(value);
    if (selectedProgram && `${selectedProgram.code} - ${selectedProgram.name}` !== value) {
      setSelectedProgram(null);
    }
  };

  const selectProgram = (program: TuitionProgram) => {
    setSelectedProgram(program);
    setQuery(`${program.code} - ${program.name}`);
  };

  const clearProgram = () => {
    setSelectedProgram(null);
    setQuery('');
  };

  const handleReset = () => {
    setAcademicScore('');
    setConductScore('');
    setCredits(DEFAULT_CREDITS);
    setSchoolYear(DEFAULT_YEAR);
    clearProgram();
  };

  return (
    <div className="page-container tool-page simplified">
      <ToolPageHeader
        icon={Award}
        title="Tính điểm học bổng"
        description="Xem bạn đạt học bổng khuyến khích học tập mức nào và ước tính số tiền nhận được."
      />

      <div className="tool-grid">
        <div className="tool-main">
          <ToolSection id="scholarship-input" title="Thông tin xét học bổng" action={<ResetButton onClick={handleReset} />}>
            <div className="tool-group">
              <h3>Điểm học kỳ xét</h3>
              <div className="tool-fields">
                <TextField
                  id="scholarship-gpa"
                  label="GPA học kỳ"
                  value={academicScore}
                  onChange={(value) => setAcademicScore(sanitizeDecimal(value))}
                  suffix="/ 4.0"
                  placeholder="VD: 3.50"
                  error={academicError}
                  hint="Chiếm 80% điểm xét."
                />
                <TextField
                  id="scholarship-conduct"
                  label="Điểm rèn luyện"
                  value={conductScore}
                  onChange={(value) => setConductScore(sanitizeInteger(value))}
                  inputMode="numeric"
                  suffix="/ 100"
                  placeholder="VD: 85"
                  error={conductError}
                  hint="Quy đổi sang thang 4, chiếm 20%."
                />
              </div>
            </div>

            <div className="tool-group">
              <h3>
                Số tiền học bổng <small>không bắt buộc</small>
              </h3>
              <ProgramSearch
                id="scholarship-program"
                label="Ngành đào tạo"
                hint="Dùng để tra đơn giá tín chỉ."
                query={query}
                selectedProgram={selectedProgram}
                onQueryChange={handleQueryChange}
                onSelect={selectProgram}
                onClear={clearProgram}
              />
              <div className="tool-fields">
                <SelectField
                  id="scholarship-year"
                  label="Năm học"
                  value={schoolYear}
                  options={YEAR_OPTIONS}
                  onChange={setSchoolYear}
                />
                <NumberStepper
                  id="scholarship-credits"
                  label="Số tín chỉ học kỳ"
                  hint="Cần tối thiểu 15 TC (học kỳ tốt nghiệp: 6 TC)."
                  value={credits}
                  min={1}
                  fallback={15}
                  onChange={setCredits}
                />
              </div>
              {isBelowMinimum && (
                <p className="tool-inline-warning">
                  <AlertTriangle size={15} aria-hidden="true" />
                  Dưới 15 tín chỉ thì không đủ điều kiện xét học bổng, trừ học kỳ tốt nghiệp (tối thiểu 6 TC).
                </p>
              )}
            </div>
          </ToolSection>
        </div>

        <ResultCard
          id="scholarship-result"
          tone={result ? (classified ? 'success' : 'warning') : null}
          chip={result ? (classified ? 'Đạt học bổng' : 'Chưa đạt') : null}
        >
          {result ? (
            <>
              <div aria-live="polite">
                <p className="tool-big-label">Xếp loại dự kiến</p>
                <p
                  className={`tool-big text ${
                    result.classification ? `grade-tone-${TIER_TONES[result.classification]}` : 'is-muted'
                  }`}
                >
                  <strong>{result.classification ?? 'Chưa đạt'}</strong>
                  {result.classification && <span>hệ số {result.multiplier}</span>}
                </p>
              </div>

              <TierLadder tiers={result.tierDetails} current={result.classification} />

              {targetTier && (
                <CriteriaProgress
                  tier={targetTier}
                  heading={criteriaHeading}
                  score={result.score}
                  gpa={gpa ?? 0}
                  conduct={conduct ?? 0}
                />
              )}

              {classified && (
                <div className="tool-amount">
                  {amount !== null && result.classification ? (
                    <>
                      <span>Số tiền dự kiến</span>
                      <strong>{formatVnd(amount)}</strong>
                      <small>
                        {creditCount} TC × {formatVnd(perCredit)} × hệ số {result.multiplier}
                      </small>
                    </>
                  ) : isBelowMinimum ? (
                    <span className="tool-amount-warning">
                      Chưa tính số tiền vì học kỳ dưới <strong>15 tín chỉ</strong>.
                    </span>
                  ) : !selectedProgram ? (
                    <span>Chọn ngành đào tạo để ước tính số tiền.</span>
                  ) : (
                    <span>Nhập số tín chỉ học kỳ để ước tính số tiền.</span>
                  )}
                </div>
              )}
            </>
          ) : (
            <p className="tool-empty">Nhập GPA và điểm rèn luyện để xem xếp loại học bổng.</p>
          )}

          <div className="tool-source">
            <span>Kết quả chỉ để tham khảo.</span>
            <button type="button" className="tool-text-btn" onClick={() => setShowRulesModal(true)}>
              Xem quy chế học bổng
            </button>
          </div>
        </ResultCard>
      </div>

      <ScholarshipRulesModal isOpen={showRulesModal} onClose={() => setShowRulesModal(false)} />
    </div>
  );
}
