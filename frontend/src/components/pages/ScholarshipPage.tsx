import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Award, ChevronDown, History, Minus, Plus, MessageCircle } from 'lucide-react';
import {
  calculateScholarshipScore,
  getFinalSemesterMinCredits,
  type ScholarshipClassification,
  type ScholarshipTierDetail,
} from '../../utils/scholarship';
import {
  SCHOOL_YEARS,
  formatVnd,
  type SchoolYear,
  type TuitionProgram,
} from '../../data/tuitionRates';
import type { Cohort } from '../../utils/gradeScale';
import type { GradeTone } from '../../utils/gradeTone';
import { sanitizeDecimal, sanitizeInteger } from '../../utils/numberInput';
import { useStudentProfile } from '../../hooks/useStudentProfile';
import { ShareResultButton } from '../tool/ShareResultButton';
import { scholarshipShareText } from '../../utils/shareText';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton } from '../tool/ToolSection';
import { ProgramSearch } from '../tool/ProgramSearch';

interface ScholarshipPageProps {
  cohort: Cohort;
  onAskChat: (text: string) => void;
}

const MIN_SCHOLARSHIP_CREDITS = 15;
const DEFAULT_CREDITS = '15';
// Newest school year first-class: the last entry is the one students are most likely paying now.
const DEFAULT_YEAR: SchoolYear = SCHOOL_YEARS[SCHOOL_YEARS.length - 1];
const PROGRAM_INPUT_ID = 'scholarship-program';

// Scholarship tiers reuse the letter-grade colour bands, so "Xuất sắc" reads like an A.
const TIER_TONES: Record<ScholarshipClassification, GradeTone> = {
  'Xuất sắc': 'excellent',
  Giỏi: 'good',
  Khá: 'fair',
};

const toneClass = (label: ScholarshipClassification) => `grade-tone-${TIER_TONES[label]} ct-gn-${TIER_TONES[label]}`;

interface CriteriaListProps {
  tier: ScholarshipTierDetail;
  score: number;
  gpa: number;
  conduct: number;
}

/** Each criterion as value, bar with the tier's threshold marked, and the remaining gap. */
function CriteriaList({ tier, score, gpa, conduct }: CriteriaListProps) {
  const rows = [
    { label: 'Điểm xét', value: score, valueDecimals: 3, target: tier.minScholarshipScore, max: 4, decimals: 2, met: tier.isScoreMet },
    { label: 'GPA', value: gpa, valueDecimals: 2, target: tier.minAcademicScore, max: 4, decimals: 2, met: tier.isAcademicMet },
    { label: 'Rèn luyện', value: conduct, valueDecimals: 0, target: tier.minConductScore, max: 100, decimals: 0, met: tier.isConductMet },
  ];

  return (
    <ul className="sc-crit" aria-label={`Điều kiện của mức ${tier.label}`}>
      {rows.map((row) => {
        const factor = 10 ** row.decimals;
        // Round the gap up (after trimming float noise) so the gap never understates what is still needed.
        const gap = Math.ceil(Math.round((row.target - row.value) * factor * 1000) / 1000) / factor;
        return (
          <li key={row.label} className={row.met ? 'met' : undefined}>
            <span className="k">{row.label}</span>
            <span className="val">{row.value.toFixed(row.valueDecimals)}</span>
            <span className="trk" aria-hidden="true">
              <i style={{ width: `${Math.min(100, (row.value / row.max) * 100)}%` }} />
              <em style={{ left: `${(row.target / row.max) * 100}%` }} />
            </span>
            <span className="gap">
              <b>{row.met ? '✓' : `−${gap.toFixed(row.decimals)}`}</b>
              <span className="sr-only">{row.met ? 'đã đạt' : `còn thiếu ${gap.toFixed(row.decimals)}`}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function ScholarshipPage({ cohort, onAskChat }: ScholarshipPageProps) {
  const [academicScore, setAcademicScore] = useState('');
  const [conductScore, setConductScore] = useState('');
  const [credits, setCredits] = useState(DEFAULT_CREDITS);
  const [query, setQuery] = useState('');
  const [selectedProgram, setSelectedProgram] = useState<TuitionProgram | null>(null);
  const [schoolYear, setSchoolYear] = useState<SchoolYear>(DEFAULT_YEAR);
  const [pickedTier, setPickedTier] = useState<ScholarshipClassification | null>(null);
  const [estimateOpen, setEstimateOpen] = useState(false);

  // Offered, never filled in silently: the semester GPA last calculated on the GPA page.
  const { profile } = useStudentProfile();
  const lastSemesterGpa = profile.lastSemesterGpa;

  const conductRef = useRef<HTMLInputElement | null>(null);
  const focusProgram = useRef(false);

  useEffect(() => {
    if (focusProgram.current && estimateOpen) {
      document.getElementById(PROGRAM_INPUT_ID)?.focus();
      focusProgram.current = false;
    }
  });

  const gpa = academicScore !== '' ? Number(academicScore) : null;
  const conduct = conductScore !== '' ? Number(conductScore) : null;
  const academicError = gpa !== null && (!Number.isFinite(gpa) || gpa < 0 || gpa > 4) ? 'GPA từ 0 đến 4.' : null;
  const conductError =
    conduct !== null && (!Number.isFinite(conduct) || conduct < 0 || conduct > 100) ? 'Rèn luyện từ 0 đến 100.' : null;

  // No result until both scores are entered and valid, so nothing reads "Chưa đạt" before any input.
  const result =
    gpa !== null && conduct !== null && !academicError && !conductError
      ? calculateScholarshipScore(gpa, conduct)
      : null;
  const classified = Boolean(result?.classification);

  const creditCount = Number(credits);
  const hasCredits = credits !== '' && creditCount > 0;
  const isBelowMinimum = hasCredits && creditCount < MIN_SCHOLARSHIP_CREDITS;
  const finalSemesterMin = getFinalSemesterMinCredits(cohort);
  const perCredit = selectedProgram?.perCredit[schoolYear] ?? 0;
  const amount =
    result?.classification && perCredit > 0 && hasCredits && !isBelowMinimum
      ? creditCount * perCredit * result.multiplier
      : null;

  // Tiers come highest first. The picker reads low to high; by default it points at the tier just
  // above the one reached (the top tier once it is reached, Khá when nothing is reached).
  const tiersAscending = result ? [...result.tierDetails].reverse() : [];
  let defaultTier: ScholarshipClassification | null = null;
  if (result) {
    const currentIndex = result.classification
      ? result.tierDetails.findIndex((tier) => tier.label === result.classification)
      : result.tierDetails.length;
    defaultTier = result.tierDetails[Math.max(0, currentIndex - 1)].label;
  }
  const selectedLabel = pickedTier ?? defaultTier;
  const selectedTier = result?.tierDetails.find((tier) => tier.label === selectedLabel) ?? null;

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
    setPickedTier(null);
    clearProgram();
  };

  const openEstimate = () => {
    focusProgram.current = true;
    setEstimateOpen(true);
  };

  const stepCredits = (delta: number) => {
    const current = Number(credits || DEFAULT_CREDITS);
    setCredits(String(Math.max(1, current + delta)));
  };

  const handleGpaKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    conductRef.current?.focus();
  };

  const handleConductKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    event.currentTarget.blur();
  };

  const shareText = result
    ? scholarshipShareText({
        classification: result.classification,
        multiplier: result.multiplier,
        score: result.score,
        amount,
        cohort,
      })
    : null;

  const skin = !result ? '' : classified ? 'sc-s-ok' : 'sc-s-warn';
  const heroTone = result?.classification ? toneClass(result.classification) : '';

  let moneyBlock = null;
  if (result && classified) {
    if (isBelowMinimum) {
      moneyBlock = (
        <div className="sc-money">
          <span className="sc-warnline">Dưới {MIN_SCHOLARSHIP_CREDITS} TC: chưa tính tiền.</span>
        </div>
      );
    } else if (!selectedProgram) {
      moneyBlock = (
        <div className="sc-money">
          <span>Số tiền dự kiến (tham khảo)</span>
          <button type="button" className="sc-pill" onClick={openEstimate}>
            Chọn ngành để tính
          </button>
        </div>
      );
    } else if (amount !== null) {
      moneyBlock = (
        <div className="sc-money">
          <div className="sc-money-row">
            <span>Số tiền dự kiến (tham khảo)</span>
            <strong>{formatVnd(amount)}</strong>
          </div>
          <small>
            {creditCount} TC × {formatVnd(perCredit)} × {result.multiplier}
          </small>
        </div>
      );
    } else {
      moneyBlock = (
        <div className="sc-money">
          <span>Nhập số tín chỉ để tính tiền.</span>
        </div>
      );
    }
  }

  return (
    <div className="page-container tool-page simplified sc-page">
      <ToolPageHeader
        icon={Award}
        title="Tính điểm học bổng"
        description="Xem bạn đạt học bổng khuyến khích học tập mức nào và ước tính số tiền nhận được."
      />

      <div className="gpa-m-page-header sc-m-header">
        <div className="gpa-m-title-wrap">
          <Award size={18} aria-hidden="true" className="sc-m-title-icon" />
          <h1 className="gpa-m-page-title">Tính điểm học bổng</h1>
        </div>
      </div>

      <div className="sc-grid">
        <section className={`sc-result ${skin}`} aria-label="Kết quả">
          <div aria-live="polite">
            <div className="sc-label">Học bổng dự kiến</div>
            <div className={`sc-num ${heroTone}`}>
              {result ? (
                result.classification ? (
                  <>
                    <b>{result.classification}</b>
                    <span>× {result.multiplier}</span>
                  </>
                ) : (
                  <b className="none">Chưa đạt</b>
                )
              ) : (
                <b className="none">--</b>
              )}
            </div>
            <div className="sc-cap-wrap">
              {result ? (
                <span className="sc-cap">
                  <span className={`sc-badge${classified ? '' : ' warn'}`}>{classified ? 'Đạt' : 'Chưa đạt'}</span>
                  <span className="sc-sep">│</span>
                  <span>
                    Điểm xét <b>{result.score.toFixed(3)}</b>
                  </span>
                </span>
              ) : (
                <span className="sc-cap empty">Nhập GPA và điểm rèn luyện bên dưới</span>
              )}
            </div>
          </div>

          {result && (
            <div className="sc-detail">
              <div className="sc-tiers" role="group" aria-label="Các mức học bổng">
                {tiersAscending.map((tier) => (
                  <button
                    key={tier.label}
                    type="button"
                    aria-pressed={tier.label === selectedLabel}
                    className={`${tier.isFullyMet ? 'met ' : ''}${toneClass(tier.label)}`}
                    onClick={() => setPickedTier(tier.label)}
                  >
                    <span className="l">{tier.label}</span>
                    {tier.isFullyMet && (
                      <>
                        <span className="v" aria-hidden="true">✓</span>
                        <span className="sr-only">đã đạt</span>
                      </>
                    )}
                  </button>
                ))}
              </div>
              {selectedTier && !selectedTier.isFullyMet && (
                <CriteriaList tier={selectedTier} score={result.score} gpa={gpa ?? 0} conduct={conduct ?? 0} />
              )}
              {moneyBlock}
              <p className="sc-need-more">Cần thêm: mọi tín chỉ trong kỳ đều đạt, không bị kỷ luật.</p>
            </div>
          )}

          <div className="sc-foot">
            <ShareResultButton text={shareText} className="sc-link" />
            <button
              type="button"
              className="sc-link"
              onClick={() => onAskChat(`Điều kiện xét học bổng khuyến khích học tập của ${cohort} là gì?`)}
            >
              <MessageCircle size={14} aria-hidden="true" />
              Hỏi chatbot về quy chế học bổng
            </button>
          </div>
        </section>

        <section className="sc-sheet" aria-labelledby="sc-sheet-title">
          <div className="sc-sheet-head">
            <h2 id="sc-sheet-title">Thông tin xét</h2>
            <ResetButton onClick={handleReset} />
          </div>

          <div className="sc-pair">
            <div className="sc-field">
              <label htmlFor="scholarship-gpa">GPA học kỳ</label>
              <div className={`sc-box${academicError ? ' bad' : ''}`}>
                <input
                  id="scholarship-gpa"
                  type="text"
                  inputMode="decimal"
                  enterKeyHint="next"
                  autoComplete="off"
                  placeholder="VD: 3.50"
                  value={academicScore}
                  onChange={(e) => setAcademicScore(sanitizeDecimal(e.target.value))}
                  onKeyDown={handleGpaKeyDown}
                  aria-invalid={Boolean(academicError)}
                  aria-describedby={academicError ? 'scholarship-gpa-error' : undefined}
                />
                <i>/ 4</i>
              </div>
              {academicScore === '' && lastSemesterGpa && (
                <button
                  type="button"
                  className="sc-use-last"
                  onClick={() => {
                    setAcademicScore(lastSemesterGpa);
                    conductRef.current?.focus();
                  }}
                >
                  <History size={13} aria-hidden="true" />
                  Dùng GPA học kỳ vừa tính: {lastSemesterGpa}
                </button>
              )}
              {academicError && (
                <span id="scholarship-gpa-error" className="sc-ferr">
                  {academicError}
                </span>
              )}
            </div>
            <div className="sc-field">
              <label htmlFor="scholarship-conduct">Điểm rèn luyện</label>
              <div className={`sc-box${conductError ? ' bad' : ''}`}>
                <input
                  id="scholarship-conduct"
                  ref={conductRef}
                  type="text"
                  inputMode="numeric"
                  enterKeyHint="done"
                  autoComplete="off"
                  placeholder="VD: 85"
                  value={conductScore}
                  onChange={(e) => setConductScore(sanitizeInteger(e.target.value))}
                  onKeyDown={handleConductKeyDown}
                  aria-invalid={Boolean(conductError)}
                  aria-describedby={conductError ? 'scholarship-conduct-error' : undefined}
                />
                <i>/ 100</i>
              </div>
              {conductError && (
                <span id="scholarship-conduct-error" className="sc-ferr">
                  {conductError}
                </span>
              )}
            </div>
          </div>

          <div className="sc-row">
            <label className="sc-row-label" htmlFor="scholarship-credits">
              Tín chỉ đăng ký
            </label>
            <span className="sc-step">
              <button type="button" onClick={() => stepCredits(-1)} aria-label="Giảm số tín chỉ">
                <Minus size={16} aria-hidden="true" />
              </button>
              <input
                id="scholarship-credits"
                type="text"
                inputMode="numeric"
                maxLength={3}
                value={credits}
                onChange={(e) => setCredits(sanitizeInteger(e.target.value))}
              />
              <button type="button" onClick={() => stepCredits(1)} aria-label="Tăng số tín chỉ">
                <Plus size={16} aria-hidden="true" />
              </button>
            </span>
          </div>
          {isBelowMinimum && (
            <p className="sc-inline-warn" role="status">
              Cần tối thiểu {MIN_SCHOLARSHIP_CREDITS} TC (học kỳ tốt nghiệp: {finalSemesterMin} TC).
            </p>
          )}

          <div className="sc-opt">
            <button
              type="button"
              className="sc-opt-toggle"
              aria-expanded={estimateOpen}
              aria-controls="sc-opt-body"
              onClick={() => setEstimateOpen((open) => !open)}
            >
              <span>Ước tính số tiền</span>
              <ChevronDown size={16} aria-hidden="true" />
            </button>
            <div className="sc-opt-body" id="sc-opt-body" hidden={!estimateOpen}>
              <ProgramSearch
                id={PROGRAM_INPUT_ID}
                label="Ngành đào tạo"
                query={query}
                selectedProgram={selectedProgram}
                onQueryChange={handleQueryChange}
                onSelect={selectProgram}
                onClear={clearProgram}
              />
              <div>
                <div className="sc-sub" id="sc-year-label">
                  Năm học
                </div>
                <div className="sc-years" role="group" aria-labelledby="sc-year-label">
                  {SCHOOL_YEARS.map((year) => (
                    <button key={year} type="button" aria-pressed={year === schoolYear} onClick={() => setSchoolYear(year)}>
                      {year.replace('-20', '–')}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
