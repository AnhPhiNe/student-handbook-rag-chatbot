import { useMemo, useState } from 'react';
import {
  Target,
  Plus,
  Trash2,
  RotateCcw,
  Sparkles,
  Info,
  GraduationCap,
} from 'lucide-react';
import {
  getCourseGroupOptions,
  getDefaultCourseGroup,
  getGradeScale,
  isSplitGradeCohort,
  type Cohort,
  type CourseGroup,
  type LetterGrade,
} from '../../utils/gradeScale';
import { PageContextBadges } from '../PageContextBadges';
import { GpaReferenceModal } from '../GpaReferenceModal';

interface CourseTargetPageProps {
  cohort: Cohort;
}

interface ScoreComponent {
  id: string;
  name: string;
  weight: string;
  score: string;
}

type TargetStatus = 'possible' | 'achieved' | 'impossible' | 'error' | 'fail';

interface SyllabusPreset {
  label: string;
  components: Array<{ name: string; weight: string }>;
}

const SYLLABUS_PRESETS: SyllabusPreset[] = [
  {
    label: '20% - 20% (Thi 60%)',
    components: [
      { name: 'Quá trình', weight: '20' },
      { name: 'Giữa kỳ', weight: '20' },
    ],
  },
  {
    label: '30% (Thi 70%)',
    components: [{ name: 'Quá trình', weight: '30' }],
  },
  {
    label: '10% - 30% (Thi 60%)',
    components: [
      { name: 'Chuyên cần', weight: '10' },
      { name: 'Giữa kỳ', weight: '30' },
    ],
  },
  {
    label: '10% - 40% (Thi 50%)',
    components: [
      { name: 'Chuyên cần', weight: '10' },
      { name: 'Giữa kỳ', weight: '40' },
    ],
  },
];

const GRADE_META: Record<
  LetterGrade,
  { name: string; color: string }
> = {
  A: { name: 'Xuất sắc', color: '#ec4899' },
  'B+': { name: 'Giỏi', color: '#8b5cf6' },
  B: { name: 'Khá', color: '#3b82f6' },
  'C+': { name: 'Trung bình Khá', color: '#10b981' },
  C: { name: 'Trung bình', color: '#f59e0b' },
  'D+': { name: 'Trung bình Yếu', color: '#f97316' },
  D: { name: 'Qua môn', color: '#ef4444' },
  'F+': { name: 'Không đạt', color: '#94a3b8' },
  F: { name: 'Không đạt', color: '#64748b' },
};

export function CourseTargetPage({ cohort }: CourseTargetPageProps) {
  const [courseGroup, setCourseGroup] = useState<CourseGroup>(getDefaultCourseGroup(cohort));
  const [components, setComponents] = useState<ScoreComponent[]>([
    { id: 'comp-1', name: 'Quá trình', weight: '20', score: '' },
    { id: 'comp-2', name: 'Giữa kỳ', weight: '20', score: '' },
  ]);
  const [referenceModalTab, setReferenceModalTab] = useState<'scale' | 'rules' | null>(null);

  const activeGroup = isSplitGradeCohort(cohort) ? courseGroup : getDefaultCourseGroup(cohort);
  const scale = getGradeScale(cohort, activeGroup);

  const addComponent = () => {
    setComponents((curr) => [
      ...curr,
      { id: `comp-${Date.now()}`, name: 'Quá trình', weight: '', score: '' },
    ]);
  };

  const removeComponent = (id: string) => {
    if (components.length <= 1) return;
    setComponents((curr) => curr.filter((c) => c.id !== id));
  };

  const updateComponent = (id: string, field: keyof ScoreComponent, value: string) => {
    setComponents((curr) =>
      curr.map((c) => (c.id === id ? { ...c, [field]: value } : c))
    );
  };

  const applyPreset = (preset: SyllabusPreset) => {
    setComponents(
      preset.components.map((c, idx) => ({
        id: `comp-preset-${idx}-${Date.now()}`,
        name: c.name,
        weight: c.weight,
        score: '',
      }))
    );
  };

  const handleReset = () => {
    const hasData = components.some((c) => c.score !== '' || (c.weight !== '20' && c.weight !== ''));
    if (hasData) {
      if (!window.confirm('Bạn có chắc chắn muốn khôi phục về bảng điểm mặc định không?')) {
        return;
      }
    }
    setComponents([
      { id: 'comp-1', name: 'Quá trình', weight: '20', score: '' },
      { id: 'comp-2', name: 'Giữa kỳ', weight: '20', score: '' },
    ]);
  };

  const result = useMemo(() => {
    let totalWeight = 0;
    let accumulatedScore = 0;
    let hasInvalidWeight = false;
    let hasInvalidScore = false;

    for (const comp of components) {
      const w = Number(comp.weight);
      const s = Number(comp.score);

      if (comp.weight !== '') {
        if (!Number.isFinite(w) || w < 0 || w > 100) hasInvalidWeight = true;
        totalWeight += w;
      }

      if (comp.score !== '') {
        if (!Number.isFinite(s) || s < 0 || s > 10) {
          hasInvalidScore = true;
        } else if (comp.weight !== '' && Number.isFinite(w) && w >= 0) {
          accumulatedScore += (s * w) / 100;
        }
      }
    }

    const remainingWeight = Math.max(0, 100 - totalWeight);
    const isError = totalWeight > 100 || hasInvalidWeight || hasInvalidScore;

    const targets = scale.rows
      .filter((row) => row.letter !== 'F' && row.letter !== 'F+')
      .map((grade) => {
        const meta = GRADE_META[grade.letter];
        const isFailingByRule = grade.status === 'Không đạt';

        if (isFailingByRule) {
          return {
            ...grade,
            ...meta,
            requiredScore: null,
            status: 'fail' as TargetStatus,
          };
        }

        if (isError) {
          return { ...grade, ...meta, requiredScore: null, status: 'error' as TargetStatus };
        }

        const missingScore = grade.min10 - accumulatedScore;

        if (remainingWeight === 0) {
          return {
            ...grade,
            ...meta,
            requiredScore: null,
            status: (missingScore <= 0 ? 'achieved' : 'impossible') as TargetStatus,
          };
        }

        const requiredScoreOnFinal = (missingScore * 100) / remainingWeight;

        let status: TargetStatus = 'possible';
        if (requiredScoreOnFinal > 10.0) status = 'impossible';
        else if (requiredScoreOnFinal <= 0) status = 'achieved';

        return {
          ...grade,
          ...meta,
          requiredScore: requiredScoreOnFinal,
          status,
        };
      });

    const passingRows = scale.rows.filter((r) => r.status === 'Đạt');
    const lowestPassingRow = passingRows[passingRows.length - 1];
    const passTarget = lowestPassingRow ? targets.find((t) => t.letter === lowestPassingRow.letter) : null;

    return {
      totalWeight,
      remainingWeight,
      accumulatedScore,
      isError,
      targets,
      passTarget,
      lowestPassingLetter: lowestPassingRow?.letter ?? 'D',
    };
  }, [components, scale]);

  return (
    <div className="page-container tool-page">
      {/* Header with Title & Badges */}
      <div className="page-header">
        <h1 className="page-title-with-icon">
          <Target aria-hidden="true" />
          <span>Mục tiêu môn học</span>
        </h1>
        <p>Tính điểm thi cuối kỳ cần đạt dựa trên các cột điểm thành phần và bảng quy đổi của {cohort}.</p>
        <PageContextBadges cohort={cohort} source="Thang điểm áp dụng theo khóa" advisory />
      </div>

      {/* Main 2-Column Split Layout */}
      <div className="course-target-split-layout">
        {/* Left Column: Input Form */}
        <section className="gpa-main-column">
          {/* Toolbar: Group Selector & Action Buttons */}
          <div className="gpa-toolbar">
            {isSplitGradeCohort(cohort) ? (
              <div className="gpa-mode-control">
                <span className="gpa-mode-label">Nhóm môn:</span>
                <div className="gpa-mode-pills" role="radiogroup" aria-label="Nhóm môn học">
                  {getCourseGroupOptions(cohort).map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      className={`gpa-mode-btn ${courseGroup === option.id ? 'active' : ''}`}
                      onClick={() => setCourseGroup(option.id as CourseGroup)}
                      title={option.label}
                    >
                      {option.shortLabel}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="gpa-mode-control">
                <span className="gpa-mode-label">Điểm thành phần đã có:</span>
              </div>
            )}

            <div className="gpa-action-buttons">
              <button
                type="button"
                className="tool-btn gpa-reset-btn gpa-btn-sm"
                onClick={handleReset}
                title="Khôi phục các cột điểm mặc định"
              >
                <RotateCcw size={14} />
                <span>Làm mới</span>
              </button>
              <button
                type="button"
                className="tool-btn primary gpa-btn-sm gpa-add-top-btn"
                onClick={addComponent}
                title="Thêm một cột điểm thành phần mới"
                disabled={result.totalWeight >= 100}
              >
                <Plus size={15} />
                <span>Thêm cột</span>
              </button>
            </div>
          </div>

          {/* Form Card */}
          <div className="course-target-form-card">
            {/* Quick Presets Bar (Single line, horizontal scroll) */}
            <div className="course-target-presets-bar">
              <span className="course-target-presets-label">
                <Sparkles size={13} /> Mẫu:
              </span>
              {SYLLABUS_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className="course-target-preset-chip"
                  onClick={() => applyPreset(preset)}
                  title={`Áp dụng phân bổ: ${preset.label}`}
                >
                  {preset.label}
                </button>
              ))}
            </div>

            {/* Components Table */}
            <div className="course-target-table-wrap">
              <table className="course-target-table">
                <thead>
                  <tr>
                    <th style={{ width: '35%' }}>THÀNH PHẦN</th>
                    <th style={{ width: '28%' }}>TRỌNG SỐ (%)</th>
                    <th style={{ width: '28%' }}>ĐIỂM (10)</th>
                    <th style={{ width: '9%', textAlign: 'center' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {components.map((comp) => {
                    const isWeightInvalid =
                      comp.weight !== '' &&
                      (Number(comp.weight) < 0 || Number(comp.weight) > 100 || isNaN(Number(comp.weight)));
                    const isScoreInvalid =
                      comp.score !== '' &&
                      (Number(comp.score) < 0 || Number(comp.score) > 10 || isNaN(Number(comp.score)));
                    return (
                      <tr key={comp.id}>
                        <td>
                          <select
                            value={comp.name}
                            onChange={(e) => updateComponent(comp.id, 'name', e.target.value)}
                            className="course-target-select"
                          >
                            <option value="Quá trình">Quá trình</option>
                            <option value="Chuyên cần">Chuyên cần</option>
                            <option value="Giữa kỳ">Giữa kỳ</option>
                            <option value="Thực hành">Thực hành</option>
                            <option value="Bài tập">Bài tập</option>
                            <option value="Tiểu luận">Tiểu luận</option>
                            <option value="Thuyết trình">Thuyết trình</option>
                            <option value="Khác">Khác...</option>
                          </select>
                        </td>
                        <td>
                          <div className="course-target-input-wrap">
                            <input
                              type="text"
                              inputMode="decimal"
                              value={comp.weight}
                              onChange={(e) => {
                                const val = e.target.value.replace(',', '.');
                                if (val === '' || /^[0-9.]*$/.test(val)) updateComponent(comp.id, 'weight', val);
                              }}
                              className={`course-target-input ${isWeightInvalid ? 'input-error' : ''}`}
                              placeholder="VD: 20"
                            />
                            <span className="course-target-affix">%</span>
                          </div>
                        </td>
                        <td>
                          <div className="course-target-input-wrap">
                            <input
                              type="text"
                              inputMode="decimal"
                              value={comp.score}
                              onChange={(e) => {
                                const val = e.target.value.replace(',', '.');
                                if (val === '' || /^[0-9.]*$/.test(val)) updateComponent(comp.id, 'score', val);
                              }}
                              className={`course-target-input ${isScoreInvalid ? 'input-error' : ''}`}
                              placeholder="VD: 7.5"
                            />
                            <span className="course-target-affix">/ 10</span>
                          </div>
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          {components.length > 1 && (
                            <button
                              type="button"
                              className="course-target-del-btn"
                              onClick={() => removeComponent(comp.id)}
                              title="Xóa cột điểm này"
                            >
                              <Trash2 size={15} />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Visual Weight Balance Bar */}
            <div className="course-target-weight-bar-card">
              <div className="course-target-weight-header">
                <div className="course-target-weight-stat">
                  <span className="course-target-dot entered" />
                  <span>
                    Đã có: <strong>{result.totalWeight}%</strong>
                  </span>
                  {result.accumulatedScore > 0 && (
                    <span className="course-target-subscore">
                      (tích lũy: <strong>{result.accumulatedScore.toFixed(2)}</strong> đ)
                    </span>
                  )}
                </div>
                <div className="course-target-weight-stat">
                  <span className="course-target-dot final" />
                  <span>
                    Trọng số thi cuối kỳ:{' '}
                    <strong>
                      {result.totalWeight > 100 ? '0%' : `${result.remainingWeight}%`}
                    </strong>
                  </span>
                </div>
              </div>

              <div className="course-target-progress-track">
                <div
                  className={`course-target-progress-fill entered ${result.totalWeight > 100 ? 'error' : ''}`}
                  style={{ width: `${Math.min(100, Math.max(0, result.totalWeight))}%` }}
                />
                {result.totalWeight < 100 && (
                  <div
                    className="course-target-progress-fill final"
                    style={{ width: `${Math.max(0, result.remainingWeight)}%` }}
                  />
                )}
              </div>

              {result.totalWeight > 100 && (
                <div className="course-target-weight-warning">
                  ⚠️ Tổng trọng số các cột điểm đang là <strong>{result.totalWeight}%</strong> (vượt quá 100%). Vui lòng điều chỉnh lại!
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Right Column: Sticky Summary & Target Result Card */}
        <aside className="gpa-summary-card sticky-card">
          <div className="gpa-card-inner">
            {/* Header: Title & Remaining Weight Pill */}
            <div className="gpa-result-top">
              <div className="gpa-result-tag-wrap">
                <span className="gpa-live-dot" />
                <span className="gpa-result-tag">MỤC TIÊU CUỐI KỲ</span>
              </div>
              <span className="gpa-cohort-pill">
                {result.isError && result.totalWeight > 100 ? 'Lỗi trọng số' : `Thi: ${result.remainingWeight}%`}
              </span>
            </div>

            {/* Summary Stats Grid (2 Equal Symmetrical Cards) */}
            <div className="course-target-stats-grid">
              <div className="gpa-stat-box">
                <span className="gpa-stat-label">Điểm tích lũy</span>
                <strong className="gpa-stat-val">
                  {result.accumulatedScore > 0 ? result.accumulatedScore.toFixed(2) : '--'}
                </strong>
              </div>
              <div className="gpa-stat-box">
                <span className="gpa-stat-label">Qua môn ({result.lowestPassingLetter})</span>
                <strong
                  className="gpa-stat-val"
                  style={{
                    color:
                      result.passTarget?.status === 'achieved'
                        ? '#10b981'
                        : result.passTarget?.status === 'impossible'
                        ? '#ef4444'
                        : undefined,
                  }}
                >
                  {result.isError
                    ? '--'
                    : result.passTarget
                    ? result.passTarget.status === 'achieved'
                      ? 'Đã đạt'
                      : result.passTarget.status === 'impossible'
                      ? '> 10'
                      : result.passTarget.requiredScore !== null
                      ? result.passTarget.requiredScore.toFixed(2)
                      : '--'
                    : '--'}
                </strong>
              </div>
            </div>

            {/* Compact Target Matrix Table */}
            <div className="course-target-compact-table">
              <div className="course-target-table-header-row">
                <span>MỨC ĐIỂM</span>
                <span>ĐIỂM THI CẦN ĐẠT</span>
              </div>
              {result.targets.map((target) => (
                <div key={target.letter} className="course-target-compact-row">
                  <div className="course-target-row-left">
                    <span
                      className="course-target-row-badge"
                      style={{ backgroundColor: target.color }}
                    >
                      {target.letter}
                    </span>
                    <span className="course-target-row-label">
                      {target.name} <span className="course-target-min10">(≥ {target.min10.toFixed(1)})</span>
                    </span>
                  </div>

                  <div className="course-target-row-right">
                    {target.status === 'fail' ? (
                      <span className="course-target-row-score fail">Không đạt (rớt)</span>
                    ) : target.status === 'impossible' ? (
                      <span className="course-target-row-score impossible">Bất khả thi</span>
                    ) : target.status === 'achieved' ? (
                      <span className="course-target-row-score achieved">Đã đạt 🎉</span>
                    ) : target.requiredScore !== null ? (
                      <span className="course-target-row-score score-val">
                        {target.requiredScore.toFixed(2)}
                      </span>
                    ) : (
                      <span className="course-target-row-score">--</span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Quick Actionable Tip Box */}
            <div className="course-target-tip-box">
              <span className="course-target-tip-icon">💡</span>
              <span className="course-target-tip-text">
                {result.passTarget?.status === 'achieved'
                  ? 'Bạn đã tích lũy đủ điểm để qua môn học phần này!'
                  : result.passTarget?.requiredScore !== null && result.passTarget?.status === 'possible'
                  ? `Cần thi đạt tối thiểu ${result.passTarget.requiredScore.toFixed(2)} điểm để qua môn (${result.lowestPassingLetter}).`
                  : 'Nhập điểm quá trình để tính toán điểm thi cần đạt.'}
              </span>
            </div>

            {/* Footer Reference Modal Buttons */}
            <div className="gpa-card-footer">
              <div className="gpa-action-pills-row">
                <button
                  type="button"
                  className="gpa-footer-pill-btn"
                  onClick={() => setReferenceModalTab('rules')}
                  title="Xem quy chế tính điểm học phần"
                >
                  <Info size={14} />
                  <span>Quy chế điểm</span>
                </button>
                <button
                  type="button"
                  className="gpa-footer-pill-btn"
                  onClick={() => setReferenceModalTab('scale')}
                  title={`Tra cứu bảng quy đổi điểm (${cohort})`}
                >
                  <GraduationCap size={15} />
                  <span>Bảng quy đổi điểm</span>
                </button>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* Reference Modal */}
      <GpaReferenceModal
        isOpen={referenceModalTab !== null}
        onClose={() => setReferenceModalTab(null)}
        cohort={cohort}
        initialTab={referenceModalTab ?? 'scale'}
      />
    </div>
  );
}
