import { useState } from 'react';
import { BookOpen, Calculator } from 'lucide-react';
import {
  SCHOOL_YEARS,
  formatVnd,
  type SchoolYear,
  type TuitionProgram,
} from '../../data/tuitionRates';
import { ToolPageHeader } from '../tool/ToolPageHeader';
import { ResetButton, ToolSection } from '../tool/ToolSection';
import { SelectField } from '../tool/fields';
import { NumberStepper } from '../tool/NumberStepper';
import { ProgramSearch } from '../tool/ProgramSearch';
import { ResultCard } from '../tool/ResultCard';
import { DetailsToggle } from '../tool/DetailsToggle';
import { ResultFacts } from '../tool/ResultFacts';

const DEFAULT_YEAR: SchoolYear = '2024-2025';
const DEFAULT_CREDITS = '15';
const YEAR_OPTIONS = SCHOOL_YEARS.map((year) => ({ value: year, label: `Năm học ${year}` }));

export function TuitionPage() {
  const [query, setQuery] = useState('');
  const [selectedProgram, setSelectedProgram] = useState<TuitionProgram | null>(null);
  const [schoolYear, setSchoolYear] = useState<SchoolYear>(DEFAULT_YEAR);
  const [credits, setCredits] = useState(DEFAULT_CREDITS);

  const creditCount = Number(credits);
  const hasValidCredits = Number.isFinite(creditCount) && creditCount > 0;
  const annual = selectedProgram?.annual[schoolYear] ?? 0;
  const semester = annual / 2;
  const perCredit = selectedProgram?.perCredit[schoolYear] ?? 0;
  const creditEstimate = hasValidCredits ? perCredit * creditCount : 0;

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
    setCredits(DEFAULT_CREDITS);
  };

  return (
    <div className="page-container tool-page simplified">
      <ToolPageHeader
        icon={Calculator}
        title="Ước tính học phí"
        description="Tra học phí theo ngành và năm học, rồi ước tính theo số tín chỉ bạn đăng ký."
      />

      <div className="tool-grid">
        <div className="tool-main">
          <ToolSection id="tuition-input" title="Ngành và học kỳ" action={<ResetButton onClick={handleReset} />}>
            <ProgramSearch
              id="tuition-program"
              label="Ngành đào tạo"
              hint="Gõ tên hoặc mã ngành rồi chọn trong danh sách."
              query={query}
              selectedProgram={selectedProgram}
              onQueryChange={handleQueryChange}
              onSelect={selectProgram}
              onClear={clearProgram}
            />
            <div className="tool-fields">
              <SelectField
                id="tuition-year"
                label="Năm học"
                value={schoolYear}
                options={YEAR_OPTIONS}
                onChange={setSchoolYear}
              />
              <NumberStepper
                id="tuition-credits"
                label="Số tín chỉ học kỳ"
                hint="Số tín chỉ bạn dự kiến đăng ký."
                value={credits}
                min={0}
                fallback={0}
                onChange={setCredits}
              />
            </div>
          </ToolSection>
        </div>

        <ResultCard id="tuition-result">
          {selectedProgram ? (
            <>
              <div aria-live="polite">
                <p className="tool-big-label">
                  {hasValidCredits ? `Học phí cho ${creditCount} tín chỉ` : `Học phí cả năm ${schoolYear}`}
                </p>
                <p className="tool-big money">
                  <strong>{formatVnd(hasValidCredits ? creditEstimate : annual)}</strong>
                </p>
              </div>
              <p className="tool-sub">
                {selectedProgram.name} ({selectedProgram.code})
              </p>
              <ResultFacts
                facts={[
                  { label: 'Đơn giá / TC', value: formatVnd(perCredit) },
                  { label: 'Cả năm', value: formatVnd(annual) },
                  { label: '1 học kỳ', value: formatVnd(semester) },
                ]}
              />

              <DetailsToggle id="tuition-calc" label="Xem cách tính">
                <dl className="tool-calc">
                  <dt>Đơn giá 1 tín chỉ ({schoolYear})</dt>
                  <dd>{formatVnd(perCredit)}</dd>
                  {hasValidCredits && (
                    <>
                      <dt>Học phí theo tín chỉ</dt>
                      <dd>{creditCount} × {formatVnd(perCredit)} = {formatVnd(creditEstimate)}</dd>
                    </>
                  )}
                  <dt>Học phí cả năm</dt>
                  <dd>{formatVnd(annual)}</dd>
                  <dt>Ước tính 1 học kỳ (cả năm ÷ 2)</dt>
                  <dd>{formatVnd(semester)}</dd>
                </dl>
              </DetailsToggle>

              <p className="tool-source">
                <BookOpen size={14} aria-hidden="true" />
                Theo bảng học phí năm học {schoolYear}. Số tiền thực tế theo thông báo thu học phí của Nhà trường.
              </p>
            </>
          ) : (
            <p className="tool-empty">Chọn ngành đào tạo để xem học phí.</p>
          )}
        </ResultCard>
      </div>
    </div>
  );
}
