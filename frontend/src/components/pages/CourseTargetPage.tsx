import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { ArrowUpRight, BookOpen, Plus, RotateCcw, Target, Trash2 } from 'lucide-react';
import {
  getCourseGroupOptions,
  getDefaultCourseGroup,
  getGradeScale,
  isSplitGradeCohort,
  type Cohort,
  type CourseGroup,
} from '../../utils/gradeScale';
import { sanitizeDecimal } from '../../utils/numberInput';
import {
  analyzeCourseTarget,
  HARD_FINAL_SCORE,
  isScoreInvalid,
  isWeightInvalid,
} from '../../utils/courseTarget';
import { useAnimatedNumber } from '../../hooks/useAnimatedNumber';
import { GpaReferenceModal } from '../GpaReferenceModal';
import { ShareResultButton } from '../tool/ShareResultButton';
import { courseTargetShareText } from '../../utils/shareText';
import { ToolPageHeader } from '../tool/ToolPageHeader';

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
  { label: '30 - 70', components: [{ name: 'Quá trình', weight: '30' }] },
  { label: '10 - 30 - 60', components: [{ name: 'Chuyên cần', weight: '10' }, { name: 'Giữa kỳ', weight: '30' }] },
];

const COMPONENT_NAMES = ['Quá trình', 'Chuyên cần', 'Giữa kỳ', 'Thực hành', 'Bài tập', 'Tiểu luận', 'Thuyết trình', 'Khác'];

let addedComponentCount = 0;
function createComponentId() {
  addedComponentCount += 1;
  return `comp-added-${addedComponentCount}`;
}

function defaultComponents(): ScoreComponent[] {
  return [
    { id: 'comp-1', name: 'Chuyên cần', weight: '10', score: '' },
    { id: 'comp-2', name: 'Giữa kỳ', weight: '30', score: '' },
  ];
}

function signature(items: Array<{ name: string; weight: string }>) {
  return items.map((item) => `${item.name}:${item.weight}`).join('|');
}

const fmt = (value: number) => value.toFixed(2);

export function CourseTargetPage({ cohort }: CourseTargetPageProps) {
  const [courseGroup, setCourseGroup] = useState<CourseGroup>(getDefaultCourseGroup(cohort));
  const [components, setComponents] = useState<ScoreComponent[]>(defaultComponents);
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

  const bestReachable = result.isReady
    ? result.targets.find((t) => t.status !== 'impossible') ?? null
    : null;
  const isHard = target?.status === 'possible' && (target.requiredScore ?? 0) > HARD_FINAL_SCORE;
  const labelLetter = selectedRow?.letter ?? '';
  const isPassSelected = selectedRow != null && selectedRow.letter === passRow?.letter;

  const passTarget = passRow ? result.targets.find((t) => t.grade.letter === passRow.letter) ?? null : null;

  const shareText =
    target && selectedRow
      ? courseTargetShareText({
          status: target.status,
          letter: selectedRow.letter,
          isPassGrade: isPassSelected,
          requiredScore: target.requiredScore,
          coveredPercent: 100 - result.remainingWeight,
          bestLetter: bestReachable?.grade.letter ?? null,
          cohort,
        })
      : null;

  const presetSignature = signature(components);
  const ribbonSegments = components
    .map((component, index) => ({ index, weight: isWeightInvalid(component.weight) ? 0 : Number(component.weight) || 0 }))
    .filter((segment) => segment.weight > 0);

  // Status Badge for Right Card Header
  const statusBadge = useMemo(() => {
    if (!result.isReady) {
      return <span className="gpa-d-result-badge unranked">• Chờ nhập liệu</span>;
    }
    if (result.hasWeightOverflow) {
      return <span className="gpa-d-result-badge tier-danger">⚠️ Lỗi trọng số</span>;
    }
    if (target?.status === 'achieved') {
      return <span className="gpa-d-result-badge tier-success">✓ Đã đủ điểm</span>;
    }
    if (target?.status === 'impossible') {
      return <span className="gpa-d-result-badge tier-danger">⚠️ Không thể đạt</span>;
    }
    if (isHard) {
      return <span className="gpa-d-result-badge tier-warning">⚡ Cần cố gắng</span>;
    }
    return <span className="gpa-d-result-badge tier-success">★ Khả thi</span>;
  }, [result.isReady, result.hasWeightOverflow, target, isHard]);

  // Milestone Prompt for Bottom of Right Card Milestone Box
  const milestonePrompt = useMemo(() => {
    if (!result.isReady) {
      return (
        <span className="gpa-d-motivation-text">
          💡 Nhập điểm các cột thành phần để xem điểm thi cần đạt
        </span>
      );
    }
    if (result.hasWeightOverflow) {
      return (
        <span className="gpa-d-motivation-text" style={{ color: '#ef4444' }}>
          ⚠️ Tổng trọng số vượt quá 100%, vui lòng kiểm tra lại
        </span>
      );
    }
    if (passTarget?.status === 'achieved') {
      return (
        <span className="gpa-d-motivation-text">
          🎉 Bạn đã tích lũy đủ điểm qua môn ngay cả khi thi 0 điểm
        </span>
      );
    }
    if (passTarget?.status === 'possible') {
      return (
        <span className="gpa-d-motivation-text">
          💡 Thi cuối kỳ từ <strong className="gpa-motivate-highlight">{fmt(passTarget.requiredScore ?? 0)} điểm</strong> là đủ qua môn (tổng kết điểm {passRow?.letter} ≥ {passRow?.min10.toFixed(1)})
        </span>
      );
    }
    if (passTarget?.status === 'impossible') {
      return (
        <span className="gpa-d-motivation-text" style={{ color: '#ef4444' }}>
          ⚠️ Điểm tích lũy chưa đủ qua môn kể cả khi thi 10 điểm
        </span>
      );
    }
    return null;
  }, [result.isReady, result.hasWeightOverflow, passTarget, passRow]);

  // Mobile Capsule Status Badge
  const mobileCapsuleBadge = useMemo(() => {
    if (target?.status === 'achieved') {
      return <span className="font-extrabold tracking-wide" style={{ color: '#34d399' }}>ĐÃ ĐỦ ĐIỂM</span>;
    }
    if (target?.status === 'impossible') {
      return <span className="font-extrabold tracking-wide" style={{ color: '#f87171' }}>KHÔNG THỂ</span>;
    }
    if (isHard) {
      return <span className="font-extrabold tracking-wide" style={{ color: '#FBBF24' }}>CẦN CỐ GẮNG</span>;
    }
    return <span className="font-extrabold tracking-wide" style={{ color: '#34d399' }}>KHẢ THI</span>;
  }, [target, isHard]);

  return (
    <div className="page-container tool-page simplified gpa-page-wrapper">
      {/* Desktop Header */}
      <ToolPageHeader
        icon={Target}
        title="Mục tiêu môn học"
        description={
          <>
            Tính điểm thi cuối kỳ cần đạt từ các cột điểm đã có, theo thang điểm <strong>{cohort}</strong>.
          </>
        }
      />

      {/* ============================================================== */}
      {/* 1. BẢN DESKTOP 2 CỘT CÂN ĐỐI (ĐỒNG BỘ 100% GPAPAGE & TARGETGPA)  */}
      {/* ============================================================== */}
      <div className="gpa-desktop-layout">
        {/* CỘT TRÁI (7 Cols): CƠ CẤU ĐIỂM */}
        <div className="gpa-d-table-card">
          {/* Toolbar */}
          <div className="gpa-d-toolbar">
            <div className="gpa-d-toolbar-title">
              <span className="tool-step-badge">1</span>
              <span className="gpa-d-table-heading">CƠ CẤU ĐIỂM</span>
              <span
                className="gpa-d-table-badge"
                style={result.hasWeightOverflow ? { background: '#fef2f2', color: '#b91c1c', borderColor: '#fecaca' } : undefined}
              >
                {result.hasWeightOverflow ? `Tổng: ${result.totalWeight}% (Vượt 100%)` : `Thi cuối kỳ: ${result.remainingWeight}%`}
              </span>
            </div>

            <button
              type="button"
              className="gpa-d-reset-btn"
              onClick={handleReset}
              title="Đặt lại bảng điểm"
              aria-label="Đặt lại bảng điểm"
            >
              <RotateCcw size={14} />
              <span>Đặt lại</span>
            </button>
          </div>

          {/* Thanh Chọn Tỷ Lệ Phổ Biến & Phân Bổ Trọng Số */}
          <div className="ct-v2-preset-bar">
            {isSplit && (
              <div className="ct-v2-group-row">
                <span className="ct-v2-preset-label">Nhóm môn học:</span>
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

            <div className="ct-v2-preset-row">
              <span className="ct-v2-preset-label">Tỷ lệ mẫu:</span>
              <div className="ct-v2-preset-chips" role="group" aria-label="Mẫu tỷ lệ phổ biến">
                {SYLLABUS_PRESETS.map((preset) => {
                  const isActive = signature(preset.components) === presetSignature;
                  return (
                    <button
                      key={preset.label}
                      type="button"
                      className={`ct-v2-preset-btn ${isActive ? 'active' : ''}`}
                      aria-pressed={isActive}
                      onClick={() => applyPreset(preset)}
                    >
                      {preset.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Thanh Phân Bổ Trọng Số Trực Quan 100% */}
            <div className="ct-v2-ribbon-bar" aria-hidden="true">
              {result.hasWeightOverflow ? (
                <div className="ct-v2-ribbon-seg overflow" style={{ width: '100%' }} />
              ) : (
                <>
                  {ribbonSegments.map((segment) => (
                    <div
                      key={segment.index}
                      className={`ct-v2-ribbon-seg seg-${segment.index % 4}`}
                      style={{ width: `${segment.weight}%` }}
                      title={`Cột ${segment.index + 1}: ${segment.weight}%`}
                    />
                  ))}
                  {result.remainingWeight > 0 && (
                    <div
                      className="ct-v2-ribbon-seg final"
                      style={{ width: `${result.remainingWeight}%` }}
                      title={`Thi cuối kỳ: ${result.remainingWeight}%`}
                    />
                  )}
                </>
              )}
            </div>
          </div>

          {/* Bảng Các Cột Điểm: 4 Cột Cân Đối (36% | 26% | 28% | 10%) */}
          <table className="gpa-d-table">
            <thead className="gpa-d-thead">
              <tr>
                <th style={{ width: '36%', textAlign: 'left' }}>Cột điểm</th>
                <th style={{ width: '26%', textAlign: 'center' }}>Trọng số (%)</th>
                <th style={{ width: '28%', textAlign: 'center' }}>Điểm hệ 10</th>
                <th style={{ width: '10%', textAlign: 'right' }}></th>
              </tr>
            </thead>
            <tbody className="gpa-d-tbody">
              {components.map((component, index) => {
                const weightErr = isWeightInvalid(component.weight);
                const scoreErr = isScoreInvalid(component.score);

                return (
                  <tr key={component.id}>
                    {/* Cột 1: Tên cột điểm */}
                    <td>
                      <div className="ct-v2-name-cell">
                        <span className={`ct-v2-dot seg-${index % 4}`} aria-hidden="true" />
                        <select
                          className="ct-v2-select"
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
                      </div>
                    </td>

                    {/* Cột 2: Trọng số */}
                    <td style={{ textAlign: 'center' }}>
                      <div className="gpa-d-input-wrap">
                        <div className="ct-v2-weight-box">
                          <input
                            ref={(el) => {
                              inputRefs.current[`w-${component.id}`] = el;
                            }}
                            type="text"
                            inputMode="decimal"
                            enterKeyHint="next"
                            placeholder="VD: 30"
                            value={component.weight}
                            className={`ct-v2-weight-input ${weightErr ? 'input-error' : component.weight ? 'has-val' : ''}`}
                            onChange={(e) => updateComponent(component.id, 'weight', sanitizeDecimal(e.target.value))}
                            onKeyDown={(e) => handleEnter(e, index, 'w')}
                            aria-label={`Trọng số cột ${index + 1} (${component.name})`}
                            aria-invalid={weightErr}
                          />
                          <span className="ct-v2-weight-unit">%</span>
                        </div>
                        {weightErr && <span className="gpa-d-error-tag">1-100%</span>}
                      </div>
                    </td>

                    {/* Cột 3: Điểm hệ 10 */}
                    <td style={{ textAlign: 'center' }}>
                      <div className="gpa-d-input-wrap">
                        <input
                          ref={(el) => {
                            inputRefs.current[`s-${component.id}`] = el;
                          }}
                          type="text"
                          inputMode="decimal"
                          enterKeyHint="next"
                          placeholder="VD: 8.5"
                          value={component.score}
                          className={`ct-v2-score-input ${scoreErr ? 'input-error' : component.score ? 'has-val' : ''}`}
                          onChange={(e) => updateComponent(component.id, 'score', sanitizeDecimal(e.target.value))}
                          onKeyDown={(e) => handleEnter(e, index, 's')}
                          aria-label={`Điểm cột ${index + 1} (${component.name})`}
                          aria-invalid={scoreErr}
                        />
                        {scoreErr && <span className="gpa-d-error-tag">0 - 10</span>}
                      </div>
                    </td>

                    {/* Cột 4: Nút xóa */}
                    <td style={{ textAlign: 'right' }}>
                      {components.length > 1 && (
                        <button
                          type="button"
                          className="gpa-d-del-btn"
                          onClick={() => removeComponent(component.id)}
                          aria-label={`Xóa cột điểm ${index + 1}`}
                          title="Xóa cột điểm này"
                        >
                          <Trash2 size={15} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}

              {/* Dòng Tổng Kết: THI CUỐI KỲ */}
              <tr className="ct-v2-final-row">
                <td>
                  <div className="ct-v2-name-cell">
                    <span className="ct-v2-dot final" aria-hidden="true" />
                    <span className="ct-v2-final-label">THI CUỐI KỲ</span>
                  </div>
                </td>
                <td style={{ textAlign: 'center' }}>
                  <div className="ct-v2-final-weight-badge">
                    {result.hasWeightOverflow ? '—' : `${result.remainingWeight}%`}
                  </div>
                </td>
                <td style={{ textAlign: 'center' }}>
                  {(() => {
                    if (!result.isReady || result.hasWeightOverflow) {
                      return <span className="ct-v2-final-score-badge status-empty">—</span>;
                    }
                    if (target?.status === 'achieved') {
                      return <span className="ct-v2-final-score-badge status-achieved">✓ Đã đủ</span>;
                    }
                    if (target?.status === 'impossible') {
                      return <span className="ct-v2-final-score-badge status-impossible">&gt; 10</span>;
                    }
                    return (
                      <span className="ct-v2-final-score-badge status-possible">
                        Cần ≥ {fmt(target?.requiredScore ?? 0)}
                      </span>
                    );
                  })()}
                </td>
                <td></td>
              </tr>
            </tbody>
          </table>

          {/* Nút Thêm Cột Điểm Nét Đứt */}
          <div className="gpa-d-add-row">
            <button
              type="button"
              className="gpa-d-add-dashed-btn"
              onClick={addComponent}
              disabled={result.totalWeight >= 100}
              title={result.totalWeight >= 100 ? 'Đã đạt 100% trọng số' : 'Thêm cột điểm thành phần'}
            >
              <Plus size={15} />
              <span>Thêm cột điểm thành phần</span>
            </button>
          </div>
        </div>

        {/* CỘT PHẢI (5 Cols): KẾT QUẢ MÔN HỌC (STICKY) */}
        <div className="gpa-d-sticky-col">
          <div className="gpa-d-result-card">
            {/* Header Thẻ Kết Quả */}
            <div className="gpa-d-result-header">
              <span className="gpa-d-result-title">KẾT QUẢ MÔN HỌC</span>
              {statusBadge}
            </div>

            {/* Điểm Thi Cần Đạt Trung Tâm */}
            <div className="gpa-d-hero-score-box">
              <div className="gpa-d-hero-sub">
                ĐIỂM THI CUỐI KỲ CẦN ĐẠT (MỨC {labelLetter})
              </div>
              <div className="gpa-d-hero-score-row">
                {!result.isReady || !target ? (
                  <>
                    <span className="gpa-d-hero-score">--</span>
                    <span className="gpa-d-hero-max">/ 10</span>
                  </>
                ) : target.status === 'achieved' ? (
                  <span className="gpa-d-hero-score" style={{ fontSize: '2.4rem', color: '#047857' }}>
                    Đã đủ
                  </span>
                ) : target.status === 'impossible' ? (
                  <span className="gpa-d-hero-score" style={{ fontSize: '2.4rem', color: '#dc2626' }}>
                    Không thể
                  </span>
                ) : (
                  <>
                    <span className="gpa-d-hero-score">{fmt(animatedRequired)}</span>
                    <span className="gpa-d-hero-max">/ 10</span>
                  </>
                )}
              </div>

              <div className="gpa-d-gpa10-pill">
                <span className="gpa-d-gpa10-label">Mục tiêu tổng kết:</span>
                <strong className="gpa-d-gpa10-val" style={{ color: '#059669' }}>
                  Điểm {selectedRow?.letter} (≥ {selectedRow?.min10.toFixed(1)} hệ 10)
                </strong>
              </div>
            </div>

            {/* Khung Chọn Mức Điểm Chữ 7 Mức & Tóm Tắt */}
            <div className="gpa-d-milestone-box">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.72rem', fontWeight: 700 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><span className="tool-step-badge">2</span><span style={{ color: 'var(--text-muted, #64748B)' }}>CHỌN MỨC ĐIỂM MUỐN ĐẠT:</span></div>
                <span style={{ color: result.isReady ? '#059669' : 'var(--text-muted, #64748B)', fontWeight: 800 }}>
                  Khả thi tối đa: {result.isReady && bestReachable ? `Mức ${bestReachable.grade.letter}` : '—'}
                </span>
              </div>

              <div className="ct-v2-target-grid" role="group" aria-label="Chọn mức điểm muốn đạt">
                {result.targets.map((item) => {
                  const isSelected = item.grade.letter === selectedRow?.letter;
                  const valText = !result.isReady
                    ? '—'
                    : item.status === 'achieved'
                    ? '✓'
                    : item.status === 'impossible'
                    ? '—'
                    : fmt(item.requiredScore ?? 0);

                  return (
                    <button
                      key={item.grade.letter}
                      type="button"
                      aria-pressed={isSelected}
                      className={`ct-v2-target-btn ${isSelected ? 'active' : ''}`}
                      onClick={() => setSelectedLetter(item.grade.letter)}
                      title={`Mục tiêu điểm ${item.grade.letter} (≥ ${item.grade.min10.toFixed(1)} hệ 10)`}
                    >
                      <span className="ct-v2-target-letter">{item.grade.letter}</span>
                      <span className="ct-v2-target-val">{valText}</span>
                    </button>
                  );
                })}
              </div>

              <div className="gpa-d-milestone-prompt">
                {milestonePrompt}
              </div>
            </div>

            {/* 3 Ô Thống Kê Gọn Gàng */}
            <div className="gpa-d-stats-grid">
              <div className="gpa-d-stat-box">
                <span className="gpa-d-stat-label">Điểm quá trình</span>
                <span className="gpa-d-stat-val">
                  {result.isReady ? `${fmt(result.accumulatedScore)} đ` : '—'}
                </span>
              </div>
              <div className="gpa-d-stat-box passed">
                <span className="gpa-d-stat-label">Tỷ lệ thi CK</span>
                <span className="gpa-d-stat-val" style={{ color: result.hasWeightOverflow ? '#ef4444' : '#059669' }}>
                  {result.hasWeightOverflow ? '—' : `${result.remainingWeight}%`}
                </span>
              </div>
              <div className="gpa-d-stat-box">
                <span className="gpa-d-stat-label">Đạt tối đa</span>
                <span className="gpa-d-stat-val">
                  {result.isReady ? (bestReachable ? `Mức ${bestReachable.grade.letter}` : 'Rớt môn') : '—'}
                </span>
              </div>
            </div>

            {/* Footer */}
            <div className="gpa-d-result-footer">
              <button
                type="button"
                className="gpa-d-footer-link"
                onClick={() => setReferenceModalOpen(true)}
              >
                <BookOpen size={14} aria-hidden="true" />
                <span>Bảng quy đổi {cohort}</span>
                <ArrowUpRight size={14} aria-hidden="true" />
              </button>
              {shareText ? (
                <ShareResultButton text={shareText} className="gpa-d-footer-link" />
              ) : (
                <span className="gpa-d-footer-watermark">ĐHSP TP.HCM</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ============================================================== */}
      {/* 2. BẢN MOBILE NATIVE TINH GỌN (HERO NAVY + 2 THẺ TRẮNG THOÁNG)  */}
      {/* ============================================================== */}
      <div className="gpa-mobile-layout">
        {/* Header Mobile */}
        <div className="ct-v2-m-header">
          <div className="ct-v2-m-title">
            <Target size={20} className="gpa-m-title-icon" aria-hidden="true" />
            <span>Mục tiêu môn học</span>
          </div>
          <button
            type="button"
            className="gpa-d-reset-btn"
            onClick={handleReset}
            aria-label="Đặt lại"
          >
            <RotateCcw size={13} />
            <span>Đặt lại</span>
          </button>
        </div>

        {/* Mobile Hero Navy Card */}
        <div className="gpa-mobile-hero-container">
          <div className="gpa-mobile-hero-card">
            <div className="gpa-m-hero-label">
              ĐIỂM THI CUỐI KỲ CẦN ĐẠT (MỨC {labelLetter})
            </div>
            <div className="gpa-m-score-row">
              {!result.isReady || !target ? (
                <>
                  <span className="gpa-m-score-val">--</span>
                  <span className="gpa-m-score-max">/ 10</span>
                </>
              ) : target.status === 'achieved' ? (
                <span className="gpa-m-score-val" style={{ fontSize: '2.1rem' }}>Đã đủ</span>
              ) : target.status === 'impossible' ? (
                <span className="gpa-m-score-val" style={{ fontSize: '2.1rem', color: '#f87171' }}>Không thể</span>
              ) : (
                <>
                  <span className="gpa-m-score-val">{fmt(animatedRequired)}</span>
                  <span className="gpa-m-score-max">/ 10</span>
                </>
              )}
            </div>

            <div className="gpa-m-capsule-wrap">
              {!result.isReady ? (
                <div className="gpa-m-capsule empty">
                  <span>Nhập tỷ lệ và điểm bên dưới</span>
                </div>
              ) : (
                <div className="gpa-m-capsule">
                  {mobileCapsuleBadge}
                  <span className="gpa-m-sep">│</span>
                  <span className="gpa-m-stat-item">
                    Đang có: <strong>{fmt(result.accumulatedScore)} đ</strong>
                  </span>
                  <span className="gpa-m-bullet">•</span>
                  <span className="gpa-m-stat-item">
                    Thi <strong>{result.remainingWeight}%</strong>
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Thẻ 1 (Mobile): Mức Điểm Mục Tiêu */}
        <div className="ct-v2-m-card">
          <div className="ct-v2-m-card-header">
            <span className="ct-v2-m-card-title"><span className="tool-step-badge">1</span><span>CHỌN MỨC ĐIỂM MỤC TIÊU</span></span>
            <span className="ct-v2-m-card-sub">
              Mức {labelLetter} (≥ {selectedRow?.min10.toFixed(1)} hệ 10)
            </span>
          </div>

          <div className="ct-v2-target-grid" role="group" aria-label="Chọn mức điểm mục tiêu">
            {result.targets.map((item) => {
              const isSelected = item.grade.letter === selectedRow?.letter;
              const valText = !result.isReady
                ? '—'
                : item.status === 'achieved'
                ? '✓'
                : item.status === 'impossible'
                ? '—'
                : fmt(item.requiredScore ?? 0);

              return (
                <button
                  key={item.grade.letter}
                  type="button"
                  aria-pressed={isSelected}
                  className={`ct-v2-target-btn ${isSelected ? 'active' : ''}`}
                  onClick={() => setSelectedLetter(item.grade.letter)}
                >
                  <span className="ct-v2-target-letter">{item.grade.letter}</span>
                  <span className="ct-v2-target-val">{valText}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Thẻ 2 (Mobile): Đề Cương Điểm */}
        <div className="ct-v2-m-card">
          <div className="ct-v2-m-card-header">
            <span className="ct-v2-m-card-title"><span className="tool-step-badge">2</span><span>CƠ CẤU ĐIỂM</span></span>
            <div className="ct-v2-preset-chips">
              {SYLLABUS_PRESETS.map((preset) => {
                const isActive = signature(preset.components) === presetSignature;
                return (
                  <button
                    key={preset.label}
                    type="button"
                    className={`ct-v2-preset-btn ${isActive ? 'active' : ''}`}
                    style={{ padding: '0.2rem 0.5rem', fontSize: '0.68rem' }}
                    aria-pressed={isActive}
                    onClick={() => applyPreset(preset)}
                  >
                    {preset.label}
                  </button>
                );
              })}
            </div>
          </div>

          {isSplit && (
            <div className="ct-v2-group-row" style={{ paddingTop: '0.25rem', paddingBottom: '0.45rem' }}>
              <span className="ct-v2-preset-label">Nhóm:</span>
              <div className="tool-segmented" role="group" aria-label="Nhóm môn học">
                {getCourseGroupOptions(cohort).map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    aria-pressed={courseGroup === option.id}
                    onClick={() => setCourseGroup(option.id)}
                  >
                    {option.shortLabel}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Visual 100% Weight Bar */}
          <div className="ct-v2-ribbon-bar" aria-hidden="true" style={{ height: '6px' }}>
            {result.hasWeightOverflow ? (
              <div className="ct-v2-ribbon-seg overflow" style={{ width: '100%' }} />
            ) : (
              <>
                {ribbonSegments.map((segment) => (
                  <div
                    key={segment.index}
                    className={`ct-v2-ribbon-seg seg-${segment.index % 4}`}
                    style={{ width: `${segment.weight}%` }}
                  />
                ))}
                {result.remainingWeight > 0 && (
                  <div
                    className="ct-v2-ribbon-seg final"
                    style={{ width: `${result.remainingWeight}%` }}
                  />
                )}
              </>
            )}
          </div>

          {/* Danh Sách Các Cột Điểm Mobile */}
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {components.map((component, index) => {
              const weightErr = isWeightInvalid(component.weight);
              const scoreErr = isScoreInvalid(component.score);

              return (
                <div key={component.id} className="ct-v2-m-comp-row">
                  <div className="ct-v2-name-cell" style={{ flex: '1 1 0', minWidth: 0 }}>
                    <span className={`ct-v2-dot seg-${index % 4}`} aria-hidden="true" />
                    <select
                      className="ct-v2-select"
                      style={{ maxWidth: '120px', padding: '0.3rem 1.4rem 0.3rem 0.5rem', fontSize: '0.76rem' }}
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
                  </div>

                  <div className="ct-v2-m-comp-inputs">
                    <div className="ct-v2-weight-box" style={{ width: '70px', height: '34px' }}>
                      <input
                        type="text"
                        inputMode="decimal"
                        enterKeyHint="next"
                        placeholder="VD: 30"
                        value={component.weight}
                        className={`ct-v2-weight-input ${weightErr ? 'input-error' : component.weight ? 'has-val' : ''}`}
                        style={{ fontSize: '0.8rem', padding: '0 1rem 0 0.4rem' }}
                        onChange={(e) => updateComponent(component.id, 'weight', sanitizeDecimal(e.target.value))}
                        aria-label={`Trọng số cột ${index + 1} (${component.name})`}
                      />
                      <span className="ct-v2-weight-unit" style={{ right: '0.35rem', fontSize: '0.68rem' }}>%</span>
                    </div>

                    <input
                      type="text"
                      inputMode="decimal"
                      enterKeyHint="next"
                      placeholder="VD: 8.5"
                      value={component.score}
                      className={`ct-v2-score-input ${scoreErr ? 'input-error' : component.score ? 'has-val' : ''}`}
                      style={{ width: '74px', height: '34px', fontSize: '0.82rem' }}
                      onChange={(e) => updateComponent(component.id, 'score', sanitizeDecimal(e.target.value))}
                      aria-label={`Điểm cột ${index + 1} (${component.name})`}
                    />

                    {components.length > 1 && (
                      <button
                        type="button"
                        className="gpa-d-del-btn"
                        onClick={() => removeComponent(component.id)}
                        aria-label={`Xóa cột điểm ${index + 1}`}
                        style={{ width: '28px', height: '28px', padding: 0 }}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Dòng Thi Cuối Kỳ Mobile */}
            <div className="ct-v2-m-final-row">
              <div className="ct-v2-name-cell">
                <span className="ct-v2-dot final" aria-hidden="true" />
                <span className="ct-v2-final-label" style={{ fontSize: '0.74rem' }}>
                  Thi cuối kỳ ({result.hasWeightOverflow ? '—' : `${result.remainingWeight}%`})
                </span>
              </div>
              {(() => {
                if (!result.isReady || result.hasWeightOverflow) {
                  return <span className="ct-v2-final-score-badge status-empty" style={{ height: '32px' }}>—</span>;
                }
                if (target?.status === 'achieved') {
                  return <span className="ct-v2-final-score-badge status-achieved" style={{ height: '32px' }}>✓ Đã đủ</span>;
                }
                if (target?.status === 'impossible') {
                  return <span className="ct-v2-final-score-badge status-impossible" style={{ height: '32px' }}>&gt; 10</span>;
                }
                return (
                  <span className="ct-v2-final-score-badge status-possible" style={{ height: '32px' }}>
                    Cần ≥ {fmt(target?.requiredScore ?? 0)}
                  </span>
                );
              })()}
            </div>
          </div>

          {/* Nút Thêm Cột Điểm Mobile */}
          <button
            type="button"
            className="gpa-d-add-dashed-btn"
            onClick={addComponent}
            disabled={result.totalWeight >= 100}
            style={{ padding: '0.55rem' }}
          >
            <Plus size={14} />
            <span>Thêm cột điểm</span>
          </button>

          {/* Footer Actions Mobile */}
          <div className="ct-v2-m-footer-actions">
            <button
              type="button"
              className="gpa-d-footer-link"
              onClick={() => setReferenceModalOpen(true)}
            >
              <BookOpen size={13} aria-hidden="true" />
              <span>Bảng quy đổi {cohort}</span>
              <ArrowUpRight size={13} aria-hidden="true" />
            </button>
            {shareText ? (
              <ShareResultButton text={shareText} className="gpa-d-footer-link" />
            ) : (
              <span className="gpa-d-footer-watermark">ĐHSP TP.HCM</span>
            )}
          </div>
        </div>
      </div>

      {/* Modal Bảng Quy Đổi Điểm */}
      <GpaReferenceModal
        isOpen={referenceModalOpen}
        onClose={() => setReferenceModalOpen(false)}
        cohort={cohort}
        initialTab="scale"
        activeGroup={activeGroup}
      />
    </div>
  );
}
