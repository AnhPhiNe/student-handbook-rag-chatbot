import { useEffect, useMemo, useId, useRef, useState, type ReactNode } from 'react';
import { ShareResultButton } from '../tool/ShareResultButton';
import { gpaShareText } from '../../utils/shareText';
import { useStudentProfile } from '../../hooks/useStudentProfile';
import { AlertTriangle, ArrowUpRight, BookOpen, GraduationCap, Plus, Trash2, X, RotateCcw } from 'lucide-react';
import {
  calculateGpa,
  getCourseGrade,
  getCourseGroupOptions,
  getDefaultCourseGroup,
  isCreditsInvalid,
  isScore10Invalid,
  isSplitGradeCohort,
  type Cohort,
  type CourseInput,
  type GradeScaleRow,
} from '../../utils/gradeScale';
import { sanitizeDecimal } from '../../utils/numberInput';
import { useAnimatedNumber } from '../../hooks/useAnimatedNumber';
import { GpaReferenceModal } from '../GpaReferenceModal';
import { ToolPageHeader } from '../tool/ToolPageHeader';

interface GpaPageProps {
  cohort: Cohort;
  onNavigate?: (tab: string) => void;
}

function newCourse(id: string, cohort: Cohort): CourseInput {
  return {
    id,
    name: '',
    credits: '3',
    inputType: 'score10',
    score10: '',
    letter: '',
    courseGroup: getDefaultCourseGroup(cohort),
  };
}

function createEmptyCourses(cohort: Cohort): CourseInput[] {
  return [
    newCourse('course-1', cohort),
    newCourse('course-2', cohort),
    newCourse('course-3', cohort),
    newCourse('course-4', cohort),
    newCourse('course-5', cohort),
  ];
}

interface AcademicTier {
  label: string;
  tone: 'success' | 'warning' | 'danger';
  description: ReactNode;
}

function getAcademicTier(gpa: number): AcademicTier {
  if (gpa >= 3.6) {
    return {
      label: 'Xuất sắc',
      tone: 'success',
      description: <>Xếp loại học lực <strong>Xuất sắc</strong> (GPA từ <strong>3.60</strong> đến <strong>4.00</strong>).</>,
    };
  }
  if (gpa >= 3.2) {
    return {
      label: 'Giỏi',
      tone: 'success',
      description: <>Xếp loại học lực <strong>Giỏi</strong> (GPA từ <strong>3.20</strong> đến <strong>3.59</strong>).</>,
    };
  }
  if (gpa >= 2.5) {
    return {
      label: 'Khá',
      tone: 'success',
      description: <>Xếp loại học lực <strong>Khá</strong> (GPA từ <strong>2.50</strong> đến <strong>3.19</strong>).</>,
    };
  }
  if (gpa >= 2.0) {
    return {
      label: 'Trung bình',
      tone: 'warning',
      description: <>Xếp loại học lực <strong>Trung bình</strong> (GPA từ <strong>2.00</strong> đến <strong>2.49</strong>).</>,
    };
  }
  return {
    label: 'Yếu',
    tone: 'danger',
    description: <>Xếp loại học lực <strong>Yếu</strong> (GPA dưới <strong>2.00</strong>). Cần cải thiện điểm để tránh bị cảnh báo học vụ.</>,
  };
}

// Bảng màu chuẩn mực cho điểm chữ theo quy chế
function getGradeBadgeClass(grade: GradeScaleRow | null): string {
  if (!grade) return 'empty';
  if (grade.status === 'Không đạt') return 'grade-F';
  const letter = grade.letter;
  if (letter === 'A') return 'grade-A';
  if (letter === 'B+' || letter === 'B') return 'grade-B';
  if (letter === 'C+' || letter === 'C') return 'grade-C';
  if (letter === 'D+' || letter === 'D') return 'grade-D';
  return 'grade-F';
}

interface SheetState {
  courseId: string;
  isNew: boolean;
  courseTitle: string;
  credits: string;
  score10: string;
  courseGroup: CourseInput['courseGroup'];
}

export interface CreditWheelPickerProps {
  value: string;
  onChange: (val: string) => void;
  /** id của phần tử nhãn gắn với listbox */
  labelledBy?: string;
}

export function CreditWheelPicker({ value, onChange, labelledBy }: CreditWheelPickerProps) {
  const idPrefix = useId();
  const trackRef = useRef<HTMLDivElement>(null);
  const itemWidth = 72; // 72px gọn gàng, vuốt mượt mà vừa vặn
  const items = useMemo(() => ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10'], []);
  const selectedNum = value.trim() || '3';

  const initialNumRef = useRef(selectedNum);

  // Canh số được chọn vào đúng tâm khi mount (chỉ chạy một lần)
  useEffect(() => {
    const idx = items.indexOf(initialNumRef.current);
    if (idx !== -1 && trackRef.current) {
      trackRef.current.scrollLeft = idx * itemWidth;
    }
  }, [items]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const scrollLeft = e.currentTarget.scrollLeft;
    const centerIndex = Math.round(scrollLeft / itemWidth);
    const clamped = Math.max(0, Math.min(items.length - 1, centerIndex));
    const newVal = items[clamped];
    if (newVal !== value) {
      onChange(newVal);
    }
  };

  const handleItemClick = (num: string, idx: number) => {
    onChange(num);
    if (trackRef.current) {
      trackRef.current.scrollTo({ left: idx * itemWidth, behavior: 'smooth' });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const idx = Math.max(0, items.indexOf(selectedNum));
    let next: number;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') next = idx - 1;
    else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') next = idx + 1;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = items.length - 1;
    else return;
    e.preventDefault();
    next = Math.max(0, Math.min(items.length - 1, next));
    if (next !== idx) handleItemClick(items[next], next);
  };

  return (
    <div className="wheel-picker-wrapper">
      <div className="wheel-center-indicator" />
      <div
        ref={trackRef}
        className="wheel-picker-track"
        onScroll={handleScroll}
        role="listbox"
        aria-label="Số tín chỉ"
        aria-labelledby={labelledBy}
        aria-orientation="horizontal"
        tabIndex={0}
        aria-activedescendant={`${idPrefix}-opt-${selectedNum}`}
        onKeyDown={handleKeyDown}
      >
        {items.map((num, idx) => {
          const isActive = num === selectedNum;
          return (
            <div
              key={num}
              id={`${idPrefix}-opt-${num}`}
              role="option"
              aria-selected={isActive}
              className={`wheel-item ${isActive ? 'active' : ''}`}
              onClick={() => handleItemClick(num, idx)}
            >
              <span className="wheel-num">{num}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function GpaPage({ cohort, onNavigate }: GpaPageProps) {
  const [courses, setCourses] = useState<CourseInput[]>(() => createEmptyCourses(cohort));
  const [referenceModalTab, setReferenceModalTab] = useState<'scale' | 'rules' | null>(null);
  const [sheetState, setSheetState] = useState<SheetState | null>(null);
  const scoreInputsRef = useRef<(HTMLInputElement | null)[]>([]);

  const result = useMemo(() => calculateGpa(courses, cohort), [courses, cohort]);
  const groupOptions = getCourseGroupOptions(cohort);
  const hasResult = !result.error && result.totalCredits > 0;
  const academicTier = hasResult ? getAcademicTier(result.gpa) : null;
  const animatedGpa = useAnimatedNumber(hasResult ? result.gpa : 0, 2);

  // Điểm trung bình hệ 10 có trọng số theo tín chỉ của các môn hợp lệ đã nhập điểm thang 10
  const gpa10 = useMemo(() => {
    let weightedSum = 0;
    let totalValidCredits = 0;
    courses.forEach((course) => {
      const creds = Number(course.credits.trim().replace(',', '.'));
      const s10 = Number(course.score10.trim().replace(',', '.'));
      if (
        course.credits.trim() &&
        Number.isFinite(creds) &&
        creds > 0 &&
        course.score10.trim() &&
        Number.isFinite(s10) &&
        s10 >= 0 &&
        s10 <= 10
      ) {
        weightedSum += s10 * creds;
        totalValidCredits += creds;
      }
    });
    return totalValidCredits > 0 ? Math.round((weightedSum / totalValidCredits) * 100) / 100 : 0;
  }, [courses]);

  // Tổng tín chỉ dự kiến của toàn bộ bảng môn học
  const totalPlannedCredits = useMemo(() => {
    return courses.reduce((sum, course) => {
      const creds = Number(course.credits.trim().replace(',', '.'));
      return sum + (Number.isFinite(creds) && creds > 0 ? creds : 0);
    }, 0);
  }, [courses]);

  const courseStats = useMemo(() => {
    let passed = 0;
    const failedCourses: string[] = [];
    courses.forEach((course, index) => {
      const credits = Number(course.credits.trim().replace(',', '.'));
      if (!course.credits.trim() || !Number.isFinite(credits) || credits <= 0) return;
      const grade = getCourseGrade(course, cohort);
      if (!grade) return;
      if (grade.status === 'Đạt') passed++;
      else failedCourses.push(`Môn học ${index + 1} (${grade.letter})`);
    });
    return { passed, failed: failedCourses.length, failedCourses };
  }, [courses, cohort]);

  const stepCredits = (id: string, delta: number) => {
    setCourses((current) =>
      current.map((course) => {
        if (course.id !== id) return course;
        const currentVal = parseInt(course.credits.trim(), 10);
        const base = Number.isFinite(currentVal) ? currentVal : 3;
        const nextVal = Math.min(10, Math.max(1, base + delta));
        return { ...course, credits: String(nextVal) };
      })
    );
  };

  const updateCourse = (id: string, patch: Partial<CourseInput>) => {
    setCourses((current) => current.map((course) => (course.id === id ? { ...course, ...patch } : course)));
  };

  const addCourse = () => {
    setCourses((current) => [...current, newCourse(`course-${Date.now()}`, cohort)]);
  };

  const removeCourse = (id: string) => {
    setCourses((current) => (current.length > 1 ? current.filter((course) => course.id !== id) : current));
  };

  const resetCourses = () => {
    if (courses.some((course) => course.score10.trim() !== '')) {
      if (!window.confirm('Bạn có chắc chắn muốn làm mới (xóa trắng điểm) danh sách môn học không?')) {
        return;
      }
    }
    setCourses(createEmptyCourses(cohort));
  };

  // Open Bottom Sheet for Mobile
  const triggerElementRef = useRef<HTMLElement | null>(null);

  const invalidCoursesCount = useMemo(() => {
    return courses.filter((c) => isCreditsInvalid(c.credits) || isScore10Invalid(c.score10)).length;
  }, [courses]);
  const hasInvalidData = invalidCoursesCount > 0;

  // Keep the last valid semester GPA so the scholarship page can offer it (never while rows are invalid).
  const { profile, update: updateProfile } = useStudentProfile();
  const savedSemesterGpa = profile.lastSemesterGpa;
  const semesterGpaText = hasResult && !hasInvalidData ? result.gpa.toFixed(2) : null;
  const shareText =
    semesterGpaText && academicTier
      ? gpaShareText({ gpa: Number(semesterGpaText), tier: academicTier.label, credits: result.totalCredits, cohort })
      : null;
  useEffect(() => {
    if (semesterGpaText && semesterGpaText !== savedSemesterGpa) {
      const timer = window.setTimeout(() => updateProfile({ lastSemesterGpa: semesterGpaText }), 400);
      return () => window.clearTimeout(timer);
    }
  }, [semesterGpaText, savedSemesterGpa, updateProfile]);

  const closeSheet = () => {
    setSheetState(null);
    if (triggerElementRef.current && typeof triggerElementRef.current.focus === 'function') {
      setTimeout(() => triggerElementRef.current?.focus(), 50);
    }
  };

  useEffect(() => {
    if (!sheetState) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeSheet();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [sheetState]);

  const handleOpenEditSheet = (course: CourseInput, index: number, el?: HTMLElement) => {
    triggerElementRef.current = el || (document.activeElement as HTMLElement) || null;
    setSheetState({
      courseId: course.id,
      isNew: false,
      courseTitle: `Môn học ${index + 1}`,
      credits: course.credits || '3',
      score10: course.score10,
      courseGroup: course.courseGroup ?? getDefaultCourseGroup(cohort),
    });
  };

  const handleOpenAddSheet = (el?: HTMLElement) => {
    triggerElementRef.current = el || (document.activeElement as HTMLElement) || null;
    const newId = `course-${Date.now()}`;
    setSheetState({
      courseId: newId,
      isNew: true,
      courseTitle: `Môn học ${courses.length + 1}`,
      credits: '3',
      score10: '',
      courseGroup: getDefaultCourseGroup(cohort),
    });
  };

  const sheetPreviewGrade = useMemo(() => {
    if (!sheetState || !sheetState.score10.trim()) return null;
    if (isScore10Invalid(sheetState.score10)) return null;
    const tempCourse: CourseInput = {
      id: sheetState.courseId,
      name: '',
      credits: sheetState.credits,
      inputType: 'score10',
      score10: sheetState.score10,
      letter: '',
      courseGroup: sheetState.courseGroup,
    };
    return getCourseGrade(tempCourse, cohort);
  }, [sheetState, cohort]);

  const handleSaveSheet = () => {
    if (!sheetState) return;
    const credErr = isCreditsInvalid(sheetState.credits);
    const scoreErr = isScore10Invalid(sheetState.score10);
    if (credErr || scoreErr) {
      return;
    }
    const finalCredits = sheetState.credits.trim() || '3';
    if (sheetState.isNew) {
      const newCourseObj: CourseInput = {
        id: sheetState.courseId,
        name: '',
        credits: finalCredits,
        inputType: 'score10',
        score10: sheetState.score10,
        letter: '',
        courseGroup: sheetState.courseGroup,
      };
      setCourses((curr) => [...curr, newCourseObj]);
    } else {
      updateCourse(sheetState.courseId, {
        credits: finalCredits,
        score10: sheetState.score10,
        courseGroup: sheetState.courseGroup,
      });
    }
    closeSheet();
  };

  const handleDeleteFromSheet = () => {
    if (!sheetState || sheetState.isNew) return;
    removeCourse(sheetState.courseId);
    closeSheet();
  };

  const progressPercent = hasResult ? Math.min(100, Math.max(0, (result.gpa / 4.0) * 100)) : 0;

  const milestoneMotivation = useMemo(() => {
    if (!hasResult) {
      return (
        <span className="gpa-d-motivation-text">
          Nhập điểm hệ 10 ở bảng bên trái để xem dự báo học lực
        </span>
      );
    }
    const gpa = result.gpa;
    if (gpa >= 3.6) {
      return (
        <span className="gpa-d-motivation-text">
          Bạn đạt học lực <strong>Xuất sắc</strong>
        </span>
      );
    }
    if (gpa >= 3.2) {
      const diff = (3.6 - gpa).toFixed(2);
      return (
        <span className="gpa-d-motivation-text">
          Cách mức <strong className="gpa-motivate-highlight">Xuất sắc (3.60)</strong> còn <strong className="gpa-motivate-highlight">+{diff}</strong> điểm
        </span>
      );
    }
    if (gpa >= 2.5) {
      const diff = (3.2 - gpa).toFixed(2);
      return (
        <span className="gpa-d-motivation-text">
          Cách mức <strong className="gpa-motivate-highlight">Giỏi (3.20)</strong> còn <strong className="gpa-motivate-highlight">+{diff}</strong> điểm
        </span>
      );
    }
    if (gpa >= 2.0) {
      const diff = (2.5 - gpa).toFixed(2);
      return (
        <span className="gpa-d-motivation-text">
          Cách mức <strong className="gpa-motivate-highlight">Khá (2.50)</strong> còn <strong className="gpa-motivate-highlight">+{diff}</strong> điểm
        </span>
      );
    }
    const diff = (2.0 - gpa).toFixed(2);
    return (
      <span className="gpa-d-motivation-text">
        Cách mức <strong className="gpa-motivate-highlight">Trung bình (2.00)</strong> còn <strong className="gpa-motivate-highlight">+{diff}</strong> điểm
      </span>
    );
  }, [hasResult, result.gpa]);

  return (
    <div className="page-container tool-page simplified gpa-page-wrapper">
      
      {/* HEADER DESKTOP */}
      <ToolPageHeader
        icon={GraduationCap}
        title="Tính GPA học kỳ"
        description={
          <>
            Tính điểm trung bình học kỳ và xác định xếp loại học lực theo quy chế <strong>{cohort}</strong>.
          </>
        }
      />

      {/* ============================================================== */}
      {/* 1. BẢN DESKTOP 2 CỘT CÂN ĐỐI (KHỚP 100% PROTOTYPE V2.3)        */}
      {/* ============================================================== */}
      <div className="gpa-desktop-layout">
        
        {/* CỘT TRÁI (7 Cols): BẢNG MÔN HỌC LIỀN KHỐI (4 CỘT CÂN ĐỐI) */}
        <div className="gpa-d-table-card">
          
          {/* TOOLBAR ĐẦU BẢNG */}
          <div className="gpa-d-toolbar">
            <div className="gpa-d-toolbar-title">
              <span className="tool-step-badge">1</span>
              <span className="gpa-d-table-heading">BẢNG MÔN HỌC</span>
              <span className="gpa-d-table-badge">
                {courses.length} môn • {totalPlannedCredits} TC
              </span>
            </div>

            <button
              type="button"
              className="gpa-d-reset-btn"
              onClick={resetCourses}
              title="Làm mới điểm để nhập lại"
            >
              <RotateCcw size={14} />
              <span>Đặt lại</span>
            </button>
          </div>

          {/* BẢNG 4 CỘT CÂN ĐỐI (26% | 24% | 24% | 26%) */}
          <table className="gpa-d-table gpa-d-course-table">
            <thead className="gpa-d-thead">
              <tr>
                <th style={{ width: '26%', paddingLeft: '1.25rem' }}>Môn học</th>
                <th style={{ width: '22%', textAlign: 'center' }}>Tín chỉ</th>
                <th style={{ width: '22%', textAlign: 'center' }}>Điểm hệ 10</th>
                <th style={{ width: '24%', textAlign: 'center' }}>Quy đổi</th>
                <th className="gpa-d-delete-cell"><span className="sr-only">Xóa môn</span></th>
              </tr>
            </thead>
            <tbody className="gpa-d-tbody">
              {courses.map((course, index) => {
                const grade = getCourseGrade(course, cohort);
                const isScoreErr = isScore10Invalid(course.score10);
                const isCreditsErr = isCreditsInvalid(course.credits);
                const hasScore = course.score10.trim() !== '';

                return (
                  <tr key={course.id}>
                    {/* Cột 1: MÔN HỌC */}
                    <td style={{ paddingLeft: '1.25rem' }}>
                      <div className="gpa-d-course-info">
                        <span className="gpa-d-course-name">Môn học {index + 1}</span>
                        {isSplitGradeCohort(cohort) && (
                          <select
                            className="gpa-d-group-select-compact"
                            value={course.courseGroup ?? getDefaultCourseGroup(cohort)}
                            onChange={(e) => updateCourse(course.id, { courseGroup: e.target.value as CourseInput['courseGroup'] })}
                            aria-label={`Nhóm môn của Môn học ${index + 1}`}
                          >
                            {groupOptions.map((opt) => (
                              <option key={opt.id} value={opt.id}>
                                {opt.shortLabel}
                              </option>
                            ))}
                          </select>
                        )}
                      </div>
                    </td>

                    {/* Cột 2: TÍN CHỈ (Stepper Capsule) */}
                    <td style={{ textAlign: 'center' }}>
                      <div className="gpa-d-input-wrap">
                        <div className={`gpa-d-credit-capsule ${isCreditsErr ? 'input-error' : ''}`}>
                          <button
                            type="button"
                            className="credit-step-btn"
                            onClick={() => stepCredits(course.id, -1)}
                            aria-label={`Giảm 1 tín chỉ cho Môn học ${index + 1}`}
                          >
                            −
                          </button>
                          <input
                            type="text"
                            inputMode="numeric"
                            className="credit-val-input"
                            value={course.credits}
                            onChange={(e) => updateCourse(course.id, { credits: sanitizeDecimal(e.target.value) })}
                            aria-label={`Số tín chỉ Môn học ${index + 1}`}
                            aria-invalid={isCreditsErr}
                          />
                          <button
                            type="button"
                            className="credit-step-btn"
                            onClick={() => stepCredits(course.id, 1)}
                            aria-label={`Tăng 1 tín chỉ cho Môn học ${index + 1}`}
                          >
                            +
                          </button>
                        </div>
                        {isCreditsErr && <span className="gpa-d-error-tag">1 – 10 TC</span>}
                      </div>
                    </td>

                    {/* Cột 3: ĐIỂM HỆ 10 */}
                    <td style={{ textAlign: 'center' }}>
                      <div className="gpa-d-input-wrap">
                        <input
                          ref={(el) => {
                            scoreInputsRef.current[index] = el;
                          }}
                          type="text"
                          inputMode="decimal"
                          className={`gpa-d-score10-input ${
                            isScoreErr ? 'input-error' : hasScore ? 'has-score' : ''
                          }`}
                          value={course.score10}
                          onChange={(e) => updateCourse(course.id, { score10: sanitizeDecimal(e.target.value) })}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              if (index + 1 < courses.length) {
                                scoreInputsRef.current[index + 1]?.focus();
                                scoreInputsRef.current[index + 1]?.select();
                              }
                            }
                          }}
                          placeholder="VD: 8.5"
                          aria-label={`Điểm hệ 10 Môn học ${index + 1}`}
                          aria-invalid={isScoreErr}
                        />
                        {isScoreErr && <span className="gpa-d-error-tag">0 – 10 đ</span>}
                      </div>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                        {grade && !isScoreErr && !isCreditsErr ? (
                          <span className={`gpa-d-grade-badge ${getGradeBadgeClass(grade)}`}>
                            <span>{grade.letter}</span>
                            <span className="gpa-d-badge-sub">({grade.score4.toFixed(1)})</span>
                          </span>
                        ) : (
                          <span className="gpa-d-grade-badge empty">
                            {isScoreErr || isCreditsErr ? 'Lỗi' : '—'}
                          </span>
                        )}

                    </td>
                    <td className="gpa-d-delete-cell">
                        <button
                          type="button"
                          className="gpa-d-del-btn"
                          onClick={() => removeCourse(course.id)}
                          disabled={courses.length <= 1}
                          title={courses.length <= 1 ? 'Cần giữ ít nhất 1 môn' : 'Xóa môn này'}
                          aria-label={`Xóa Môn học ${index + 1}`}
                        >
                          <Trash2 size={15} />
                        </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* CHÂN BẢNG: NÚT THÊM MÔN VIỀN NÉT ĐỨT */}
          <div className="gpa-d-add-wrapper">
            <button type="button" className="gpa-d-add-dashed-btn" onClick={addCourse}>
              <Plus size={15} />
              <span>Thêm môn học</span>
            </button>
          </div>

        </div>

        {/* CỘT PHẢI (5 Cols): THẺ KẾT QUẢ DỰ TÍNH CỐ ĐỊNH (TINH GỌN, SẮC NÉT) */}
        <div className="gpa-d-sticky-col">
          <div className="gpa-d-result-card">
            
            {/* Header Kết Quả */}
            <div className="gpa-d-result-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="tool-step-badge">2</span>
                <span className="gpa-d-result-title">KẾT QUẢ DỰ TÍNH</span>
              </div>
              {hasResult && academicTier ? (
                <span className={`gpa-d-result-badge tier-${academicTier.tone}`}>
                  Học lực {academicTier.label}
                </span>
              ) : (
                <span className="gpa-d-result-badge unranked">
                  • Chưa xếp loại
                </span>
              )}
            </div>

            {/* Cảnh Báo Khi Có Dữ Liệu Sai */}
            {hasInvalidData && (
              <div className="gpa-d-error-banner" role="alert">
                <AlertTriangle size={16} aria-hidden="true" style={{ flexShrink: 0, marginTop: '0.05rem' }} />
                <span>
                  Có <strong>{invalidCoursesCount}</strong> môn nhập điểm/tín chỉ chưa hợp lệ (xem ô viền đỏ).
                </span>
              </div>
            )}

            {/* Khu vực Điểm Trung Tâm */}
            <div className="gpa-d-hero-score-box">
              <div className="gpa-d-hero-sub">
                ĐIỂM TRUNG BÌNH HỌC KỲ
              </div>
              <div className="gpa-d-hero-score-row">
                <span className="gpa-d-hero-score">{hasResult ? animatedGpa.toFixed(2) : '--'}</span>
                <span className="gpa-d-hero-max">/ 4.00</span>
              </div>

              <div className="gpa-d-gpa10-pill">
                <span className="gpa-d-gpa10-label">Trung bình hệ 10:</span>
                <strong className="gpa-d-gpa10-val">
                  {hasResult ? `${gpa10.toFixed(2)} / 10` : '-- / 10'}
                </strong>
              </div>
            </div>

            {/* Khung Thanh Tiến Độ Cột Mốc Học Lực */}
            <div className="gpa-d-milestone-box">
              <div className="gpa-d-milestone-labels">
                  <span>0.0</span><span>TB 2.0</span>
                  <span className="gpa-milestone-blue">Khá 2.5</span>
                  <span className="gpa-milestone-green">Giỏi 3.2</span>
                  <span className="gpa-milestone-amber">XS 3.6</span>
                </div>
                <div className="gpa-d-milestone-bar-wrap">
                  <div className="gpa-d-milestone-bar-fill" style={{ width: `${progressPercent}%` }} />
                  <div className="gpa-d-milestone-tick" style={{ left: '50%' }} title="Trung bình (2.0)" />
                  <div className="gpa-d-milestone-tick" style={{ left: '62.5%' }} title="Khá (2.5)" />
                  <div className="gpa-d-milestone-tick" style={{ left: '80%' }} title="Giỏi (3.2)" />
                  <div className="gpa-d-milestone-tick" style={{ left: '90%' }} title="Xuất sắc (3.6)" />
                </div>

              <div className="gpa-d-milestone-prompt">
                {milestoneMotivation}
              </div>
            </div>

            {/* 3 Ô Thống Kê Gọn Gàng */}
            <div className="gpa-d-stats-grid">
              <div className="gpa-d-stat-box">
                <span className="gpa-d-stat-label">Tín chỉ</span>
                <span className="gpa-d-stat-val">{hasResult ? result.totalCredits : 0}</span>
              </div>
              <div className={`gpa-d-stat-box ${courseStats.passed > 0 ? 'passed' : ''}`}>
                <span className="gpa-d-stat-label">Môn đạt</span>
                <span className="gpa-d-stat-val">{courseStats.passed}</span>
              </div>
              <div className="gpa-d-stat-box">
                <span className="gpa-d-stat-label">Môn rớt</span>
                <span className="gpa-d-stat-val" style={{ color: courseStats.failed > 0 ? '#ef4444' : undefined }}>
                  {courseStats.failed}
                </span>
              </div>
            </div>

            {/* Thanh Tính điểm xét học bổng 1 dòng duy nhất */}
            <div className="gpa-d-scholarship-prompt">
              <div className="gpa-d-scholarship-left">

                <span>Đủ điều kiện xét học bổng?</span>
              </div>
              <button
                type="button"
                className="gpa-d-scholarship-btn"
                onClick={() => onNavigate?.('scholarship')}
              >
                Xem học bổng →
              </button>
            </div>

            {/* Footer */}
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
      {/* 2. BẢN MOBILE NATIVE TINH GỌN (CHO PHÉP GÕ TRỰC TIẾP HOẶC SHEET) */}
      {/* ============================================================== */}
      <div className="gpa-mobile-layout">
        
        {/* TIÊU ĐỀ MOBILE GỌN 1 HÀNG */}
        <div className="gpa-m-page-header">
          <div className="gpa-m-title-wrap">
            <GraduationCap size={20} className="gpa-m-title-icon" aria-hidden="true" />
            <h1 className="gpa-m-page-title">Tính GPA học kỳ</h1>
          </div>
        </div>

        {/* MOBILE HERO SCORE CARD */}
        <div className="gpa-mobile-hero-container">
          <div className="gpa-mobile-hero-card">
            <div className="gpa-m-hero-label">GPA HỌC KỲ DỰ TÍNH</div>
            <div className="gpa-m-score-row">
              <span className="gpa-m-score-val">{hasResult ? animatedGpa.toFixed(2) : '--'}</span>
              <span className="gpa-m-score-max">/ 4.00</span>
            </div>

            {/* Viên thuốc hợp nhất (Capsule đồng nhất, bỏ nền xanh lá chói) */}
            <div className="gpa-m-capsule-wrap">
              {hasResult && academicTier ? (
                <div className="gpa-m-capsule">
                  <span className={`gpa-m-tier-text tier-${academicTier.tone}`}>
                    {academicTier.label}
                  </span>
                  <span className="gpa-m-sep">│</span>
                  <span className="gpa-m-stat-item">
                    <span className="gpa-m-unit">Hệ 10:</span> <strong>{gpa10.toFixed(2)}</strong>
                  </span>
                  <span className="gpa-m-sep">│</span>
                  <span className="gpa-m-stat-item">
                    <strong>{result.totalCredits}</strong> <span className="gpa-m-unit">TC</span>
                  </span>
                  <span className="gpa-m-bullet">•</span>
                  <span className="gpa-m-stat-item">
                    <strong>{courseStats.passed}/{result.countedCourses}</strong> <span className="gpa-m-unit">môn đạt</span>
                  </span>
                </div>
              ) : (
                <div className="gpa-m-capsule empty">
                  <span>Chạm vào môn bên dưới để nhập</span>
                </div>
              )}
            </div>

            

            {hasInvalidData && (
              <div className="gpa-m-hero-alert" role="alert">
                <AlertTriangle size={14} aria-hidden="true" />
                <span>{invalidCoursesCount} môn học nhập sai dữ liệu</span>
              </div>
            )}
          </div>

          {/* GỢI Ý HỌC BỔNG BÊN NGOÀI CARD */}
          {hasResult && result.gpa >= 2.5 && (
            <div className="gpa-m-scholarship-banner">
              <div className="gpa-d-scholarship-left">

                <span>Đủ điều kiện xét học bổng?</span>
              </div>
              <button
                type="button"
                className="gpa-d-scholarship-btn"
                onClick={() => (onNavigate ? onNavigate('scholarship') : undefined)}
              >
                Xem học bổng →
              </button>
            </div>
          )}
        </div>

        {/* TOOLBAR MOBILE */}
        <div className="gpa-m-toolbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span className="tool-step-badge">1</span>
            <span className="gpa-m-toolbar-count">Môn học ({courses.length})</span>
          </div>

          <button
            type="button"
            className="gpa-m-reset-btn"
            onClick={resetCourses}
          >
            <RotateCcw size={13} />
            <span>Đặt lại</span>
          </button>
        </div>

        {/* INSET GROUPED LIST MOBILE */}
        <div className="gpa-mobile-grouped-list">
          <div className="gpa-m-list-card">
            {courses.map((course, index) => {
              const grade = getCourseGrade(course, cohort);
              const isScoreErr = isScore10Invalid(course.score10);
              const isCreditsErr = isCreditsInvalid(course.credits);
              const isCourseInvalid = isScoreErr || isCreditsErr;
              const hasScore = course.score10.trim() !== '';
              const isFailed = !isCourseInvalid && grade?.status === 'Không đạt';
              const groupOption = groupOptions.find((o) => o.id === (course.courseGroup ?? getDefaultCourseGroup(cohort)));

              return (
                <div
                  key={course.id}
                  className={`gpa-m-list-row ${isCourseInvalid ? 'row-invalid' : isFailed ? 'row-failed' : ''}`}
                  onClick={(e) => handleOpenEditSheet(course, index, e.currentTarget)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleOpenEditSheet(course, index, e.currentTarget);
                    }
                  }}
                  aria-label={`Chỉnh sửa Môn học ${index + 1}`}
                >
                  <div className="gpa-m-row-left">
                    <span className="gpa-m-row-title">Môn học {index + 1}</span>
                    <span className="gpa-m-row-desc">
                      {isCreditsErr ? (
                        <span style={{ color: '#ef4444', fontWeight: 600 }}>Sai tín chỉ</span>
                      ) : course.credits ? (
                        `${course.credits} tín chỉ`
                      ) : (
                        'Chưa có TC'
                      )}{' '}
                      {isSplitGradeCohort(cohort) ? `• ${groupOption?.shortLabel || 'Đại cương'}` : ''}
                    </span>
                  </div>

                  <div className="gpa-m-row-right">
                    {isCourseInvalid ? (
                      <span className="gpa-m-row-badge error">Sai dữ liệu</span>
                    ) : hasScore ? (
                      <span className="gpa-m-row-score">{course.score10}</span>
                    ) : (
                      <span className="gpa-m-row-placeholder">--</span>
                    )}

                    {grade && !isCourseInvalid ? (
                      <span className={`gpa-m-row-badge ${getGradeBadgeClass(grade)}`}>
                        {grade.letter}
                      </span>
                    ) : (
                      <span className="gpa-m-row-badge empty">—</span>
                    )}

                    <span className="gpa-m-row-chevron">›</span>
                  </div>
                </div>
              );
            })}

            {/* NÚT THÊM MÔN Ở CHÂN DANH SÁCH MOBILE */}
            <button
              type="button"
              className="gpa-m-add-row-btn"
              onClick={(e) => handleOpenAddSheet(e.currentTarget)}
              aria-label="Thêm môn học mới"
            >
              <span>+ Thêm môn học</span>
            </button>
          </div>
        </div>

      </div>

      {/* ============================================================== */}
      {/* 3. MOBILE 1-TOUCH BOTTOM SHEET EDITOR                           */}
      {/* ============================================================== */}
      {sheetState && (
        <div className="gpa-m-sheet-overlay" onClick={closeSheet}>
          <div
            className="gpa-m-sheet-container"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="gpa-sheet-title"
          >
            {/* Grab Handle */}
            <div className="gpa-m-sheet-handle-bar">
              <div className="gpa-m-sheet-handle" />
            </div>

            {/* Header */}
            <div className="gpa-m-sheet-header">
              <h3 id="gpa-sheet-title" className="gpa-m-sheet-title">
                {sheetState.courseTitle}
              </h3>
              <button
                type="button"
                className="gpa-m-sheet-close-btn"
                onClick={closeSheet}
                aria-label="Đóng bảng chỉnh sửa"
              >
                <X size={18} />
              </button>
            </div>

            {/* Content Body */}
            <div className="gpa-m-sheet-body">
              {(() => {
                const sheetCredErr = isCreditsInvalid(sheetState.credits);
                const sheetScoreErr = isScore10Invalid(sheetState.score10);

                return (
                  <>
                    {/* 1. Số tín chỉ: Con lăn thước cuộn (Wheel Picker) */}
                    <div className="gpa-m-sheet-field">
                      <div className="gpa-m-sheet-label-row">
                        <span id="gpa-sheet-credits-label" className="gpa-m-sheet-label" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}><span className="tool-step-badge" style={{ width: '18px', height: '18px', fontSize: '0.65rem' }}>1</span><span>Số tín chỉ</span></span>
                        <span className="gpa-m-sheet-hint">
                          {sheetState.credits ? `${sheetState.credits} tín chỉ` : '3 tín chỉ'}
                        </span>
                      </div>
                      <CreditWheelPicker
                        labelledBy="gpa-sheet-credits-label"
                        value={sheetState.credits}
                        onChange={(val) => setSheetState((s) => (s ? { ...s, credits: val } : null))}
                      />
                    </div>

                    {/* 2. Điểm môn học thang 10 */}
                    <div className="gpa-m-sheet-field">
                      <div className="gpa-m-sheet-label-row">
                        <label className="gpa-m-sheet-label" htmlFor="gpa-sheet-score-input">
                          2. Điểm môn học (Thang 10)
                        </label>
                        {sheetPreviewGrade && !sheetScoreErr && (
                          <span className={`gpa-m-sheet-live-preview ${getGradeBadgeClass(sheetPreviewGrade)}`}>
                            Quy đổi: <strong>{sheetPreviewGrade.letter}</strong> ({sheetPreviewGrade.score4.toFixed(1)})
                          </span>
                        )}
                      </div>

                      <div className={`gpa-m-score-input-wrap ${sheetScoreErr ? 'input-error' : ''}`}>
                        <input
                          id="gpa-sheet-score-input"
                          type="text"
                          inputMode="decimal"
                          className="gpa-m-score-input"
                          value={sheetState.score10}
                          onChange={(e) => {
                            const val = sanitizeDecimal(e.target.value);
                            setSheetState((s) => (s ? { ...s, score10: val } : null));
                          }}
                          placeholder="VD: 8.5"
                          autoFocus
                          aria-label="Nhập điểm thang 10"
                          aria-invalid={sheetScoreErr}
                        />
                      </div>

                      {sheetScoreErr && (
                        <span className="gpa-m-inline-error">
                          <AlertTriangle size={13} aria-hidden="true" />
                          Điểm phải từ 0.0 đến 10.0
                        </span>
                      )}
                    </div>

                    {/* 3. Phân loại môn (chỉ hiển thị nếu quy chế yêu cầu) */}
                    {isSplitGradeCohort(cohort) && (
                      <div className="gpa-m-sheet-field">
                        <label className="gpa-m-sheet-label">3. Phân loại môn học</label>
                        <div className="gpa-m-sheet-group-grid">
                          {groupOptions.map((option) => (
                            <button
                              key={option.id}
                              type="button"
                              className={`gpa-m-group-pill ${sheetState.courseGroup === option.id ? 'active' : ''}`}
                              onClick={() => setSheetState((s) => (s ? { ...s, courseGroup: option.id } : null))}
                            >
                              {option.shortLabel}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 4. Nút hành động */}
                    <div className="gpa-m-sheet-actions">
                      <button
                        type="button"
                        className={`gpa-m-sheet-save-btn ${sheetCredErr || sheetScoreErr ? 'disabled' : ''}`}
                        onClick={handleSaveSheet}
                        disabled={sheetCredErr || sheetScoreErr}
                      >
                        {sheetState.isNew ? 'Thêm môn học' : 'Lưu thay đổi'}
                      </button>

                      {!sheetState.isNew && courses.length > 1 && (
                        <button type="button" className="gpa-m-sheet-del-btn" onClick={handleDeleteFromSheet}>
                          <Trash2 size={16} />
                          <span>Xóa môn này</span>
                        </button>
                      )}
                    </div>
                  </>
                );
              })()}
            </div>
          </div>
        </div>
      )}

      {/* MODAL QUY CHẾ VÀ BẢNG ĐIỂM */}
      <GpaReferenceModal
        isOpen={referenceModalTab !== null}
        onClose={() => setReferenceModalTab(null)}
        cohort={cohort}
        initialTab={referenceModalTab ?? 'scale'}
      />
    </div>
  );
}
