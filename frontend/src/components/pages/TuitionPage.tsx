import { useState } from 'react';
import { Calculator, GraduationCap, MessageCircle, Minus, Plus } from 'lucide-react';
import {
  SCHOOL_YEARS,
  formatVnd,
  type SchoolYear,
  type TuitionProgram,
} from '../../data/tuitionRates';
import { estimateSemester, isTeacherTraining } from '../../utils/tuition';
import { sanitizeInteger } from '../../utils/numberInput';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton } from '../tool/ToolSection';
import { ProgramSearch } from '../tool/ProgramSearch';

interface TuitionPageProps {
  onAskChat: (text: string) => void;
}

const DEFAULT_YEAR: SchoolYear = SCHOOL_YEARS[SCHOOL_YEARS.length - 1];
const MAX_RETAKE_CREDITS = 99;
const DECREE_116_QUESTION = 'Chính sách hỗ trợ học phí và sinh hoạt phí theo Nghị định 116 cho sinh viên sư phạm là gì?';

/** Amount without the trailing " đ" that formatVnd adds, so the unit can be styled apart. */
const plainAmount = (value: number) => formatVnd(value).replace(/\s*đ$/, '');

export function TuitionPage({ onAskChat }: TuitionPageProps) {
  const [query, setQuery] = useState('');
  const [selectedProgram, setSelectedProgram] = useState<TuitionProgram | null>(null);
  const [schoolYear, setSchoolYear] = useState<SchoolYear>(DEFAULT_YEAR);
  const [retake, setRetake] = useState('0');

  const retakeCredits = Number(retake) || 0;
  const estimate = selectedProgram ? estimateSemester(selectedProgram, schoolYear, retakeCredits) : null;
  const hasRetake = Boolean(estimate && estimate.extra > 0);
  const teacherTraining = Boolean(selectedProgram && isTeacherTraining(selectedProgram.code));

  const handleQueryChange = (value: string) => {
    setQuery(value);
    if (selectedProgram && `${selectedProgram.code} - ${selectedProgram.name}` !== value) {
      setSelectedProgram(null);
    }
  };

  const selectProgram = (program: TuitionProgram) => {
    setSelectedProgram(program);
    setQuery(`${program.code} - ${program.name}`);
  };

  const clearProgram = () => {
    setSelectedProgram(null);
    setQuery('');
  };

  const handleReset = () => {
    clearProgram();
    setSchoolYear(DEFAULT_YEAR);
    setRetake('0');
  };

  const stepRetake = (delta: number) => {
    setRetake(String(Math.min(MAX_RETAKE_CREDITS, Math.max(0, retakeCredits + delta))));
  };

  return (
    <div className="page-container tool-page simplified sc-page tu-page">
      <ToolPageHeader
        icon={Calculator}
        title="Ước tính học phí"
        description="Tra học phí học kỳ theo ngành và năm học, cộng thêm tín chỉ học lại nếu có."
      />

      <div className="gpa-m-page-header sc-m-header">
        <div className="gpa-m-title-wrap">
          <Calculator size={18} aria-hidden="true" className="sc-m-title-icon" />
          <h1 className="gpa-m-page-title">Ước tính học phí</h1>
        </div>
      </div>

      <div className="sc-grid">
        <section className="sc-result" aria-label="Kết quả">
          <div aria-live="polite">
            <div className="sc-label">{hasRetake ? 'Tổng học phí học kỳ' : 'Học phí 1 học kỳ chính'}</div>
            <div className="sc-num">
              {estimate ? (
                <>
                  <b className="amt">{plainAmount(estimate.total)}</b>
                  <span>đ</span>
                </>
              ) : (
                <b className="none">--</b>
              )}
            </div>
            <div className="sc-cap-wrap">
              {estimate ? (
                <span className="sc-cap">
                  {hasRetake
                    ? `Học kỳ ${plainAmount(estimate.semester)} đ + học lại ${plainAmount(estimate.extra)} đ`
                    : `Năm học ${schoolYear.replace('-20', '–')}`}
                </span>
              ) : (
                <span className="sc-cap empty">Chọn ngành đào tạo bên dưới</span>
              )}
            </div>
          </div>

          {estimate && (
            <>
              <dl className="tu-facts">
                <div>
                  <dt>Học lại, cải thiện / TC</dt>
                  <dd>{formatVnd(estimate.perCredit)}</dd>
                </div>
                <div>
                  <dt>Học phí cả năm</dt>
                  <dd>{formatVnd(estimate.annual)}</dd>
                </div>
              </dl>

              {teacherTraining && (
                <div className="tu-note">
                  <GraduationCap size={18} aria-hidden="true" />
                  <div>
                    Ngành sư phạm: nếu được duyệt hưởng <b>Nghị định 116</b>, Nhà nước hỗ trợ tiền học phí và 3,63 triệu
                    đồng/tháng sinh hoạt phí (có điều kiện bồi hoàn).
                    <br />
                    <button type="button" className="tu-ask" onClick={() => onAskChat(DECREE_116_QUESTION)}>
                      <MessageCircle size={14} aria-hidden="true" />
                      Hỏi chatbot về Nghị định 116
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {estimate && <p className="tu-foot">Chưa gồm các khoản thu khác (nếu có). Số thực tế theo thông báo của trường.</p>}
        </section>

        <section className="sc-sheet" aria-labelledby="tu-sheet-title">
          <div className="sc-sheet-head">
            <h2 id="tu-sheet-title">Thông tin</h2>
            <ResetButton onClick={handleReset} />
          </div>

          <div className="sc-opt-body tu-inputs">
            <ProgramSearch
              id="tuition-program"
              label="Ngành đào tạo"
              query={query}
              selectedProgram={selectedProgram}
              onQueryChange={handleQueryChange}
              onSelect={selectProgram}
              onClear={clearProgram}
            />
            <div>
              <div className="sc-sub" id="tu-year-label">
                Năm học
              </div>
              <div className="sc-years" role="group" aria-labelledby="tu-year-label">
                {SCHOOL_YEARS.map((year) => (
                  <button key={year} type="button" aria-pressed={year === schoolYear} onClick={() => setSchoolYear(year)}>
                    {year.replace('-20', '–')}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="sc-row tu-row">
            <label className="sc-row-label" htmlFor="tuition-retake">
              Tín chỉ học lại, cải thiện
            </label>
            <span className="sc-step">
              <button type="button" onClick={() => stepRetake(-1)} aria-label="Giảm số tín chỉ">
                <Minus size={16} aria-hidden="true" />
              </button>
              <input
                id="tuition-retake"
                type="text"
                inputMode="numeric"
                maxLength={2}
                value={retake}
                onChange={(e) => setRetake(sanitizeInteger(e.target.value))}
                onBlur={() => setRetake(String(retakeCredits))}
              />
              <button type="button" onClick={() => stepRetake(1)} aria-label="Tăng số tín chỉ">
                <Plus size={16} aria-hidden="true" />
              </button>
            </span>
          </div>
        </section>
      </div>
    </div>
  );
}
