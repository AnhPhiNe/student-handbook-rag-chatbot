import { Database, ShieldCheck } from 'lucide-react';
import type { StructuredCellValue, StructuredResult } from '../hooks/useChat';

const FIELD_LABELS: Record<string, string> = {
  academic_classification: 'Xếp loại học tập',
  academic_score_range: 'Khoảng điểm học tập',
  address: 'Địa chỉ',
  category: 'Nhóm',
  certificate: 'Chứng chỉ',
  cohort: 'Khóa',
  conduct_score_condition: 'Điều kiện điểm rèn luyện',
  email: 'Email',
  equivalent_level_3: 'Tương đương bậc 3',
  equivalent_level_4: 'Tương đương bậc 4',
  faculty_name: 'Khoa',
  label: 'Xếp loại',
  language: 'Ngoại ngữ',
  level_or_scale: 'Bậc / thang điểm',
  letter_grade: 'Điểm chữ',
  matched_level: 'Bậc tương đương',
  matched_score: 'Điểm đối chiếu',
  matched_value: 'Giá trị đối chiếu',
  max_years: 'Thời gian tối đa',
  maximum_duration: 'Thời gian tối đa',
  minimum: 'Từ',
  maximum: 'Đến',
  passing_score: 'Điểm đạt',
  phone: 'Điện thoại',
  program_type: 'Loại chương trình',
  program_name: 'Ngành',
  range: 'Khoảng điểm',
  required_score: 'Điểm yêu cầu',
  scholarship_level: 'Mức học bổng',
  scholarship_score_range: 'Khoảng điểm học bổng',
  standard_duration: 'Thời gian chuẩn',
  summary: 'Thông tin',
  table_name: 'Bảng',
  training_mode: 'Hình thức đào tạo',
  unit_name: 'Đơn vị',
  responsibilities: 'Chức năng / nhiệm vụ',
  value: 'Giá trị',
};

function fieldLabel(field: string): string {
  if (FIELD_LABELS[field]) return FIELD_LABELS[field];
  const words = field.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function displayValue(value: StructuredCellValue | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Có' : 'Không';
  return String(value);
}

interface StructuredResultsProps {
  results: StructuredResult[];
}

export function StructuredResults({ results }: StructuredResultsProps) {
  if (results.length === 0) return null;

  return (
    <section className="structured-results" aria-label="Kết quả tra cứu dữ liệu">
      <div className="structured-results-heading">
        <Database size={17} aria-hidden="true" />
        <span>Kết quả tra cứu dữ liệu</span>
      </div>

      <div className="structured-results-list">
        {results.map((result) => (
          <article className="structured-result-card" key={result.id}>
            <header className="structured-result-card-header">
              <div>
                <h3>{result.title}</h3>
                <p>{result.provenance.source_label || 'Dữ liệu có cấu trúc từ Sổ tay sinh viên'}</p>
              </div>
              {result.cohort && <span className="structured-result-badge">{result.cohort}</span>}
            </header>

            {result.applicability && (
              <p className="structured-result-applicability">{result.applicability}</p>
            )}

            <div className="structured-result-table-wrap" tabIndex={0} role="region" aria-label={result.title}>
              <table className="structured-result-table">
                <thead>
                  <tr>
                    {result.columns.map((column) => (
                      <th scope="col" key={column}>{fieldLabel(column)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, rowIndex) => (
                    <tr key={`${result.id}:${rowIndex}`}>
                      {result.columns.map((column) => (
                        <td key={column}>{displayValue(row[column])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {Object.values(result.field_provenance || {}).map((provenance) => (
              <div className="structured-result-provenance" key={provenance.source_label}>
                <ShieldCheck size={14} aria-hidden="true" />
                <span>{provenance.source_label}; đây là dữ liệu danh mục đã chuẩn hóa, không phải trích dẫn trực tiếp từ một trang quy định.</span>
              </div>
            ))}
          </article>
        ))}
      </div>
    </section>
  );
}
