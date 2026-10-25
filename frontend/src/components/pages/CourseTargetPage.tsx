import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react';
import { ArrowUpRight, Plus, Target, X } from 'lucide-react';
import {
  getCourseGroupOptions,
  getDefaultCourseGroup,
  getGradeScale,
  isSplitGradeCohort,
  type Cohort,
  type CourseGroup,
} from '../../utils/gradeScale';
import { sanitizeDecimal } from '../../utils/numberInput';
import { getGradeTone } from '../../utils/gradeTone';
import {
  analyzeCourseTarget,
  HARD_FINAL_SCORE,
  isScoreInvalid,
  isWeightInvalid,
} from '../../utils/courseTarget';
import { useAnimatedNumber } from '../../hooks/useAnimatedNumber';
import { GpaReferenceModal } from '../GpaReferenceModal';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton } from '../tool/ToolSection';

interface CourseTargetPageProps {
  cohort: Cohort;
}

interface ScoreComponent {
  id: string;
  name: string;
  weight: string;
  score: string;
}

interface SyllabusPreset {
  label: string;
  components: Array<{ name: string; weight: string }>;
}

const SYLLABUS_PRESETS: SyllabusPreset[] = [
  { label: '20·20·60', components: [{ name: 'Quá trình', weight: '20' }, { name: 'Giữa kỳ', weight: '20' }] },
  { label: '30·70', components: [{ name: 'Quá trình', weight: '30' }] },
  { label: '10·30·60', components: [{ name: 'Chuyên cần', weight: '10' }, { name: 'Giữa kỳ', weight: '30' }] },
  { label: '10·40·50', components: [{ name: 'Chuyên cần', weight: '10' }, { name: 'Giữa kỳ', weight: '40' }] },
];

const COMPONENT_NAMES = ['Quá trình', 'Chuyên cần', 'Giữa kỳ', 'Thực hành', 'Bài tập', 'Tiểu luận', 'Thuyết trình', 'Khác'];

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

function signature(items: Array<{ name: string; weight: string }>) {
  return items.map((item) => `${item.name}:${item.weight}`).join('|');
}

const fmt = (value: number) => value.toFixed(2);

export function CourseTargetPage({ cohort }: CourseTargetPageProps) {
  const [courseGroup, setCourseGroup] = useState<CourseGroup>(getDefaultCourseGroup(cohort));
  const [components, setComponents] = useState<ScoreComponent[]>(defaultComponents);
  // null means "the pass grade" (the lowest passing row), which is also what reset restores.
  const [selectedLetter, setSelectedLetter] = useState<string | null>(null);
  const [referenceModalOpen, setReferenceModalOpen] = useState(false);

  const inputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const pendingFocus = useRef<string | null>(null);

  useEffect(() => {
    if (pendingFocus.current) {
      inputRefs.current[pendingFocus.current]?.focus();
      pendingFocus.current = null;
    }
  });

  const isSplit = isSplitGradeCohort(cohort);
  const activeGroup = isSplit ? courseGroup : getDefaultCourseGroup(cohort);
  const scale = getGradeScale(cohort, activeGroup);
  const passingRows = useMemo(() => scale.rows.filter((row) => row.status === 'Đạt'), [scale]);
  const passRow = passingRows.length > 0 ? passingRows[passingRows.length - 1] : null;
  const selectedRow = passingRows.find((row) => row.letter === selectedLetter) ?? passRow;

  const addComponent = () => {
    const id = createComponentId();
    pendingFocus.current = `w-${id}`;
    setComponents((current) => [...current, { id, name: 'Bài tập', weight: '', score: '' }]);
  };

  const removeComponent = (id: string) => {
    setComponents((current) => (current.length > 1 ? current.filter((component) => component.id !== id) : current));
  };

  const updateComponent = (id: string, field: keyof ScoreComponent, value: string) => {
    setComponents((current) => current.map((component) => (component.id === id ? { ...component, [field]: value } : component)));
  };

  const applyPreset = (preset: SyllabusPreset) => {
    const next = preset.components.map((component) => ({
      id: createComponentId(),
      name: component.name,
      weight: component.weight,
      score: components.find((existing) => existing.name === component.name)?.score ?? '',
    }));
    pendingFocus.current = `s-${next[0].id}`;
    setComponents(next);
  };

  const handleReset = () => {
    const hasData = components.some((c) => c.score !== '' || (c.weight !== '20' && c.weight !== ''));
    if (hasData && !window.confirm('Bạn có chắc chắn muốn khôi phục về bảng điểm mặc định không?')) {
      return;
    }
    setComponents(defaultComponents());
    setSelectedLetter(null);
  };

  const handleEnter = (event: KeyboardEvent<HTMLInputElement>, index: number, kind: 'w' | 's') => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const current = components[index];
    if (kind === 'w') {
      inputRefs.current[`s-${current.id}`]?.focus();
      return;
    }
    const next = components[index + 1];
    if (!next) {
      event.currentTarget.blur();
      return;
    }
    inputRefs.current[`${next.weight === '' ? 'w' : 's'}-${next.id}`]?.focus();
  };

  const result = useMemo(() => analyzeCourseTarget(components, passingRows), [components, passingRows]);
  const selectedTarget = selectedRow ? result.targets.find((t) => t.grade.letter === selectedRow.letter) ?? null : null;
  const target = result.isReady ? selectedTarget : null;

  const animatedRequired = useAnimatedNumber(
    target?.status === 'possible' && target.requiredScore != null ? target.requiredScore : 0,
    2,
  );

  const bestReachable = result.targets.find((t) => t.status !== 'impossible') ?? null;
  const isHard = target?.status === 'possible' && (target.requiredScore ?? 0) > HARD_FINAL_SCORE;
  const skin = !target
    ? ''
    : target.status === 'achieved'
    ? 'ct-s-ok'
    : target.status === 'impossible'
    ? 'ct-s-bad'
    : isHard
    ? 'ct-s-warn'
    : 'ct-s-ok';

  const groupLabel = getCourseGroupOptions(cohort).find((option) => option.id === activeGroup)?.shortLabel;
  const selectedTone = selectedRow ? `grade-tone-${getGradeTone(selectedRow)} ct-gn-${getGradeTone(selectedRow)}` : '';
  const labelLetter = selectedRow?.letter ?? '';
  const isPassSelected = selectedRow != null && selectedRow.letter === passRow?.letter;

  const base = (
    <>
      Đang có <b>{fmt(result.accumulatedScore)}</b> • Thi {result.remainingWeight}%
    </>
  );

  let bigNumber;
  let capsule;
  if (!target) {
    bigNumber = (
      <>
        <b>--</b>
        <span>/ 10</span>
      </>
    );
    capsule = (
      <span className="ct-cap empty">{result.errorMessage ? 'Sửa các cột đang báo lỗi' : 'Nhập điểm các cột đã có bên dưới'}</span>
    );
  } else if (target.status === 'achieved') {
    bigNumber = <b className="word">Đã đủ</b>;
    capsule = (
      <span className="ct-cap">
        <span className="ct-badge">Đã đạt</span>
        <span className="ct-sep">│</span>
        {base}
      </span>
    );
  } else if (target.status === 'impossible') {
    bigNumber = <b className="word">Không thể</b>;
    capsule = (
      <span className="ct-cap">
        <span className="ct-badge bad">Thi 10 vẫn chưa đủ</span>
        <span className="ct-sep">│</span>
        {bestReachable ? `Cao nhất ${bestReachable.grade.letter}` : 'Không qua được môn'}
      </span>
    );
  } else {
    bigNumber = (
      <>
        <b>{fmt(animatedRequired)}</b>
        <span>/ 10</span>
      </>
    );
    capsule = (
      <span className="ct-cap">
        <span className={`ct-badge${isHard ? ' warn' : ''}`}>{isHard ? 'Cần điểm cao' : 'Khả thi'}</span>
        <span className="ct-sep">│</span>
        {base}
      </span>
    );
  }

  let needChip;
  if (!target) {
    needChip = <span className="ct-need empty">—</span>;
  } else if (target.status === 'achieved') {
    needChip = <span className={`ct-need ${selectedTone}`}>Đã đủ</span>;
  } else if (target.status === 'impossible') {
    needChip = <span className={`ct-need ${selectedTone}`}>&gt; 10</span>;
  } else {
    needChip = (
      <span className={`ct-need ${selectedTone}`}>
        <small>cần</small>
        {fmt(target.requiredScore ?? 0)}
      </span>
    );
  }

  const presetSignature = signature(components);
  const ribbonSegments = components
    .map((component, index) => ({ index, weight: isWeightInvalid(component.weight) ? 0 : Number(component.weight) || 0 }))
    .filter((segment) => segment.weight > 0);

  return (
    <div className="page-container tool-page simplified ct-page">
      <ToolPageHeader
        icon={Target}
        title="Mục tiêu môn học"
        description={`Tính điểm thi cuối kỳ cần đạt từ các cột điểm đã có, theo thang điểm ${cohort}.`}
      />

      <div className="gpa-m-page-header ct-m-header">
        <div className="gpa-m-title-wrap">
          <Target size={18} aria-hidden="true" className="ct-m-title-icon" />
          <h1 className="gpa-m-page-title">Mục tiêu môn học</h1>
        </div>
      </div>

      <div className="ct-grid">
        <section className={`ct-result ${skin}`} aria-label="Kết quả">
          <div aria-live="polite">
            <div className="ct-label">
              Điểm thi cuối kỳ để đạt {labelLetter}
              {isPassSelected ? ' (qua môn)' : ''}
            </div>
            <div className="ct-num">{bigNumber}</div>
            <div className="ct-cap-wrap">{capsule}</div>
          </div>

          <div className="ct-strip" role="group" aria-label="Chọn mức điểm muốn đạt" style={{ '--ct-n': passingRows.length } as CSSProperties}>
            {result.targets.map((item) => {
              const tone = getGradeTone(item.grade);
              const state = !result.isReady ? '' : item.status === 'achieved' ? 'done' : item.status === 'impossible' ? 'no' : 'ok';
              return (
                <button
                  key={item.grade.letter}
                  type="button"
                  aria-pressed={item.grade.letter === selectedRow?.letter}
                  className={`${state} grade-tone-${tone} ct-gn-${tone}`}
                  onClick={() => setSelectedLetter(item.grade.letter)}
                >
                  <span className="l">{item.grade.letter}</span>
                  <span className="v">
                    {!result.isReady ? '·' : item.status === 'achieved' ? '✓' : item.status === 'impossible' ? '—' : fmt(item.requiredScore ?? 0)}
                  </span>
                </button>
              );
            })}
          </div>

          {result.errorMessage && (
            <p className="ct-err" role="alert">
              {result.errorMessage}
            </p>
          )}

          <div className="ct-foot">
            <span>
              Thang điểm {cohort}
              {isSplit && groupLabel ? `, nhóm ${groupLabel}` : ''}
            </span>
            <button type="button" className="ct-link" onClick={() => setReferenceModalOpen(true)}>
              Bảng quy đổi
              <ArrowUpRight size={13} aria-hidden="true" />
            </button>
          </div>
        </section>

        <section className="ct-sheet" aria-labelledby="ct-sheet-title">
          <div className="ct-sheet-head">
            <h2 id="ct-sheet-title">Đề cương điểm</h2>
            <ResetButton onClick={handleReset} />
          </div>

          {isSplit && (
            <div className="ct-group">
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
            </div>
          )}

          <div className="ct-ribbon" aria-hidden="true">
            {result.hasWeightOverflow ? (
              <div className="ct-rib over" style={{ flex: 1 }} />
            ) : (
              <>
                {ribbonSegments.map((segment) => (
                  <div key={segment.index} className={`ct-rib seg-${segment.index % 4}`} style={{ flex: `${segment.weight} 1 0` }} />
                ))}
                {result.remainingWeight > 0 && <div className="ct-rib final" style={{ flex: `${result.remainingWeight} 1 0` }} />}
              </>
            )}
          </div>
          {result.hasWeightOverflow && (
            <div className="ct-legend">
              <span>
                Tổng trọng số <b>{result.totalWeight}%</b>
              </span>
              <span>vượt 100%</span>
            </div>
          )}

          <div className="ct-presets" role="group" aria-label="Mẫu trọng số">
            <small>Mẫu:</small>
            {SYLLABUS_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                aria-pressed={signature(preset.components) === presetSignature}
                onClick={() => applyPreset(preset)}
              >
                {preset.label}
              </button>
            ))}
          </div>

          <div className="ct-tbl" role="table" aria-label="Các cột điểm">
            <div className="ct-tr ct-th" role="row">
              <span role="columnheader">Cột điểm</span>
              <span role="columnheader">Trọng số</span>
              <span role="columnheader">Điểm</span>
              <span />
            </div>
            <div role="rowgroup">
              {components.map((component, index) => (
                <div className="ct-tr" role="row" key={component.id}>
                  <span className="ct-namewrap" role="cell">
                    <span className={`ct-dot seg-${index % 4}`} />
                    <select
                      className="ct-name"
                      value={component.name}
                      onChange={(e) => updateComponent(component.id, 'name', e.target.value)}
                      aria-label={`Tên cột điểm ${index + 1}`}
                    >
                      {COMPONENT_NAMES.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                  </span>
                  <span role="cell">
                    <label className={`ct-box${isWeightInvalid(component.weight) ? ' bad' : ''}`}>
                      <input
                        ref={(el) => {
                          inputRefs.current[`w-${component.id}`] = el;
                        }}
                        type="text"
                        inputMode="decimal"
                        enterKeyHint="next"
                        placeholder="20"
                        value={component.weight}
                        onChange={(e) => updateComponent(component.id, 'weight', sanitizeDecimal(e.target.value))}
                        onKeyDown={(e) => handleEnter(e, index, 'w')}
                        aria-label={`Trọng số cột ${index + 1} (${component.name})`}
                        aria-invalid={isWeightInvalid(component.weight)}
                      />
                      <i>%</i>
                    </label>
                  </span>
                  <span role="cell">
                    <label className={`ct-box score${isScoreInvalid(component.score) ? ' bad' : ''}`}>
                      <input
                        ref={(el) => {
                          inputRefs.current[`s-${component.id}`] = el;
                        }}
                        type="text"
                        inputMode="decimal"
                        enterKeyHint="next"
                        placeholder="7.5"
                        value={component.score}
                        onChange={(e) => updateComponent(component.id, 'score', sanitizeDecimal(e.target.value))}
                        onKeyDown={(e) => handleEnter(e, index, 's')}
                        aria-label={`Điểm cột ${index + 1} (${component.name})`}
                        aria-invalid={isScoreInvalid(component.score)}
                      />
                      <i>/10</i>
                    </label>
                  </span>
                  <span role="cell">
                    {components.length > 1 && (
                      <button
                        type="button"
                        className="ct-del"
                        onClick={() => removeComponent(component.id)}
                        aria-label={`Xóa cột điểm ${index + 1}`}
                      >
                        <X size={16} aria-hidden="true" />
                      </button>
                    )}
                  </span>
                </div>
              ))}
            </div>

            <div className={`ct-tr final${result.hasWeightOverflow ? ' over' : ''}`} role="row">
              <span className="ct-namewrap" role="cell">
                <span className="ct-dot final" />
                Thi cuối kỳ
              </span>
              <span className="ct-lock" role="cell">
                {result.hasWeightOverflow ? (
                  <>
                    —<small>vượt 100%</small>
                  </>
                ) : (
                  <>
                    {result.remainingWeight}%<small>tự tính</small>
                  </>
                )}
              </span>
              <span role="cell">{needChip}</span>
              <span />
            </div>

            <button type="button" className="ct-add" onClick={addComponent} disabled={result.totalWeight >= 100}>
              <Plus size={16} aria-hidden="true" />
              Thêm cột điểm
            </button>
          </div>
        </section>
      </div>

      <GpaReferenceModal
        isOpen={referenceModalOpen}
        onClose={() => setReferenceModalOpen(false)}
        cohort={cohort}
        initialTab="scale"
      />
    </div>
  );
}
