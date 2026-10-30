import { useMemo, useState } from 'react';
import { useAnimatedNumber } from '../../hooks/useAnimatedNumber';
import {
  TrendingUp,
  Trash2,
  RotateCcw,
  BookOpen,
  ArrowUpRight,
  FileText,
  Plus,
  X,
  ArrowRight,
} from 'lucide-react';
import { CreditWheelPicker } from './GpaPage';
import { type Cohort } from '../../utils/gradeScale';
import { sanitizeDecimal } from '../../utils/numberInput';
import { useStudentProfile } from '../../hooks/useStudentProfile';
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

/** A retake row being edited */
type RetakeDraft = Omit<RetakeCourse, 'oldGrade'> & { oldGrade: number | null };

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

export function TargetGpaPage({ cohort = 'K49' }: TargetGpaPageProps) {
  // Tab Navigation
  const [activeTab, setActiveTab] = useState<TabType>('term');

  // Shared Profile State across all tabs (persisted in localStorage via useStudentProfile)
  const { profile, update: updateProfile, clear: clearProfile } = useStudentProfile();

  const currentGpaStr = profile.currentGpa;
  const currentCreditsStr = profile.currentCredits;
  const totalDegreeCreditsStr = profile.totalDegreeCredits;

  const currentGpaNum = Number(currentGpaStr);
  const currentCreditsNum = Number(currentCreditsStr);
  const totalDegreeCreditsNum = Number(totalDegreeCreditsStr) || 122;

  const hasEnteredProfile =
    currentGpaStr.trim() !== '' &&
    currentCreditsStr.trim() !== '' &&
    Number.isFinite(currentGpaNum) &&
    currentGpaNum >= 0 &&
    currentGpaNum <= 4.0 &&
    Number.isFinite(currentCreditsNum) &&
    currentCreditsNum >= 0 &&
    currentCreditsNum <= 250;

  // Tab 1: 1 Học Kỳ Tới State
  const [targetGpaStr, setTargetGpaStr] = useState('3.60');
  const [futureCredits, setFutureCredits] = useState(15);

  // Tab 2: Cải Thiện Môn State (mặc định 2 dòng môn học)
  const [retakes, setRetakes] = useState<RetakeDraft[]>(() => [
    { id: 'retake-1', label: 'Môn học 1', oldGrade: 1.0, targetGrade: 4.0, credits: 3 },
    { id: 'retake-2', label: 'Môn học 2', oldGrade: 2.0, targetGrade: 4.0, credits: 3 },
  ]);

  const completeRetakes = useMemo(
    () => retakes.filter((r): r is RetakeCourse => r.oldGrade !== null),
    [retakes],
  );
  const hasRetakes = completeRetakes.length > 0;

  // Tab 3: Lộ Trình Ra Trường State
  const [targetGradGpaStr, setTargetGradGpaStr] = useState('3.60');

  // Tín chỉ còn lại tự động suy ra từ CTĐT và số TC đã tích lũy
  const remainingCredits = useMemo(() => {
    const total = Number.isFinite(totalDegreeCreditsNum) && totalDegreeCreditsNum > 0 ? totalDegreeCreditsNum : 122;
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

  const maxGradGpa =
    totalDegreeCreditsNum > 0
      ? Math.min(4, (currentGpaNum * currentCreditsNum + 4 * Math.max(0, remainingCredits)) / totalDegreeCreditsNum)
      : 0;

  const roadmapNeededLabel = Number.isFinite(roadmapPlan.averageGpaNeeded)
    ? format2(roadmapPlan.averageGpaNeeded)
    : '> 4.00';

  // Share text
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

  // Steppers for GPA
  const stepTargetGpa = (delta: number) => {
    const currentVal = Number(targetGpaStr) || 3.60;
    const nextVal = Math.min(4.0, Math.max(1.0, Math.round((currentVal + delta) * 100) / 100));
    setTargetGpaStr(nextVal.toFixed(2));
  };

  const stepTargetGradGpa = (delta: number) => {
    const currentVal = Number(targetGradGpaStr) || 3.60;
    const nextVal = Math.min(4.0, Math.max(1.0, Math.round((currentVal + delta) * 100) / 100));
    setTargetGradGpaStr(nextVal.toFixed(2));
  };

  // Handlers for profile updates
  const handleCurrentGpaChange = (val: string) => updateProfile({ currentGpa: sanitizeDecimal(val) });
  const handleCurrentCreditsChange = (val: string) => updateProfile({ currentCredits: sanitizeDecimal(val) });
  const handleTotalDegreeCreditsChange = (val: string) => updateProfile({ totalDegreeCredits: sanitizeDecimal(val) });

  // Handlers for Tab 2 (Retake Courses)
  const handleAddRetake = () => {
    if (retakes.length >= 6) return;
    const nextId = `retake-${Date.now()}`;
    const nextIdx = retakes.length + 1;
    setRetakes((prev) => [
      ...prev,
      { id: nextId, label: `Môn học ${nextIdx}`, oldGrade: 1.0, targetGrade: 4.0, credits: 3 },
    ]);
  };

  const handleRemoveRetake = (id: string) => {
    setRetakes((prev) => (prev.length > 1 ? prev.filter((r) => r.id !== id) : prev));
  };

  const handleUpdateRetake = (id: string, field: keyof RetakeDraft, val: number | string) => {
    setRetakes((prev) =>
      prev.map((r) => {
        if (r.id !== id) return r;
        if (field === 'oldGrade') {
          const newOld = Number(val);
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
      oldGrade: 1.0,
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
          label: `Môn học ${prev.length + 1}`,
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
    setRetakes((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== mobileRetakeSheet.index) : prev));
    setMobileRetakeSheet(null);
  };

  // Handler for Global Reset
  const handleReset = () => {
    if (window.confirm('Bạn có chắc chắn muốn đặt lại các thông số về mặc định không?')) {
      clearProfile();
      setTargetGpaStr('3.60');
      setFutureCredits(15);
      setRetakes([
        { id: `retake-1-${Date.now()}`, label: 'Môn học 1', oldGrade: 1.0, targetGrade: 4.0, credits: 3 },
        { id: `retake-2-${Date.now()}`, label: 'Môn học 2', oldGrade: 2.0, targetGrade: 4.0, credits: 3 },
      ]);
      setTargetGradGpaStr('3.60');
      setMobileRetakeSheet(null);
    }
  };

  // Milestone Progress Widths
  const termProgressPercent = termPlan.isComplete
    ? Math.min(100, Math.max(0, (termPlan.requiredGpa / 4.0) * 100))
    : 0;

  const retakeProgressPercent = hasEnteredProfile && hasRetakes
    ? Math.min(100, Math.max(0, (retakePlan.newBaselineGpa / 4.0) * 100))
    : 0;

  const roadmapProgressPercent = hasEnteredProfile && totalDegreeCreditsNum > 0
    ? Math.min(100, Math.round((currentCreditsNum / totalDegreeCreditsNum) * 100))
    : 0;

  // Status badges for Desktop Right Card Header
  const tab1Badge = (() => {
    if (!hasEnteredProfile || !targetGpaStr) {
      return <span className="gpa-d-result-badge unranked">• Chờ nhập liệu</span>;
    }
    if (termPlan.status === 'achieved') {
      return <span className="gpa-d-result-badge tier-success">★ Đã đạt</span>;
    }
    if (termPlan.status === 'impossible') {
      return <span className="gpa-d-result-badge tier-danger">⚠️ Khó khả thi</span>;
    }
    if (termPlan.requiredGpa >= 3.6) {
      return <span className="gpa-d-result-badge tier-warning">★ Lên Xuất sắc</span>;
    }
    return <span className="gpa-d-result-badge tier-success">★ Khả thi</span>;
  })();

  const tab2Badge = (() => {
    if (!hasEnteredProfile || !hasRetakes) {
      return <span className="gpa-d-result-badge unranked">• Chờ nhập liệu</span>;
    }
    return <span className="gpa-d-result-badge tier-success">★ Cải thiện tốt</span>;
  })();

  const tab3Badge = (() => {
    if (!hasEnteredProfile || !targetGradGpaStr) {
      return <span className="gpa-d-result-badge unranked">• Chờ nhập liệu</span>;
    }
    if (!roadmapPlan.isFeasible) {
      return <span className="gpa-d-result-badge tier-danger">⚠️ Khó khả thi</span>;
    }
    if (Number(targetGradGpaStr) >= 3.6) {
      return <span className="gpa-d-result-badge tier-warning">★ Lên Xuất sắc</span>;
    }
    return <span className="gpa-d-result-badge tier-success">★ Khả thi</span>;
  })();

  const targetTierLabel = useMemo(() => {
    const val = Number(targetGpaStr) || 3.60;
    if (val >= 3.6) return 'Xuất sắc';
    if (val >= 3.2) return 'Giỏi';
    return 'Khá';
  }, [targetGpaStr]);

  const targetGradTierLabel = useMemo(() => {
    const val = Number(targetGradGpaStr) || 3.60;
    if (val >= 3.6) return 'Xuất sắc';
    if (val >= 3.2) return 'Giỏi';
    return 'Khá';
  }, [targetGradGpaStr]);

  return (
    <div className="page-container tool-page simplified gpa-page-wrapper">
      {/* Header Desktop - Đồng bộ 100% GpaPage.tsx */}
      <ToolPageHeader
        icon={TrendingUp}
        title="Mục tiêu GPA"
        description={
          <>
            Tính toán chiến lược GPA học kỳ, cải thiện môn và lộ trình tốt nghiệp toàn khóa theo quy chế <strong>{cohort}</strong>.
          </>
        }
      />

      {/* ============================================================== */}
      {/* 1. BẢN DESKTOP 2 CỘT CÂN ĐỐI (ĐỒNG BỘ 100% GPAPAGE)             */}
      {/* ============================================================== */}
      <div className="gpa-desktop-layout">
        {/* CỘT TRÁI (7 Cols): THIẾT LẬP MỤC TIÊU */}
        <div className="gpa-d-table-card">
          {/* TOOLBAR ĐẦU THẺ */}
          <div className="gpa-d-toolbar">
            <div className="gpa-d-toolbar-title">
              <span className="gpa-d-table-heading">THIẾT LẬP MỤC TIÊU</span>
              <span className="gpa-d-table-badge">3 chế độ</span>
            </div>

            <button
              type="button"
              className="gpa-d-reset-btn"
              onClick={handleReset}
              title="Đặt lại thông số"
              aria-label="Đặt lại thông số"
            >
              <RotateCcw size={14} />
              <span>Đặt lại</span>
            </button>
          </div>

          {/* THÂN THẺ */}
          <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* 3-Tab Segmented Switcher */}
            <div className="target-gpa-tabs-bar" role="tablist" aria-label="Bộ chọn 3 chế độ mục tiêu GPA">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'term'}
                className={`target-gpa-tab-item ${activeTab === 'term' ? 'active' : ''}`}
                onClick={() => setActiveTab('term')}
              >
                <span>🎯</span> <span>1 học kỳ tới</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'retake'}
                className={`target-gpa-tab-item ${activeTab === 'retake' ? 'active' : ''}`}
                onClick={() => setActiveTab('retake')}
              >
                <span>⚡</span> <span>Cải thiện môn</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'roadmap'}
                className={`target-gpa-tab-item ${activeTab === 'roadmap' ? 'active' : ''}`}
                onClick={() => setActiveTab('roadmap')}
              >
                <span>🎓</span> <span>Lộ trình ra trường</span>
              </button>
            </div>

            {/* MỤC 1: ĐIỂM TÍCH LŨY HIỆN TẠI (ĐÃ BỎ HOÀN TOÀN HUY HIỆU ĐÃ LƯU VÀ XÓA DỮ LIỆU) */}
            <div className="target-section-box">
              <div className="target-section-heading">
                <span className="tool-step-badge">1</span>
                <span>Điểm tích lũy hiện tại</span>
              </div>

              {activeTab !== 'roadmap' ? (
                /* Tab 1 & Tab 2: 2 Ô NHẬP TRÊN LƯỚI 2 CỘT */
                <div className="target-grid-2">
                  <div>
                    <label className="target-input-label" htmlFor="curr-gpa-input">
                      GPA tích lũy hiện tại
                    </label>
                    <div className="target-input-wrapper">
                      <input
                        id="curr-gpa-input"
                        type="text"
                        inputMode="decimal"
                        value={currentGpaStr}
                        onChange={(e) => handleCurrentGpaChange(e.target.value)}
                        placeholder="VD: 3.56"
                        className="target-text-input"
                        aria-label="GPA tích lũy hiện tại"
                      />
                      <span className="target-input-unit">/ 4.00</span>
                    </div>
                  </div>
                  <div>
                    <label className="target-input-label" htmlFor="curr-creds-input">
                      Số tín chỉ đã học <span className="target-label-sub">(tính cả môn F)</span>
                    </label>
                    <div className="target-input-wrapper">
                      <input
                        id="curr-creds-input"
                        type="text"
                        inputMode="numeric"
                        value={currentCreditsStr}
                        onChange={(e) => handleCurrentCreditsChange(e.target.value)}
                        placeholder="VD: 106"
                        className="target-text-input"
                        aria-label="Số tín chỉ đã tích lũy (gồm cả TC môn F)"
                      />
                      <span className="target-input-unit">TC</span>
                    </div>
                  </div>
                </div>
              ) : (
                /* Tab 3: 3 Ô NHẬP TRÊN LƯỚI 3 CỘT */
                <div className="target-grid-3">
                  <div>
                    <label className="target-input-label" htmlFor="curr-gpa-input-r">
                      GPA tích lũy hiện tại
                    </label>
                    <div className="target-input-wrapper">
                      <input
                        id="curr-gpa-input-r"
                        type="text"
                        inputMode="decimal"
                        value={currentGpaStr}
                        onChange={(e) => handleCurrentGpaChange(e.target.value)}
                        placeholder="VD: 3.56"
                        className="target-text-input"
                        aria-label="GPA tích lũy hiện tại"
                      />
                      <span className="target-input-unit">/ 4.00</span>
                    </div>
                  </div>
                  <div>
                    <label className="target-input-label" htmlFor="curr-creds-input-r">
                      Số TC đã học <span className="target-label-sub">(tính cả môn F)</span>
                    </label>
                    <div className="target-input-wrapper">
                      <input
                        id="curr-creds-input-r"
                        type="text"
                        inputMode="numeric"
                        value={currentCreditsStr}
                        onChange={(e) => handleCurrentCreditsChange(e.target.value)}
                        placeholder="VD: 106"
                        className="target-text-input"
                        aria-label="Số tín chỉ đã tích lũy"
                      />
                      <span className="target-input-unit">TC</span>
                    </div>
                  </div>
                  <div>
                    <label className="target-input-label" htmlFor="total-degree-creds-input">
                      Tổng TC toàn khóa
                    </label>
                    <div className="target-input-wrapper">
                      <input
                        id="total-degree-creds-input"
                        type="text"
                        inputMode="numeric"
                        value={totalDegreeCreditsStr}
                        onChange={(e) => handleTotalDegreeCreditsChange(e.target.value)}
                        placeholder="VD: 122"
                        className="target-text-input"
                        aria-label="Tổng số tín chỉ toàn khóa"
                      />
                      <span className="target-input-unit">TC</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* MỤC 2: TAB 1 (1 HỌC KỲ TỚI) - BỎ HOÀN TOÀN SLIDER */}
            {activeTab === 'term' && (
              <div className="target-section-box">
                <div className="target-section-header-row">
                  <div>
                    <div className="target-section-heading"><span className="tool-step-badge">2</span><span>Mục tiêu sau học kỳ tới</span></div>
                    <span className="target-section-sub">Chọn mốc học lực hoặc điều chỉnh mức GPA mong muốn</span>
                  </div>
                  {/* Cụm nút tăng/giảm kiêm ô nhập trực tiếp [ - | 3.60 / 4.00 | + ] */}
                  <div className="target-gpa-stepper-box">
                    <button
                      type="button"
                      className="target-gpa-stepper-arrow"
                      onClick={() => stepTargetGpa(-0.05)}
                      aria-label="Giảm 0.05 GPA mục tiêu"
                    >
                      −
                    </button>
                    <div className="target-gpa-stepper-input-wrap">
                      <input
                        type="text"
                        inputMode="decimal"
                        value={targetGpaStr}
                        onChange={(e) => setTargetGpaStr(sanitizeDecimal(e.target.value))}
                        className="target-gpa-val-input"
                        placeholder="VD: 3.60"
                        aria-label="GPA mục tiêu muốn đạt"
                      />
                      <span className="target-gpa-max-tag">/ 4.00</span>
                    </div>
                    <button
                      type="button"
                      className="target-gpa-stepper-arrow"
                      onClick={() => stepTargetGpa(0.05)}
                      aria-label="Tăng 0.05 GPA mục tiêu"
                    >
                      +
                    </button>
                  </div>
                </div>

                {/* 3 Nút mốc học lực có màu sắc ngữ nghĩa rõ ràng */}
                <div className="target-preset-grid">
                  <button
                    type="button"
                    className={`target-preset-btn preset-blue ${targetGpaStr === '2.50' ? 'active' : ''}`}
                    onClick={() => setTargetGpaStr('2.50')}
                  >
                    <span className="target-preset-dot dot-blue" />
                    <span>Khá (2.50)</span>
                  </button>
                  <button
                    type="button"
                    className={`target-preset-btn preset-emerald ${targetGpaStr === '3.20' ? 'active' : ''}`}
                    onClick={() => setTargetGpaStr('3.20')}
                  >
                    <span className="target-preset-dot dot-emerald" />
                    <span>Giỏi (3.20)</span>
                  </button>
                  <button
                    type="button"
                    className={`target-preset-btn preset-amber ${targetGpaStr === '3.60' ? 'active' : ''}`}
                    onClick={() => setTargetGpaStr('3.60')}
                  >
                    <span className="target-preset-star">★</span>
                    <span>Xuất sắc (3.60)</span>
                  </button>
                </div>

                {/* Tín chỉ đăng ký kỳ tới */}
                <div className="target-credits-row">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="tool-step-badge">3</span>
                    <span className="target-credits-label">Tín chỉ đăng ký kỳ tới:</span>
                  </div>
                  <div className="target-credits-control-group">
                    <div className="gpa-d-credit-capsule">
                      <button
                        type="button"
                        className="credit-step-btn"
                        onClick={() => setFutureCredits((prev) => Math.max(3, prev - 1))}
                        aria-label="Giảm 1 tín chỉ kỳ tới"
                      >
                        −
                      </button>
                      <input
                        type="text"
                        className="credit-val-input"
                        value={futureCredits}
                        readOnly
                        aria-label="Số tín chỉ đăng ký kỳ tới"
                      />
                      <button
                        type="button"
                        className="credit-step-btn"
                        onClick={() => setFutureCredits((prev) => Math.min(35, prev + 1))}
                        aria-label="Tăng 1 tín chỉ kỳ tới"
                      >
                        +
                      </button>
                    </div>
                    <div className="target-credit-pills">
                      {TERM_CREDIT_PRESETS.map((c) => (
                        <button
                          key={c}
                          type="button"
                          className={`target-credit-pill-btn ${futureCredits === c ? 'active' : ''}`}
                          onClick={() => setFutureCredits(c)}
                        >
                          {c} TC
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* MỤC 2: TAB 2 (CẢI THIỆN MÔN) - ĐỒNG BỘ BẢNG VỚI GPAPAGE */}
            {activeTab === 'retake' && (
              <div className="target-section-box">
                <div className="target-section-heading" style={{ marginBottom: '0.65rem' }}>
                  <span className="tool-step-badge">2</span>
                  <span>Chọn môn cải thiện</span>
                </div>

                <table className="gpa-d-table target-retake-table">
                  <thead className="gpa-d-thead">
                    <tr>
                      <th style={{ width: '25%', paddingLeft: '1.25rem' }}>MÔN HỌC</th>
                      <th style={{ width: '22%', textAlign: 'center' }}>TÍN CHỈ</th>
                      <th style={{ width: '33%', textAlign: 'center' }}>ĐIỂM CŨ → ĐIỂM MỚI</th>
                      <th style={{ width: '20%', paddingRight: '1.25rem', textAlign: 'right' }}>TĂNG GPA</th>
                    </tr>
                  </thead>
                  <tbody className="gpa-d-tbody">
                    {retakes.map((course, idx) => {
                      const rowDelta =
                        course.oldGrade !== null && currentCreditsNum > 0
                          ? Math.round(
                              (((course.targetGrade - course.oldGrade) * course.credits) / currentCreditsNum) * 100,
                            ) / 100
                          : null;

                      return (
                        <tr key={course.id}>
                          {/* Cột 1: MÔN HỌC */}
                          <td style={{ paddingLeft: '1.25rem' }}>
                            <span className="gpa-d-course-name">Môn học {idx + 1}</span>
                          </td>

                          {/* Cột 2: TÍN CHỈ (Capsule Stepper) */}
                          <td style={{ textAlign: 'center' }}>
                            <div className="gpa-d-credit-capsule">
                              <button
                                type="button"
                                className="credit-step-btn"
                                onClick={() =>
                                  handleUpdateRetake(course.id, 'credits', Math.max(1, course.credits - 1))
                                }
                                aria-label={`Giảm 1 tín chỉ cho Môn học ${idx + 1}`}
                              >
                                −
                              </button>
                              <input
                                type="text"
                                className="credit-val-input"
                                value={course.credits}
                                readOnly
                                aria-label={`Tín chỉ Môn học ${idx + 1}`}
                              />
                              <button
                                type="button"
                                className="credit-step-btn"
                                onClick={() =>
                                  handleUpdateRetake(course.id, 'credits', Math.min(10, course.credits + 1))
                                }
                                aria-label={`Tăng 1 tín chỉ cho Môn học ${idx + 1}`}
                              >
                                +
                              </button>
                            </div>
                          </td>

                          {/* Cột 3: ĐIỂM CŨ → ĐIỂM MỚI */}
                          <td style={{ textAlign: 'center' }}>
                            <div className="target-retake-grade-pair">
                              <select
                                className="target-retake-select"
                                value={course.oldGrade ?? ''}
                                onChange={(e) => handleUpdateRetake(course.id, 'oldGrade', Number(e.target.value))}
                                aria-label={`Điểm cũ Môn học ${idx + 1}`}
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
                              <span className="target-retake-arrow">→</span>
                              <select
                                className="target-retake-select"
                                value={course.targetGrade}
                                onChange={(e) => handleUpdateRetake(course.id, 'targetGrade', Number(e.target.value))}
                                aria-label={`Điểm mới Môn học ${idx + 1}`}
                              >
                                {ALL_TARGET_GRADES.filter((g) => g.value > (course.oldGrade ?? -1)).map((g) => (
                                  <option key={g.value} value={g.value}>
                                    {g.label}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </td>

                          {/* Cột 4: TĂNG GPA & XÓA */}
                          <td style={{ paddingRight: '1.25rem', textAlign: 'right' }}>
                            <div className="gpa-d-convert-cluster">
                              {rowDelta !== null && rowDelta > 0 ? (
                                <span className="gpa-d-grade-badge grade-A">+{rowDelta.toFixed(2)}</span>
                              ) : (
                                <span className="gpa-d-grade-badge empty">—</span>
                              )}
                              <button
                                type="button"
                                className="gpa-d-del-btn"
                                onClick={() => handleRemoveRetake(course.id)}
                                disabled={retakes.length <= 1}
                                title={retakes.length <= 1 ? 'Cần giữ ít nhất 1 môn' : 'Xóa môn này'}
                                aria-label={`Xóa Môn học ${idx + 1}`}
                              >
                                <Trash2 size={15} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {/* NÚT THÊM MÔN VIỀN NÉT ĐỨT */}
                {retakes.length < 6 && (
                  <div
                    className="gpa-d-add-wrapper"
                    style={{ background: 'transparent', borderTop: 'none', paddingTop: '0.65rem' }}
                  >
                    <button type="button" className="gpa-d-add-dashed-btn" onClick={handleAddRetake}>
                      <Plus size={15} />
                      <span>Thêm môn cải thiện</span>
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* MỤC 2: TAB 3 (LỘ TRÌNH RA TRƯỜNG) - BỎ HOÀN TOÀN SLIDER */}
            {activeTab === 'roadmap' && (
              <div className="target-section-box">
                <div className="target-section-header-row">
                  <div>
                    <div className="target-section-heading"><span className="tool-step-badge">2</span><span>Kế hoạch tốt nghiệp</span></div>
                    <span className="target-section-sub">Chọn mốc xếp loại tốt nghiệp muốn đạt</span>
                  </div>
                  {/* Stepper kiêm ô nhập trực tiếp [ - | 3.60 / 4.00 | + ] */}
                  <div className="target-gpa-stepper-box">
                    <button
                      type="button"
                      className="target-gpa-stepper-arrow"
                      onClick={() => stepTargetGradGpa(-0.05)}
                      aria-label="Giảm 0.05 GPA tốt nghiệp"
                    >
                      −
                    </button>
                    <div className="target-gpa-stepper-input-wrap">
                      <input
                        type="text"
                        inputMode="decimal"
                        value={targetGradGpaStr}
                        onChange={(e) => setTargetGradGpaStr(sanitizeDecimal(e.target.value))}
                        className="target-gpa-val-input"
                        placeholder="VD: 3.60"
                        aria-label="GPA tốt nghiệp muốn đạt"
                      />
                      <span className="target-gpa-max-tag">/ 4.00</span>
                    </div>
                    <button
                      type="button"
                      className="target-gpa-stepper-arrow"
                      onClick={() => stepTargetGradGpa(0.05)}
                      aria-label="Tăng 0.05 GPA tốt nghiệp"
                    >
                      +
                    </button>
                  </div>
                </div>

                {/* 3 Nút mốc học lực có màu sắc ngữ nghĩa */}
                <div className="target-preset-grid">
                  <button
                    type="button"
                    className={`target-preset-btn preset-blue ${targetGradGpaStr === '2.50' ? 'active' : ''}`}
                    onClick={() => setTargetGradGpaStr('2.50')}
                  >
                    <span className="target-preset-dot dot-blue" />
                    <span>Khá (2.50)</span>
                  </button>
                  <button
                    type="button"
                    className={`target-preset-btn preset-emerald ${targetGradGpaStr === '3.20' ? 'active' : ''}`}
                    onClick={() => setTargetGradGpaStr('3.20')}
                  >
                    <span className="target-preset-dot dot-emerald" />
                    <span>Giỏi (3.20)</span>
                  </button>
                  <button
                    type="button"
                    className={`target-preset-btn preset-amber ${targetGradGpaStr === '3.60' ? 'active' : ''}`}
                    onClick={() => setTargetGradGpaStr('3.60')}
                  >
                    <span className="target-preset-star">★</span>
                    <span>Xuất sắc (3.60)</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* CỘT PHẢI (5 Cols): THẺ KẾT QUẢ DỰ TÍNH (ĐỒNG BỘ 100% CẤU TRÚC VỚI GPAPAGE) */}
        <div className="gpa-d-sticky-col">
          <div className="gpa-d-result-card" id="target-gpa-result">
            {/* Header Kết Quả */}
            <div className="gpa-d-result-header">
              <span className="gpa-d-result-title">
                {activeTab === 'term'
                  ? 'KẾT QUẢ KỲ TỚI'
                  : activeTab === 'retake'
                    ? 'HIỆU QUẢ CẢI THIỆN'
                    : 'LỘ TRÌNH TỐT NGHIỆP'}
              </span>
              {activeTab === 'term' ? tab1Badge : activeTab === 'retake' ? tab2Badge : tab3Badge}
            </div>

            {/* Khu vực Điểm Trung Tâm */}
            <div className="gpa-d-hero-score-box">
              <div className="gpa-d-hero-sub">
                {activeTab === 'term'
                  ? termPlan.status === 'achieved'
                    ? 'GPA TÍCH LŨY HIỆN TẠI'
                    : 'GPA HỌC KỲ TỚI CẦN ĐẠT'
                  : activeTab === 'retake'
                    ? 'GPA TÍCH LŨY DỰ KIẾN SAU CẢI THIỆN'
                    : 'GPA CẦN DUY TRÌ MỖI KỲ CÒN LẠI'}
              </div>

              <div className="gpa-d-hero-score-row">
                <span className="gpa-d-hero-score">
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
                <span className="gpa-d-hero-max">/ 4.00</span>
              </div>

              {/* Viên thuốc phụ bên dưới điểm trung tâm */}
              <div className="gpa-d-gpa10-pill">
                {activeTab === 'term' ? (
                  hasEnteredProfile && targetGpaStr ? (
                    <>
                      <span className="gpa-d-gpa10-label">Tích lũy mục tiêu:</span>
                      <strong className="target-pill-bold-amber">
                        {format2(currentGpaNum)} → {format2(Number(targetGpaStr))} ({targetTierLabel})
                      </strong>
                    </>
                  ) : (
                    <span className="gpa-d-gpa10-label">Nhập điểm tích lũy và mục tiêu bên trái</span>
                  )
                ) : activeTab === 'retake' ? (
                  hasEnteredProfile && hasRetakes ? (
                    <>
                      <span className="gpa-d-gpa10-label">Tích lũy mới:</span>
                      <strong className="target-pill-bold-emerald">
                        {format2(currentGpaNum)} → {format2(retakePlan.newBaselineGpa)} (+{format2(retakePlan.deltaGpa)} GPA)
                      </strong>
                    </>
                  ) : (
                    <span className="gpa-d-gpa10-label">Chọn điểm môn học để tính mức tăng</span>
                  )
                ) : hasEnteredProfile && targetGradGpaStr ? (
                  <>
                    <span className="gpa-d-gpa10-label">Mục tiêu bằng:</span>
                    <strong className="target-pill-bold-amber">
                      ★ {targetGradTierLabel} (GPA ≥ {format2(Number(targetGradGpaStr))})
                    </strong>
                  </>
                ) : (
                  <span className="gpa-d-gpa10-label">Chưa chọn mức GPA tốt nghiệp</span>
                )}
              </div>
            </div>

            {/* Khối giữa: Thanh mốc học lực / Thanh tiến độ + 1 dòng gợi ý duy nhất (KHÔNG card lồng card) */}
            {activeTab === 'term' && (
              <div className="gpa-d-milestone-box">
                <div className="gpa-d-milestone-labels">
                  <span>0.0</span>
                  <span>TB 2.0</span>
                  <span className="gpa-milestone-blue">Khá 2.5</span>
                  <span className="gpa-milestone-green">Giỏi 3.2</span>
                  <span className="gpa-milestone-amber">★ XS 3.6</span>
                </div>

                <div className="gpa-d-milestone-bar-wrap">
                  <div className="gpa-d-milestone-bar-fill" style={{ width: `${termProgressPercent}%` }} />
                  <div className="gpa-d-milestone-tick" style={{ left: '50%' }} title="Trung bình (2.0)" />
                  <div className="gpa-d-milestone-tick" style={{ left: '62.5%' }} title="Khá (2.5)" />
                  <div className="gpa-d-milestone-tick" style={{ left: '80%' }} title="Giỏi (3.2)" />
                  <div className="gpa-d-milestone-tick" style={{ left: '90%' }} title="Xuất sắc (3.6)" />
                </div>

                <div className="gpa-d-milestone-prompt">
                  {!hasEnteredProfile || !targetGpaStr ? (
                    <span>💡 Nhập điểm tích lũy và mục tiêu để xem gợi ý</span>
                  ) : termPlan.status === 'impossible' ? (
                    <span>
                      ⚠️ Cần tối thiểu {termPlan.minCreditsNeeded ?? '> 20'} TC điểm A để đạt mục tiêu
                    </span>
                  ) : termPlan.status === 'achieved' ? (
                    <span>🎉 Điểm hiện tại ({format2(currentGpaNum)}) đã đạt mục tiêu này</span>
                  ) : (
                    <span>
                      🎯 Gợi ý ({prescription.totalCourses} môn): Cần{' '}
                      {prescription.coursesA > 0 && (
                        <strong style={{ color: '#047857' }}>{prescription.coursesA} môn A</strong>
                      )}
                      {prescription.coursesA > 0 && prescription.coursesBPlus > 0 && ' + '}
                      {prescription.coursesBPlus > 0 && (
                        <strong style={{ color: '#2563eb' }}>{prescription.coursesBPlus} môn B+</strong>
                      )}
                      {(prescription.coursesA > 0 || prescription.coursesBPlus > 0) && prescription.coursesB > 0 && ' + '}
                      {prescription.coursesB > 0 && (
                        <strong style={{ color: '#475569' }}>{prescription.coursesB} môn B</strong>
                      )}
                    </span>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'retake' && (
              <div className="gpa-d-milestone-box">
                <div className="gpa-d-milestone-labels">
                  <span>0.0</span>
                  <span>TB 2.0</span>
                  <span className="gpa-milestone-blue">Khá 2.5</span>
                  <span className="gpa-milestone-green">Giỏi 3.2</span>
                  <span className="gpa-milestone-amber">★ XS 3.6</span>
                </div>

                <div className="gpa-d-milestone-bar-wrap">
                  <div className="gpa-d-milestone-bar-fill" style={{ width: `${retakeProgressPercent}%` }} />
                  <div className="gpa-d-milestone-tick" style={{ left: '50%' }} title="Trung bình (2.0)" />
                  <div className="gpa-d-milestone-tick" style={{ left: '62.5%' }} title="Khá (2.5)" />
                  <div className="gpa-d-milestone-tick" style={{ left: '80%' }} title="Giỏi (3.2)" />
                  <div className="gpa-d-milestone-tick" style={{ left: '90%' }} title="Xuất sắc (3.6)" />
                </div>

                <div className="gpa-d-milestone-prompt">
                  {hasEnteredProfile && hasRetakes ? (
                    <span>
                      🚀 Cải thiện {completeRetakes.length} môn giúp GPA tăng{' '}
                      <strong style={{ color: '#047857' }}>+{format2(retakePlan.deltaGpa)}</strong> điểm
                    </span>
                  ) : (
                    <span>💡 Chọn điểm cũ và điểm mới ở bảng bên trái</span>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'roadmap' && (
              <div className="gpa-d-milestone-box">
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    color: '#475569',
                    marginBottom: '0.45rem',
                  }}
                >
                  <span>Tiến độ tích lũy toàn khóa</span>
                  <span style={{ color: '#047857', fontWeight: 800 }}>
                    {hasEnteredProfile
                      ? `${currentCreditsNum} / ${totalDegreeCreditsNum} TC (${roadmapProgressPercent}%)`
                      : `-- / ${totalDegreeCreditsNum} TC`}
                  </span>
                </div>

                <div className="gpa-d-milestone-bar-wrap" style={{ height: '10px' }}>
                  <div
                    className="gpa-d-milestone-bar-fill"
                    style={{
                      width: `${roadmapProgressPercent}%`,
                      background: 'linear-gradient(90deg, #2563EB 0%, #10B981 100%)',
                    }}
                  />
                </div>

                <div className="gpa-d-milestone-prompt">
                  {roadmapPlan.isFeasible ? (
                    <span>
                      🎯 Cần duy trì trung bình ~<strong>{format2(roadmapPlan.averageGpaNeeded)} GPA</strong> mỗi kỳ còn lại
                    </span>
                  ) : (
                    <span>
                      ⚠️ Cần trung bình vượt 4.00. Hãy cân nhắc điều chỉnh mục tiêu hoặc học cải thiện môn cũ.
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* 3 Ô Thống Kê Gọn Gàng */}
            <div className="gpa-d-stats-grid">
              {activeTab === 'term' ? (
                <>
                  <div className="gpa-d-stat-box">
                    <span className="gpa-d-stat-label">TC hiện tại</span>
                    <span className="gpa-d-stat-val">{hasEnteredProfile ? currentCreditsNum : '--'}</span>
                  </div>
                  <div className="gpa-d-stat-box passed">
                    <span className="gpa-d-stat-label">TC kỳ tới</span>
                    <span className="gpa-d-stat-val">+{futureCredits}</span>
                  </div>
                  <div className="gpa-d-stat-box">
                    <span className="gpa-d-stat-label">Tổng TC mới</span>
                    <span className="gpa-d-stat-val">
                      {hasEnteredProfile ? currentCreditsNum + futureCredits : '--'}
                    </span>
                  </div>
                </>
              ) : activeTab === 'retake' ? (
                <>
                  <div className="gpa-d-stat-box">
                    <span className="gpa-d-stat-label">Số môn</span>
                    <span className="gpa-d-stat-val">{completeRetakes.length}</span>
                  </div>
                  <div className={`gpa-d-stat-box ${completeRetakes.length > 0 ? 'passed' : ''}`}>
                    <span className="gpa-d-stat-label">TC cải thiện</span>
                    <span className="gpa-d-stat-val">
                      {completeRetakes.reduce((sum, r) => sum + r.credits, 0)}
                    </span>
                  </div>
                  <div className="gpa-d-stat-box">
                    <span className="gpa-d-stat-label">Mức tăng GPA</span>
                    <span className="gpa-d-stat-val" style={{ color: '#047857' }}>
                      +{format2(retakePlan.deltaGpa)}
                    </span>
                  </div>
                </>
              ) : (
                <>
                  <div className="gpa-d-stat-box">
                    <span className="gpa-d-stat-label">Đã tích lũy</span>
                    <span className="gpa-d-stat-val">{hasEnteredProfile ? `${currentCreditsNum} TC` : '-- TC'}</span>
                  </div>
                  <div className="gpa-d-stat-box passed">
                    <span className="gpa-d-stat-label">Còn lại</span>
                    <span className="gpa-d-stat-val">{hasEnteredProfile ? `${remainingCredits} TC` : '-- TC'}</span>
                  </div>
                  <div className="gpa-d-stat-box">
                    <span className="gpa-d-stat-label">Tương đương</span>
                    <span className="gpa-d-stat-val">
                      {hasEnteredProfile ? `~${roadmapPlan.termsRemaining} kỳ` : '--'}
                    </span>
                  </div>
                </>
              )}
            </div>

            {/* 1-Line Footer */}
            <div className="gpa-d-result-footer">
              <button
                type="button"
                className="gpa-d-footer-link"
                onClick={() => setReferenceModalTab('scale')}
              >
                <BookOpen size={14} aria-hidden="true" />
                <span>Bảng quy đổi {cohort}</span>
                <ArrowUpRight size={14} aria-hidden="true" />
              </button>
              {activeTab === 'roadmap' ? (
                <button
                  type="button"
                  className="gpa-d-footer-link"
                  onClick={() => setReferenceModalTab('rules')}
                >
                  <FileText size={14} aria-hidden="true" />
                  <span>Quy chế đào tạo</span>
                  <ArrowUpRight size={14} aria-hidden="true" />
                </button>
              ) : shareText ? (
                <ShareResultButton text={shareText} className="gpa-d-footer-link" />
              ) : (
                <span className="gpa-d-footer-watermark">ĐHSP TP.HCM</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ============================================================== */}
      {/* 2. BẢN MOBILE NATIVE TINH GỌN (THOÁNG ĐÃNG, ĐỒNG BỘ GPAPAGE)   */}
      {/* ============================================================== */}
      <div className="gpa-mobile-layout">
        {/* Tiêu đề mobile gọn 1 hàng */}
        <div className="gpa-m-page-header">
          <div className="gpa-m-title-wrap">
            <TrendingUp size={20} className="gpa-m-title-icon" aria-hidden="true" />
            <h1 className="gpa-m-page-title">Mục tiêu GPA</h1>
          </div>
          <button
            type="button"
            className="gpa-d-reset-btn"
            onClick={handleReset}
            title="Đặt lại thông số"
            aria-label="Đặt lại thông số"
          >
            <RotateCcw size={12} />
            <span>Đặt lại</span>
          </button>
        </div>

        {/* 3-Tab Switcher ngay dưới tiêu đề */}
        <div className="target-m-tab-switcher" role="tablist" aria-label="Bộ chọn chế độ tính toán GPA">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'term'}
            className={`target-m-tab-btn ${activeTab === 'term' ? 'active' : ''}`}
            onClick={() => setActiveTab('term')}
          >
            <span>🎯</span>
            <span>1 kỳ tới</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'retake'}
            className={`target-m-tab-btn ${activeTab === 'retake' ? 'active' : ''}`}
            onClick={() => setActiveTab('retake')}
          >
            <span>⚡</span>
            <span>Cải thiện</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'roadmap'}
            className={`target-m-tab-btn ${activeTab === 'roadmap' ? 'active' : ''}`}
            onClick={() => setActiveTab('roadmap')}
          >
            <span>🎓</span>
            <span>Ra trường</span>
          </button>
        </div>

        {/* Hero Score Card Navy */}
        <div className="gpa-mobile-hero-container">
          <div className="gpa-mobile-hero-card">
            <div className="gpa-m-hero-label">
              {activeTab === 'term'
                ? termPlan.status === 'achieved'
                  ? 'GPA TÍCH LŨY HIỆN TẠI'
                  : 'GPA HỌC KỲ TỚI CẦN ĐẠT'
                : activeTab === 'retake'
                  ? 'GPA TÍCH LŨY SAU CẢI THIỆN'
                  : 'GPA CẦN DUY TRÌ MỖI KỲ'}
            </div>

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

            {/* Viên thuốc capsule hợp nhất (Chữ màu ngọc lục bảo phẳng .gpa-m-tier-text, không dùng pill nền xanh lá cũ) */}
            <div className="gpa-m-capsule-wrap">
              {activeTab === 'term' ? (
                hasEnteredProfile && targetGpaStr ? (
                  <div className="gpa-m-capsule">
                    <span className="gpa-m-tier-text">
                      {termPlan.status === 'achieved'
                        ? 'ĐÃ ĐẠT'
                        : termPlan.status === 'impossible'
                          ? 'KHÓ KHẢ THI'
                          : 'KHẢ THI'}
                    </span>
                    <span className="gpa-m-sep">│</span>
                    <span className="gpa-m-stat-item">
                      Mục tiêu: <strong style={{ color: '#38bdf8' }}>{targetGpaStr}</strong>
                    </span>
                    <span className="gpa-m-bullet">•</span>
                    <span className="gpa-m-stat-item">
                      <strong style={{ color: '#ffffff' }}>{futureCredits}</strong> TC
                    </span>
                  </div>
                ) : (
                  <div className="gpa-m-capsule empty">
                    <span className="gpa-m-stat-item" style={{ color: 'rgba(255,255,255,0.75)' }}>
                      Nhập điểm và mục tiêu bên dưới
                    </span>
                  </div>
                )
              ) : activeTab === 'retake' ? (
                hasEnteredProfile && hasRetakes ? (
                  <div className="gpa-m-capsule">
                    <span className="gpa-m-tier-text">CẢI THIỆN TỐT</span>
                    <span className="gpa-m-sep">│</span>
                    <span className="gpa-m-stat-item">
                      +{format2(retakePlan.deltaGpa)} GPA
                    </span>
                    <span className="gpa-m-bullet">•</span>
                    <span className="gpa-m-stat-item">
                      <strong style={{ color: '#ffffff' }}>{completeRetakes.length}</strong> môn
                    </span>
                  </div>
                ) : (
                  <div className="gpa-m-capsule empty">
                    <span className="gpa-m-stat-item" style={{ color: 'rgba(255,255,255,0.75)' }}>
                      Nhập môn học lại bên dưới
                    </span>
                  </div>
                )
              ) : (
                hasEnteredProfile && targetGradGpaStr ? (
                  <div className="gpa-m-capsule">
                    <span className="gpa-m-tier-text">
                      {roadmapPlan.isFeasible ? 'KHẢ THI' : 'KHÓ KHẢ THI'}
                    </span>
                    <span className="gpa-m-sep">│</span>
                    <span className="gpa-m-stat-item">
                      Mục tiêu: <strong style={{ color: '#38bdf8' }}>{targetGradGpaStr}</strong>
                    </span>
                    <span className="gpa-m-bullet">•</span>
                    <span className="gpa-m-stat-item">
                      <strong style={{ color: '#ffffff' }}>{remainingCredits}</strong> TC
                    </span>
                  </div>
                ) : (
                  <div className="gpa-m-capsule empty">
                    <span className="gpa-m-stat-item" style={{ color: 'rgba(255,255,255,0.75)' }}>
                      Nhập điểm và mục tiêu bên dưới
                    </span>
                  </div>
                )
              )}
            </div>
          </div>
        </div>

        {/* THẺ 1 (Thẻ trắng riêng biệt): 1. Tích lũy hiện tại */}
        <div className="target-m-card">
          <div className="target-m-card-header">
            <span className="target-m-card-title"><span className="tool-step-badge">1</span><span>Tích lũy hiện tại</span></span>
          </div>

          {activeTab !== 'roadmap' ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem' }}>
              <div>
                <label className="target-m-field-label" htmlFor="m-curr-gpa">
                  GPA tích lũy
                </label>
                <div className="target-m-input-box">
                  <input
                    id="m-curr-gpa"
                    type="text"
                    inputMode="decimal"
                    value={currentGpaStr}
                    onChange={(e) => handleCurrentGpaChange(e.target.value)}
                    placeholder="VD: 3.56"
                    className="target-m-input"
                    aria-label="GPA tích lũy hiện tại"
                  />
                  <span className="target-m-unit">/ 4.0</span>
                </div>
              </div>
              <div>
                <label className="target-m-field-label" htmlFor="m-curr-creds">
                  Tín chỉ tích lũy
                </label>
                <div className="target-m-input-box">
                  <input
                    id="m-curr-creds"
                    type="text"
                    inputMode="numeric"
                    value={currentCreditsStr}
                    onChange={(e) => handleCurrentCreditsChange(e.target.value)}
                    placeholder="VD: 106"
                    className="target-m-input"
                    aria-label="Số tín chỉ đã tích lũy"
                  />
                  <span className="target-m-unit">TC</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="target-m-grid-3">
              <div>
                <label className="target-m-field-label" htmlFor="m-curr-gpa-r">
                  GPA tích lũy
                </label>
                <div className="target-m-input-box">
                  <input
                    id="m-curr-gpa-r"
                    type="text"
                    inputMode="decimal"
                    value={currentGpaStr}
                    onChange={(e) => handleCurrentGpaChange(e.target.value)}
                    placeholder="VD: 3.56"
                    className="target-m-input"
                    aria-label="GPA tích lũy hiện tại"
                  />
                  <span className="target-m-unit">/ 4.0</span>
                </div>
              </div>
              <div>
                <label className="target-m-field-label" htmlFor="m-curr-creds-r">
                  Đã tích lũy
                </label>
                <div className="target-m-input-box">
                  <input
                    id="m-curr-creds-r"
                    type="text"
                    inputMode="numeric"
                    value={currentCreditsStr}
                    onChange={(e) => handleCurrentCreditsChange(e.target.value)}
                    placeholder="VD: 106"
                    className="target-m-input"
                    aria-label="Số tín chỉ đã tích lũy"
                  />
                  <span className="target-m-unit">TC</span>
                </div>
              </div>
              <div>
                <label className="target-m-field-label" htmlFor="m-total-degree">
                  Tổng CTĐT
                </label>
                <div className="target-m-input-box">
                  <input
                    id="m-total-degree"
                    type="text"
                    inputMode="numeric"
                    value={totalDegreeCreditsStr}
                    onChange={(e) => handleTotalDegreeCreditsChange(e.target.value)}
                    placeholder="VD: 122"
                    className="target-m-input"
                    aria-label="Tổng tín chỉ chương trình đào tạo"
                  />
                  <span className="target-m-unit">TC</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* THẺ 2 (Thẻ trắng riêng biệt): 2. Mục tiêu GPA */}
        <div key={activeTab} className="target-m-tab-content">
          {activeTab === 'term' && (
            <div className="target-m-card">
              <div className="target-m-card-header">
                <span className="target-m-card-title"><span className="tool-step-badge">2</span><span>Mục tiêu GPA kỳ tới</span></span>
                <div className="target-gpa-stepper-box" style={{ height: '32px' }}>
                  <button
                    type="button"
                    className="target-gpa-stepper-arrow"
                    onClick={() => stepTargetGpa(-0.05)}
                    aria-label="Giảm 0.05 GPA"
                  >
                    −
                  </button>
                  <div className="target-gpa-stepper-input-wrap">
                    <input
                      type="text"
                      inputMode="decimal"
                      value={targetGpaStr}
                      onChange={(e) => setTargetGpaStr(sanitizeDecimal(e.target.value))}
                      className="target-gpa-val-input"
                      placeholder="VD: 3.60"
                      style={{ width: '38px', fontSize: '0.9rem' }}
                      aria-label="GPA mục tiêu muốn đạt"
                    />
                    <span className="target-gpa-max-tag">/ 4.0</span>
                  </div>
                  <button
                    type="button"
                    className="target-gpa-stepper-arrow"
                    onClick={() => stepTargetGpa(0.05)}
                    aria-label="Tăng 0.05 GPA"
                  >
                    +
                  </button>
                </div>
              </div>

              {/* 3 nút mốc học lực có màu sắc */}
              <div className="target-preset-grid">
                <button
                  type="button"
                  className={`target-preset-btn preset-blue ${targetGpaStr === '2.50' ? 'active' : ''}`}
                  onClick={() => setTargetGpaStr('2.50')}
                >
                  Khá (2.5)
                </button>
                <button
                  type="button"
                  className={`target-preset-btn preset-emerald ${targetGpaStr === '3.20' ? 'active' : ''}`}
                  onClick={() => setTargetGpaStr('3.20')}
                >
                  Giỏi (3.2)
                </button>
                <button
                  type="button"
                  className={`target-preset-btn preset-amber ${targetGpaStr === '3.60' ? 'active' : ''}`}
                  onClick={() => setTargetGpaStr('3.60')}
                >
                  ★ XS (3.6)
                </button>
              </div>

              {/* Tín chỉ kỳ tới có cả Stepper tùy ý và nút nhanh */}
              <div
                className="target-credits-row"
                style={{ marginTop: '0.65rem', borderTop: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><span className="tool-step-badge">3</span><span className="target-credits-label">Tín chỉ kỳ tới:</span></div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <div className="gpa-d-credit-capsule" style={{ height: '32px' }}>
                    <button
                      type="button"
                      className="credit-step-btn"
                      onClick={() => setFutureCredits((prev) => Math.max(3, prev - 1))}
                      aria-label="Giảm 1 tín chỉ"
                    >
                      −
                    </button>
                    <span className="credit-step-val" style={{ fontSize: '0.9rem', minWidth: '24px' }}>{futureCredits}</span>
                    <button
                      type="button"
                      className="credit-step-btn"
                      onClick={() => setFutureCredits((prev) => Math.min(30, prev + 1))}
                      aria-label="Tăng 1 tín chỉ"
                    >
                      +
                    </button>
                  </div>
                  <div className="target-credit-pills">
                    {TERM_CREDIT_PRESETS.map((c) => (
                      <button
                        key={c}
                        type="button"
                        className={`target-credit-pill-btn ${futureCredits === c ? 'active' : ''}`}
                        onClick={() => setFutureCredits(c)}
                        style={{ height: '32px', minWidth: '32px', padding: '0 6px' }}
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'retake' && (
            <div className="target-m-card">
              <div className="target-m-card-header">
                <span className="target-m-card-title"><span className="tool-step-badge">2</span><span>Môn học cải thiện ({retakes.length})</span></span>
                <span className="target-m-retake-hint">Chạm dòng để sửa</span>
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
                        aria-label={`Chỉnh sửa Môn học ${idx + 1}`}
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

          {activeTab === 'roadmap' && (
            <div className="target-m-card">
              <div className="target-m-card-header">
                <span className="target-m-card-title"><span className="tool-step-badge">2</span><span>Mục tiêu tốt nghiệp</span></span>
                <div className="target-gpa-stepper-box" style={{ height: '32px' }}>
                  <button
                    type="button"
                    className="target-gpa-stepper-arrow"
                    onClick={() => stepTargetGradGpa(-0.05)}
                    aria-label="Giảm 0.05 GPA tốt nghiệp"
                  >
                    −
                  </button>
                  <div className="target-gpa-stepper-input-wrap">
                    <input
                      type="text"
                      inputMode="decimal"
                      value={targetGradGpaStr}
                      onChange={(e) => setTargetGradGpaStr(sanitizeDecimal(e.target.value))}
                      className="target-gpa-val-input"
                      placeholder="VD: 3.60"
                      style={{ width: '38px', fontSize: '0.9rem' }}
                      aria-label="GPA tốt nghiệp muốn đạt"
                    />
                    <span className="target-gpa-max-tag">/ 4.0</span>
                  </div>
                  <button
                    type="button"
                    className="target-gpa-stepper-arrow"
                    onClick={() => stepTargetGradGpa(0.05)}
                    aria-label="Tăng 0.05 GPA tốt nghiệp"
                  >
                    +
                  </button>
                </div>
              </div>

              {/* 3 Presets */}
              <div className="target-preset-grid">
                <button
                  type="button"
                  className={`target-preset-btn preset-blue ${targetGradGpaStr === '2.50' ? 'active' : ''}`}
                  onClick={() => setTargetGradGpaStr('2.50')}
                >
                  Khá (2.5)
                </button>
                <button
                  type="button"
                  className={`target-preset-btn preset-emerald ${targetGradGpaStr === '3.20' ? 'active' : ''}`}
                  onClick={() => setTargetGradGpaStr('3.20')}
                >
                  Giỏi (3.2)
                </button>
                <button
                  type="button"
                  className={`target-preset-btn preset-amber ${targetGradGpaStr === '3.60' ? 'active' : ''}`}
                  onClick={() => setTargetGradGpaStr('3.60')}
                >
                  ★ XS (3.6)
                </button>
              </div>

              <div className="target-m-summary-line" style={{ marginTop: '0.75rem' }}>
                <span>
                  Còn lại: <strong>{remainingCredits} TC</strong>
                </span>
                <span className="target-m-summary-tag">~{roadmapPlan.termsRemaining} học kỳ</span>
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
      {/* MOBILE 1-TOUCH BOTTOM SHEET EDITOR                             */}
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
                  <span id="target-sheet-credits-label" className="gpa-m-sheet-label">
                    1. Số tín chỉ
                  </span>
                  <span className="gpa-m-sheet-hint">{mobileRetakeSheet.credits || '3'} tín chỉ</span>
                </div>
                <CreditWheelPicker
                  labelledBy="target-sheet-credits-label"
                  value={mobileRetakeSheet.credits}
                  onChange={(val) => setMobileRetakeSheet((s) => (s ? { ...s, credits: val } : null))}
                />
              </div>

              {/* 2. Chuyển đổi điểm số */}
              <div className="gpa-m-sheet-field">
                <label className="gpa-m-sheet-label">2. Chuyển đổi điểm số</label>
                <div className="target-m-dual-select">
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

                  <div className="target-m-select-arrow" aria-hidden="true">
                    <ArrowRight size={14} />
                  </div>

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
