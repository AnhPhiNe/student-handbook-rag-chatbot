import { useMemo, useState } from 'react';
import { Plus, RotateCcw, Trash2 } from 'lucide-react';
import {
  calculateGpa,
  getCourseGrade,
  getCourseGroupOptions,
  getDefaultCourseGroup,
  getGradeScale,
  getGradeScales,
  isSplitGradeCohort,
  type Cohort,
  type CourseInput,
  type LetterGrade,
} from '../../utils/gradeScale';

interface GpaPageProps {
  cohort: Cohort;
}

function newCourse(id: string, cohort: Cohort): CourseInput {
  return {
    id,
    name: '',
    credits: '',
    inputType: 'score10',
    score10: '',
    letter: 'A',
    courseGroup: getDefaultCourseGroup(cohort),
  };
}

function createDefaultCourses(cohort: Cohort): CourseInput[] {
  return [newCourse('course-1', cohort), newCourse('course-2', cohort), newCourse('course-3', cohort)];
}

export function GpaPage({ cohort }: GpaPageProps) {
  const [courses, setCourses] = useState<CourseInput[]>(() => createDefaultCourses(cohort));
  const result = useMemo(() => calculateGpa(courses, cohort), [courses, cohort]);
  const showCourseGroup = isSplitGradeCohort(cohort);
  const groupOptions = getCourseGroupOptions(cohort);

  const updateCourse = (id: string, patch: Partial<CourseInput>) => {
    setCourses((current) => current.map((course) => course.id === id ? { ...course, ...patch } : course));
  };

  const addCourse = () => {
    setCourses((current) => [...current, newCourse(`course-${Date.now()}`, cohort)]);
  };

  const removeCourse = (id: string) => {
    setCourses((current) => current.length > 1 ? current.filter((course) => course.id !== id) : current);
  };

  const resetCourses = () => {
    setCourses(createDefaultCourses(cohort));
  };

  return (
    <div className="page-container tool-page">
      <div className="page-header">
        <h1>Tính GPA học kỳ</h1>
        <p>Nhập danh sách học phần, số tín chỉ và điểm để tính GPA theo bảng quy đổi đang áp dụng cho {cohort}.</p>
      </div>

      <div className="tool-layout wide">
        <section className="tool-panel gpa-panel">
          <div className="tool-panel-header">
            <div>
              <h2>Danh sách học phần</h2>
              <p>Điểm chữ, trạng thái đạt và điểm hệ 4 được suy ra theo đúng Khóa đang chọn.</p>
            </div>
            <div className="tool-actions">
              <button className="tool-btn ghost" onClick={resetCourses}>
                <RotateCcw size={16} />
                <span>Reset</span>
              </button>
              <button className="tool-btn primary" onClick={addCourse}>
                <Plus size={16} />
                <span>Thêm môn</span>
              </button>
            </div>
          </div>

          <div className="scroll-hint">Vuốt ngang để xem bảng</div>
          <div className="tool-table-wrap">
            <table className="tool-table gpa-table">
              <thead>
                <tr>
                  <th>STT</th>
                  <th>Tên môn học</th>
                  <th>Số tín chỉ</th>
                  {showCourseGroup && <th>Nhóm học phần</th>}
                  <th>Kiểu điểm</th>
                  <th>Điểm nhập</th>
                  <th>Điểm chữ</th>
                  <th>Hệ 4</th>
                  <th>Trạng thái</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {courses.map((course, index) => {
                  const grade = getCourseGrade(course, cohort);
                  const scale = getGradeScale(cohort, course.courseGroup);
                  const isFailed = grade?.status === 'Không đạt';
                  return (
                    <tr key={course.id}>
                      <td className="tool-index">{index + 1}</td>
                      <td>
                        <input
                          className="tool-input"
                          value={course.name}
                          onChange={(event) => updateCourse(course.id, { name: event.target.value })}
                          placeholder="Tên môn..."
                        />
                      </td>
                      <td>
                        <input
                          className="tool-input small"
                          type="number"
                          min="0"
                          step="0.5"
                          value={course.credits}
                          onChange={(event) => updateCourse(course.id, { credits: event.target.value })}
                          placeholder="0"
                        />
                      </td>
                      {showCourseGroup && (
                        <td>
                          <select
                            className="tool-select"
                            value={course.courseGroup ?? getDefaultCourseGroup(cohort)}
                            onChange={(event) => updateCourse(course.id, { courseGroup: event.target.value as CourseInput['courseGroup'] })}
                          >
                            {groupOptions.map((option) => (
                              <option key={option.id} value={option.id}>{option.shortLabel}</option>
                            ))}
                          </select>
                        </td>
                      )}
                      <td>
                        <select
                          className="tool-select"
                          value={course.inputType}
                          onChange={(event) => updateCourse(course.id, { inputType: event.target.value as CourseInput['inputType'] })}
                        >
                          <option value="score10">Thang 10</option>
                          <option value="letter">Điểm chữ</option>
                        </select>
                      </td>
                      <td>
                        {course.inputType === 'score10' ? (
                          <input
                            className="tool-input small"
                            type="number"
                            min="0"
                            max="10"
                            step="0.1"
                            value={course.score10}
                            onChange={(event) => updateCourse(course.id, { score10: event.target.value })}
                            placeholder="0.0"
                          />
                        ) : (
                          <select
                            className="tool-select small"
                            value={course.letter}
                            onChange={(event) => updateCourse(course.id, { letter: event.target.value as LetterGrade })}
                          >
                            {scale.rows.map((row) => (
                              <option key={row.letter} value={row.letter}>{row.letter}</option>
                            ))}
                          </select>
                        )}
                      </td>
                      <td><span className={`grade-badge ${isFailed ? 'danger' : ''}`}>{grade?.letter ?? '-'}</span></td>
                      <td>{grade ? grade.score4.toFixed(1) : '-'}</td>
                      <td>
                        {grade ? (
                          <span className={`status-badge ${isFailed ? 'danger' : 'success'}`}>
                            {grade.status}
                          </span>
                        ) : '-'}
                      </td>
                      <td>
                        <button className="icon-btn" onClick={() => removeCourse(course.id)} aria-label="Xóa môn">
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="gpa-summary">
            <div>
              <p className="result-label">GPA học kỳ</p>
              <div className="result-number text-gradient">{result.error ? '--' : result.gpa.toFixed(2)}</div>
            </div>
            <div className="result-grid">
              <div>
                <span>Tổng tín chỉ</span>
                <strong>{result.error ? '--' : result.totalCredits}</strong>
              </div>
              <div>
                <span>Số môn tính</span>
                <strong>{result.error ? '--' : result.countedCourses}</strong>
              </div>
            </div>
            <div className="gpa-summary-note">
              {result.error ? (
                <p className="tool-warning">{result.error}</p>
              ) : (
                <>
                  <p className="tool-note" style={{ marginBottom: '1rem' }}>GPA được tính theo trọng số số tín chỉ và làm tròn đến 2 chữ số.</p>
                  <div style={{ padding: '1rem', background: 'rgba(59, 130, 246, 0.1)', borderRadius: '8px', borderLeft: '4px solid #3b82f6', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    <strong style={{ color: '#2563eb', display: 'block', marginBottom: '0.25rem' }}>Lưu ý về môn học:</strong>
                    <ul style={{ paddingLeft: '1.25rem', margin: 0, display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                      <li>Giáo dục Thể chất, Giáo dục Quốc phòng không tính vào GPA.</li>
                      <li>Môn học lại, học cải thiện được tính vào GPA học kỳ, nhưng không được tính số tín chỉ để xét học bổng.</li>
                    </ul>
                  </div>
                </>
              )}
            </div>
          </div>
        </section>

        <section className="tool-panel grade-scale-panel">
          <div className="tool-panel-header compact-header">
            <div>
              <h2>Bảng quy đổi nhanh</h2>
              <p>Tra nhanh điểm chữ, khoảng điểm thang 10, điểm hệ 4 và trạng thái theo {cohort}.</p>
            </div>
          </div>
          <div className="grade-scale-sections">
            {getGradeScales(cohort).map((scale) => (
              <div key={scale.id} className="grade-scale-section">
                <div className="grade-scale-section-header">
                  <h3>{scale.label}</h3>
                  <p>{scale.applicability}</p>
                </div>
                <div className="grade-scale-grid">
                  {scale.rows.map((row) => {
                    const isFailed = row.status === 'Không đạt';
                    return (
                      <div key={`${scale.id}-${row.letter}`} className={`grade-scale-item ${isFailed ? 'failed' : 'passed'}`}>
                        <strong>{row.letter}</strong>
                        <span>{row.min10} - {row.max10}</span>
                        <em>{row.score4.toFixed(1)}</em>
                        <div className={`status-badge ${isFailed ? 'danger' : 'success'}`}>
                          {row.status}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
