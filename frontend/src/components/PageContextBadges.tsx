import { CalendarDays, Database, GraduationCap, ShieldCheck } from 'lucide-react';

interface PageContextBadgesProps {
  cohort?: string;
  schoolYear?: string;
  source: string;
  advisory?: boolean;
  advisoryLabel?: string;
}

export function PageContextBadges({
  cohort,
  schoolYear,
  source,
  advisory = false,
  advisoryLabel = 'Kết quả tham khảo',
}: PageContextBadgesProps) {
  return (
    <div className="page-context-badges" aria-label="Phạm vi dữ liệu đang áp dụng">
      {cohort && (
        <span className="page-context-badge primary">
          <GraduationCap size={14} aria-hidden="true" />
          {cohort}
        </span>
      )}
      {schoolYear && (
        <span className="page-context-badge primary">
          <CalendarDays size={14} aria-hidden="true" />
          Đang chọn: {schoolYear}
        </span>
      )}
      <span className="page-context-badge">
        <Database size={14} aria-hidden="true" />
        {source}
      </span>
      {advisory && (
        <span className="page-context-badge advisory">
          <ShieldCheck size={14} aria-hidden="true" />
          {advisoryLabel}
        </span>
      )}
    </div>
  );
}
