import { useMemo, useState } from 'react';
import { TrendingUp, Trash2, RotateCcw } from 'lucide-react';
import { type Cohort } from '../../utils/gradeScale';
import { sanitizeDecimal } from '../../utils/numberInput';
import { useLocalStorage } from '../../hooks/useLocalStorage';
import { GpaReferenceModal } from '../GpaReferenceModal';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import {
  type RetakeCourse,
  calculateTermPlan,
  calculateRetakeImpact,
  calculateRoadmapPlan,
  getCoursePrescription,
  format2,
} from '../../utils/targetGpaCalculations';

interface TargetGpaPageProps {
  cohort?: Cohort;
}

type TabType = 'term' | 'retake' | 'roadmap';

interface StoredGpaProfile {
  currentGpa: string;
  currentCredits: string;
}

const DEFAULT_PROFILE: StoredGpaProfile = {
  currentGpa: '2.85',
  currentCredits: '60',
};

const TARGET_PRESETS = [
  { label: 'Khá', value: '2.50' },
  { label: 'Giỏi', value: '3.20' },
  { label: 'Xuất sắc', value: '3.60' },
];

const TERM_CREDIT_PRESETS = [12, 15, 18, 21];
const ROADMAP_CREDIT_PRESETS = [30, 45, 60, 75];

export function TargetGpaPage({ cohort = 'K51' }: TargetGpaPageProps) {
  // Tab Navigation
  const [activeTab, setActiveTab] = useState<TabType>('term');

  // Shared Profile State across all tabs (persisted in localStorage)
  const [profile, setProfile] = useLocalStorage<StoredGpaProfile>(
    'hcmue_target_gpa_profile',
    DEFAULT_PROFILE,
  );

  const currentGpaStr = profile?.currentGpa ?? DEFAULT_PROFILE.currentGpa;
  const currentCreditsStr = profile?.currentCredits ?? DEFAULT_PROFILE.currentCredits;

  const currentGpaNum = Number(currentGpaStr);
  const currentCreditsNum = Number(currentCreditsStr);

  const isProfileValid =
    Number.isFinite(currentGpaNum) &&
    currentGpaNum >= 0 &&
    currentGpaNum <= 4.0 &&
    Number.isFinite(currentCreditsNum) &&
    currentCreditsNum >= 0 &&
    currentCreditsNum <= 250;

  const progressPercent = Math.min(
    100,
    Math.max(0, Math.round(((Number.isFinite(currentCreditsNum) ? currentCreditsNum : 0) / 135) * 100)),
  );

  // Tab 1: 1 Học Kỳ Tới State
  const [targetGpaStr, setTargetGpaStr] = useState('3.20');
  const [futureCredits, setFutureCredits] = useState(15);

  // Tab 2: Cải Thiện Môn F/D State
  const [retakes, setRetakes] = useState<RetakeCourse[]>([
    { id: 'retake-1', label: 'Môn 1', oldGrade: 0.0, targetGrade: 4.0, credits: 3 },
  ]);

  // Tab 3: Lộ Trình Ra Trường State
  const [targetGradGpaStr, setTargetGradGpaStr] = useState('3.20');
  const [remainingCredits, setRemainingCredits] = useState(() =>
    Math.max(15, 135 - (Number.isFinite(currentCreditsNum) ? currentCreditsNum : 60)),
  );

  // Reference Modal State
  const [referenceModalTab, setReferenceModalTab] = useState<'scale' | 'rules' | null>(null);

  // Tab 1 Calculations
  const termPlan = useMemo(() => {
    return calculateTermPlan(
      currentGpaNum,
      currentCreditsNum,
      Number(targetGpaStr) || 3.20,
      futureCredits,
    );
  }, [currentGpaNum, currentCreditsNum, targetGpaStr, futureCredits]);

  const prescription = useMemo(() => {
    return getCoursePrescription(termPlan.requiredGpa, futureCredits);
  }, [termPlan.requiredGpa, futureCredits]);

  // Tab 2 Calculations
  const retakePlan = useMemo(() => {
    return calculateRetakeImpact(
      currentGpaNum,
      currentCreditsNum,
      retakes,
      15,
      Number(targetGpaStr) || 3.20,
    );
  }, [currentGpaNum, currentCreditsNum, retakes, targetGpaStr]);

  // Tab 3 Calculations
  const roadmapPlan = useMemo(() => {
    return calculateRoadmapPlan(
      currentGpaNum,
      currentCreditsNum,
      Number(targetGradGpaStr) || 3.20,
      remainingCredits,
      135,
    );
  }, [currentGpaNum, currentCreditsNum, targetGradGpaStr, remainingCredits]);

  // Handlers for profile updates
  const handleCurrentGpaChange = (val: string) => {
    const clean = sanitizeDecimal(val);
    setProfile((prev) => ({
      currentGpa: clean,
      currentCredits: prev?.currentCredits ?? DEFAULT_PROFILE.currentCredits,
    }));
  };

  const handleCurrentCreditsChange = (val: string) => {
    const clean = sanitizeDecimal(val);
    setProfile((prev) => ({
      currentGpa: prev?.currentGpa ?? DEFAULT_PROFILE.currentGpa,
      currentCredits: clean,
    }));
  };

  // Handlers for Tab 2 (Retake Courses)
  const handleAddRetake = () => {
    if (retakes.length >= 6) return;
    const nextId = `retake-${Date.now()}`;
    const nextIdx = retakes.length + 1;
    setRetakes((prev) => [
      ...prev,
      { id: nextId, label: `Môn ${nextIdx}`, oldGrade: 0.0, targetGrade: 4.0, credits: 3 },
    ]);
  };

  const handleRemoveRetake = (id: string) => {
    if (retakes.length <= 1) return;
    setRetakes((prev) => prev.filter((r) => r.id !== id));
  };

  const handleUpdateRetake = (id: string, field: keyof RetakeCourse, val: number | string) => {
    setRetakes((prev) =>
      prev.map((r) => (r.id === id ? { ...r, [field]: val } : r)),
    );
  };

  // Handler for Global Reset
  const handleReset = () => {
    if (window.confirm('Bạn có chắc chắn muốn đặt lại các thông số về mặc định không?')) {
      setProfile(DEFAULT_PROFILE);
      setTargetGpaStr('3.20');
      setFutureCredits(15);
      setRetakes([
        { id: 'retake-1', label: 'Môn 1', oldGrade: 0.0, targetGrade: 4.0, credits: 3 },
      ]);
      setTargetGradGpaStr('3.20');
      setRemainingCredits(75);
    }
  };

  return (
    <div className="page-container tool-page simplified">
      <div className="target-gpa-header-wrap">
        <ToolPageHeader
          icon={TrendingUp}
          title="Mục tiêu GPA"
          description="Studio tính toán chiến lược GPA học kỳ, cải thiện môn F/D và lộ trình tốt nghiệp toàn khóa."
        />
        <button
          type="button"
          className="tool-reset-btn"
          onClick={handleReset}
          title="Đặt lại thông số"
          aria-label="Đặt lại thông số"
        >
          <RotateCcw size={15} />
          <span>Đặt lại</span>
        </button>
      </div>

      <div className="target-gpa-studio">
        {/* 3-Tab Navigation Bar */}
        <div className="target-gpa-tabs-bar" role="tablist" aria-label="Các chế độ tính toán GPA">
          <div className="target-gpa-tabs-row">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'term'}
              className={`target-gpa-tab-item ${activeTab === 'term' ? 'active' : ''}`}
              onClick={() => setActiveTab('term')}
            >
              🎯 1 Học Kỳ Tới
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'retake'}
              className={`target-gpa-tab-item ${activeTab === 'retake' ? 'active' : ''}`}
              onClick={() => setActiveTab('retake')}
            >
              ⚡ Cải Thiện Môn F/D
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'roadmap'}
              className={`target-gpa-tab-item ${activeTab === 'roadmap' ? 'active' : ''}`}
              onClick={() => setActiveTab('roadmap')}
            >
              🎓 Lộ Trình Ra Trường
            </button>
          </div>
        </div>

        {/* 2-Column Layout */}
        <div className="target-gpa-layout-2col">
          {/* Left Column: Form Cards */}
          <div className="target-gpa-form-stack">
            {/* Card 1: Shared Profile (Điểm Hiện Tại) */}
            <div className="target-gpa-form-card">
              <div className="target-gpa-card-title">
                <span>1. Điểm Hiện Tại</span>
                <span className="target-gpa-tag-status">
                  {isProfileValid ? '✓ Đã lưu' : 'Chưa lưu'}
                </span>
              </div>

              <div className="target-gpa-fields-grid">
                <div className="target-gpa-field-item">
                  <label htmlFor="target-curr-gpa">GPA tích lũy:</label>
                  <div className="target-gpa-input-box">
                    <input
                      id="target-curr-gpa"
                      type="text"
                      inputMode="decimal"
                      value={currentGpaStr}
                      onChange={(e) => handleCurrentGpaChange(e.target.value)}
                      placeholder="2.85"
                    />
                    <span>/ 4.00</span>
                  </div>
                </div>

                <div className="target-gpa-field-item">
                  <label htmlFor="target-curr-creds">Đã tích lũy:</label>
                  <div className="target-gpa-input-box">
                    <input
                      id="target-curr-creds"
                      type="text"
                      inputMode="numeric"
                      value={currentCreditsStr}
                      onChange={(e) => handleCurrentCreditsChange(e.target.value)}
                      placeholder="60"
                    />
                    <span>TC</span>
                  </div>
                </div>
              </div>

              <div className="target-gpa-progress-hint">
                <span>Tiến độ chương trình</span>
                <span>
                  {currentCreditsStr || '0'} / 135 TC ({progressPercent}%)
                </span>
              </div>
              <div className="target-gpa-mini-progress">
                <div
                  className="target-gpa-mini-fill"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

            {/* Card 2: Tab-specific Controls */}
            {activeTab === 'term' && (
              <div className="target-gpa-form-card">
                <div className="target-gpa-card-title">
                  <span>2. Mục Tiêu Kỳ Tới</span>
                </div>

                {/* Slider for Target GPA */}
                <div className="target-gpa-slider-header">
                  <label htmlFor="target-goal-slider">GPA muốn đạt:</label>
                  <div className="target-gpa-slider-val-tag">
                    {format2(Number(targetGpaStr) || 3.2)} <span>/ 4.00</span>
                  </div>
                </div>

                <input
                  id="target-goal-slider"
                  type="range"
                  className="target-gpa-slider-range"
                  min="2.00"
                  max="4.00"
                  step="0.05"
                  value={Number(targetGpaStr) || 3.2}
                  onChange={(e) => setTargetGpaStr(e.target.value)}
                  aria-label="Kéo chọn GPA muốn đạt"
                />

                <div className="target-gpa-presets-row" role="group" aria-label="Chọn nhanh mức GPA mục tiêu">
                  {TARGET_PRESETS.map((p) => {
                    const isActive = targetGpaStr === p.value;
                    return (
                      <button
                        key={p.value}
                        type="button"
                        className={`target-gpa-btn-preset ${isActive ? 'active' : ''}`}
                        onClick={() => setTargetGpaStr(p.value)}
                      >
                        {p.label} ({p.value})
                      </button>
                    );
                  })}
                </div>

                {/* Stepper for Future Credits */}
                <div className="target-gpa-stepper-row">
                  <label>Tín chỉ kỳ tới:</label>
                  <div className="target-gpa-stepper-combo">
                    <div className="target-gpa-stepper-wrap">
                      <button
                        type="button"
                        className="target-gpa-stepper-btn"
                        onClick={() => setFutureCredits((prev) => Math.max(3, prev - 1))}
                        aria-label="Giảm 1 tín chỉ"
                      >
                        −
                      </button>
                      <div className="target-gpa-stepper-val">{futureCredits} TC</div>
                      <button
                        type="button"
                        className="target-gpa-stepper-btn"
                        onClick={() => setFutureCredits((prev) => Math.min(35, prev + 1))}
                        aria-label="Tăng 1 tín chỉ"
                      >
                        +
                      </button>
                    </div>

                    {TERM_CREDIT_PRESETS.map((c) => (
                      <button
                        key={c}
                        type="button"
                        className={`target-gpa-pill-btn ${futureCredits === c ? 'active' : ''}`}
                        onClick={() => setFutureCredits(c)}
                      >
                        {c} TC
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'retake' && (
              <div className="target-gpa-form-card">
                <div className="target-gpa-card-title">
                  <span>2. Môn Cải Thiện Điểm</span>
                </div>

                <table className="target-gpa-retake-table">
                  <thead>
                    <tr>
                      <th style={{ width: '28%' }}>Môn</th>
                      <th style={{ width: '24%' }}>Điểm cũ</th>
                      <th style={{ width: '20%' }}>Số TC</th>
                      <th style={{ width: '22%' }}>Mục tiêu</th>
                      <th style={{ width: '6%' }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {retakes.map((course, idx) => (
                      <tr key={course.id}>
                        <td>
                          <input
                            type="text"
                            className="target-gpa-select"
                            value={course.label ?? `Môn ${idx + 1}`}
                            onChange={(e) =>
                              handleUpdateRetake(course.id, 'label', e.target.value)
                            }
                            aria-label={`Tên môn ${idx + 1}`}
                          />
                        </td>
                        <td>
                          <select
                            className="target-gpa-select"
                            value={course.oldGrade}
                            onChange={(e) =>
                              handleUpdateRetake(course.id, 'oldGrade', Number(e.target.value))
                            }
                            aria-label="Điểm cũ"
                          >
                            <option value={0.0}>F (0.0)</option>
                            <option value={1.0}>D (1.0)</option>
                            <option value={1.5}>D+ (1.5)</option>
                            <option value={2.0}>C (2.0)</option>
                          </select>
                        </td>
                        <td>
                          <select
                            className="target-gpa-select"
                            value={course.credits}
                            onChange={(e) =>
                              handleUpdateRetake(course.id, 'credits', Number(e.target.value))
                            }
                            aria-label="Số tín chỉ"
                          >
                            <option value={1}>1 TC</option>
                            <option value={2}>2 TC</option>
                            <option value={3}>3 TC</option>
                            <option value={4}>4 TC</option>
                          </select>
                        </td>
                        <td>
                          <select
                            className="target-gpa-select"
                            value={course.targetGrade}
                            onChange={(e) =>
                              handleUpdateRetake(course.id, 'targetGrade', Number(e.target.value))
                            }
                            aria-label="Mục tiêu điểm mới"
                          >
                            <option value={4.0}>A (4.0)</option>
                            <option value={3.5}>B+ (3.5)</option>
                            <option value={3.0}>B (3.0)</option>
                            <option value={2.5}>C+ (2.5)</option>
                          </select>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="target-gpa-btn-del"
                            disabled={retakes.length <= 1}
                            onClick={() => handleRemoveRetake(course.id)}
                            title="Xóa môn"
                            aria-label="Xóa môn này"
                          >
                            <Trash2 size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {retakes.length < 6 && (
                  <button
                    type="button"
                    className="target-gpa-btn-add"
                    onClick={handleAddRetake}
                  >
                    + Thêm Môn Cải Thiện
                  </button>
                )}
              </div>
            )}

            {activeTab === 'roadmap' && (
              <div className="target-gpa-form-card">
                <div className="target-gpa-card-title">
                  <span>2. Kế Hoạch Tốt Nghiệp</span>
                </div>

                {/* Slider for Graduation GPA */}
                <div className="target-gpa-slider-header">
                  <label htmlFor="target-grad-slider">GPA tốt nghiệp muốn đạt:</label>
                  <div className="target-gpa-slider-val-tag">
                    {format2(Number(targetGradGpaStr) || 3.2)} <span>/ 4.00</span>
                  </div>
                </div>

                <input
                  id="target-grad-slider"
                  type="range"
                  className="target-gpa-slider-range"
                  min="2.00"
                  max="4.00"
                  step="0.05"
                  value={Number(targetGradGpaStr) || 3.2}
                  onChange={(e) => setTargetGradGpaStr(e.target.value)}
                  aria-label="Kéo chọn GPA tốt nghiệp muốn đạt"
                />

                <div className="target-gpa-presets-row" role="group" aria-label="Chọn nhanh mức GPA tốt nghiệp">
                  {TARGET_PRESETS.map((p) => {
                    const isActive = targetGradGpaStr === p.value;
                    return (
                      <button
                        key={p.value}
                        type="button"
                        className={`target-gpa-btn-preset ${isActive ? 'active' : ''}`}
                        onClick={() => setTargetGradGpaStr(p.value)}
                      >
                        {p.label} ({p.value})
                      </button>
                    );
                  })}
                </div>

                {/* Stepper for Remaining Credits */}
                <div className="target-gpa-stepper-row">
                  <label>Tín chỉ còn lại để ra trường:</label>
                  <div className="target-gpa-stepper-combo">
                    <div className="target-gpa-stepper-wrap">
                      <button
                        type="button"
                        className="target-gpa-stepper-btn"
                        onClick={() => setRemainingCredits((prev) => Math.max(3, prev - 3))}
                        aria-label="Giảm 3 tín chỉ"
                      >
                        −
                      </button>
                      <div className="target-gpa-stepper-val">{remainingCredits} TC</div>
                      <button
                        type="button"
                        className="target-gpa-stepper-btn"
                        onClick={() => setRemainingCredits((prev) => Math.min(150, prev + 3))}
                        aria-label="Tăng 3 tín chỉ"
                      >
                        +
                      </button>
                    </div>

                    {ROADMAP_CREDIT_PRESETS.map((c) => (
                      <button
                        key={c}
                        type="button"
                        className={`target-gpa-pill-btn ${remainingCredits === c ? 'active' : ''}`}
                        onClick={() => setRemainingCredits(c)}
                      >
                        {c} TC
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Unified Result Card */}
          <div className="target-gpa-sticky-col">
            <div className="target-gpa-result-card" id="target-gpa-result">
              {activeTab === 'term' && (
                <>
                  <div className="target-gpa-res-header">
                    <span className="res-title">KẾT QUẢ KỲ TỚI</span>
                    {termPlan.status === 'achieved' && (
                      <span className="target-gpa-badge-feasible">✓ Đã Đạt</span>
                    )}
                    {termPlan.status === 'impossible' && (
                      <span className="target-gpa-badge-feasible danger">✕ Không Khả Thi</span>
                    )}
                    {termPlan.status === 'feasible' && (
                      <span
                        className={`target-gpa-badge-feasible ${
                          termPlan.requiredGpa >= 3.6 ? 'warning' : ''
                        }`}
                      >
                        {termPlan.requiredGpa >= 3.6 ? '▲ Rất Khó' : '● Khả Thi'}
                      </span>
                    )}
                  </div>

                  <div className="target-gpa-hero-section">
                    {termPlan.status === 'achieved' ? (
                      <>
                        <div className="hero-label">GPA TÍCH LŨY HIỆN TẠI</div>
                        <div className="hero-score">
                          {format2(currentGpaNum)} <span>/ 4.00</span>
                        </div>
                        <div className="hero-rank">
                          Đã đạt mục tiêu {format2(Number(targetGpaStr) || 3.2)}
                        </div>
                      </>
                    ) : termPlan.status === 'impossible' ? (
                      <>
                        <div className="hero-label">GPA HỌC KỲ TỚI CẦN ĐẠT</div>
                        <div className="hero-score danger">
                          {format2(termPlan.requiredGpa)} <span>/ 4.00</span>
                        </div>
                        <div className="hero-rank">Vượt quá thang điểm tối đa (4.00)</div>
                      </>
                    ) : (
                      <>
                        <div className="hero-label">GPA HỌC KỲ TỚI CẦN ĐẠT</div>
                        <div className="hero-score">
                          {format2(termPlan.requiredGpa)} <span>/ 4.00</span>
                        </div>
                        <div className="hero-rank">
                          Mức điểm chữ: {termPlan.equivalentLetter}
                        </div>
                      </>
                    )}
                  </div>

                  <div className="target-gpa-presc-section">
                    <div className="target-gpa-presc-title">
                      <span>
                        Gợi ý phân bổ điểm ({futureCredits} TC ~ {prescription.totalCourses} môn)
                      </span>
                    </div>
                    <div className="target-gpa-presc-badges">
                      {termPlan.status === 'impossible' ? (
                        <div className="target-gpa-badge-grade">
                          Cần {termPlan.minCreditsNeeded ?? '> 20'} TC điểm A toàn bộ
                        </div>
                      ) : (
                        <>
                          {prescription.coursesA > 0 && (
                            <div className="target-gpa-badge-grade">
                              {prescription.coursesA} môn A (4.0)
                            </div>
                          )}
                          {prescription.coursesBPlus > 0 && (
                            <div className="target-gpa-badge-grade">
                              {prescription.coursesBPlus} môn B+ (3.5)
                            </div>
                          )}
                          {prescription.coursesB > 0 && (
                            <div className="target-gpa-badge-grade">
                              {prescription.coursesB} môn B (3.0)
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </div>

                  <div className="target-gpa-clean-notice">
                    {termPlan.status === 'impossible' ? (
                      <>
                        Không thể đạt <strong>{format2(Number(targetGpaStr) || 3.2)}</strong> chỉ với{' '}
                        <strong>{futureCredits} TC</strong> trong 1 kỳ.{' '}
                        {termPlan.minCreditsNeeded ? (
                          <>
                            Cần học tối thiểu <strong>{termPlan.minCreditsNeeded} TC</strong> và đạt{' '}
                            <strong>4.00</strong> toàn bộ.
                          </>
                        ) : null}
                      </>
                    ) : termPlan.status === 'achieved' ? (
                      <>
                        GPA hiện tại (<strong>{format2(currentGpaNum)}</strong>) đã đạt hoặc vượt mục tiêu{' '}
                        <strong>{format2(Number(targetGpaStr) || 3.2)}</strong>. Hãy tiếp tục giữ vững phong độ ở kỳ tới.
                      </>
                    ) : (
                      <>
                        Cần tối thiểu{' '}
                        <strong>
                          {prescription.coursesA > 0
                            ? `${prescription.coursesA} môn A`
                            : `${prescription.coursesBPlus} môn B+`}
                        </strong>{' '}
                        để kéo GPA tích lũy lên{' '}
                        <strong>{format2(Number(targetGpaStr) || 3.2)}</strong>. Có thể đăng ký thêm môn tự chọn vừa sức.
                      </>
                    )}
                  </div>
                </>
              )}

              {activeTab === 'retake' && (
                <>
                  <div className="target-gpa-res-header">
                    <span className="res-title">HIỆU QUẢ CẢI THIỆN</span>
                    <span className="target-gpa-badge-feasible">● Tăng Vọt</span>
                  </div>

                  <div className="target-gpa-hero-section">
                    <div className="hero-label">MỨC KÉO ĐIỂM TỰ THÂN</div>
                    <div className="hero-score">
                      ▲ +{format2(retakePlan.deltaGpa)} <span>GPA</span>
                    </div>
                    <div className="hero-rank">
                      GPA mới: {format2(currentGpaNum)} ➔ {format2(retakePlan.newBaselineGpa)}
                    </div>
                  </div>

                  <div className="target-gpa-impact-row">
                    <span className="target-label">Nhận thêm:</span>
                    <span className="target-val">
                      +{retakePlan.qualityPointsAdded} Điểm chất lượng
                    </span>
                  </div>

                  <div className="target-gpa-clean-notice">
                    Học lại <strong>{retakes.length} môn</strong> giúp nâng trực tiếp điểm tích lũy lên{' '}
                    <strong>{format2(retakePlan.newBaselineGpa)}</strong> mà không làm tăng tổng tín chỉ tốt nghiệp.
                  </div>
                </>
              )}

              {activeTab === 'roadmap' && (
                <>
                  <div className="target-gpa-res-header">
                    <span className="res-title">LỘ TRÌNH DÀI HẠN</span>
                    <span
                      className={`target-gpa-badge-feasible ${
                        roadmapPlan.isFeasible ? '' : 'danger'
                      }`}
                    >
                      {roadmapPlan.isFeasible ? '● Khả Thi' : '✕ Quá Tải'}
                    </span>
                  </div>

                  <div className="target-gpa-hero-section">
                    <div className="hero-label">GPA CẦN DUY TRÌ MỖI KỲ</div>
                    <div
                      className={`hero-score ${
                        roadmapPlan.isFeasible ? '' : 'danger'
                      }`}
                    >
                      {format2(roadmapPlan.averageGpaNeeded)} <span>/ 4.00</span>
                    </div>
                    <div className="hero-rank">
                      Dự kiến còn ~{roadmapPlan.termsRemaining} học kỳ (15 TC/kỳ)
                    </div>
                  </div>

                  <div className="target-gpa-roadmap-grid">
                    <div className="target-gpa-roadmap-card">
                      <div className="m-title">{roadmapPlan.milestones[0].title}</div>
                      <div className="m-score">{roadmapPlan.milestones[0].score}</div>
                      <div className="m-sub">{roadmapPlan.milestones[0].sub}</div>
                    </div>
                    <div className="target-gpa-roadmap-card">
                      <div className="m-title">{roadmapPlan.milestones[1].title}</div>
                      <div className="m-score">{roadmapPlan.milestones[1].score}</div>
                      <div className="m-sub">{roadmapPlan.milestones[1].sub}</div>
                    </div>
                    <div className="target-gpa-roadmap-card grad-finish">
                      <div className="m-title">{roadmapPlan.milestones[2].title}</div>
                      <div className="m-score">{roadmapPlan.milestones[2].score}</div>
                      <div className="m-sub">{roadmapPlan.milestones[2].sub}</div>
                    </div>
                  </div>

                  <div className="target-gpa-clean-notice">
                    {roadmapPlan.isFeasible ? (
                      <>
                        Duy trì mức <strong>{format2(roadmapPlan.averageGpaNeeded)}</strong> mỗi kỳ trong{' '}
                        <strong>{roadmapPlan.termsRemaining} kỳ tới</strong> để tốt nghiệp loại{' '}
                        <strong>
                          {Number(targetGradGpaStr) >= 3.6
                            ? 'Xuất Sắc'
                            : Number(targetGradGpaStr) >= 3.2
                              ? 'Giỏi'
                              : 'Khá'}
                        </strong>.
                      </>
                    ) : (
                      <>
                        Mục tiêu <strong>{format2(Number(targetGradGpaStr) || 3.2)}</strong> đòi hỏi điểm trung bình vượt quá 4.00 cho số tín chỉ còn lại. Hãy kết hợp học cải thiện môn F/D ở Tab 2.
                      </>
                    )}
                  </div>
                </>
              )}

              {/* Shared Result Card Footer */}
              <div className="tool-source">
                <span>Kết quả chỉ để tham khảo.</span>
                <button
                  type="button"
                  className="tool-text-btn"
                  onClick={() => setReferenceModalTab('rules')}
                >
                  Quy chế điểm
                </button>
                <button
                  type="button"
                  className="tool-text-btn"
                  onClick={() => setReferenceModalTab('scale')}
                >
                  Bảng quy đổi điểm
                </button>
              </div>
            </div>
          </div>
        </div>
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
