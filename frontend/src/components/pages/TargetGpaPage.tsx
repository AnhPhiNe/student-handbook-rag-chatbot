import { useMemo, useState } from 'react';
import { useAnimatedNumber } from '../../hooks/useAnimatedNumber';
import {
  TrendingUp,
  Trash2,
  RotateCcw,
  BookOpen,
  ExternalLink,
  FileText,
  AlertCircle,
  CheckCircle2,
  X,
  Target,
  Zap,
  GraduationCap,
  ArrowRight,
  Hourglass,
} from 'lucide-react';
import { CreditWheelPicker } from './GpaPage';
import { type Cohort } from '../../utils/gradeScale';
import { sanitizeDecimal } from '../../utils/numberInput';
import { useStudentProfile } from '../../hooks/useStudentProfile';
import { hasStoredProfile } from '../../utils/studentProfile';
import { GpaReferenceModal } from '../GpaReferenceModal';
import { ShareResultButton } from '../tool/ShareResultButton';
import { targetRetakeShareText, targetRoadmapShareText, targetTermShareText } from '../../utils/shareText';
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

/** A retake row being edited: the old grade stays empty until the student picks it. */
type RetakeDraft = Omit<RetakeCourse, 'oldGrade'> & { oldGrade: number | null };

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
  const { profile, update: updateProfile, clear: clearProfile } = useStudentProfile();

  const currentGpaStr = profile.currentGpa;
  const currentCreditsStr = profile.currentCredits;
  const totalDegreeCreditsStr = profile.totalDegreeCredits;

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
    (!totalDegreeCreditsStr.trim() ||
      (Number.isFinite(totalDegreeCreditsNum) &&
        totalDegreeCreditsNum >= 50 &&
        totalDegreeCreditsNum <= 300));

  // Tab 1: 1 Học Kỳ Tới State
  const [targetGpaStr, setTargetGpaStr] = useState('');
  const [futureCredits, setFutureCredits] = useState(15);

  // Tab 2: Cải Thiện Môn F/D State
  // A course row has no old grade until the student picks one; only complete rows count.
  const [retakes, setRetakes] = useState<RetakeDraft[]>([]);
  const completeRetakes = useMemo(
    () => retakes.filter((r): r is RetakeCourse => r.oldGrade !== null),
    [retakes],
  );
  const hasRetakeRows = retakes.length > 0;
  const hasRetakes = completeRetakes.length > 0;

  // Tab 3: Lộ Trình Ra Trường State
  const [targetGradGpaStr, setTargetGradGpaStr] = useState('');
  
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
    if (!hasEnteredProfile || !targetGpaStr) {
      return {
        isComplete: false,
        requiredGpa: 0,
        status: 'empty' as const,
        minCreditsNeeded: null,
        totalCredits: 0,
        equivalentLetter: '--',
      };
    }
    return calculateTermPlan(
      currentGpaNum,
      currentCreditsNum,
      Number(targetGpaStr),
      futureCredits,
    );
  }, [hasEnteredProfile, currentGpaNum, currentCreditsNum, targetGpaStr, futureCredits]);

  const prescription = useMemo(() => {
    return getCoursePrescription(termPlan.requiredGpa, futureCredits);
  }, [termPlan.requiredGpa, futureCredits]);

  // Tab 2 Calculations
  const retakePlan = useMemo(() => {
    return calculateRetakeImpact(
      currentGpaNum,
      currentCreditsNum,
      completeRetakes,
      15,
      Number(targetGpaStr) || 3.20,
    );
  }, [currentGpaNum, currentCreditsNum, completeRetakes, targetGpaStr]);

  // Tab 3 Calculations
  const roadmapPlan = useMemo(() => {
    if (!hasEnteredProfile || !targetGradGpaStr) {
      return {
        averageGpaNeeded: 0,
        termsRemaining: Math.max(1, Math.ceil(remainingCredits / 15)),
        isFeasible: true,
        milestones: [],
      };
    }
    return calculateRoadmapPlan(
      currentGpaNum,
      currentCreditsNum,
      Number(targetGradGpaStr),
      remainingCredits,
      totalDegreeCreditsNum,
    );
  }, [hasEnteredProfile, currentGpaNum, currentCreditsNum, targetGradGpaStr, remainingCredits, totalDegreeCreditsNum]);

  // Best possible graduation GPA (every remaining credit an A): shown when the target is out of reach.
  const maxGradGpa =
    totalDegreeCreditsNum > 0
      ? Math.min(4, (currentGpaNum * currentCreditsNum + 4 * Math.max(0, remainingCredits)) / totalDegreeCreditsNum)
      : 0;
  const roadmapNeededLabel = Number.isFinite(roadmapPlan.averageGpaNeeded)
    ? format2(roadmapPlan.averageGpaNeeded)
    : '> 4.00';

  // Plain-text summary of the active tab's result, or null while there is no result to share.
  const shareText = (() => {
    if (!hasEnteredProfile) return null;
    if (activeTab === 'term') {
      if (!termPlan.isComplete || !targetGpaStr || termPlan.status === 'empty') return null;
      return targetTermShareText({
        status: termPlan.status,
        requiredGpa: termPlan.requiredGpa,
        targetGpa: Number(targetGpaStr),
        currentGpa: currentGpaNum,
        cohort,
      });
    }
    if (activeTab === 'retake') {
      if (!hasRetakes) return null;
      return targetRetakeShareText({
        courses: completeRetakes.length,
        credits: completeRetakes.reduce((sum, r) => sum + r.credits, 0),
        baselineGpa: currentGpaNum,
        newGpa: retakePlan.newBaselineGpa,
        deltaGpa: retakePlan.deltaGpa,
        cohort,
      });
    }
    if (!targetGradGpaStr) return null;
    return targetRoadmapShareText({
      feasible: roadmapPlan.isFeasible,
      targetGpa: Number(targetGradGpaStr),
      neededGpa: roadmapPlan.averageGpaNeeded,
      maxGpa: maxGradGpa,
      remainingCredits,
      terms: roadmapPlan.termsRemaining,
      cohort,
    });
  })();

  // Animated Hero Score for Mobile and Desktop
  const activeHeroNumber = useMemo(() => {
    if (activeTab === 'term') {
      if (!termPlan.isComplete || termPlan.status === 'impossible') return 0;
      if (termPlan.status === 'achieved') return currentGpaNum;
      return termPlan.requiredGpa;
    }
    if (activeTab === 'retake') {
      return hasEnteredProfile && hasRetakes ? retakePlan.newBaselineGpa : 0;
    }
    if (activeTab === 'roadmap') {
      if (!hasEnteredProfile || !targetGradGpaStr || !roadmapPlan.isFeasible) return 0;
      return roadmapPlan.averageGpaNeeded;
    }
    return 0;
  }, [activeTab, termPlan, currentGpaNum, hasEnteredProfile, hasRetakes, retakePlan.newBaselineGpa, targetGradGpaStr, roadmapPlan]);

  const animatedHeroScore = useAnimatedNumber(activeHeroNumber, 2);

  // Dynamic Feasibility Aura status for Mobile Hero Card
  const heroStatusClass = useMemo(() => {
    if (activeTab === 'term') {
      if (!termPlan.isComplete) return '';
      if (termPlan.status === 'achieved') return 'status-achieved';
      if (termPlan.status === 'impossible') return 'status-impossible';
      if (termPlan.requiredGpa > 3.5) return 'status-warning';
      return 'status-feasible';
    }
    if (activeTab === 'retake') {
      if (!hasEnteredProfile || !hasRetakes) return '';
      return retakePlan.deltaGpa > 0 ? 'status-achieved' : 'status-feasible';
    }
    if (activeTab === 'roadmap') {
      if (!hasEnteredProfile || !targetGradGpaStr) return '';
      if (!roadmapPlan.isFeasible) return 'status-impossible';
      if (roadmapPlan.averageGpaNeeded > 3.5) return 'status-warning';
      return 'status-feasible';
    }
    return '';
  }, [activeTab, termPlan, hasEnteredProfile, hasRetakes, retakePlan.deltaGpa, targetGradGpaStr, roadmapPlan]);

  // Handlers for profile updates
  const handleCurrentGpaChange = (val: string) => updateProfile({ currentGpa: sanitizeDecimal(val) });
  const handleCurrentCreditsChange = (val: string) => updateProfile({ currentCredits: sanitizeDecimal(val) });
  const handleTotalDegreeCreditsChange = (val: string) => updateProfile({ totalDegreeCredits: sanitizeDecimal(val) });

  const canClearSaved = hasStoredProfile(profile);
  const handleClearSaved = () => {
    if (window.confirm('Xóa GPA, số tín chỉ và các số liệu đã lưu trên máy này?')) {
      clearProfile();
    }
  };

  // Handlers for Tab 2 (Retake Courses)
  const handleAddRetake = () => {
    if (retakes.length >= 6) return;
    const nextId = `retake-${Date.now()}`;
    const nextIdx = retakes.length + 1;
    setRetakes((prev) => [
      ...prev,
      { id: nextId, label: `Môn ${nextIdx}`, oldGrade: null, targetGrade: 4.0, credits: 3 },
    ]);
  };

  const handleRemoveRetake = (id: string) => {
    setRetakes((prev) => prev.filter((r) => r.id !== id));
  };

  const handleUpdateRetake = (id: string, field: keyof RetakeDraft, val: number | string) => {
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

  // Mobile Retake Bottom Sheet State
  interface MobileRetakeSheetState {
    index: number;
    isNew: boolean;
    id: string;
    credits: string;
    oldGrade: number | null;
    targetGrade: number;
  }
  const [mobileRetakeSheet, setMobileRetakeSheet] = useState<MobileRetakeSheetState | null>(null);

  const openEditRetakeSheet = (index: number) => {
    const r = retakes[index];
    if (!r) return;
    setMobileRetakeSheet({
      index,
      isNew: false,
      id: r.id,
      credits: String(r.credits),
      oldGrade: r.oldGrade,
      targetGrade: r.targetGrade,
    });
  };

  const openAddRetakeSheet = () => {
    if (retakes.length >= 6) return;
    setMobileRetakeSheet({
      index: retakes.length,
      isNew: true,
      id: `retake-${Date.now()}`,
      credits: '3',
      oldGrade: null,
      targetGrade: 4.0,
    });
  };

  const handleSaveMobileRetake = () => {
    if (!mobileRetakeSheet || mobileRetakeSheet.oldGrade === null) return;
    const parsedCreds = Math.max(1, Math.min(10, parseInt(mobileRetakeSheet.credits, 10) || 3));
    const oldG = mobileRetakeSheet.oldGrade;
    const targetG = mobileRetakeSheet.targetGrade <= oldG ? 4.0 : mobileRetakeSheet.targetGrade;

    if (mobileRetakeSheet.isNew) {
      setRetakes((prev) => [
        ...prev,
        {
          id: mobileRetakeSheet.id,
          label: `Môn ${prev.length + 1}`,
          oldGrade: oldG,
          targetGrade: targetG,
          credits: parsedCreds,
        },
      ]);
    } else {
      setRetakes((prev) =>
        prev.map((r, i) =>
          i === mobileRetakeSheet.index
            ? { ...r, credits: parsedCreds, oldGrade: oldG, targetGrade: targetG }
            : r,
        ),
      );
    }
    setMobileRetakeSheet(null);
  };

  const handleDeleteMobileRetake = () => {
    if (!mobileRetakeSheet) return;
    setRetakes((prev) => prev.filter((_, i) => i !== mobileRetakeSheet.index));
    setMobileRetakeSheet(null);
  };

  // Handler for Global Reset
  const handleReset = () => {
    if (window.confirm('Bạn có chắc chắn muốn đặt lại các thông số về mặc định không?')) {
      clearProfile();
      setTargetGpaStr('');
      setFutureCredits(15);
      setRetakes([]);
      setTargetGradGpaStr('');
      setMobileRetakeSheet(null);
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

      {/* ============================================================== */}
      {/* DESKTOP 2-COLUMN VIEW (FAITHFUL TO EXISTING DESIGN) */}
      {/* ============================================================== */}
      <div className="target-gpa-desktop-layout">
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
                <Target size={15} aria-hidden="true" />
                <span>1 học kỳ tới</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'retake'}
                className={`target-gpa-tab-item ${activeTab === 'retake' ? 'active' : ''}`}
                onClick={() => setActiveTab('retake')}
              >
                <Zap size={15} aria-hidden="true" />
                <span>Cải thiện môn</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'roadmap'}
                className={`target-gpa-tab-item ${activeTab === 'roadmap' ? 'active' : ''}`}
                onClick={() => setActiveTab('roadmap')}
              >
                <GraduationCap size={15} aria-hidden="true" />
                <span>Lộ trình ra trường</span>
              </button>
            </div>

            {/* PHẦN 1: ĐIỂM HIỆN TẠI (Dùng chung cho cả 3 chế độ - 3 ô trên 1 hàng gọn gàng) */}
            <div className="target-gpa-section-block">
              <div className="target-gpa-card-title">
                <span>1. Điểm tích lũy hiện tại</span>
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
                      placeholder="VD: 2.85"
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
                      placeholder="VD: 60"
                      aria-label="Số tín chỉ đã tích lũy"
                    />
                    <span>TC</span>
                  </div>
                  <span className="target-gpa-field-hint">Tính cả TC môn bị F</span>
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
                      placeholder="VD: 135"
                      aria-label="Tổng số tín chỉ theo chương trình đào tạo"
                    />
                    <span>TC</span>
                  </div>
                </div>
              </div>
              {canClearSaved && (
                <button type="button" className="tool-clear-saved" onClick={handleClearSaved}>
                  <Trash2 size={13} aria-hidden="true" />
                  Xóa dữ liệu đã lưu
                </button>
              )}
            </div>

            {/* PHẦN 2: THÔNG SỐ TÙY CHỌN THEO CHẾ ĐỘ */}
              {activeTab === 'term' && (
                <div className="target-gpa-section-block divider">
                  <div className="target-gpa-card-title">
                    <span>2. Mục tiêu học kỳ tới</span>
                  </div>

                  {/* Slider for Target GPA */}
                  <div className="target-gpa-slider-header">
                    <label htmlFor="target-goal-slider">GPA tích lũy muốn đạt:</label>
                    <div className="target-gpa-slider-val-tag">
                      {targetGpaStr ? format2(Number(targetGpaStr)) : '--'} <span>/ 4.00</span>
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
                    aria-label="Kéo chọn GPA tích lũy muốn đạt"
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
                    <span>2. Chọn môn cải thiện</span>
                  </div>

                  {hasRetakeRows && (
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
                              value={course.label || ''}
                              placeholder={`Môn ${idx + 1}`}
                              onChange={(e) =>
                                handleUpdateRetake(course.id, 'label', e.target.value)
                              }
                              aria-label={`Tên môn ${idx + 1}`}
                            />
                          </td>
                          <td>
                            <select
                              className="target-gpa-select"
                              value={course.oldGrade ?? ''}
                              onChange={(e) =>
                                handleUpdateRetake(course.id, 'oldGrade', Number(e.target.value))
                              }
                              aria-label="Điểm cũ"
                            >
                              <option value="" disabled>
                                Chọn điểm
                              </option>
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
                              {ALL_TARGET_GRADES.filter((g) => g.value > (course.oldGrade ?? -1)).map((g) => (
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
                  )}

                  {retakes.length < 6 && (
                    <button
                      type="button"
                      className="target-gpa-btn-add"
                      onClick={handleAddRetake}
                    >
                      + Thêm môn cải thiện
                    </button>
                  )}
                </div>
              )}

              {activeTab === 'roadmap' && (
                <div className="target-gpa-section-block divider">
                  <div className="target-gpa-card-title">
                    <span>2. Kế hoạch tốt nghiệp</span>
                  </div>

                  {/* Slider for Graduation GPA */}
                  <div className="target-gpa-slider-header">
                    <label htmlFor="target-grad-slider">GPA tốt nghiệp muốn đạt:</label>
                    <div className="target-gpa-slider-val-tag">
                      {targetGradGpaStr ? format2(Number(targetGradGpaStr)) : '--'} <span>/ 4.00</span>
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
                    {!hasEnteredProfile || !targetGpaStr ? (
                      <span className="target-gpa-badge-feasible neutral">Chờ nhập liệu</span>
                    ) : termPlan.status === 'achieved' ? (
                      <span className="target-gpa-badge-feasible">✓ Đã đạt</span>
                    ) : termPlan.status === 'impossible' ? (
                      <span className="target-gpa-badge-feasible danger">✕ Không khả thi</span>
                    ) : (
                      <span
                        className={`target-gpa-badge-feasible ${
                          termPlan.requiredGpa >= 3.6 ? 'warning' : ''
                        }`}
                      >
                        {termPlan.requiredGpa >= 3.6 ? '▲ Rất khó' : '● Khả thi'}
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
                    ) : !targetGpaStr ? (
                      <>
                        <div className="hero-label">GPA HỌC KỲ TỚI CẦN ĐẠT</div>
                        <div className="hero-score score-empty">
                          -- <span>/ 4.00</span>
                        </div>
                        <div className="hero-rank">Vui lòng chọn mức GPA tích lũy muốn đạt ở Mục 2</div>
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

                  {!hasEnteredProfile ? (
                    <div className="target-gpa-empty-hint">
                      Nhập điểm tích lũy và số TC ở Mục 1 để nhận phân bổ chi tiết.
                    </div>
                  ) : !targetGpaStr ? (
                    <div className="target-gpa-empty-hint">
                      Chọn mức GPA tích lũy muốn đạt ở Mục 2 để nhận phân bổ môn học.
                    </div>
                  ) : termPlan.status === 'impossible' ? (
                    <div className="target-gpa-callout-impossible">
                      <AlertCircle size={15} className="callout-icon" />
                      <span>
                        Cần tích lũy tối thiểu <strong>{termPlan.minCreditsNeeded ?? '> 20'} TC</strong> điểm A toàn bộ để đạt mục tiêu này.
                      </span>
                    </div>
                  ) : termPlan.status === 'achieved' ? (
                    <div className="target-gpa-callout-achieved">
                      <CheckCircle2 size={15} className="callout-icon" />
                      <span>Điểm tích lũy hiện tại đã đạt hoặc vượt mục tiêu này.</span>
                    </div>
                  ) : (
                    <div className="target-gpa-presc-section">
                      <div className="target-gpa-presc-title">
                        <span>Phân bổ mục tiêu ({futureCredits} TC ~ {prescription.totalCourses} môn):</span>
                      </div>
                      <div className="target-gpa-presc-badges">
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
                      </div>
                    </div>
                  )}
                </>
              )}

              {activeTab === 'retake' && (
                <>
                  <div className="target-gpa-res-header">
                    <span className="res-title">HIỆU QUẢ CẢI THIỆN</span>
                    {!hasEnteredProfile || !hasRetakes ? (
                      <span className="target-gpa-badge-feasible neutral">Chờ nhập liệu</span>
                    ) : (
                      <span className="target-gpa-badge-feasible">● Tăng vọt</span>
                    )}
                  </div>

                  <div className="target-gpa-hero-section">
                    <div className="hero-label">MỨC KÉO ĐIỂM TỰ THÂN</div>
                    {!hasEnteredProfile || !hasRetakes ? (
                      <>
                        <div className="hero-score score-empty">
                          -- <span>GPA</span>
                        </div>
                        <div className="hero-rank">
                          {!hasEnteredProfile
                            ? 'Vui lòng nhập GPA và số TC ở Mục 1'
                            : hasRetakeRows
                              ? 'Chọn điểm cũ của môn cải thiện ở Mục 2'
                              : 'Thêm ít nhất một môn cải thiện ở Mục 2'}
                        </div>
                      </>
                    ) : (
                      <div className="hero-score score-boost">
                        ▲ +{format2(retakePlan.deltaGpa)} <span>GPA</span>
                      </div>
                    )}
                  </div>

                  {!hasEnteredProfile || !hasRetakes ? (
                    <div className="target-gpa-empty-hint">
                      Chọn môn và điểm cải thiện để xem GPA tăng thêm.
                    </div>
                  ) : (
                    <>
                      {/* Thẻ So Sánh Trực Quan Before -> After (Thoáng đãng, số to rõ ràng) */}
                      <div className="target-gpa-compare-box">
                        <div className="compare-col">
                          <span className="compare-caption">GPA ban đầu</span>
                          <span className="compare-num">{format2(currentGpaNum)}</span>
                        </div>
                        <div className="compare-arrow">
                          <ArrowRight size={20} aria-hidden="true" />
                        </div>
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
                    </>
                  )}
                </>
              )}

              {activeTab === 'roadmap' && (
                <>
                  <div className="target-gpa-res-header">
                    <span className="res-title">LỘ TRÌNH DÀI HẠN</span>
                    {!hasEnteredProfile || !targetGradGpaStr ? (
                      <span className="target-gpa-badge-feasible neutral">Chờ nhập liệu</span>
                    ) : (
                      <span
                        className={`target-gpa-badge-feasible ${
                          roadmapPlan.isFeasible ? '' : 'danger'
                        }`}
                      >
                        {roadmapPlan.isFeasible ? '● Khả thi' : '✕ Quá tải'}
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
                    ) : !targetGradGpaStr ? (
                      <>
                        <div className="hero-score score-empty">
                          -- <span>/ 4.00</span>
                        </div>
                        <div className="hero-rank">Vui lòng chọn GPA tốt nghiệp muốn đạt ở Mục 2</div>
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
                          {roadmapNeededLabel} <span>/ 4.00</span>
                        </div>
                        <div className="hero-rank">
                          {!roadmapPlan.isFeasible ? (
                            <>Cao nhất khi ra trường: <strong>{format2(maxGradGpa)}</strong></>
                          ) : (
                            <>
                          Tương đương mức điểm chữ:{' '}
                          {roadmapPlan.averageGpaNeeded >= 3.6
                            ? 'A / B+'
                            : roadmapPlan.averageGpaNeeded >= 3.2
                              ? 'B+'
                              : roadmapPlan.averageGpaNeeded >= 2.5
                                ? 'B'
                                : 'C+'}
                            </>
                          )}
                        </div>
                      </>
                    )}
                  </div>

                  {/* Thanh Tiến Độ Tích Lũy Trực Quan */}
                  <div className="target-gpa-progress-section">
                    <div className="progress-header">
                      <span>
                        Đã học:{' '}
                        <strong>
                          {hasEnteredProfile
                            ? `${currentCreditsNum} / ${totalDegreeCreditsNum} TC`
                            : '-- / -- TC'}
                        </strong>
                      </span>
                      <span className="progress-pct">
                        {hasEnteredProfile && totalDegreeCreditsNum > 0
                          ? `${Math.min(100, Math.round((currentCreditsNum / totalDegreeCreditsNum) * 100))}%`
                          : '0%'}
                      </span>
                    </div>
                    <div className="progress-track">
                      <div
                        className="progress-fill"
                        style={{
                          width:
                            hasEnteredProfile && totalDegreeCreditsNum > 0
                              ? `${Math.min(100, Math.round((currentCreditsNum / totalDegreeCreditsNum) * 100))}%`
                              : '0%',
                        }}
                      />
                    </div>
                  </div>

                  {/* Thẻ Tóm Tắt Kế Hoạch 2 Cột (Gọn gàng, không ngắt dòng) */}
                  <div className="target-gpa-roadmap-snapshot">
                    <div className="snapshot-box">
                      <span className="snapshot-label">Còn lại</span>
                      <strong className="snapshot-val">
                        {hasEnteredProfile ? `${remainingCredits} TC` : '-- TC'}
                        <span className="snapshot-sub">
                          {hasEnteredProfile ? `~${roadmapPlan.termsRemaining} học kỳ` : '--'}
                        </span>
                      </strong>
                    </div>
                    <div className="snapshot-box">
                      <span className="snapshot-label">Mục tiêu</span>
                      <strong className="snapshot-val finish">
                        {targetGradGpaStr
                          ? Number(targetGradGpaStr) >= 3.6
                            ? 'Xuất sắc'
                            : Number(targetGradGpaStr) >= 3.2
                              ? 'Bằng Giỏi'
                              : 'Bằng Khá'
                          : '--'}
                        <span className="snapshot-sub">
                          GPA ≥ {targetGradGpaStr ? format2(Number(targetGradGpaStr)) : '--'}
                        </span>
                      </strong>
                    </div>
                  </div>

                  {hasEnteredProfile && !roadmapPlan.isFeasible && (
                    <div className="target-gpa-callout-impossible">
                      <AlertCircle size={15} className="callout-icon" />
                      <span>Mục tiêu vượt 4.00. Cần học cải thiện môn ở Tab 2 để giảm áp lực.</span>
                    </div>
                  )}
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
                  <ShareResultButton text={shareText} className="target-gpa-footer-pill" />
                </div>
                <div className="target-gpa-footer-meta">
                  <span className="target-gpa-meta-note">* Kết quả mang tính tham khảo</span>
                  <span className="target-gpa-meta-school">ĐHSP TP.HCM</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ============================================================== */}
      {/* MOBILE NATIVE LAYOUT (PHƯƠNG ÁN A: ĐỒNG BỘ 100% GPAPAGE) */}
      {/* ============================================================== */}
      <div className="target-gpa-mobile-layout">
        {/* Header di động chuẩn GpaPage (Bỏ nút Đặt lại trơ trọi ở đầu trang) */}
        <div className="gpa-m-page-header">
          <div className="gpa-m-title-wrap">
            <TrendingUp size={20} className="gpa-m-title-icon" aria-hidden="true" />
            <h1 className="gpa-m-page-title">Mục tiêu GPA</h1>
          </div>
        </div>

        {/* Hero Score Card */}
        <div className="gpa-mobile-hero-container">
          <div className={`gpa-mobile-hero-card ${heroStatusClass}`}>
            <span className="target-m-hero-sublabel">
              {activeTab === 'term'
                ? termPlan.status === 'achieved'
                  ? 'GPA TÍCH LŨY HIỆN TẠI'
                  : 'GPA HỌC KỲ TỚI CẦN ĐẠT'
                : activeTab === 'retake'
                  ? 'GPA DỰ KIẾN SAU CẢI THIỆN'
                  : 'GPA MỖI KỲ CẦN ĐẠT'}
            </span>

            <div className="gpa-m-score-row">
              <span className="gpa-m-score-val">
                {activeTab === 'term'
                  ? termPlan.isComplete
                    ? termPlan.status === 'impossible'
                      ? format2(termPlan.requiredGpa)
                      : animatedHeroScore.toFixed(2)
                    : '--'
                  : activeTab === 'retake'
                    ? hasEnteredProfile && hasRetakes
                      ? animatedHeroScore.toFixed(2)
                      : '--'
                    : hasEnteredProfile && targetGradGpaStr
                      ? roadmapPlan.isFeasible
                        ? animatedHeroScore.toFixed(2)
                        : roadmapNeededLabel
                      : '--'}
              </span>
              <span className="gpa-m-score-max">/ 4.00</span>
            </div>

            {/* Capsule Pill */}
            <div className="gpa-m-capsule-wrap">
              {activeTab === 'term' ? (
                !termPlan.isComplete ? (
                  <div className="gpa-m-capsule empty">
                    <span>Nhập mục tiêu học kỳ để tính</span>
                  </div>
                ) : termPlan.status === 'achieved' ? (
                  <div className="gpa-m-capsule">
                    <span className="gpa-m-tier-badge">✓ Đã đạt</span>
                    <span className="gpa-m-sep">│</span>
                    <span className="gpa-m-creds">Mục tiêu {targetGpaStr || '3.20'}</span>
                  </div>
                ) : termPlan.status === 'feasible' ? (
                  <div className="gpa-m-capsule">
                    <span className="gpa-m-tier-badge">Mục tiêu {targetGpaStr}</span>
                    <span className="gpa-m-sep">│</span>
                    <span className="gpa-m-creds">Điểm chữ {termPlan.equivalentLetter}</span>
                  </div>
                ) : (
                  <div className="gpa-m-capsule">
                    <span className="gpa-m-tier-badge tier-danger">✕ Không khả thi</span>
                  </div>
                )
              ) : activeTab === 'retake' ? (
                hasEnteredProfile && hasRetakes ? (
                  <div className="gpa-m-capsule">
                    <span className="gpa-m-tier-badge">
                      +{format2(retakePlan.deltaGpa)} GPA
                    </span>
                    <span className="gpa-m-sep">│</span>
                    <span className="gpa-m-creds">{retakes.length} môn cải thiện</span>
                  </div>
                ) : (
                  <div className="gpa-m-capsule empty">
                    <span>{!hasEnteredProfile ? 'Nhập điểm tích lũy ở mục 1' : hasRetakeRows ? 'Chọn điểm cũ của môn bên dưới' : 'Thêm môn cải thiện bên dưới'}</span>
                  </div>
                )
              ) : (
                /* roadmap */
                !hasEnteredProfile || !targetGradGpaStr ? (
                  <div className="gpa-m-capsule empty">
                    <span>Nhập mục tiêu ra trường để tính</span>
                  </div>
                ) : roadmapPlan.isFeasible ? (
                  <div className="gpa-m-capsule">
                    <span className="gpa-m-tier-badge">
                      {Number(targetGradGpaStr) >= 3.6
                        ? 'Xuất sắc'
                        : Number(targetGradGpaStr) >= 3.2
                          ? 'Giỏi'
                          : 'Khá'}
                    </span>
                    <span className="gpa-m-sep">│</span>
                    <span className="gpa-m-creds">~{roadmapPlan.termsRemaining} kỳ nữa</span>
                  </div>
                ) : (
                  <div className="gpa-m-capsule">
                    <span className="gpa-m-tier-badge tier-danger">✕ Không khả thi</span>
                    <span className="gpa-m-sep">│</span>
                    <span className="gpa-m-creds">Cao nhất khi ra trường: {format2(maxGradGpa)}</span>
                  </div>
                )
              )}
            </div>
            <ShareResultButton text={shareText} className="tool-share-hero" />
          </div>

          {/* Standalone Alert Banner outside Hero Card */}
          {activeTab === 'term' && termPlan.isComplete && termPlan.status === 'impossible' && (
            <div className="target-m-alert-banner" role="alert">
              <AlertCircle size={16} className="target-m-alert-icon" />
              <div>
                Mục tiêu vượt quá 4.00! Với {futureCredits} tín chỉ, bạn cần tích lũy tối thiểu{' '}
                <strong>{termPlan.minCreditsNeeded} TC</strong> hoặc hạ mục tiêu GPA xuống.
              </div>
            </div>
          )}

          {activeTab === 'roadmap' && hasEnteredProfile && targetGradGpaStr && !roadmapPlan.isFeasible && (
            <div className="target-m-alert-banner" role="alert">
              <AlertCircle size={16} className="target-m-alert-icon" />
              <div>
                Mục tiêu tốt nghiệp {targetGradGpaStr} đòi hỏi GPA mỗi kỳ &gt; 4.00. Hãy cân nhắc học cải thiện các môn F/D ở Tab &quot;Cải thiện&quot; để tăng điểm nền.
              </div>
            </div>
          )}
        </div>

        {/* Toolbar thiết lập mục tiêu (Đồng bộ vị trí với Desktop & GpaPage) */}
        <div className="target-m-toolbar">
          <span className="target-m-toolbar-heading">Thiết lập mục tiêu</span>
          <button
            type="button"
            className="target-m-reset-btn"
            onClick={handleReset}
            title="Đặt lại thông số về mặc định"
            aria-label="Đặt lại thông số"
          >
            <RotateCcw size={12} />
            <span>Đặt lại</span>
          </button>
        </div>

        {/* 3-Tab Segmented Switcher */}
        <div className="target-m-tab-switcher" role="tablist" aria-label="Bộ chọn chế độ tính toán GPA">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'term'}
            className={`target-m-tab-btn ${activeTab === 'term' ? 'active' : ''}`}
            onClick={() => setActiveTab('term')}
          >
            <Target size={14} aria-hidden="true" />
            <span>Kỳ tới</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'retake'}
            className={`target-m-tab-btn ${activeTab === 'retake' ? 'active' : ''}`}
            onClick={() => setActiveTab('retake')}
          >
            <Zap size={14} aria-hidden="true" />
            <span>Cải thiện</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'roadmap'}
            className={`target-m-tab-btn ${activeTab === 'roadmap' ? 'active' : ''}`}
            onClick={() => setActiveTab('roadmap')}
          >
            <GraduationCap size={14} aria-hidden="true" />
            <span>Tốt nghiệp</span>
          </button>
        </div>

        {/* Card 1: Điểm Tích Lũy Hiện Tại (Dùng chung cho cả 3 tabs) */}
        <div className="target-m-card">
          <div className="target-m-card-header">
            <span className="target-m-card-title">
              <span className="target-m-badge-num">1</span>
              Điểm tích lũy hiện tại
            </span>
            <span className={`target-m-badge-saved ${!isProfileValid ? 'empty' : ''}`}>
              {isProfileValid ? '✓ Đã lưu' : 'Chưa nhập'}
            </span>
          </div>

          <div className="target-m-grid-3">
            <div>
              <label className="target-m-field-label" htmlFor="m-curr-gpa">GPA tích lũy</label>
              <div className="target-m-input-box">
                <input
                  id="m-curr-gpa"
                  type="text"
                  inputMode="decimal"
                  value={currentGpaStr}
                  onChange={(e) => handleCurrentGpaChange(e.target.value)}
                  placeholder="VD: 2.85"
                  className="target-m-input"
                  aria-label="GPA tích lũy hiện tại"
                />
                <span className="target-m-unit">/4</span>
              </div>
            </div>

            <div>
              <label className="target-m-field-label" htmlFor="m-curr-creds">Đã tích lũy</label>
              <div className="target-m-input-box">
                <input
                  id="m-curr-creds"
                  type="text"
                  inputMode="numeric"
                  value={currentCreditsStr}
                  onChange={(e) => handleCurrentCreditsChange(e.target.value)}
                  placeholder="VD: 60"
                  className="target-m-input"
                  aria-label="Số tín chỉ đã tích lũy"
                />
                <span className="target-m-unit">TC</span>
              </div>
            </div>

            <div>
              <label className="target-m-field-label" htmlFor="m-total-degree">Tổng CTĐT</label>
              <div className="target-m-input-box">
                <input
                  id="m-total-degree"
                  type="text"
                  inputMode="numeric"
                  value={totalDegreeCreditsStr}
                  onChange={(e) => handleTotalDegreeCreditsChange(e.target.value)}
                  placeholder="VD: 135"
                  className="target-m-input"
                  aria-label="Tổng tín chỉ chương trình đào tạo"
                />
                <span className="target-m-unit">TC</span>
              </div>
            </div>
          </div>
          <div className="target-m-field-hint">Đã tích lũy: tính cả TC môn bị F</div>
          {canClearSaved && (
            <button type="button" className="tool-clear-saved" onClick={handleClearSaved}>
              <Trash2 size={13} aria-hidden="true" />
              Xóa dữ liệu đã lưu
            </button>
          )}
        </div>

        {/* Content Container với chuyển cảnh êm ái */}
        <div key={activeTab} className="target-m-tab-content">
        {/* Tab 1 Content: Mục tiêu học kỳ tới */}
        {activeTab === 'term' && (
          <div className="target-m-card">
            <div className="target-m-card-header">
              <span className="target-m-card-title">
                <span className="target-m-badge-num">2</span>
                Mục tiêu học kỳ tới
              </span>
              <div className="target-m-target-display">
                <span className="target-m-target-num">{targetGpaStr || '3.20'}</span>
                <span className="target-m-target-max">/ 4.00</span>
              </div>
            </div>

            {/* GPA Slider */}
            <input
              type="range"
              min="2.00"
              max="4.00"
              step="0.05"
              value={targetGpaStr || '3.20'}
              onChange={(e) => setTargetGpaStr(e.target.value)}
              className="target-m-slider"
              aria-label="Thanh trượt chọn GPA tích lũy muốn đạt"
            />

            {/* 3 Presets */}
            <div className="target-m-preset-grid">
              {TARGET_PRESETS.map((preset) => {
                const isActive = targetGpaStr === preset.value;
                return (
                  <button
                    key={preset.value}
                    type="button"
                    className={`target-m-preset-btn ${isActive ? 'active' : ''}`}
                    onClick={() => setTargetGpaStr(preset.value)}
                  >
                    {preset.label} ({preset.value})
                  </button>
                );
              })}
            </div>

            {/* Stepper Tín chỉ */}
            <div className="target-m-stepper-row">
              <span className="target-m-stepper-label">Tín chỉ kỳ tới:</span>
              <div className="target-m-stepper">
                <button
                  type="button"
                  className="target-m-stepper-btn"
                  onClick={() => setFutureCredits((prev) => Math.max(3, prev - 1))}
                  aria-label="Giảm 1 tín chỉ"
                >
                  −
                </button>
                <span className="target-m-stepper-val">{futureCredits} TC</span>
                <button
                  type="button"
                  className="target-m-stepper-btn"
                  onClick={() => setFutureCredits((prev) => Math.min(30, prev + 1))}
                  aria-label="Tăng 1 tín chỉ"
                >
                  +
                </button>
              </div>
            </div>

            {/* Quick Credit Pills (Chuẩn công thái học 1-chạm) */}
            <div className="target-m-quick-creds-row">
              {TERM_CREDIT_PRESETS.map((cr) => (
                <button
                  key={cr}
                  type="button"
                  className={`target-m-quick-cred-btn ${futureCredits === cr ? 'active' : ''}`}
                  onClick={() => setFutureCredits(cr)}
                >
                  {cr} TC
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Tab 2 Content: Cải thiện môn F/D */}
        {activeTab === 'retake' && (
          <div>
            <div className="target-m-retake-header">
              <span className="target-m-retake-count">
                Môn học cải thiện ({retakes.length})
              </span>
              {retakes.length > 0 && (
                <span className="target-m-retake-hint">
                  Chạm dòng để sửa hoặc xóa
                </span>
              )}
            </div>

            <div className="gpa-mobile-grouped-list">
              <div className="gpa-m-list-card">
                {retakes.map((course, idx) => {
                  const oldGradeObj = RETAKE_OLD_GRADES.find((g) => g.value === course.oldGrade);
                  const targetGradeObj = ALL_TARGET_GRADES.find((g) => g.value === course.targetGrade);
                  const oldLabel = course.oldGrade === null ? 'chưa chọn' : oldGradeObj?.label || `${course.oldGrade}`;
                  const targetLabel = targetGradeObj?.label || `${course.targetGrade}`;

                  return (
                    <div
                      key={course.id}
                      className="gpa-m-list-row cursor-pointer"
                      onClick={() => openEditRetakeSheet(idx)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          openEditRetakeSheet(idx);
                        }
                      }}
                      aria-label={`Chỉnh sửa môn học ${idx + 1}`}
                    >
                      <div className="gpa-m-row-left">
                        <span className="gpa-m-row-title">Môn học {idx + 1}</span>
                        <span className="gpa-m-row-desc">
                          {course.credits} tín chỉ • Điểm cũ:{' '}
                          <strong style={{ color: 'var(--text-secondary)' }}>{oldLabel}</strong>
                        </span>
                      </div>

                      <div className="gpa-m-row-right">
                        <span className="target-m-course-target-pill">
                          <span>Mục tiêu:</span>
                          <strong>{targetLabel}</strong>
                        </span>
                        <span className="gpa-m-row-chevron">›</span>
                      </div>
                    </div>
                  );
                })}

                {retakes.length < 6 && (
                  <button
                    type="button"
                    className="gpa-m-add-row-btn"
                    onClick={openAddRetakeSheet}
                    aria-label="Thêm môn cải thiện"
                  >
                    <span>+ Thêm môn cải thiện</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Tab 3 Content: Lộ trình ra trường */}
        {activeTab === 'roadmap' && (
          <div className="target-m-card">
            <div className="target-m-card-header">
              <span className="target-m-card-title">
                <span className="target-m-badge-num">2</span>
                Mục tiêu tốt nghiệp
              </span>
              <div className="target-m-target-display">
                <span className="target-m-target-num">{targetGradGpaStr || '3.20'}</span>
                <span className="target-m-target-max">/ 4.00</span>
              </div>
            </div>

            {/* 3 Presets */}
            <div className="target-m-preset-grid">
              {TARGET_PRESETS.map((preset) => {
                const isActive = targetGradGpaStr === preset.value;
                return (
                  <button
                    key={preset.value}
                    type="button"
                    className={`target-m-preset-btn ${isActive ? 'active' : ''}`}
                    onClick={() => setTargetGradGpaStr(preset.value)}
                  >
                    {preset.label} ({preset.value})
                  </button>
                );
              })}
            </div>

            {/* Slider GPA */}
            <div style={{ marginTop: '0.4rem', marginBottom: '0.6rem' }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '0.7rem',
                  color: 'var(--text-muted)',
                  fontWeight: 600,
                  marginBottom: '0.25rem',
                }}
              >
                <span>Kéo tinh chỉnh GPA:</span>
                <span style={{ color: 'var(--brand-primary, #0f294a)', fontWeight: 700 }}>
                  2.00 <ArrowRight size={11} aria-hidden="true" style={{ verticalAlign: '-1px' }} /> 4.00
                </span>
              </div>
              <input
                type="range"
                min="2.00"
                max="4.00"
                step="0.05"
                value={targetGradGpaStr || '3.20'}
                onChange={(e) => setTargetGradGpaStr(e.target.value)}
                className="target-m-slider"
                aria-label="Thanh trượt chọn GPA mục tiêu tốt nghiệp"
              />
            </div>

            {/* Clean 1-Line Progress Summary */}
            <div className="target-m-summary-line">
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontWeight: 600 }}>
                <Hourglass size={13} aria-hidden="true" /> Còn lại:{' '}
                <strong style={{ color: 'var(--text-primary)', fontWeight: 800 }}>
                  {hasEnteredProfile ? `${remainingCredits} TC` : '-- TC'}
                </strong>
              </span>
              <span className="target-m-summary-tag">
                {hasEnteredProfile ? `~${roadmapPlan.termsRemaining} học kỳ (15 TC/kỳ)` : '--'}
              </span>
            </div>
          </div>
        )}

        </div>

        {/* Clean 1-Line Mobile Footer */}
        <div className="target-m-footer-note">
          * Kết quả tính toán theo Quy chế đào tạo tín chỉ ĐHSP TP.HCM
        </div>
      </div>

      {/* ============================================================== */}
      {/* MOBILE 1-TOUCH BOTTOM SHEET EDITOR (PHƯƠNG ÁN A: DROPDOWN ĐẦY ĐỦ) */}
      {/* ============================================================== */}
      {mobileRetakeSheet && (
        <div className="gpa-m-sheet-overlay" onClick={() => setMobileRetakeSheet(null)}>
          <div
            className="gpa-m-sheet-container"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="target-sheet-title"
          >
            {/* Grab Handle */}
            <div className="gpa-m-sheet-handle-bar">
              <div className="gpa-m-sheet-handle" />
            </div>

            {/* Header */}
            <div className="gpa-m-sheet-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Zap size={16} aria-hidden="true" />
                <h3 id="target-sheet-title" className="gpa-m-sheet-title">
                  Môn học {mobileRetakeSheet.index + 1}
                </h3>
              </div>
              <button
                type="button"
                className="gpa-m-sheet-close-btn"
                onClick={() => setMobileRetakeSheet(null)}
                aria-label="Đóng bảng chỉnh sửa"
              >
                <X size={18} />
              </button>
            </div>

            {/* Sheet Body */}
            <div className="gpa-m-sheet-body">
              {/* 1. Số tín chỉ: Wheel Picker */}
              <div className="gpa-m-sheet-field">
                <div className="gpa-m-sheet-label-row">
                  <span id="target-sheet-credits-label" className="gpa-m-sheet-label">1. Số tín chỉ</span>
                  <span className="gpa-m-sheet-hint">
                    {mobileRetakeSheet.credits || '3'} tín chỉ
                  </span>
                </div>
                <CreditWheelPicker
                  labelledBy="target-sheet-credits-label"
                  value={mobileRetakeSheet.credits}
                  onChange={(val) =>
                    setMobileRetakeSheet((s) => (s ? { ...s, credits: val } : null))
                  }
                />
              </div>

              {/* 2. Chuyển đổi điểm số: Dual Dropdown (Phương Án A) */}
              <div className="gpa-m-sheet-field">
                <label className="gpa-m-sheet-label">
                  2. Chuyển đổi điểm số (Đầy đủ 8 mốc)
                </label>
                <div className="target-m-dual-select">
                  {/* Điểm cũ */}
                  <div className="target-m-select-box">
                    <span className="target-m-select-label">Điểm cũ</span>
                    <select
                      className="target-m-native-select"
                      value={mobileRetakeSheet.oldGrade ?? ''}
                      onChange={(e) => {
                        const newOld = Number(e.target.value);
                        setMobileRetakeSheet((s) => {
                          if (!s) return null;
                          const newTarget = s.targetGrade <= newOld ? 4.0 : s.targetGrade;
                          return { ...s, oldGrade: newOld, targetGrade: newTarget };
                        });
                      }}
                      aria-label="Chọn điểm cũ"
                    >
                      <option value="" disabled>
                        Chọn
                      </option>
                      {RETAKE_OLD_GRADES.map((g) => (
                        <option key={g.value} value={g.value}>
                          {g.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Mũi tên */}
                  <div className="target-m-select-arrow" aria-hidden="true">
                    <ArrowRight size={14} />
                  </div>

                  {/* Mục tiêu */}
                  <div className="target-m-select-box target">
                    <span className="target-m-select-label">Mục tiêu</span>
                    <select
                      className="target-m-native-select"
                      value={mobileRetakeSheet.targetGrade}
                      onChange={(e) => {
                        const newTarget = Number(e.target.value);
                        setMobileRetakeSheet((s) => (s ? { ...s, targetGrade: newTarget } : null));
                      }}
                      aria-label="Chọn điểm mục tiêu"
                    >
                      {ALL_TARGET_GRADES.map((g) => (
                        <option
                          key={g.value}
                          value={g.value}
                          disabled={g.value <= (mobileRetakeSheet.oldGrade ?? -1)}
                        >
                          {g.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="gpa-m-sheet-actions">
                <button
                  type="button"
                  className={`gpa-m-sheet-save-btn ${mobileRetakeSheet.oldGrade === null ? 'disabled' : ''}`}
                  onClick={handleSaveMobileRetake}
                  disabled={mobileRetakeSheet.oldGrade === null}
                >
                  {mobileRetakeSheet.isNew ? 'Thêm học phần' : 'Lưu thay đổi'}
                </button>

                {!mobileRetakeSheet.isNew && (
                  <button
                    type="button"
                    className="gpa-m-sheet-del-btn"
                    onClick={handleDeleteMobileRetake}
                  >
                    <Trash2 size={16} />
                    <span>Xóa môn này</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      <GpaReferenceModal
        isOpen={referenceModalTab !== null}
        onClose={() => setReferenceModalTab(null)}
        cohort={cohort}
        initialTab={referenceModalTab ?? 'scale'}
      />
    </div>
  );
}
