import { useMemo, useState } from 'react';
import {
  GraduationCap,
  Plus,
  RotateCcw,
  Trash2,
  Info,
} from 'lucide-react';
import {
  calculateGpa,
  convertScore10ToGrade,
  getCourseGrade,
  getCourseGroupOptions,
  getDefaultCourseGroup,
  getGradeScale,
  isCreditsInvalid,
  isScore10Invalid,
  type Cohort,
  type CourseInput,
  type LetterGrade,
} from '../../utils/gradeScale';
import { PageContextBadges } from '../PageContextBadges';
import { GpaReferenceModal } from '../GpaReferenceModal';

interface GpaPageProps {
  cohort: Cohort;
}

function newCourse(
  id: string,
  cohort: Cohort,
  inputType: 'score10' | 'letter' = 'score10'
): CourseInput {
  return {
    id,
    name: '',
    credits: '',
    inputType,
    score10: '',
    letter: '',
    courseGroup: getDefaultCourseGroup(cohort),
  };
}

function createEmptyCourses(
  cohort: Cohort,
  inputType: 'score10' | 'letter' = 'score10'
): CourseInput[] {
  return [
    newCourse('course-1', cohort, inputType),
    newCourse('course-2', cohort, inputType),
    newCourse('course-3', cohort, inputType),
  ];
}

interface AcademicTier {
  label: string;
  badgeClass: string;
  icon: string;
  description: string;
}

function getAcademicTier(gpa: number): AcademicTier {
  if (gpa >= 3.6) {
    return {
      label: 'Xuất sắc',
      badgeClass: 'tier-excellent',
      icon: '⭐',
      description: 'Đạt chuẩn xét học bổng Xuất sắc (nếu ĐRL >= 90 và tích lũy đủ tín chỉ).',
    };
  }
  if (gpa >= 3.2) {
    return {
      label: 'Giỏi',
      badgeClass: 'tier-good',
      icon: '🏆',
      description: 'Đạt chuẩn xét học bổng Giỏi (nếu ĐRL >= 80 và tích lũy đủ tín chỉ).',
    };
  }
  if (gpa >= 2.5) {
    return {
      label: 'Khá',
      badgeClass: 'tier-fair',
      icon: '📈',
      description: 'Đạt chuẩn xét học bổng Khá (nếu ĐRL >= 70 và tích lũy đủ tín chỉ).',
    };
  }
  if (gpa >= 2.0) {
    return {
      label: 'Trung bình',
      badgeClass: 'tier-average',
      icon: '⚖️',
      description: 'Đạt chuẩn học lực Trung bình, cần cố gắng hơn để nâng cao điểm số.',
    };
  }
  return {
    label: 'Yếu',
    badgeClass: 'tier-weak',
    icon: '⚠️',
    description: 'Cần chú ý cải thiện điểm số để tránh bị cảnh báo học vụ.',
  };
}

export function GpaPage({ cohort }: GpaPageProps) {
  const [globalInputType, setGlobalInputType] = useState<'score10' | 'letter'>('score10');
  const [courses, setCourses] = useState<CourseInput[]>(() =>
    createEmptyCourses(cohort, 'score10')
  );
  const [referenceModalTab, setReferenceModalTab] = useState<'scale' | 'rules' | null>(null);

  const result = useMemo(() => calculateGpa(courses, cohort), [courses, cohort]);
  const showCourseGroup = true;
  const groupOptions = getCourseGroupOptions(cohort);

  // Calculate stats for passed / failed courses
  const courseStats = useMemo(() => {
    let passed = 0;
    let failed = 0;
    courses.forEach((c) => {
      const rawCredits = c.credits.trim();
      if (!rawCredits) return;
      const credits = Number(rawCredits.replace(',', '.'));
      if (!Number.isFinite(credits) || credits <= 0) return;

      const grade = getCourseGrade(c, cohort);
      if (grade) {
        if (grade.status === 'Đạt') passed++;
        else failed++;
      }
    });
    return { passed, failed };
  }, [courses, cohort]);

  const validationErrors = useMemo(() => {
    let hasScoreError = false;
    let hasCreditsError = false;
    courses.forEach((c) => {
      if (globalInputType === 'score10' && isScore10Invalid(c.score10)) {
        hasScoreError = true;
      }
      if (isCreditsInvalid(c.credits)) {
        hasCreditsError = true;
      }
    });
    return {
      hasScoreError,
      hasCreditsError,
      hasAnyError: hasScoreError || hasCreditsError,
    };
  }, [courses, globalInputType]);

  const academicTier = useMemo(() => {
    if (result.error || result.gpa <= 0) return null;
    return getAcademicTier(result.gpa);
  }, [result]);

  const changeGlobalInputType = (type: 'score10' | 'letter') => {
    setGlobalInputType(type);
    setCourses((current) =>
      current.map((c) => {
        if (type === 'letter') {
          let letterVal: LetterGrade | '' = c.letter || '';
          if (c.score10.trim() !== '') {
            const num = Number(c.score10.trim().replace(',', '.'));
            if (Number.isFinite(num) && num >= 0 && num <= 10) {
              const g = convertScore10ToGrade(num, cohort, c.courseGroup);
              if (g) letterVal = g.letter;
            }
          }
          return { ...c, inputType: type, letter: letterVal };
        } else {
          return { ...c, inputType: type };
        }
      })
    );
  };

  const updateCourse = (id: string, patch: Partial<CourseInput>) => {
    setCourses((current) =>
      current.map((course) => (course.id === id ? { ...course, ...patch } : course))
    );
  };

  const addCourse = () => {
    setCourses((current) => [
      ...current,
      newCourse(`course-${Date.now()}`, cohort, globalInputType),
    ]);
  };

  const removeCourse = (id: string) => {
    setCourses((current) =>
      current.length > 1 ? current.filter((course) => course.id !== id) : current
    );
  };

  const resetCourses = () => {
    if (courses.some((c) => c.name || c.credits || c.score10 || c.letter)) {
      if (!window.confirm('Bạn có chắc chắn muốn làm mới (xóa trắng) danh sách môn học không?')) {
        return;
      }
    }
    setCourses(createEmptyCourses(cohort, globalInputType));
  };

  return (
    <div className="page-container tool-page gpa-page-wrapper">
      {/* Header */}
      <div className="page-header gpa-header">
        <h1 className="page-title-with-icon">
          <GraduationCap aria-hidden="true" />
          <span>Tính GPA học kỳ</span>
        </h1>
        <p>
          Tính điểm trung bình học kỳ và xếp loại theo quy chế của <strong>{cohort}</strong>.
        </p>
        <PageContextBadges cohort={cohort} source="Bảng quy đổi Sổ tay sinh viên" />
      </div>

      {/* Top Hero GPA Card on Mobile (Pinned to top, zero bottom-nav overlap) */}
      <section className="gpa-mobile-hero-card" aria-label="Kết quả GPA học kỳ">
        <div className="gpa-mobile-hero-top">
          <div className="gpa-result-tag-wrap">
            <span className="gpa-live-dot" aria-hidden="true" />
            <span className="gpa-hero-tag">GPA HỌC KỲ • {cohort}</span>
          </div>
          {academicTier && result.totalCredits > 0 && (
            <span className={`gpa-tier-pill ${academicTier.badgeClass}`}>
              {academicTier.icon} {academicTier.label}
            </span>
          )}
        </div>

        <div className="gpa-mobile-hero-middle">
          <div className="gpa-hero-score">
            <span className="gpa-score-num text-gradient">
              {result.error || result.totalCredits === 0 ? '--' : result.gpa.toFixed(2)}
            </span>
            <span className="gpa-score-den">/ 4.00</span>
          </div>

          <div className="gpa-mobile-stats-chips">
            <span className="gpa-stat-chip">
              <strong>{result.error || result.totalCredits === 0 ? 0 : result.totalCredits}</strong> TC
            </span>
            <span className="gpa-stat-chip">
              <strong>{result.error || result.totalCredits === 0 ? 0 : result.countedCourses}</strong> môn
            </span>
            <span className="gpa-stat-chip">
              <span className="text-success">{courseStats.passed} Đạt</span>
              {courseStats.failed > 0 && (
                <span className="text-danger"> • {courseStats.failed} Rớt</span>
              )}
            </span>
          </div>
        </div>

        {/* Mini progress bar */}
        <div className="gpa-progress-track">
          <div
            className={`gpa-progress-fill ${academicTier ? academicTier.badgeClass : ''}`}
            style={{
              width: `${result.error || result.totalCredits === 0 ? 0 : Math.min(100, Math.max(0, (result.gpa / 4) * 100))}%`,
            }}
          />
        </div>

        {/* Validation error notice on Mobile */}
        {validationErrors.hasAnyError && (
          <div
            className="gpa-validation-error-notice"
            role="alert"
            style={{ marginTop: '0.45rem', fontSize: '0.74rem' }}
          >
            <span>⚠️</span>
            <span>
              {validationErrors.hasScoreError && validationErrors.hasCreditsError
                ? 'Điểm và tín chỉ chưa hợp lệ (báo đỏ).'
                : validationErrors.hasScoreError
                ? 'Điểm thang 10 phải từ 0 đến 10 (báo đỏ).'
                : 'Số tín chỉ phải lớn hơn 0 (báo đỏ).'}
            </span>
          </div>
        )}
      </section>

      {/* Main 2-Column Split Layout */}
      <div className="gpa-split-layout">
        {/* Left Column: Course List */}
        <section className="gpa-main-column">
          {/* Controls Bar: Mode selector & action buttons */}
          <div className="gpa-toolbar">
            <div className="gpa-mode-control">
              <span className="gpa-mode-label">Nhập theo:</span>
              <div className="gpa-mode-pills" role="radiogroup" aria-label="Chế độ nhập điểm">
                <button
                  type="button"
                  className={`gpa-mode-btn mode-score10 ${globalInputType === 'score10' ? 'active' : ''}`}
                  onClick={() => changeGlobalInputType('score10')}
                >
                  Thang 10 (8.5)
                </button>
                <button
                  type="button"
                  className={`gpa-mode-btn mode-letter ${globalInputType === 'letter' ? 'active' : ''}`}
                  onClick={() => changeGlobalInputType('letter')}
                >
                  Điểm chữ (A, B+)
                </button>
              </div>
            </div>

            <div className="gpa-action-buttons">
              <button
                type="button"
                className="tool-btn ghost gpa-btn-sm"
                onClick={resetCourses}
                title="Xóa trắng toàn bộ môn học"
              >
                <RotateCcw size={14} />
                <span>Làm mới</span>
              </button>
              <button
                type="button"
                className="tool-btn primary gpa-btn-sm gpa-btn-highlight gpa-add-top-btn"
                onClick={addCourse}
                title="Thêm một môn học mới"
              >
                <Plus size={15} />
                <span>Thêm môn</span>
              </button>
            </div>
          </div>

          {/* Desktop Single-Row Table */}
          <div className="gpa-desktop-table-container">
            <div className={`gpa-table-header-row ${showCourseGroup ? 'has-group' : ''}`}>
              <span className="th-col th-idx">STT</span>
              <span className="th-col th-name">Tên Học Phần</span>
              {showCourseGroup && <span className="th-col th-group">Nhóm môn</span>}
              <span className="th-col th-creds">Tín chỉ</span>
              <span className={`th-col th-score ${globalInputType === 'score10' ? 'mode-score10' : 'mode-letter'}`}>
                {globalInputType === 'score10' ? 'Điểm 10' : 'Điểm chữ'}
              </span>
              <span className="th-col th-grade">
                {globalInputType === 'score10' ? 'Quy đổi' : 'Hệ 4'}
              </span>
              <span className="th-col th-del"></span>
            </div>

            <div className="gpa-table-body">
              {courses.map((course, index) => {
                const grade = getCourseGrade(course, cohort);
                const scale = getGradeScale(cohort, course.courseGroup);
                const isFailed = grade?.status === 'Không đạt';
                const isScoreErr = globalInputType === 'score10' && isScore10Invalid(course.score10);
                const isCreditsErr = isCreditsInvalid(course.credits);

                return (
                  <div
                    key={course.id}
                    className={`gpa-table-row ${showCourseGroup ? 'has-group' : ''} ${isFailed ? 'row-failed' : ''}`}
                  >
                    <span className="td-col td-idx">
                      <span className="gpa-row-badge">#{index + 1}</span>
                    </span>

                    <input
                      className="gpa-row-name-input"
                      value={course.name}
                      onChange={(e) => updateCourse(course.id, { name: e.target.value })}
                      placeholder="Tên học phần..."
                      aria-label={`Tên môn học ${index + 1}`}
                    />

                    {showCourseGroup && (
                      <select
                        className="gpa-row-group-select"
                        value={course.courseGroup ?? getDefaultCourseGroup(cohort)}
                        onChange={(e) =>
                          updateCourse(course.id, {
                            courseGroup: e.target.value as CourseInput['courseGroup'],
                          })
                        }
                        title="Chọn nhóm học phần"
                      >
                        {groupOptions.map((opt) => (
                          <option key={opt.id} value={opt.id}>
                            {opt.id === 'foundation' ? 'Đại cương' : 'Chuyên ngành'}
                          </option>
                        ))}
                      </select>
                    )}

                    <div className="td-creds">
                      <input
                        type="text"
                        inputMode="decimal"
                        className={`gpa-input-field credits ${isCreditsErr ? 'input-error' : ''}`}
                        value={course.credits}
                        onChange={(e) => {
                          const val = e.target.value;
                          if (val === '' || /^[0-9.,]*$/.test(val)) {
                            updateCourse(course.id, { credits: val });
                          }
                        }}
                        placeholder="--"
                        aria-label={`Số tín chỉ môn ${index + 1}`}
                        title={isCreditsErr ? 'Số tín chỉ không hợp lệ (phải lớn hơn 0)' : undefined}
                      />
                    </div>

                    <div className="td-score">
                      {globalInputType === 'score10' ? (
                        <input
                          type="text"
                          inputMode="decimal"
                          className={`gpa-input-field score mode-score10 ${isScoreErr ? 'input-error' : ''}`}
                          value={course.score10}
                          onChange={(e) => {
                            const val = e.target.value;
                            if (val === '' || /^[0-9.,]*$/.test(val)) {
                              updateCourse(course.id, { score10: val });
                            }
                          }}
                          placeholder="--"
                          aria-label={`Điểm thang 10 môn ${index + 1}`}
                          title={isScoreErr ? 'Điểm thang 10 không hợp lệ (từ 0 đến 10)' : undefined}
                        />
                      ) : (
                        <select
                          className={`gpa-select-field mode-letter ${!course.letter ? 'unselected' : ''}`}
                          value={course.letter || ''}
                          onChange={(e) =>
                            updateCourse(course.id, { letter: e.target.value as LetterGrade })
                          }
                          aria-label={`Điểm chữ môn ${index + 1}`}
                        >
                          <option value="">-- Chọn --</option>
                          {scale.rows.map((row) => (
                            <option key={row.letter} value={row.letter}>
                              {row.letter}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>

                    <div className="td-grade">
                      {isScoreErr ? (
                        <span className="gpa-mini-chip failed" title="Điểm thang 10 không hợp lệ (0 - 10)">
                          Lỗi điểm
                        </span>
                      ) : isCreditsErr && grade ? (
                        <span className="gpa-mini-chip failed" title="Số tín chỉ không hợp lệ (phải > 0)">
                          Lỗi TC
                        </span>
                      ) : grade ? (
                        <span
                          className={`gpa-mini-chip ${isFailed ? 'failed' : 'passed'} grade-${grade.letter.toLowerCase().replace('+', '-plus')}`}
                        >
                          {globalInputType === 'score10' ? (
                            <>
                              <strong>{grade.letter}</strong>
                              <span>({grade.score4.toFixed(1)})</span>
                            </>
                          ) : (
                            <>
                              <strong>{grade.score4.toFixed(1)}</strong>
                              {isFailed && (
                                <span className="gpa-chip-status-text">Rớt</span>
                              )}
                            </>
                          )}
                        </span>
                      ) : (
                        <span
                          className="gpa-auto-chip"
                          title="Hệ thống tự động quy đổi khi nhập điểm"
                        >
                          Tự động
                        </span>
                      )}
                    </div>

                    <div className="td-del">
                      <button
                        type="button"
                        className="gpa-row-del-btn"
                        onClick={() => removeCourse(course.id)}
                        disabled={courses.length <= 1}
                        aria-label={`Xóa môn học ${index + 1}`}
                        title={courses.length <= 1 ? 'Tối thiểu 1 môn học' : 'Xóa môn này'}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Mobile Streamlined Cards */}
          <div className="gpa-mobile-cards-list">
            {courses.map((course, index) => {
              const grade = getCourseGrade(course, cohort);
              const scale = getGradeScale(cohort, course.courseGroup);
              const isFailed = grade?.status === 'Không đạt';
              const isScoreErr = globalInputType === 'score10' && isScore10Invalid(course.score10);
              const isCreditsErr = isCreditsInvalid(course.credits);

              return (
                <div key={course.id} className={`gpa-mobile-card ${isFailed ? 'card-failed' : ''}`}>
                  {/* Top: Index + Name + Group + Trash */}
                  <div className="gpa-mobile-card-header">
                    <div className="gpa-m-header-left">
                      <span className="gpa-m-idx">#{index + 1}</span>
                      <input
                        className="gpa-m-name-input"
                        value={course.name}
                        onChange={(e) => updateCourse(course.id, { name: e.target.value })}
                        placeholder="Tên học phần..."
                        aria-label={`Tên môn học ${index + 1}`}
                      />
                    </div>
                    <div className="gpa-m-header-right">
                      {showCourseGroup && (
                        <select
                          className="gpa-m-group-select"
                          value={course.courseGroup ?? getDefaultCourseGroup(cohort)}
                          onChange={(e) =>
                            updateCourse(course.id, {
                              courseGroup: e.target.value as CourseInput['courseGroup'],
                            })
                          }
                          aria-label={`Nhóm môn ${index + 1}`}
                        >
                          {groupOptions.map((opt) => (
                            <option key={opt.id} value={opt.id}>
                              {opt.id === 'foundation' ? 'Đại cương' : 'Chuyên ngành'}
                            </option>
                          ))}
                        </select>
                      )}
                      <button
                        type="button"
                        className="gpa-m-del-btn"
                        onClick={() => removeCourse(course.id)}
                        disabled={courses.length <= 1}
                        aria-label={`Xóa môn ${index + 1}`}
                        title={courses.length <= 1 ? 'Tối thiểu 1 môn' : 'Xóa môn'}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>

                  {/* Bottom: 3-column inputs (Credits | Score | Grade) */}
                  <div className="gpa-mobile-card-grid">
                    {/* Col 1: Tín chỉ */}
                    <div className="gpa-m-grid-field">
                      <span className="gpa-m-field-label">TÍN CHỈ</span>
                      <input
                        type="text"
                        inputMode="decimal"
                        className={`gpa-input-field credits compact ${isCreditsErr ? 'input-error' : ''}`}
                        value={course.credits}
                        onChange={(e) => {
                          const val = e.target.value;
                          if (val === '' || /^[0-9.,]*$/.test(val)) {
                            updateCourse(course.id, { credits: val });
                          }
                        }}
                        placeholder="--"
                        aria-label={`Số tín chỉ môn ${index + 1}`}
                        title={isCreditsErr ? 'Số tín chỉ không hợp lệ (phải lớn hơn 0)' : undefined}
                      />
                    </div>

                    {/* Col 2: Điểm */}
                    <div className="gpa-m-grid-field">
                      <span className="gpa-m-field-label">
                        {globalInputType === 'score10' ? 'ĐIỂM 10' : 'ĐIỂM CHỮ'}
                      </span>
                      {globalInputType === 'score10' ? (
                        <input
                          type="text"
                          inputMode="decimal"
                          className={`gpa-input-field score mode-score10 compact ${isScoreErr ? 'input-error' : ''}`}
                          value={course.score10}
                          onChange={(e) => {
                            const val = e.target.value;
                            if (val === '' || /^[0-9.,]*$/.test(val)) {
                              updateCourse(course.id, { score10: val });
                            }
                          }}
                          placeholder="--"
                          aria-label={`Điểm thang 10 môn ${index + 1}`}
                          title={isScoreErr ? 'Điểm thang 10 không hợp lệ (từ 0 đến 10)' : undefined}
                        />
                      ) : (
                        <select
                          className={`gpa-select-field mode-letter compact ${!course.letter ? 'unselected' : ''}`}
                          value={course.letter || ''}
                          onChange={(e) =>
                            updateCourse(course.id, { letter: e.target.value as LetterGrade })
                          }
                          aria-label={`Điểm chữ môn ${index + 1}`}
                        >
                          <option value="">-- Chọn --</option>
                          {scale.rows.map((row) => (
                            <option key={row.letter} value={row.letter}>
                              {row.letter}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>

                    {/* Col 3: Quy đổi */}
                    <div className="gpa-m-grid-field">
                      <span className="gpa-m-field-label">QUY ĐỔI</span>
                      <div className="gpa-m-chip-wrapper">
                        {isScoreErr ? (
                          <span className="gpa-mini-chip failed" title="Điểm thang 10 không hợp lệ (0 - 10)">
                            Lỗi điểm
                          </span>
                        ) : isCreditsErr && grade ? (
                          <span className="gpa-mini-chip failed" title="Số tín chỉ không hợp lệ (phải > 0)">
                            Lỗi TC
                          </span>
                        ) : grade ? (
                          <span
                            className={`gpa-mini-chip ${isFailed ? 'failed' : 'passed'} grade-${grade.letter.toLowerCase().replace('+', '-plus')}`}
                          >
                            {globalInputType === 'score10' ? (
                              <>
                                <strong>{grade.letter}</strong>
                                <span>({grade.score4.toFixed(1)})</span>
                              </>
                            ) : (
                              <>
                                <strong>{grade.score4.toFixed(1)}</strong>
                                {isFailed && (
                                  <span className="gpa-chip-status-text">Rớt</span>
                                )}
                              </>
                            )}
                          </span>
                        ) : (
                          <span
                            className="gpa-auto-chip"
                            title="Hệ thống tự động quy đổi khi nhập điểm"
                          >
                            Tự động
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Add Course Bottom Bar */}
          <div className="gpa-bottom-add">
            <button type="button" className="gpa-add-dashed-btn" onClick={addCourse}>
              <Plus size={16} />
              <span>Thêm một môn học mới</span>
            </button>
          </div>

          {/* Mobile Secondary Action Pills */}
          <div className="gpa-mobile-auxiliary">
            <div className="gpa-action-pills-row">
              <button
                type="button"
                className="gpa-footer-pill-btn"
                onClick={() => setReferenceModalTab('rules')}
                aria-label="Xem quy chế tính GPA và học bổng"
              >
                <Info size={14} />
                <span>Quy chế điểm</span>
              </button>
              <button
                type="button"
                className="gpa-footer-pill-btn"
                onClick={() => setReferenceModalTab('scale')}
                aria-label={`Tra cứu bảng quy đổi điểm (${cohort})`}
              >
                <GraduationCap size={15} />
                <span>Bảng quy đổi điểm</span>
              </button>
            </div>
          </div>
        </section>

        {/* Right Column: Sticky GPA Result Card (Desktop only) */}
        <aside className="gpa-sidebar-column">
          <div className="gpa-sticky-card">
            <div className="gpa-card-inner">
              <div className="gpa-result-top">
                <div className="gpa-result-tag-wrap">
                  <span className="gpa-live-dot" aria-hidden="true" />
                  <span className="gpa-result-tag">GPA HỌC KỲ • {cohort}</span>
                </div>
                {academicTier && result.totalCredits > 0 ? (
                  <span className={`gpa-tier-pill ${academicTier.badgeClass}`}>
                    {academicTier.icon} {academicTier.label}
                  </span>
                ) : (
                  <span className="gpa-cohort-pill">{cohort}</span>
                )}
              </div>

              {/* Huge GPA Score */}
              <div className="gpa-hero-score">
                <span className="gpa-score-num text-gradient">
                  {result.error || result.totalCredits === 0 ? '--' : result.gpa.toFixed(2)}
                </span>
                <span className="gpa-score-den">/ 4.00</span>
              </div>

              {/* Progress Bar (0 to 4.0) right below GPA score */}
              <div className="gpa-progress-track">
                <div
                  className={`gpa-progress-fill ${academicTier ? academicTier.badgeClass : ''}`}
                  style={{
                    width: `${result.error || result.totalCredits === 0 ? 0 : Math.min(100, Math.max(0, (result.gpa / 4) * 100))}%`,
                  }}
                />
              </div>

              {/* Summary Stats Grid (3 Equal, Symmetrical Cards) */}
              <div className="gpa-stats-grid">
                <div className="gpa-stat-box">
                  <span className="gpa-stat-label">Tổng tín chỉ</span>
                  <strong className="gpa-stat-val">
                    {result.error || result.totalCredits === 0 ? '--' : result.totalCredits}
                  </strong>
                </div>
                <div className="gpa-stat-box">
                  <span className="gpa-stat-label">Số môn tính</span>
                  <strong className="gpa-stat-val">
                    {result.error || result.totalCredits === 0 ? '--' : result.countedCourses}
                  </strong>
                </div>
                <div className="gpa-stat-box">
                  <span className="gpa-stat-label">Đạt / Rớt</span>
                  <strong className="gpa-stat-val">
                    {result.error || result.totalCredits === 0 ? (
                      '--'
                    ) : (
                      <span className="gpa-stat-split">
                        <span className="text-success">{courseStats.passed}</span>
                        <span className="gpa-split-slash">/</span>
                        <span className={courseStats.failed > 0 ? 'text-danger' : ''}>
                          {courseStats.failed}
                        </span>
                      </span>
                    )}
                  </strong>
                </div>
              </div>

              {/* Highlighted Notice Card (Scholarship reminder or warning) placed below 3 stat cards */}
              {academicTier && result.totalCredits > 0 && (
                <div className={`gpa-notice-card ${academicTier.badgeClass}`}>
                  <span className="gpa-notice-icon">
                    {academicTier.badgeClass === 'tier-weak' ? '⚠️' : academicTier.badgeClass === 'tier-average' ? '💡' : '✨'}
                  </span>
                  <p className="gpa-notice-text">{academicTier.description}</p>
                </div>
              )}

              {/* Validation error notice on Desktop */}
              {validationErrors.hasAnyError && (
                <div className="gpa-validation-error-notice" role="alert">
                  <span>⚠️</span>
                  <span>
                    {validationErrors.hasScoreError && validationErrors.hasCreditsError
                      ? 'Điểm và số tín chỉ chưa hợp lệ. Vui lòng kiểm tra các ô báo đỏ.'
                      : validationErrors.hasScoreError
                      ? 'Điểm thang 10 phải từ 0 đến 10. Vui lòng sửa lại ô báo đỏ.'
                      : 'Số tín chỉ phải lớn hơn 0. Vui lòng sửa lại ô báo đỏ.'}
                  </span>
                </div>
              )}

              {/* Footer Actions: 2 Clean Action Pills in 1 row */}
              <div className="gpa-card-footer">
                <div className="gpa-action-pills-row">
                  <button
                    type="button"
                    className="gpa-footer-pill-btn"
                    onClick={() => setReferenceModalTab('rules')}
                    title="Xem quy chế tính GPA và tiêu chuẩn học bổng"
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
          </div>
        </aside>
      </div>

      {/* GPA Reference & Rules Dialog Modal */}
      <GpaReferenceModal
        isOpen={referenceModalTab !== null}
        onClose={() => setReferenceModalTab(null)}
        cohort={cohort}
        initialTab={referenceModalTab ?? 'scale'}
      />
    </div>
  );
}
