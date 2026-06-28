import { useMemo, useState } from 'react';
import { Target, Plus, Trash2, AlertCircle } from 'lucide-react';
import {
  getCourseGroupOptions,
  getDefaultCourseGroup,
  getGradeScale,
  type Cohort,
  type CourseGroup,
  type LetterGrade,
} from '../../utils/gradeScale';

interface CourseTargetPageProps {
  cohort: Cohort;
}

interface ScoreComponent {
  id: string;
  name: string;
  weight: string;
  score: string;
}

type TargetStatus = 'possible' | 'achieved' | 'impossible' | 'error';

const GRADE_META: Record<LetterGrade, { name: string; color: string }> = {
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

  const activeGroup = cohort === 'K50-K51' ? courseGroup : getDefaultCourseGroup(cohort);
  const scale = getGradeScale(cohort, activeGroup);

  const addComponent = () => {
    setComponents((curr) => [
      ...curr,
      { id: `comp-${Date.now()}`, name: '', weight: '', score: '' },
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

  const result = useMemo(() => {
    let totalWeight = 0;
    let accumulatedScore = 0;
    let hasInvalidWeight = false;
    let hasInvalidScore = false;

    for (const comp of components) {
      const w = Number(comp.weight);
      const s = Number(comp.score);

      if (!comp.weight) continue;

      if (!Number.isFinite(w) || w < 0 || w > 100) hasInvalidWeight = true;
      totalWeight += w;

      if (comp.score) {
        if (!Number.isFinite(s) || s < 0 || s > 10) {
          hasInvalidScore = true;
        } else {
          accumulatedScore += (s * w) / 100;
        }
      }
    }

    const remainingWeight = 100 - totalWeight;
    const isError = totalWeight > 100 || hasInvalidWeight || hasInvalidScore;

    const targets = scale.rows.filter((row) => row.status === 'Đạt').map((grade) => {
      const meta = GRADE_META[grade.letter];
      if (isError) {
        return { ...grade, ...meta, requiredScore: null, status: 'error' as TargetStatus };
      }

      const missingScore = grade.min10 - accumulatedScore;

      if (remainingWeight === 0) {
        return {
          ...grade,
          ...meta,
          requiredScore: null,
          status: missingScore <= 0 ? 'achieved' as TargetStatus : 'impossible' as TargetStatus,
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

    return {
      totalWeight,
      remainingWeight,
      accumulatedScore,
      isError,
      targets,
    };
  }, [components, scale]);

  return (
    <div className="page-container tool-page">
      <div className="page-header">
        <h1>Mục tiêu môn học</h1>
        <p>Tính điểm thi cuối kỳ cần đạt dựa trên các cột điểm thành phần và bảng quy đổi của {cohort}.</p>
      </div>

      <div className="tool-layout split">
        <div className="tool-input-section" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <section className="tool-panel">
            <div className="tool-panel-header">
              <div>
                <h2>Thành phần điểm đã có</h2>
                <p>Nhập điểm quá trình, chuyên cần hoặc giữa kỳ. Trọng số thi cuối kỳ sẽ được tính từ phần còn lại.</p>
              </div>
            </div>

            {cohort === 'K50-K51' && (
              <div className="tool-field-block">
                <label>Nhóm học phần</label>
                <select
                  className="tool-select"
                  value={courseGroup}
                  onChange={(event) => setCourseGroup(event.target.value as CourseGroup)}
                >
                  {getCourseGroupOptions(cohort).map((option) => (
                    <option key={option.id} value={option.id}>{option.label}</option>
                  ))}
                </select>
                <p>{scale.applicability}</p>
              </div>
            )}

            <div className="scroll-hint">Vuốt ngang để xem bảng</div>
            <div className="tool-table-wrap">
              <table className="tool-table gpa-table" style={{ width: '100%', minWidth: '400px' }}>
                <thead>
                  <tr>
                    <th>Tên thành phần</th>
                    <th style={{ width: '25%' }}>Trọng số (%)</th>
                    <th style={{ width: '30%' }}>Điểm đạt (10)</th>
                    <th style={{ width: '42px' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {components.map((comp) => (
                    <tr key={comp.id}>
                      <td>
                        <select
                          value={comp.name}
                          onChange={(e) => updateComponent(comp.id, 'name', e.target.value)}
                          className="tool-select"
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
                        <div className="input-with-suffix" style={{ position: 'relative' }}>
                          <input
                            type="number"
                            min="0"
                            max="100"
                            value={comp.weight}
                            onChange={(e) => updateComponent(comp.id, 'weight', e.target.value)}
                            className="tool-input small"
                            placeholder="VD: 20"
                            style={{ paddingRight: '2rem', width: '100%' }}
                          />
                          <span style={{ position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)', pointerEvents: 'none' }}>%</span>
                        </div>
                      </td>
                      <td>
                        <input
                          type="number"
                          min="0"
                          max="10"
                          step="0.1"
                          value={comp.score}
                          onChange={(e) => updateComponent(comp.id, 'score', e.target.value)}
                          className="tool-input small"
                          placeholder="Chưa có"
                          style={{ width: '100%' }}
                        />
                      </td>
                      <td>
                        {components.length > 1 && (
                          <button
                            className="icon-btn danger"
                            onClick={() => removeComponent(comp.id)}
                            style={{ padding: '0.5rem', margin: '0 auto' }}
                            title="Xóa thành phần"
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <button
              className="tool-btn secondary"
              onClick={addComponent}
              style={{ marginTop: '1.5rem', width: '100%', justifyContent: 'center' }}
              disabled={result.totalWeight >= 100}
            >
              <Plus size={18} />
              <span>Thêm cột điểm</span>
            </button>
          </section>

          <div className="tool-callout info" style={{ margin: 0 }}>
            <h2>Mẹo tính trọng số thi cuối kỳ</h2>
            <p>
              Bạn không cần nhập trọng số thi cuối kỳ. Hệ thống sẽ <strong>tự động tính toán</strong> theo công thức:
            </p>
            <div className="formula-box">
              Trọng số thi = 100% - tổng trọng số đã nhập
            </div>
            <p style={{ marginTop: '0.5rem' }}>Ngưỡng qua môn hiện dùng: từ {scale.passThreshold.toFixed(1)} điểm cho {scale.shortLabel.toLowerCase()}.</p>
          </div>
        </div>

        <aside className="tool-result-card" style={{ padding: '1.5rem', background: 'var(--bg-secondary)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
            <div className="result-icon" style={{ margin: 0, padding: '0.75rem' }}>
              <Target size={24} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>Mục tiêu cuối kỳ</h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.35rem' }}>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Trọng số:</span>
                <span style={{ padding: '0.2rem 0.75rem', background: 'rgba(59, 130, 246, 0.1)', color: 'var(--primary)', borderRadius: '100px', fontSize: '1rem', fontWeight: 700 }}>
                  {result.isError ? 0 : result.remainingWeight}%
                </span>
              </div>
            </div>
          </div>

          {result.isError ? (
            <div style={{ padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '8px', color: 'var(--danger)', display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
              <AlertCircle size={20} style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <strong>Lỗi dữ liệu</strong>
                <p style={{ margin: '0.25rem 0 0', fontSize: '0.9rem' }}>Vui lòng kiểm tra trọng số và điểm thành phần. Tổng trọng số không được vượt quá 100% và điểm phải nằm trong khoảng 0-10.</p>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {result.targets.map((target) => (
                <div
                  key={target.letter}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.875rem 1rem',
                    background: target.status === 'impossible' ? 'transparent' : 'var(--bg-primary)',
                    border: `1px solid ${target.status === 'impossible' ? 'var(--border-color)' : target.color}40`,
                    borderRadius: '8px',
                    opacity: target.status === 'impossible' ? 0.6 : 1,
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div>
                      <div style={{ fontWeight: 600, color: target.status === 'impossible' ? 'var(--text-secondary)' : target.color }}>
                        Điểm {target.letter}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        {target.name} · từ {target.min10.toFixed(1)}
                      </div>
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    {target.status === 'impossible' ? (
                      <span style={{ fontSize: '0.85rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
                        Bất khả thi
                      </span>
                    ) : target.status === 'achieved' ? (
                      <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--success)' }}>
                        Đã đạt
                      </span>
                    ) : target.requiredScore !== null ? (
                      <span style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {target.requiredScore.toFixed(2)}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-secondary)' }}>--</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
