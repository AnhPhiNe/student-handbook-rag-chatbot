import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { GraduationCap, Plus, Trash2, X, RotateCcw } from 'lucide-react';
import {
  calculateGpa,
  getCourseGrade,
  getCourseGroupOptions,
  getDefaultCourseGroup,
  isCreditsInvalid,
  isScore10Invalid,
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
    credits: '',
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

interface CreditWheelPickerProps {
  value: string;
  onChange: (val: string) => void;
}

function CreditWheelPicker({ value, onChange }: CreditWheelPickerProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const itemWidth = 72; // 72px gọn gàng, vuốt mượt mà vừa vặn
  const items = useMemo(() => ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10'], []);
  const selectedNum = value.trim();

  // Canh số được chọn vào đúng tâm khi mount hoặc khi ô nhập đổi giá trị
  useEffect(() => {
    const idx = items.indexOf(selectedNum);
    if (idx !== -1 && trackRef.current) {
      trackRef.current.scrollTo({ left: idx * itemWidth, behavior: 'smooth' });
    }
  }, [selectedNum, items]);

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

  return (
    <div className="wheel-picker-wrapper">
      <div className="wheel-center-indicator" />
      <div ref={trackRef} className="wheel-picker-track" onScroll={handleScroll}>
        {items.map((num, idx) => {
          const isActive = num === selectedNum;
          return (
            <button
              type="button"
              key={num}
              className={`wheel-item ${isActive ? 'active' : ''}`}
              onClick={() => handleItemClick(num, idx)}
              aria-label={`Chọn ${num} tín chỉ`}
            >
              <span className="wheel-num">{num}</span>
            </button>
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

  const result = useMemo(() => calculateGpa(courses, cohort), [courses, cohort]);
  const groupOptions = getCourseGroupOptions(cohort);
  const hasResult = !result.error && result.totalCredits > 0;
  const academicTier = hasResult ? getAcademicTier(result.gpa) : null;
  const animatedGpa = useAnimatedNumber(hasResult ? result.gpa : 0, 2);

  const courseStats = useMemo(() => {
    let passed = 0;
    const failedCourses: string[] = [];
    courses.forEach((course, index) => {
      const credits = Number(course.credits.trim().replace(',', '.'));
      if (!course.credits.trim() || !Number.isFinite(credits) || credits <= 0) return;
      const grade = getCourseGrade(course, cohort);
      if (!grade) return;
      if (grade.status === 'Đạt') passed++;
      else failedCourses.push(`Học phần ${index + 1} (${grade.letter})`);
    });
    return { passed, failed: failedCourses.length, failedCourses };
  }, [courses, cohort]);

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
    if (courses.some((course) => course.name || course.credits || course.score10)) {
      if (!window.confirm('Bạn có chắc chắn muốn làm mới (xóa trắng) danh sách môn học không?')) {
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
      courseTitle: `Học phần ${index + 1}`,
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
      courseTitle: `Học phần ${courses.length + 1}`,
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
      return; // Chặn lưu dữ liệu sai
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

  return (
    <div className="page-container tool-page simplified gpa-page-wrapper">
      
      {/* HEADER DESKTOP */}
      <ToolPageHeader
        icon={GraduationCap}
        title="Tính GPA học kỳ"
        description={
          <>
            Tính điểm trung bình học kỳ và dự báo xếp loại học lực theo quy chế <strong>{cohort}</strong>.
          </>
        }
      />

      {/* ============================================================== */}
      {/* 1. BẢN DESKTOP CHUẨN MỰC: 2 CỘT SONG SONG (ĐÚNG NHƯ BẢN THẢO LUẬN) */}
      {/* ============================================================== */}
      <div className="gpa-desktop-layout">
        
        {/* CỘT TRÁI (65%): BẢNG NHẬP LIỆU LIỀN KHỐI (UNIFIED TABLE CARD) */}
        <div className="gpa-d-table-card">
          
          {/* TOOLBAR TÍCH HỢP TRÊN ĐẦU BẢNG */}
          <div className="gpa-d-toolbar">
            <div className="gpa-d-toolbar-title">
              <span className="gpa-d-table-heading">Bảng môn học</span>
              <span className="gpa-d-table-sub">({courses.length} học phần)</span>
            </div>

            <button
              type="button"
              className="gpa-d-reset-btn"
              onClick={resetCourses}
              title="Xóa trắng để nhập lại"
            >
              <RotateCcw size={14} />
              <span>Đặt lại</span>
            </button>
          </div>

          {/* BẢNG HỌC PHẦN */}
          <table className="gpa-d-table">
            <thead className="gpa-d-thead">
              <tr>
                <th style={{ width: '18%', paddingLeft: '1.25rem' }}>Học phần</th>
                <th style={{ width: '28%' }}>Nhóm môn</th>
                <th style={{ width: '14%', textAlign: 'center' }}>Tín chỉ</th>
                <th style={{ width: '16%', textAlign: 'center' }}>Điểm thang 10</th>
                <th style={{ width: '16%', textAlign: 'center' }}>Quy đổi</th>
                <th style={{ width: '8%', paddingRight: '1rem', textAlign: 'center' }}></th>
              </tr>
            </thead>
            <tbody className="gpa-d-tbody">
              {courses.map((course, index) => {
                const grade = getCourseGrade(course, cohort);
                const isScoreErr = isScore10Invalid(course.score10);
                const isCreditsErr = isCreditsInvalid(course.credits);

                return (
                  <tr key={course.id}>
                    <td style={{ paddingLeft: '1.25rem' }}>
                      <span className="gpa-d-course-name">Học phần {index + 1}</span>
                    </td>
                    <td>
                      <select
                        className="gpa-d-group-select"
                        value={course.courseGroup ?? getDefaultCourseGroup(cohort)}
                        onChange={(e) => updateCourse(course.id, { courseGroup: e.target.value as CourseInput['courseGroup'] })}
                        aria-label={`Nhóm môn của Học phần ${index + 1}`}
                      >
                        {groupOptions.map((opt) => (
                          <option key={opt.id} value={opt.id}>
                            {opt.shortLabel}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <div className="gpa-d-input-wrap">
                        <input
                          type="text"
                          inputMode="decimal"
                          className={`gpa-d-cred-input ${isCreditsErr ? 'input-error' : ''}`}
                          value={course.credits}
                          onChange={(e) => updateCourse(course.id, { credits: sanitizeDecimal(e.target.value) })}
                          placeholder="--"
                          aria-label={`Số tín chỉ Học phần ${index + 1}`}
                          aria-invalid={isCreditsErr}
                        />
                        {isCreditsErr && <span className="gpa-d-error-tag">1 – 30 TC</span>}
                      </div>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <div className="gpa-d-input-wrap">
                        <input
                          type="text"
                          inputMode="decimal"
                          className={`gpa-d-score-input ${isScoreErr ? 'input-error' : ''}`}
                          value={course.score10}
                          onChange={(e) => updateCourse(course.id, { score10: sanitizeDecimal(e.target.value) })}
                          placeholder="--"
                          aria-label={`Điểm thang 10 Học phần ${index + 1}`}
                          aria-invalid={isScoreErr}
                        />
                        {isScoreErr && <span className="gpa-d-error-tag">0 – 10 đ</span>}
                      </div>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {grade && !isScoreErr && !isCreditsErr ? (
                        <span className={`gpa-d-grade-badge ${getGradeBadgeClass(grade)}`}>
                          <strong>{grade.letter}</strong>
                          <span style={{ marginLeft: '4px', opacity: 0.85 }}>({grade.score4.toFixed(1)})</span>
                        </span>
                      ) : (
                        <span className="gpa-d-grade-badge empty">{isScoreErr || isCreditsErr ? 'Lỗi' : '—'}</span>
                      )}
                    </td>
                    <td style={{ paddingRight: '1rem', textAlign: 'center' }}>
                      <button
                        type="button"
                        className="gpa-d-del-btn"
                        onClick={() => removeCourse(course.id)}
                        disabled={courses.length <= 1}
                        title={courses.length <= 1 ? 'Cần giữ ít nhất 1 môn' : 'Xóa môn này'}
                        aria-label={`Xóa Học phần ${index + 1}`}
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* NÚT THÊM MÔN HỌC LIỀN KHỐI Ở ĐÁY BẢNG */}
          <button type="button" className="gpa-d-add-btn" onClick={addCourse}>
            <Plus size={16} />
            <span>Thêm môn học</span>
          </button>

        </div>

        {/* CỘT PHẢI (35%): CARD KẾT QUẢ DỰ TÍNH CỐ ĐỊNH (STICKY RESULT CARD) */}
        <div className="gpa-d-sticky-col">
          <div className="gpa-d-result-card">
            
            {/* Header Kết Quả */}
            <div className="gpa-d-result-header">
              <span className="gpa-d-result-title">Kết quả dự tính</span>
              {academicTier ? (
                <span className={`gpa-d-result-badge tier-${academicTier.tone}`}>
                  • {academicTier.label}
                </span>
              ) : (
                <span className="gpa-d-result-badge" style={{ opacity: 0.6 }}>
                  • Chưa xếp loại
                </span>
              )}
            </div>

            {/* Cảnh Báo Khi Có Dữ Liệu Sai */}
            {hasInvalidData && (
              <div className="gpa-d-error-banner" role="alert">
                <span style={{ fontSize: '1.05rem', lineHeight: 1 }}>⚠️</span>
                <span>
                  Có <strong>{invalidCoursesCount}</strong> học phần nhập sai dữ liệu. Vui lòng kiểm tra lại các ô có viền đỏ.
                </span>
              </div>
            )}

            {/* Con Số GPA To Bản */}
            <div className="gpa-d-score-section">
              <span className="gpa-d-score-sub">
                GPA học kỳ {hasInvalidData ? `(Tạm tính ${result.countedCourses}/${courses.length} môn)` : `(Tính ${result.countedCourses}/${courses.length} môn)`}
              </span>
              <div className="gpa-d-score-row">
                <span className="gpa-d-big-val">{hasResult ? animatedGpa.toFixed(2) : '--'}</span>
                <span className="gpa-d-big-max">/ 4.00</span>
              </div>
              
              {/* Thanh tiến độ */}
              <div className="gpa-d-bar-track">
                <div
                  className="gpa-d-bar-fill"
                  style={{
                    width: `${progressPercent}%`,
                    backgroundColor: academicTier?.tone === 'danger' ? '#ef4444' : academicTier?.tone === 'warning' ? '#f59e0b' : '#10b981',
                  }}
                />
              </div>
              <div className="gpa-d-bar-scale">
                <span>0.0</span>
                <span>4.00</span>
              </div>
            </div>

            {/* Thống Kê 4 Chỉ Số */}
            <div className="gpa-d-stats-grid">
              <div className="gpa-d-stat-box">
                <p className="gpa-d-stat-label">Tín chỉ</p>
                <p className="gpa-d-stat-val">{hasResult ? result.totalCredits : 0}</p>
              </div>
              <div className="gpa-d-stat-box">
                <p className="gpa-d-stat-label">Môn tính</p>
                <p className="gpa-d-stat-val">{result.countedCourses}/{courses.length}</p>
              </div>
              <div className={`gpa-d-stat-box ${courseStats.passed > 0 ? 'passed' : ''}`}>
                <p className="gpa-d-stat-label">Đạt</p>
                <p className="gpa-d-stat-val">{courseStats.passed}</p>
              </div>
              <div className="gpa-d-stat-box">
                <p className="gpa-d-stat-label">Rớt</p>
                <p className="gpa-d-stat-val" style={{ color: courseStats.failed > 0 ? '#ef4444' : undefined }}>
                  {courseStats.failed}
                </p>
              </div>
            </div>

            {/* Điều Hướng Tính Điểm Học Bổng */}
            <div className="gpa-d-scholarship-prompt">
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <span>💡</span>
                <span>Bạn muốn tính điểm xét học bổng?</span>
              </span>
              <button
                type="button"
                className="gpa-d-prompt-btn"
                onClick={() => (onNavigate ? onNavigate('scholarship') : undefined)}
              >
                Tính điểm xét học bổng →
              </button>
            </div>

            {/* Footer Modal Link */}
            <div className="gpa-d-result-footer">
              <button
                type="button"
                className="gpa-d-footer-link"
                onClick={() => setReferenceModalTab('scale')}
              >
                <span>📖 Bảng quy đổi {cohort}</span>
                <span>↗</span>
              </button>
              <span className="gpa-d-footer-watermark">ĐHSP TP.HCM</span>
            </div>

          </div>
        </div>

      </div>

      {/* ============================================================== */}
      {/* 2. BẢN MOBILE NATIVE: KHỚP 100% ẢNH THIẾT KẾ BẠN ĐÃ DUYỆT */}
      {/* ============================================================== */}
      <div className="gpa-mobile-layout">
        
        {/* TIÊU ĐỀ MOBILE GỌN 1 HÀNG KHÔNG CHOÁN DIỆN TÍCH */}
        <div className="gpa-m-page-header">
          <div className="gpa-m-title-wrap">
            <span className="gpa-m-title-icon">🎓</span>
            <h1 className="gpa-m-page-title">Tính GPA học kỳ</h1>
          </div>
        </div>

        {/* MOBILE HERO SCORE CARD (PHƯƠNG ÁN 1: THOÁNG ĐÃNG ĐẲNG CẤP APPLE) */}
        <div className="gpa-mobile-hero-container">
          <div className="gpa-mobile-hero-card">
            <div className="gpa-m-score-row">
              <span className="gpa-m-score-val">{hasResult ? animatedGpa.toFixed(2) : '--'}</span>
              <span className="gpa-m-score-max">/ 4.00</span>
            </div>

            {/* Viên thuốc hợp nhất (Phương án 2 Capsule) */}
            <div className="gpa-m-capsule-wrap">
              {hasResult && academicTier ? (
                <div className="gpa-m-capsule">
                  <span className={`gpa-m-tier-badge tier-${academicTier.tone}`}>{academicTier.label}</span>
                  <span className="gpa-m-sep">│</span>
                  <span className="gpa-m-creds">
                    {result.totalCredits} <span className="gpa-m-unit">tín chỉ</span>
                  </span>
                  <span className="gpa-m-bullet">•</span>
                  <span className="gpa-m-pass">
                    {courseStats.passed}/{result.countedCourses} <span className="gpa-m-unit">đạt</span>
                  </span>
                </div>
              ) : (
                <div className="gpa-m-capsule empty">
                  <span>Chưa nhập điểm • Nhập môn học bên dưới</span>
                </div>
              )}
            </div>

            {hasInvalidData && (
              <div className="gpa-m-hero-alert" role="alert">
                ⚠️ {invalidCoursesCount} học phần nhập sai dữ liệu
              </div>
            )}
          </div>

          {/* GỢI Ý HỌC BỔNG NHẸ NHÀNG BÊN NGOÀI CARD */}
          {hasResult && result.gpa >= 2.5 && (
            <div className="gpa-m-scholarship-banner">
              <div className="gpa-m-scholarship-left">
                <span className="gpa-m-scholarship-icon">💡</span>
                <span className="gpa-m-scholarship-text">
                  Bạn muốn tính điểm xét học bổng?
                </span>
              </div>
              <button
                type="button"
                className="gpa-m-scholarship-link"
                onClick={() => (onNavigate ? onNavigate('scholarship') : undefined)}
              >
                Tính điểm xét học bổng →
              </button>
            </div>
          )}
        </div>

        {/* TOOLBAR MOBILE (SIÊU GỌN - 1 HÀNG DUY NHẤT) */}
        <div className="gpa-m-toolbar">
          <span className="gpa-m-toolbar-count">Môn học ({courses.length})</span>

          <button
            type="button"
            className="gpa-m-reset-btn"
            onClick={resetCourses}
          >
            Đặt lại
          </button>
        </div>

        {/* INSET GROUPED LIST MOBILE (ĐIỂM CHỮ MÀU SẮC SINH ĐỘNG) */}
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
                  aria-label={`Chỉnh sửa Học phần ${index + 1}`}
                >
                  <div className="gpa-m-row-left">
                    <span className="gpa-m-row-title">Học phần {index + 1}</span>
                    <span className="gpa-m-row-desc">
                      {isCreditsErr ? (
                        <span style={{ color: '#ef4444', fontWeight: 600 }}>Sai tín chỉ</span>
                      ) : course.credits ? (
                        `${course.credits} tín chỉ`
                      ) : (
                        'Chưa có TC'
                      )}{' '}
                      • {groupOption?.shortLabel || 'Đại cương'}
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

            {/* NÚT THÊM MÔN DUY NHẤT Ở CHÂN DANH SÁCH MOBILE */}
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
      {/* MOBILE 1-TOUCH BOTTOM SHEET EDITOR */}
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
                    {/* 1. Số tín chỉ: Cho phép nhập trực tiếp VÀ vuốt nhanh con lăn */}
                    <div className="gpa-m-sheet-field">
                      <div className="gpa-m-sheet-label-row">
                        <label className="gpa-m-sheet-label" htmlFor="gpa-sheet-cred-input">
                          1. Số tín chỉ
                        </label>
                        <div className="gpa-m-cred-direct-box">
                          <input
                            id="gpa-sheet-cred-input"
                            type="text"
                            inputMode="numeric"
                            className={`gpa-m-cred-input-direct ${sheetCredErr ? 'input-error' : ''}`}
                            value={sheetState.credits}
                            onChange={(e) => {
                              const val = sanitizeDecimal(e.target.value);
                              setSheetState((s) => (s ? { ...s, credits: val } : null));
                            }}
                            placeholder="3"
                            aria-label="Nhập trực tiếp số tín chỉ"
                            aria-invalid={sheetCredErr}
                          />
                          <span className="gpa-m-cred-unit-label">tín chỉ</span>
                        </div>
                      </div>

                      {sheetCredErr && (
                        <span className="gpa-m-inline-error">⚠️ Số tín chỉ phải từ 1 đến 30</span>
                      )}

                      <div className="gpa-m-wheel-section">
                        <span className="gpa-m-wheel-guide">Hoặc vuốt nhanh con lăn (1 – 10):</span>
                        <CreditWheelPicker
                          value={sheetState.credits}
                          onChange={(val) => setSheetState((s) => (s ? { ...s, credits: val } : null))}
                        />
                      </div>
                    </div>

                    {/* 2. Điểm học phần thang 10 */}
                    <div className="gpa-m-sheet-field">
                      <div className="gpa-m-sheet-label-row">
                        <label className="gpa-m-sheet-label" htmlFor="gpa-sheet-score-input">
                          2. Điểm học phần (Thang 10)
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
                          placeholder="8.5"
                          autoFocus
                          aria-label="Nhập điểm thang 10"
                          aria-invalid={sheetScoreErr}
                        />
                      </div>

                      {sheetScoreErr && (
                        <span className="gpa-m-inline-error">⚠️ Điểm phải từ 0.0 đến 10.0</span>
                      )}
                    </div>

                    {/* 3. Phân loại môn */}
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

                    {/* 4. Nút hành động */}
                    <div className="gpa-m-sheet-actions">
                      <button
                        type="button"
                        className={`gpa-m-sheet-save-btn ${sheetCredErr || sheetScoreErr ? 'disabled' : ''}`}
                        onClick={handleSaveSheet}
                        disabled={sheetCredErr || sheetScoreErr}
                      >
                        {sheetState.isNew ? 'Thêm học phần' : 'Lưu thay đổi'}
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
