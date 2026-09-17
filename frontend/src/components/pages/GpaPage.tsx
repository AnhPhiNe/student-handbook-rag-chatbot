import { useMemo, useState, type ReactNode } from 'react';
import { GraduationCap, Plus, Trash2 } from 'lucide-react';
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
  type GradeScaleRow,
  type LetterGrade,
} from '../../utils/gradeScale';
import { sanitizeDecimal } from '../../utils/numberInput';
import { getGradeTone } from '../../utils/gradeTone';
import { useAnimatedNumber } from '../../hooks/useAnimatedNumber';
import { GpaReferenceModal } from '../GpaReferenceModal';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton } from '../tool/ToolSection';
import { ResultCard, type ResultTone } from '../tool/ResultCard';
import { ScoreBar } from '../tool/ScoreBar';
import { ToolMobileSummary } from '../tool/ToolMobileSummary';
import { ResultFacts } from '../tool/ResultFacts';
import { ResultCallout } from '../tool/ResultCallout';

interface GpaPageProps {
  cohort: Cohort;
}

type InputType = 'score10' | 'letter';

const INPUT_MODES: Array<{ id: InputType; label: string }> = [
  { id: 'score10', label: 'Thang 10 (8.5)' },
  { id: 'letter', label: 'Điểm chữ (A, B+)' },
];

function newCourse(id: string, cohort: Cohort, inputType: InputType = 'score10'): CourseInput {
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

function createEmptyCourses(cohort: Cohort, inputType: InputType = 'score10'): CourseInput[] {
  return [
    newCourse('course-1', cohort, inputType),
    newCourse('course-2', cohort, inputType),
    newCourse('course-3', cohort, inputType),
  ];
}

interface AcademicTier {
  label: string;
  tone: ResultTone;
  description: ReactNode;
}

function getAcademicTier(gpa: number): AcademicTier {
  if (gpa >= 3.6) {
    return {
      label: 'Xuất sắc',
      tone: 'success',
      description: <>Đạt chuẩn xét học bổng <strong>Xuất sắc</strong> nếu điểm rèn luyện từ <strong>90</strong> và đủ tín chỉ.</>,
    };
  }
  if (gpa >= 3.2) {
    return {
      label: 'Giỏi',
      tone: 'success',
      description: <>Đạt chuẩn xét học bổng <strong>Giỏi</strong> nếu điểm rèn luyện từ <strong>80</strong> và đủ tín chỉ.</>,
    };
  }
  if (gpa >= 2.5) {
    return {
      label: 'Khá',
      tone: 'success',
      description: <>Đạt chuẩn xét học bổng <strong>Khá</strong> nếu điểm rèn luyện từ <strong>70</strong> và đủ tín chỉ.</>,
    };
  }
  if (gpa >= 2.0) {
    return {
      label: 'Trung bình',
      tone: 'warning',
      description: <>Cần GPA từ <strong>2.50</strong> để đạt chuẩn xét học bổng <strong>Khá</strong>.</>,
    };
  }
  return {
    label: 'Yếu',
    tone: 'danger',
    description: <>GPA dưới <strong>2.00</strong>. Cần cải thiện điểm để tránh bị cảnh báo học vụ.</>,
  };
}

interface GradeCellProps {
  grade: GradeScaleRow | null;
  inputType: InputType;
  isScoreErr: boolean;
  isCreditsErr: boolean;
}

function GradeCell({ grade, inputType, isScoreErr, isCreditsErr }: GradeCellProps) {
  if (isScoreErr) {
    return <span className="gpa-mini-chip failed">Lỗi điểm</span>;
  }
  if (isCreditsErr && grade) {
    return <span className="gpa-mini-chip failed">Lỗi TC</span>;
  }
  if (!grade) {
    return <span className="gpa-grade-placeholder" aria-label="Chưa có điểm">—</span>;
  }

  const isFailed = grade.status === 'Không đạt';
  return (
    <span className={`gpa-mini-chip ${isFailed ? 'failed' : 'passed'} grade-tone-${getGradeTone(grade)}`}>
      {inputType === 'score10' ? (
        <>
          <strong>{grade.letter}</strong>
          <span>({grade.score4.toFixed(1)})</span>
        </>
      ) : (
        <>
          <strong>{grade.score4.toFixed(1)}</strong>
          {isFailed && <span className="gpa-chip-status-text">Rớt</span>}
        </>
      )}
    </span>
  );
}

export function GpaPage({ cohort }: GpaPageProps) {
  const [globalInputType, setGlobalInputType] = useState<InputType>('score10');
  const [courses, setCourses] = useState<CourseInput[]>(() => createEmptyCourses(cohort, 'score10'));
  const [referenceModalTab, setReferenceModalTab] = useState<'scale' | 'rules' | null>(null);

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
      else failedCourses.push(`Môn học ${index + 1} (${grade.letter})`);
    });
    return { passed, failed: failedCourses.length, failedCourses };
  }, [courses, cohort]);

  const validationMessage = useMemo(() => {
    const hasScoreError = globalInputType === 'score10' && courses.some((course) => isScore10Invalid(course.score10));
    const hasCreditsError = courses.some((course) => isCreditsInvalid(course.credits));
    if (hasScoreError && hasCreditsError) return 'Điểm và số tín chỉ ở các ô báo đỏ chưa hợp lệ.';
    if (hasScoreError) return 'Điểm thang 10 phải từ 0 đến 10. Hãy sửa các ô báo đỏ.';
    if (hasCreditsError) return 'Số tín chỉ mỗi môn phải từ 1 đến 30. Hãy sửa các ô báo đỏ.';
    return null;
  }, [courses, globalInputType]);

  const changeGlobalInputType = (type: InputType) => {
    setGlobalInputType(type);
    setCourses((current) =>
      current.map((course) => {
        if (type !== 'letter') return { ...course, inputType: type };
        let letter: LetterGrade | '' = course.letter || '';
        if (course.score10.trim() !== '') {
          const score = Number(course.score10.trim().replace(',', '.'));
          if (Number.isFinite(score) && score >= 0 && score <= 10) {
            const grade = convertScore10ToGrade(score, cohort, course.courseGroup);
            if (grade) letter = grade.letter;
          }
        }
        return { ...course, inputType: type, letter };
      })
    );
  };

  const updateCourse = (id: string, patch: Partial<CourseInput>) => {
    setCourses((current) => current.map((course) => (course.id === id ? { ...course, ...patch } : course)));
  };

  const addCourse = () => {
    setCourses((current) => [...current, newCourse(`course-${Date.now()}`, cohort, globalInputType)]);
  };

  const removeCourse = (id: string) => {
    setCourses((current) => (current.length > 1 ? current.filter((course) => course.id !== id) : current));
  };

  const resetCourses = () => {
    if (courses.some((course) => course.name || course.credits || course.score10 || course.letter)) {
      if (!window.confirm('Bạn có chắc chắn muốn làm mới (xóa trắng) danh sách môn học không?')) {
        return;
      }
    }
    setCourses(createEmptyCourses(cohort, globalInputType));
  };

  const renderGroupSelect = (course: CourseInput, index: number, className: string) => (
    <select
      className={className}
      value={course.courseGroup ?? getDefaultCourseGroup(cohort)}
      onChange={(e) => updateCourse(course.id, { courseGroup: e.target.value as CourseInput['courseGroup'] })}
      aria-label={`Nhóm môn của môn học ${index + 1}`}
    >
      {groupOptions.map((option) => (
        <option key={option.id} value={option.id}>
          {option.shortLabel}
        </option>
      ))}
    </select>
  );

  const renderCreditsInput = (course: CourseInput, index: number, compact: boolean) => (
    <input
      type="text"
      inputMode="decimal"
      className={`gpa-input-field credits ${compact ? 'compact' : ''} ${isCreditsInvalid(course.credits) ? 'input-error' : ''}`}
      value={course.credits}
      onChange={(e) => updateCourse(course.id, { credits: sanitizeDecimal(e.target.value) })}
      placeholder="--"
      aria-label={`Số tín chỉ môn học ${index + 1}`}
      aria-invalid={isCreditsInvalid(course.credits)}
    />
  );

  const renderScoreInput = (course: CourseInput, index: number, compact: boolean) => {
    if (globalInputType === 'score10') {
      const isScoreErr = isScore10Invalid(course.score10);
      return (
        <input
          type="text"
          inputMode="decimal"
          className={`gpa-input-field score mode-score10 ${compact ? 'compact' : ''} ${isScoreErr ? 'input-error' : ''}`}
          value={course.score10}
          onChange={(e) => updateCourse(course.id, { score10: sanitizeDecimal(e.target.value) })}
          placeholder="--"
          aria-label={`Điểm thang 10 môn học ${index + 1}`}
          aria-invalid={isScoreErr}
        />
      );
    }
    const scale = getGradeScale(cohort, course.courseGroup);
    return (
      <select
        className={`gpa-select-field mode-letter ${compact ? 'compact' : ''} ${!course.letter ? 'unselected' : ''}`}
        value={course.letter || ''}
        onChange={(e) => updateCourse(course.id, { letter: e.target.value as LetterGrade })}
        aria-label={`Điểm chữ môn học ${index + 1}`}
      >
        <option value="">-- Chọn --</option>
        {scale.rows.map((row) => (
          <option key={row.letter} value={row.letter}>
            {row.letter}
          </option>
        ))}
      </select>
    );
  };

  const gradeCell = (course: CourseInput) => (
    <GradeCell
      grade={getCourseGrade(course, cohort)}
      inputType={globalInputType}
      isScoreErr={globalInputType === 'score10' && isScore10Invalid(course.score10)}
      isCreditsErr={isCreditsInvalid(course.credits)}
    />
  );

  return (
    <div className="page-container tool-page simplified">
      <ToolPageHeader
        icon={GraduationCap}
        title="Tính GPA học kỳ"
        description={
          <>
            Tính điểm trung bình học kỳ và xếp loại theo quy chế của <strong>{cohort}</strong>.
          </>
        }
      />

      <ToolMobileSummary
        label="GPA học kỳ"
        value={hasResult ? result.gpa.toFixed(2) : '--'}
        unit="/ 4.00"
        chip={academicTier?.label}
        tone={academicTier?.tone}
      />

      <div className="tool-grid wide">
        <div className="tool-main">
          <div className="tool-toolbar">
            <div className="tool-segmented" role="group" aria-label="Cách nhập điểm">
              {INPUT_MODES.map((mode) => (
                <button
                  key={mode.id}
                  type="button"
                  aria-pressed={globalInputType === mode.id}
                  onClick={() => changeGlobalInputType(mode.id)}
                >
                  {mode.label}
                </button>
              ))}
            </div>
            <ResetButton onClick={resetCourses} />
          </div>

          <div className="gpa-desktop-table-container">
            <div className="gpa-table-header-row has-group">
              <span className="th-col th-course">Học phần</span>
              <span className="th-col th-group">Nhóm môn</span>
              <span className="th-col th-creds">Tín chỉ</span>
              <span className="th-col th-score">{globalInputType === 'score10' ? 'Điểm 10' : 'Điểm chữ'}</span>
              <span className="th-col th-grade">Quy đổi</span>
              <span className="th-col th-del"></span>
            </div>

            <div className="gpa-table-body">
              {courses.map((course, index) => {
                const isFailed = getCourseGrade(course, cohort)?.status === 'Không đạt';
                return (
                  <div key={course.id} className={`gpa-table-row has-group ${isFailed ? 'row-failed' : ''}`}>
                    <div className="td-col td-course">
                      <span className="gpa-course-fixed-title">Môn học {index + 1}</span>
                    </div>
                    {renderGroupSelect(course, index, 'gpa-row-group-select')}
                    <div className="td-creds">{renderCreditsInput(course, index, false)}</div>
                    <div className="td-score">{renderScoreInput(course, index, false)}</div>
                    <div className="td-grade">{gradeCell(course)}</div>
                    <div className="td-del">
                      <button
                        type="button"
                        className="gpa-row-del-btn"
                        onClick={() => removeCourse(course.id)}
                        disabled={courses.length <= 1}
                        aria-label={`Xóa môn học ${index + 1}`}
                        title={courses.length <= 1 ? 'Cần giữ ít nhất 1 môn' : 'Xóa môn này'}
                      >
                        <Trash2 size={15} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="gpa-mobile-cards-list">
            {courses.map((course, index) => {
              const isFailed = getCourseGrade(course, cohort)?.status === 'Không đạt';
              return (
                <div key={course.id} className={`gpa-mobile-card ${isFailed ? 'card-failed' : ''}`}>
                  <div className="gpa-mobile-card-header">
                    <div className="gpa-m-header-left">
                      <span className="gpa-m-fixed-title">Môn học {index + 1}</span>
                    </div>
                    <div className="gpa-m-header-right">
                      {renderGroupSelect(course, index, 'gpa-m-group-select')}
                      <button
                        type="button"
                        className="gpa-m-del-btn"
                        onClick={() => removeCourse(course.id)}
                        disabled={courses.length <= 1}
                        aria-label={`Xóa môn học ${index + 1}`}
                      >
                        <Trash2 size={15} aria-hidden="true" />
                      </button>
                    </div>
                  </div>

                  <div className="gpa-mobile-card-grid">
                    <div className="gpa-m-grid-field">
                      <span className="gpa-m-field-label">Tín chỉ</span>
                      {renderCreditsInput(course, index, true)}
                    </div>
                    <div className="gpa-m-grid-field">
                      <span className="gpa-m-field-label">{globalInputType === 'score10' ? 'Điểm 10' : 'Điểm chữ'}</span>
                      {renderScoreInput(course, index, true)}
                    </div>
                    <div className="gpa-m-grid-field">
                      <span className="gpa-m-field-label">Quy đổi</span>
                      <div className="gpa-m-chip-wrapper">{gradeCell(course)}</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="gpa-bottom-add">
            <button type="button" className="gpa-add-dashed-btn" onClick={addCourse}>
              <Plus size={16} aria-hidden="true" />
              <span>Thêm môn học</span>
            </button>
          </div>
        </div>

        <ResultCard id="gpa-result" tone={academicTier?.tone} chip={academicTier?.label}>
          {hasResult ? (
            <>
              <div aria-live="polite">
                <p className="tool-big-label">GPA học kỳ</p>
                <p className="tool-big">
                  <strong>{animatedGpa.toFixed(2)}</strong>
                  <span>/ 4.00</span>
                </p>
              </div>
              <ScoreBar value={result.gpa} max={4} maxLabel="4.00" />
              <ResultFacts
                facts={[
                  { label: 'Tín chỉ', value: result.totalCredits },
                  { label: 'Môn tính', value: result.countedCourses },
                  { label: 'Đạt', value: courseStats.passed, tone: courseStats.passed > 0 ? 'success' : null },
                  { label: 'Rớt', value: courseStats.failed, tone: courseStats.failed > 0 ? 'danger' : null },
                ]}
              />
              {courseStats.failed > 0 ? (
                <ResultCallout tone="danger">
                  <strong>{courseStats.failed} môn chưa đạt:</strong> {courseStats.failedCourses.join(', ')}. Các môn này cần học lại.
                </ResultCallout>
              ) : (
                academicTier && <ResultCallout tone={academicTier.tone}>{academicTier.description}</ResultCallout>
              )}
            </>
          ) : (
            <p className="tool-empty">Nhập số tín chỉ và điểm của từng môn để tính GPA học kỳ.</p>
          )}

          {validationMessage && (
            <p className="tool-error" role="alert">
              {validationMessage}
            </p>
          )}

          <div className="tool-source">
            <span>Theo bảng quy đổi điểm của {cohort}.</span>
            <button type="button" className="tool-text-btn" onClick={() => setReferenceModalTab('rules')}>
              Quy chế điểm
            </button>
            <button type="button" className="tool-text-btn" onClick={() => setReferenceModalTab('scale')}>
              Bảng quy đổi điểm
            </button>
          </div>
        </ResultCard>
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
