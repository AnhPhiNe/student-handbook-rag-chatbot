import { useMemo, useState, type ReactNode } from 'react';
import { Plus, Target, Trash2 } from 'lucide-react';
import {
  getCourseGroupOptions,
  getDefaultCourseGroup,
  getGradeScale,
  isSplitGradeCohort,
  type Cohort,
  type CourseGroup,
  type GradeScaleRow,
} from '../../utils/gradeScale';
import { sanitizeDecimal } from '../../utils/numberInput';
import { getGradeTone } from '../../utils/gradeTone';
import { useAnimatedNumber } from '../../hooks/useAnimatedNumber';
import { GpaReferenceModal } from '../GpaReferenceModal';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton } from '../tool/ToolSection';
import { ResultCard, type ResultTone } from '../tool/ResultCard';
import { ToolMobileSummary } from '../tool/ToolMobileSummary';
import { ResultFacts } from '../tool/ResultFacts';
import { ResultCallout } from '../tool/ResultCallout';

interface CourseTargetPageProps {
  cohort: Cohort;
}

interface ScoreComponent {
  id: string;
  name: string;
  weight: string;
  score: string;
}

type TargetStatus = 'possible' | 'achieved' | 'impossible';

interface GradeTarget {
  grade: GradeScaleRow;
  requiredScore: number | null;
  status: TargetStatus;
}

interface SyllabusPreset {
  label: string;
  components: Array<{ name: string; weight: string }>;
}

const SYLLABUS_PRESETS: SyllabusPreset[] = [
  { label: '20% - 20% (Thi 60%)', components: [{ name: 'Quá trình', weight: '20' }, { name: 'Giữa kỳ', weight: '20' }] },
  { label: '30% (Thi 70%)', components: [{ name: 'Quá trình', weight: '30' }] },
  { label: '10% - 30% (Thi 60%)', components: [{ name: 'Chuyên cần', weight: '10' }, { name: 'Giữa kỳ', weight: '30' }] },
  { label: '10% - 40% (Thi 50%)', components: [{ name: 'Chuyên cần', weight: '10' }, { name: 'Giữa kỳ', weight: '40' }] },
];

const COMPONENT_NAMES = ['Quá trình', 'Chuyên cần', 'Giữa kỳ', 'Thực hành', 'Bài tập', 'Tiểu luận', 'Thuyết trình', 'Khác'];

// A required final score above this is reachable but hard, so the result is flagged as a warning.
const HARD_FINAL_SCORE = 8;

// Ids for columns added after the defaults; a module counter keeps handlers pure.
let addedComponentCount = 0;
function createComponentId() {
  addedComponentCount += 1;
  return `comp-added-${addedComponentCount}`;
}

function defaultComponents(): ScoreComponent[] {
  return [
    { id: 'comp-1', name: 'Quá trình', weight: '20', score: '' },
    { id: 'comp-2', name: 'Giữa kỳ', weight: '20', score: '' },
  ];
}

export function CourseTargetPage({ cohort }: CourseTargetPageProps) {
  const [courseGroup, setCourseGroup] = useState<CourseGroup>(getDefaultCourseGroup(cohort));
  const [components, setComponents] = useState<ScoreComponent[]>(defaultComponents);
  const [referenceModalTab, setReferenceModalTab] = useState<'scale' | 'rules' | null>(null);

  const isSplit = isSplitGradeCohort(cohort);
  const activeGroup = isSplit ? courseGroup : getDefaultCourseGroup(cohort);
  const scale = getGradeScale(cohort, activeGroup);

  const addComponent = () => {
    setComponents((current) => [...current, { id: createComponentId(), name: 'Quá trình', weight: '', score: '' }]);
  };

  const removeComponent = (id: string) => {
    setComponents((current) => (current.length > 1 ? current.filter((component) => component.id !== id) : current));
  };

  const updateComponent = (id: string, field: keyof ScoreComponent, value: string) => {
    setComponents((current) => current.map((component) => (component.id === id ? { ...component, [field]: value } : component)));
  };

  const applyPreset = (preset: SyllabusPreset) => {
    setComponents(
      preset.components.map((component) => ({
        id: createComponentId(),
        name: component.name,
        weight: component.weight,
        score: '',
      }))
    );
  };

  const handleReset = () => {
    const hasData = components.some((c) => c.score !== '' || (c.weight !== '20' && c.weight !== ''));
    if (hasData && !window.confirm('Bạn có chắc chắn muốn khôi phục về bảng điểm mặc định không?')) {
      return;
    }
    setComponents(defaultComponents());
  };

  const result = useMemo(() => {
    let totalWeight = 0;
    let accumulatedScore = 0;
    let weightedCount = 0;
    let hasInvalidWeight = false;
    let hasInvalidScore = false;
    let hasMissingScore = false;

    for (const component of components) {
      const weight = Number(component.weight);
      const score = Number(component.score);

      if (component.weight !== '') {
        if (!Number.isFinite(weight) || weight < 0 || weight > 100) {
          hasInvalidWeight = true;
        } else {
          totalWeight += weight;
          if (weight > 0) weightedCount += 1;
          if (weight > 0 && component.score === '') hasMissingScore = true;
        }
      }

      if (component.score !== '') {
        if (!Number.isFinite(score) || score < 0 || score > 10) {
          hasInvalidScore = true;
        } else if (component.weight !== '' && Number.isFinite(weight) && weight >= 0) {
          accumulatedScore += (score * weight) / 100;
        }
      }
    }

    const remainingWeight = Math.max(0, 100 - totalWeight);
    const hasWeightOverflow = totalWeight > 100;
    // A column with a weight but no score would otherwise count as 0 and show alarming targets.
    const isComplete = !hasWeightOverflow && !hasInvalidWeight && !hasInvalidScore && !hasMissingScore && weightedCount > 0;

    const targets: GradeTarget[] = scale.rows
      .filter((row) => row.status === 'Đạt')
      .map((grade) => {
        const missingScore = grade.min10 - accumulatedScore;
        if (remainingWeight === 0) {
          return { grade, requiredScore: null, status: missingScore <= 0 ? 'achieved' : 'impossible' };
        }
        const requiredScore = (missingScore * 100) / remainingWeight;
        const status: TargetStatus = requiredScore > 10 ? 'impossible' : requiredScore <= 0 ? 'achieved' : 'possible';
        return { grade, requiredScore, status };
      });

    let errorMessage: string | null = null;
    if (hasWeightOverflow) errorMessage = `Tổng trọng số đang là ${totalWeight}%, vượt quá 100%. Hãy sửa lại các cột.`;
    else if (hasInvalidWeight) errorMessage = 'Trọng số mỗi cột phải từ 0 đến 100%.';
    else if (hasInvalidScore) errorMessage = 'Điểm mỗi cột phải từ 0 đến 10.';

    return {
      totalWeight,
      remainingWeight,
      accumulatedScore,
      isComplete,
      hasWeightOverflow,
      weightedCount,
      targets,
      passTarget: targets.length > 0 ? targets[targets.length - 1] : null,
      errorMessage,
    };
  }, [components, scale]);

  const passTarget = result.isComplete ? result.passTarget : null;
  let tone: ResultTone | null = null;
  let chip: string | null = null;
  if (passTarget?.status === 'achieved') {
    tone = 'success';
    chip = 'Đã đủ qua môn';
  } else if (passTarget?.status === 'impossible') {
    tone = 'danger';
    chip = 'Không thể qua môn';
  } else if (passTarget?.requiredScore != null) {
    const isHard = passTarget.requiredScore > HARD_FINAL_SCORE;
    tone = isHard ? 'warning' : 'success';
    chip = isHard ? 'Cần điểm thi cao' : 'Khả thi';
  }

  const animatedRequired = useAnimatedNumber(
    passTarget?.status === 'possible' && passTarget.requiredScore != null ? Math.round(passTarget.requiredScore * 100) / 100 : 0,
    2,
  );

  // The lowest grade above the pass mark that the final exam can still reach, as a stretch goal.
  const stretchTarget = passTarget
    ? result.targets.slice(0, -1).reverse().find((target) => target.status === 'possible') ?? null
    : null;
  const stretchAdvice =
    stretchTarget?.requiredScore != null ? (
      <>
        {' '}Muốn đạt <strong>{stretchTarget.grade.letter}</strong> cần thi <strong>{stretchTarget.requiredScore.toFixed(2)}</strong>.
      </>
    ) : null;

  let passAdvice: ReactNode = null;
  if (passTarget?.status === 'possible' && passTarget.requiredScore != null) {
    passAdvice = (
      <>
        Cần thi từ <strong>{passTarget.requiredScore.toFixed(2)}</strong> điểm để qua môn.{stretchAdvice}
      </>
    );
  } else if (passTarget?.status === 'achieved') {
    passAdvice = <>Điểm các cột đã đủ qua môn.{stretchAdvice}</>;
  } else if (passTarget?.status === 'impossible') {
    passAdvice =
      result.remainingWeight === 0 ? (
        <>
          Điểm các cột chưa đủ mức qua môn <strong>({passTarget.grade.letter})</strong> và không còn điểm thi cuối kỳ.
        </>
      ) : (
        <>
          Dù thi được <strong>10</strong> điểm cũng chưa đủ mức qua môn <strong>({passTarget.grade.letter})</strong>.
        </>
      );
  }

  const emptyMessage =
    result.weightedCount === 0
      ? 'Nhập trọng số và điểm của các cột đã có để xem điểm thi cần đạt.'
      : 'Nhập điểm cho mọi cột đã có trọng số để xem điểm thi cần đạt.';

  const summaryValue =
    passTarget?.status === 'achieved'
      ? 'Đã đủ'
      : passTarget?.status === 'impossible'
      ? '> 10'
      : passTarget?.requiredScore != null
      ? passTarget.requiredScore.toFixed(2)
      : '--';

  const groupLabel = getCourseGroupOptions(cohort).find((option) => option.id === activeGroup)?.shortLabel;

  return (
    <div className="page-container tool-page simplified">
      <ToolPageHeader
        icon={Target}
        title="Mục tiêu môn học"
        description={`Tính điểm thi cuối kỳ cần đạt từ các cột điểm đã có, theo thang điểm ${cohort}.`}
      />

      <ToolMobileSummary
        label={`Thi cần đạt${result.passTarget ? ` (${result.passTarget.grade.letter})` : ''}`}
        value={summaryValue}
        unit={passTarget?.status === 'possible' ? '/ 10' : undefined}
        chip={chip}
        tone={tone}
      />

      <div className="tool-grid wide">
        <div className="tool-main">
          <div className="tool-toolbar">
            {isSplit ? (
              <div className="tool-segmented" role="group" aria-label="Nhóm môn học">
                {getCourseGroupOptions(cohort).map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    aria-pressed={courseGroup === option.id}
                    onClick={() => setCourseGroup(option.id)}
                    title={option.label}
                  >
                    {option.shortLabel}
                  </button>
                ))}
              </div>
            ) : (
              <span className="tool-toolbar-label">Các cột điểm đã có</span>
            )}
            <ResetButton onClick={handleReset} />
          </div>

          <div className="course-target-form-card">
            <div className="course-target-presets-bar">
              <span className="course-target-presets-label">Mẫu trọng số:</span>
              {SYLLABUS_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className="course-target-preset-chip"
                  onClick={() => applyPreset(preset)}
                >
                  {preset.label}
                </button>
              ))}
            </div>

            <div className="course-target-table-wrap">
              <table className="course-target-table">
                <thead>
                  <tr>
                    <th style={{ width: '35%' }}>Thành phần</th>
                    <th style={{ width: '28%' }}>Trọng số (%)</th>
                    <th style={{ width: '28%' }}>Điểm (10)</th>
                    <th style={{ width: '9%' }}>
                      <span className="sr-only">Xóa</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {components.map((component, index) => {
                    const weight = Number(component.weight);
                    const score = Number(component.score);
                    const isWeightInvalid = component.weight !== '' && (!Number.isFinite(weight) || weight < 0 || weight > 100);
                    const isScoreInvalid = component.score !== '' && (!Number.isFinite(score) || score < 0 || score > 10);
                    return (
                      <tr key={component.id}>
                        <td>
                          <select
                            value={component.name}
                            onChange={(e) => updateComponent(component.id, 'name', e.target.value)}
                            className="course-target-select"
                            aria-label={`Tên cột điểm ${index + 1}`}
                          >
                            {COMPONENT_NAMES.map((name) => (
                              <option key={name} value={name}>
                                {name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <div className="course-target-input-wrap">
                            <input
                              type="text"
                              inputMode="decimal"
                              value={component.weight}
                              onChange={(e) => updateComponent(component.id, 'weight', sanitizeDecimal(e.target.value))}
                              className={`course-target-input ${isWeightInvalid ? 'input-error' : ''}`}
                              placeholder="VD: 20"
                              aria-label={`Trọng số cột ${index + 1}`}
                              aria-invalid={isWeightInvalid}
                            />
                            <span className="course-target-affix">%</span>
                          </div>
                        </td>
                        <td>
                          <div className="course-target-input-wrap">
                            <input
                              type="text"
                              inputMode="decimal"
                              value={component.score}
                              onChange={(e) => updateComponent(component.id, 'score', sanitizeDecimal(e.target.value))}
                              className={`course-target-input ${isScoreInvalid ? 'input-error' : ''}`}
                              placeholder="VD: 7.5"
                              aria-label={`Điểm cột ${index + 1}`}
                              aria-invalid={isScoreInvalid}
                            />
                            <span className="course-target-affix">/ 10</span>
                          </div>
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          {components.length > 1 && (
                            <button
                              type="button"
                              className="course-target-del-btn"
                              onClick={() => removeComponent(component.id)}
                              aria-label={`Xóa cột điểm ${index + 1}`}
                            >
                              <Trash2 size={15} aria-hidden="true" />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="course-target-weight-bar-card">
              <div className="course-target-weight-header">
                <div className="course-target-weight-stat">
                  <span className="course-target-dot entered" />
                  <span>
                    Đã có: <strong>{result.totalWeight}%</strong>
                  </span>
                </div>
                <div className="course-target-weight-stat">
                  <span className="course-target-dot final" />
                  <span>
                    Thi cuối kỳ: <strong>{result.hasWeightOverflow ? '0%' : `${result.remainingWeight}%`}</strong>
                  </span>
                </div>
              </div>
              <div className="course-target-progress-track">
                <div
                  className={`course-target-progress-fill entered ${result.hasWeightOverflow ? 'error' : ''}`}
                  style={{ width: `${Math.min(100, Math.max(0, result.totalWeight))}%` }}
                />
                {result.totalWeight < 100 && (
                  <div className="course-target-progress-fill final" style={{ width: `${result.remainingWeight}%` }} />
                )}
              </div>
            </div>
          </div>

          <div className="gpa-bottom-add">
            <button
              type="button"
              className="gpa-add-dashed-btn"
              onClick={addComponent}
              disabled={result.totalWeight >= 100}
            >
              <Plus size={16} aria-hidden="true" />
              <span>Thêm cột điểm</span>
            </button>
          </div>
        </div>

        <ResultCard id="course-target-result" title="Mục tiêu cuối kỳ" tone={tone} chip={chip}>
          {passTarget ? (
            <>
              <div aria-live="polite">
                <p className="tool-big-label">Điểm thi cuối kỳ cần đạt để qua môn ({passTarget.grade.letter})</p>
                {passTarget.status === 'possible' && (
                  <p className="tool-big">
                    <strong>{animatedRequired.toFixed(2)}</strong>
                    <span>/ 10</span>
                  </p>
                )}
                {passTarget.status === 'achieved' && (
                  <p className="tool-big text">
                    <strong>Đã đủ</strong>
                    <span>điểm qua môn</span>
                  </p>
                )}
                {passTarget.status === 'impossible' && (
                  <p className="tool-big text danger">
                    <strong>&gt; 10</strong>
                    <span>không thể qua môn</span>
                  </p>
                )}
              </div>
              <ResultFacts
                facts={[
                  { label: 'Điểm tích lũy', value: result.accumulatedScore.toFixed(2) },
                  { label: 'Đã có', value: `${result.totalWeight}%` },
                  { label: 'Thi cuối kỳ', value: `${result.remainingWeight}%` },
                ]}
              />
              {passAdvice && <ResultCallout tone={tone}>{passAdvice}</ResultCallout>}

              <p className="tool-grade-list-title">Điểm thi cần cho từng mức</p>
              <ul className="tool-grade-list">
                {result.targets.map((target) => (
                  <li key={target.grade.letter} className={target === passTarget ? 'is-pass' : undefined}>
                    <span>
                      <span className={`tool-grade-letter grade-tone-${getGradeTone(target.grade)}`}>{target.grade.letter}</span>
                      <span className="tool-grade-min">từ {target.grade.min10.toFixed(1)}</span>
                      {target === passTarget && <span className="tool-grade-tag">mức qua môn</span>}
                    </span>
                    <span className={`tool-grade-value ${target.status}`}>
                      {target.status === 'achieved'
                        ? 'Đã đạt'
                        : target.status === 'impossible'
                        ? 'Không thể'
                        : target.requiredScore?.toFixed(2)}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            !result.errorMessage && <p className="tool-empty">{emptyMessage}</p>
          )}

          {result.errorMessage && (
            <p className="tool-error" role="alert">
              {result.errorMessage}
            </p>
          )}

          <div className="tool-source">
            <span>
              Theo thang điểm {cohort}
              {isSplit && groupLabel ? `, nhóm ${groupLabel}` : ''}.
            </span>
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
