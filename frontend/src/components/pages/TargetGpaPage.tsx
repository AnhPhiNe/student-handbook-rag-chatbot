import { useMemo, useState } from 'react';
import { TrendingUp, Trash2, RotateCcw, BookOpen, ExternalLink, FileText } from 'lucide-react';
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
  totalDegreeCredits: string;
}

const DEFAULT_PROFILE: StoredGpaProfile = {
  currentGpa: '',
  currentCredits: '',
  totalDegreeCredits: '135',
};

const TARGET_PRESETS = [
  { label: 'Khá', value: '2.50' },
  { label: 'Giỏi', value: '3.20' },
  { label: 'Xuất sắc', value: '3.60' },
];

const TERM_CREDIT_PRESETS = [12, 15, 18, 21];

const RETAKE_OLD_GRADES = [
  { label: 'F (0.0)', value: 0.0 },
  { label: 'D (1.0)', value: 1.0 },
  { label: 'D+ (1.5)', value: 1.5 },
  { label: 'C (2.0)', value: 2.0 },
  { label: 'C+ (2.5)', value: 2.5 },
  { label: 'B (3.0)', value: 3.0 },
  { label: 'B+ (3.5)', value: 3.5 },
];

const ALL_TARGET_GRADES = [
  { label: 'D (1.0)', value: 1.0 },
  { label: 'D+ (1.5)', value: 1.5 },
  { label: 'C (2.0)', value: 2.0 },
  { label: 'C+ (2.5)', value: 2.5 },
  { label: 'B (3.0)', value: 3.0 },
  { label: 'B+ (3.5)', value: 3.5 },
  { label: 'A (4.0)', value: 4.0 },
];

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
  const totalDegreeCreditsStr = profile?.totalDegreeCredits ?? DEFAULT_PROFILE.totalDegreeCredits;

  const currentGpaNum = Number(currentGpaStr);
  const currentCreditsNum = Number(currentCreditsStr);
  const totalDegreeCreditsNum = Number(totalDegreeCreditsStr) || 135;

  const hasEnteredProfile =
    currentGpaStr.trim() !== '' &&
    currentCreditsStr.trim() !== '' &&
    Number.isFinite(currentGpaNum) &&
    currentGpaNum >= 0 &&
    currentGpaNum <= 4.0 &&
    Number.isFinite(currentCreditsNum) &&
    currentCreditsNum >= 0 &&
    currentCreditsNum <= 250;

  const isProfileValid =
    hasEnteredProfile &&
    Number.isFinite(totalDegreeCreditsNum) &&
    totalDegreeCreditsNum >= 50 &&
    totalDegreeCreditsNum <= 300;

  // Tab 1: 1 Học Kỳ Tới State
  const [targetGpaStr, setTargetGpaStr] = useState('3.20');
  const [futureCredits, setFutureCredits] = useState(15);

  // Tab 2: Cải Thiện Môn F/D State
  const [retakes, setRetakes] = useState<RetakeCourse[]>([
    { id: 'retake-1', label: 'Môn 1', oldGrade: 0.0, targetGrade: 4.0, credits: 3 },
  ]);

  // Tab 3: Lộ Trình Ra Trường State
  const [targetGradGpaStr, setTargetGradGpaStr] = useState('3.20');
  
  // Tín chỉ còn lại tự động suy ra từ CTĐT và số TC đã tích lũy (không bắt người dùng nhập trùng lặp)
  const remainingCredits = useMemo(() => {
    const total = Number.isFinite(totalDegreeCreditsNum) && totalDegreeCreditsNum > 0 ? totalDegreeCreditsNum : 135;
    const current = Number.isFinite(currentCreditsNum) ? currentCreditsNum : 0;
    return Math.max(1, total - current);
  }, [totalDegreeCreditsNum, currentCreditsNum]);

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
      totalDegreeCreditsNum,
    );
  }, [currentGpaNum, currentCreditsNum, targetGradGpaStr, remainingCredits, totalDegreeCreditsNum]);

  // Handlers for profile updates
  const handleCurrentGpaChange = (val: string) => {
    const clean = sanitizeDecimal(val);
    setProfile((prev) => ({
      currentGpa: clean,
      currentCredits: prev?.currentCredits ?? DEFAULT_PROFILE.currentCredits,
      totalDegreeCredits: prev?.totalDegreeCredits ?? DEFAULT_PROFILE.totalDegreeCredits,
    }));
  };

  const handleCurrentCreditsChange = (val: string) => {
    const clean = sanitizeDecimal(val);
    setProfile((prev) => ({
      currentGpa: prev?.currentGpa ?? DEFAULT_PROFILE.currentGpa,
      currentCredits: clean,
      totalDegreeCredits: prev?.totalDegreeCredits ?? DEFAULT_PROFILE.totalDegreeCredits,
    }));
  };

  const handleTotalDegreeCreditsChange = (val: string) => {
    const clean = sanitizeDecimal(val);
    setProfile((prev) => ({
      currentGpa: prev?.currentGpa ?? DEFAULT_PROFILE.currentGpa,
      currentCredits: prev?.currentCredits ?? DEFAULT_PROFILE.currentCredits,
      totalDegreeCredits: clean,
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
      prev.map((r) => {
        if (r.id !== id) return r;
        if (field === 'oldGrade') {
          const newOld = Number(val);
          // Điểm mục tiêu phải luôn lớn hơn điểm cũ
          const newTarget = r.targetGrade <= newOld ? 4.0 : r.targetGrade;
          return { ...r, oldGrade: newOld, targetGrade: newTarget };
        }
        return { ...r, [field]: val };
      }),
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
    }
  };

  return (
    <div className="page-container tool-page simplified target-gpa-wrapper">
      {/* Standard Clean Page Header (Khớp 100% Hình 2) */}
      <ToolPageHeader
        icon={TrendingUp}
        title="Mục tiêu GPA"
        description="Tính toán chiến lược GPA học kỳ, cải thiện môn và lộ trình tốt nghiệp toàn khóa."
      />

      {/* 2-Column Layout (Tương đồng Hình 2: Trái 63% Thẻ Nhập Liệu, Phải 37% Kết Quả) */}
      <div className="target-gpa-layout-2col">
        {/* CỘT TRÁI: THẺ LIỀN KHỐI (UNIFIED MASTER CARD) */}
        <div className="target-gpa-master-card">
          {/* TOOLBAR TÍCH HỢP ĐẦU THẺ (Khớp 100% Toolbar Hình 2) */}
          <div className="target-gpa-card-toolbar">
            <div className="target-gpa-toolbar-left">
              <span className="target-gpa-toolbar-heading">Thiết lập mục tiêu</span>
              <span className="target-gpa-toolbar-sub">(3 chế độ)</span>
            </div>

            <button
              type="button"
              className="target-gpa-reset-btn"
              onClick={handleReset}
              title="Đặt lại thông số"
              aria-label="Đặt lại thông số"
            >
              <RotateCcw size={14} />
              <span>Đặt lại</span>
            </button>
          </div>

          {/* THÂN THẺ LIỀN MẠCH */}
          <div className="target-gpa-card-body">
            {/* BỘ CHỌN 3 CHẾ ĐỘ (High-Contrast Segmented Switcher) */}
            <div className="target-gpa-tabs-bar" role="tablist" aria-label="Các chế độ tính toán GPA">
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
                ⚡ Cải Thiện Môn
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

            {/* PHẦN 1: ĐIỂM HIỆN TẠI (Dùng chung cho cả 3 chế độ - 3 ô trên 1 hàng gọn gàng) */}
            <div className="target-gpa-section-block">
              <div className="target-gpa-card-title">
                <span>1. Điểm Tích Lũy Hiện Tại</span>
                <span className={`target-gpa-tag-status ${!isProfileValid ? 'empty' : ''}`}>
                  {isProfileValid ? '✓ Đã lưu' : 'Chưa nhập'}
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
                      aria-label="GPA tích lũy hiện tại"
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
                      aria-label="Số tín chỉ đã tích lũy"
                    />
                    <span>TC</span>
                  </div>
                </div>

                <div className="target-gpa-field-item">
                  <label htmlFor="target-total-degree-creds">Tổng TC CTĐT:</label>
                  <div className="target-gpa-input-box">
                    <input
                      id="target-total-degree-creds"
                      type="text"
                      inputMode="numeric"
                      value={totalDegreeCreditsStr}
                      onChange={(e) => handleTotalDegreeCreditsChange(e.target.value)}
                      placeholder="135"
                      aria-label="Tổng số tín chỉ theo chương trình đào tạo"
                    />
                    <span>TC</span>
                  </div>
                </div>
              </div>
            </div>

            {/* PHẦN 2: THÔNG SỐ TÙY CHỌN THEO CHẾ ĐỘ */}
              {activeTab === 'term' && (
                <div className="target-gpa-section-block divider">
                  <div className="target-gpa-card-title">
                    <span>2. Mục Tiêu Học Kỳ Tới</span>
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
                <div className="target-gpa-section-block divider">
                  <div className="target-gpa-card-title">
                    <span>2. Chọn Môn Cải Thiện</span>
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
                              {RETAKE_OLD_GRADES.map((g) => (
                                <option key={g.value} value={g.value}>
                                  {g.label}
                                </option>
                              ))}
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
                              {ALL_TARGET_GRADES.filter((g) => g.value > course.oldGrade).map((g) => (
                                <option key={g.value} value={g.value}>
                                  {g.label}
                                </option>
                              ))}
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
                <div className="target-gpa-section-block divider">
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

                  {/* Tự động tính toán tiến độ dựa trên Mục 1 (không cần nhập trùng lặp) */}
                  <div className="target-gpa-roadmap-auto-calc">
                    <div className="auto-calc-badge">
                      <span className="auto-calc-label">Tín chỉ còn lại</span>
                      <span className="auto-calc-val">
                        {hasEnteredProfile ? `${remainingCredits} TC` : '-- TC'}
                      </span>
                    </div>
                    <div className="auto-calc-badge">
                      <span className="auto-calc-label">Dự kiến hoàn thành</span>
                      <span className="auto-calc-val">
                        {hasEnteredProfile ? `~${roadmapPlan.termsRemaining} học kỳ` : '--'}
                      </span>
                    </div>
                    <div className="auto-calc-badge">
                      <span className="auto-calc-label">Tiến độ tích lũy</span>
                      <span className="auto-calc-val">
                        {hasEnteredProfile && totalDegreeCreditsNum > 0
                          ? `${Math.min(100, Math.round((currentCreditsNum / totalDegreeCreditsNum) * 100))}%`
                          : '--%'}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* CỘT PHẢI: THẺ KẾT QUẢ DỰ TÍNH (STICKY RESULT CARD) */}
          <div className="target-gpa-sticky-col">
            <div className="target-gpa-result-card" id="target-gpa-result">
              {activeTab === 'term' && (
                <>
                  <div className="target-gpa-res-header">
                    <span className="res-title">KẾT QUẢ KỲ TỚI</span>
                    {!hasEnteredProfile ? (
                      <span className="target-gpa-badge-feasible neutral">Chờ nhập liệu</span>
                    ) : termPlan.status === 'achieved' ? (
                      <span className="target-gpa-badge-feasible">✓ Đã Đạt</span>
                    ) : termPlan.status === 'impossible' ? (
                      <span className="target-gpa-badge-feasible danger">✕ Không Khả Thi</span>
                    ) : (
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
                    {!hasEnteredProfile ? (
                      <>
                        <div className="hero-label">GPA HỌC KỲ TỚI CẦN ĐẠT</div>
                        <div className="hero-score score-empty">
                          -- <span>/ 4.00</span>
                        </div>
                        <div className="hero-rank">Vui lòng nhập GPA và số TC ở Mục 1</div>
                      </>
                    ) : termPlan.status === 'achieved' ? (
                      <>
                        <div className="hero-label">GPA TÍCH LŨY HIỆN TẠI</div>
                        <div className="hero-score score-achieved">
                          {format2(currentGpaNum)} <span>/ 4.00</span>
                        </div>
                        <div className="hero-rank">
                          Đã đạt mục tiêu {format2(Number(targetGpaStr) || 3.2)}
                        </div>
                      </>
                    ) : termPlan.status === 'impossible' ? (
                      <>
                        <div className="hero-label">GPA HỌC KỲ TỚI CẦN ĐẠT</div>
                        <div className="hero-score score-impossible">
                          {format2(termPlan.requiredGpa)} <span>/ 4.00</span>
                        </div>
                        <div className="hero-rank error">Vượt quá thang điểm tối đa (4.00)</div>
                      </>
                    ) : (
                      <>
                        <div className="hero-label">GPA HỌC KỲ TỚI CẦN ĐẠT</div>
                        <div
                          className={`hero-score ${
                            termPlan.requiredGpa >= 3.6 ? 'score-warning' : 'score-feasible'
                          }`}
                        >
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
                      {!hasEnteredProfile ? (
                        <div className="target-gpa-badge-grade empty">
                          Chưa có thông tin điểm hiện tại
                        </div>
                      ) : termPlan.status === 'impossible' ? (
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
                    {!hasEnteredProfile ? (
                      <>Nhập GPA và số tín chỉ ở Mục 1 để hệ thống tính toán điểm số cần đạt.</>
                    ) : termPlan.status === 'impossible' ? (
                      <>
                        Mục tiêu vượt 4.00 trong 1 kỳ. Cần tối thiểu{' '}
                        <strong>{termPlan.minCreditsNeeded ?? '> 20'} TC</strong> điểm A toàn bộ.
                      </>
                    ) : termPlan.status === 'achieved' ? (
                      <>GPA hiện tại đã vượt mục tiêu đề ra. Hãy tiếp tục duy trì phong độ kỳ tới.</>
                    ) : (
                      <>
                        Cần đạt tối thiểu{' '}
                        <strong>
                          {prescription.coursesA > 0
                            ? `${prescription.coursesA} môn A`
                            : `${prescription.coursesBPlus} môn B+`}
                        </strong>{' '}
                        trong kỳ tới để chạm mức <strong>{format2(Number(targetGpaStr) || 3.2)}</strong>.
                      </>
                    )}
                  </div>
                </>
              )}

              {activeTab === 'retake' && (
                <>
                  <div className="target-gpa-res-header">
                    <span className="res-title">HIỆU QUẢ CẢI THIỆN</span>
                    {!hasEnteredProfile ? (
                      <span className="target-gpa-badge-feasible neutral">Chờ nhập liệu</span>
                    ) : (
                      <span className="target-gpa-badge-feasible">● Tăng Vọt</span>
                    )}
                  </div>

                  <div className="target-gpa-hero-section">
                    <div className="hero-label">MỨC KÉO ĐIỂM TỰ THÂN</div>
                    {!hasEnteredProfile ? (
                      <>
                        <div className="hero-score score-empty">
                          -- <span>GPA</span>
                        </div>
                        <div className="hero-rank">Vui lòng nhập GPA và số TC ở Mục 1</div>
                      </>
                    ) : (
                      <>
                        <div className="hero-score score-boost">
                          ▲ +{format2(retakePlan.deltaGpa)} <span>GPA</span>
                        </div>
                        <div className="hero-rank">
                          Kéo điểm trực tiếp từ {retakes.length} môn học lại
                        </div>
                      </>
                    )}
                  </div>

                  {!hasEnteredProfile ? (
                    <div className="target-gpa-clean-notice">
                      Chọn các môn cần học lại để dự báo mức tăng điểm GPA tích lũy sau khi cải thiện.
                    </div>
                  ) : (
                    <>
                      {/* Thẻ So Sánh Trực Quan Before -> After (Thoáng đãng, số to rõ ràng) */}
                      <div className="target-gpa-compare-box">
                        <div className="compare-col">
                          <span className="compare-caption">GPA ban đầu</span>
                          <span className="compare-num">{format2(currentGpaNum)}</span>
                        </div>
                        <div className="compare-arrow">➔</div>
                        <div className="compare-col highlight">
                          <span className="compare-caption">GPA sau cải thiện</span>
                          <span className="compare-num boost">{format2(retakePlan.newBaselineGpa)}</span>
                        </div>
                      </div>

                      {/* Thông số quy mô cải thiện */}
                      <div className="target-gpa-retake-stats">
                        <div className="retake-stat-pill">
                          <span>Quy mô:</span>
                          <strong>
                            {retakes.length} môn ({retakes.reduce((sum, r) => sum + r.credits, 0)} TC)
                          </strong>
                        </div>
                        <div className="retake-stat-pill">
                          <span>Cơ chế:</span>
                          <strong>Thay thế điểm cũ</strong>
                        </div>
                      </div>

                      <div className="target-gpa-clean-notice">
                        Điểm mới sẽ ghi đè điểm cũ vào công thức tích lũy mà không làm phát sinh thêm tín chỉ tốt nghiệp.
                      </div>
                    </>
                  )}
                </>
              )}

              {activeTab === 'roadmap' && (
                <>
                  <div className="target-gpa-res-header">
                    <span className="res-title">LỘ TRÌNH DÀI HẠN</span>
                    {!hasEnteredProfile ? (
                      <span className="target-gpa-badge-feasible neutral">Chờ nhập liệu</span>
                    ) : (
                      <span
                        className={`target-gpa-badge-feasible ${
                          roadmapPlan.isFeasible ? '' : 'danger'
                        }`}
                      >
                        {roadmapPlan.isFeasible ? '● Khả Thi' : '✕ Quá Tải'}
                      </span>
                    )}
                  </div>

                  <div className="target-gpa-hero-section">
                    <div className="hero-label">GPA CẦN DUY TRÌ MỖI KỲ</div>
                    {!hasEnteredProfile ? (
                      <>
                        <div className="hero-score score-empty">
                          -- <span>/ 4.00</span>
                        </div>
                        <div className="hero-rank">Vui lòng nhập GPA và số TC ở Mục 1</div>
                      </>
                    ) : (
                      <>
                        <div
                          className={`hero-score ${
                            !roadmapPlan.isFeasible
                              ? 'score-impossible'
                              : roadmapPlan.averageGpaNeeded >= 3.6
                                ? 'score-warning'
                                : 'score-feasible'
                          }`}
                        >
                          {format2(roadmapPlan.averageGpaNeeded)} <span>/ 4.00</span>
                        </div>
                        <div className="hero-rank">
                          Dự kiến còn ~{roadmapPlan.termsRemaining} học kỳ (15 TC/kỳ)
                        </div>
                      </>
                    )}
                  </div>

                  <div className="target-gpa-roadmap-grid">
                    <div className="target-gpa-roadmap-card">
                      <div className="m-title">{roadmapPlan.milestones[0].title}</div>
                      <div className={`m-score ${!hasEnteredProfile ? 'empty' : 'pace'}`}>
                        {hasEnteredProfile ? roadmapPlan.milestones[0].score : '--'}
                      </div>
                      <div className="m-sub">{roadmapPlan.milestones[0].sub}</div>
                    </div>
                    <div className="target-gpa-roadmap-card">
                      <div className="m-title">{roadmapPlan.milestones[1].title}</div>
                      <div className={`m-score ${!hasEnteredProfile ? 'empty' : 'pace'}`}>
                        {hasEnteredProfile ? roadmapPlan.milestones[1].score : '--'}
                      </div>
                      <div className="m-sub">{roadmapPlan.milestones[1].sub}</div>
                    </div>
                    <div className="target-gpa-roadmap-card grad-finish">
                      <div className="m-title">{roadmapPlan.milestones[2].title}</div>
                      <div className={`m-score ${!hasEnteredProfile ? 'empty' : 'finish'}`}>
                        {hasEnteredProfile ? roadmapPlan.milestones[2].score : '--'}
                      </div>
                      <div className="m-sub">{roadmapPlan.milestones[2].sub}</div>
                    </div>
                  </div>

                  <div className="target-gpa-clean-notice">
                    {!hasEnteredProfile ? (
                      <>Nhập thông tin tín chỉ đã tích lũy và số TC CTĐT để vạch ra chiến lược duy trì điểm số mỗi kỳ.</>
                    ) : roadmapPlan.isFeasible ? (
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

              {/* Redesigned Clean Result Card Footer (Thay thế hoàn toàn Hình 4) */}
              <div className="target-gpa-result-footer">
                <div className="target-gpa-footer-pills">
                  <button
                    type="button"
                    className="target-gpa-footer-pill"
                    onClick={() => setReferenceModalTab('scale')}
                    title="Tra cứu bảng quy đổi thang điểm 10, thang điểm 4 và điểm chữ"
                  >
                    <BookOpen size={13} />
                    <span>Bảng quy đổi {cohort}</span>
                    <ExternalLink size={11} className="target-gpa-pill-arrow" />
                  </button>
                  <button
                    type="button"
                    className="target-gpa-footer-pill"
                    onClick={() => setReferenceModalTab('rules')}
                    title="Tra cứu trích dẫn điều khoản quy chế đào tạo tín chỉ"
                  >
                    <FileText size={13} />
                    <span>Quy chế đào tạo</span>
                    <ExternalLink size={11} className="target-gpa-pill-arrow" />
                  </button>
                </div>
                <div className="target-gpa-footer-meta">
                  <span className="target-gpa-meta-note">* Kết quả mang tính tham khảo</span>
                  <span className="target-gpa-meta-school">ĐHSP TP.HCM</span>
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
