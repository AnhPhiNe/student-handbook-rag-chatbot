import { useState } from 'react';
import { Copy, Check, RotateCcw, ChevronRight, Sparkles } from 'lucide-react';

interface SmartData {
  specific: string;
  measurable: string;
  achievable: string;
  relevant: string;
  timeBound: string;
}

const FIELDS = [
  {
    key: 'specific' as keyof SmartData,
    label: 'Specific – Cụ thể',
    shortLabel: 'Specific',
    emoji: '🎯',
    color: '#6366F1',
    placeholder: 'VD: Học thuộc 60 từ vựng chuyên ngành Sư phạm Anh',
    hint: 'Tôi muốn đạt điều gì cụ thể?',
  },
  {
    key: 'measurable' as keyof SmartData,
    label: 'Measurable – Đo lường được',
    shortLabel: 'Measurable',
    emoji: '📊',
    color: '#0EA5E9',
    placeholder: 'VD: Đạt 55/60 từ khi tự test trên Quizlet',
    hint: 'Tôi biết mình thành công khi nào?',
  },
  {
    key: 'achievable' as keyof SmartData,
    label: 'Achievable – Khả thi',
    shortLabel: 'Achievable',
    emoji: '💪',
    color: '#10B981',
    placeholder: 'VD: Học 10 từ/ngày trong 6 ngày liên tiếp',
    hint: 'Tôi sẽ thực hiện thế nào?',
  },
  {
    key: 'relevant' as keyof SmartData,
    label: 'Relevant – Liên quan',
    shortLabel: 'Relevant',
    emoji: '🔗',
    color: '#F59E0B',
    placeholder: 'VD: Để đủ điều kiện tốt nghiệp chuẩn đầu ra B1',
    hint: 'Mục tiêu này quan trọng vì sao?',
  },
  {
    key: 'timeBound' as keyof SmartData,
    label: 'Time-bound – Có thời hạn',
    shortLabel: 'Time-bound',
    emoji: '⏰',
    color: '#EF4444',
    placeholder: 'VD: Hoàn thành trước 21h thứ Sáu tuần này',
    hint: 'Deadline cụ thể là khi nào?',
  },
];

function buildGoalStatement(d: SmartData): string {
  return (
    `Mục tiêu của tôi là ${d.specific}. ` +
    `Tôi sẽ biết mình đã thành công khi ${d.measurable}. ` +
    `Tôi có thể thực hiện được điều này vì tôi sẽ ${d.achievable}. ` +
    `Mục tiêu này phù hợp và có ý nghĩa với tôi vì ${d.relevant}. ` +
    `Tôi cam kết hoàn thành trước ${d.timeBound}.`
  );
}

export function SmartGoalBuilder() {
  const [data, setData] = useState<SmartData>({
    specific: '', measurable: '', achievable: '', relevant: '', timeBound: '',
  });
  const [confirmed, setConfirmed] = useState(false);
  const [copied, setCopied] = useState(false);

  const filledCount = Object.values(data).filter(v => v.trim() !== '').length;
  const allFilled = filledCount === 5;
  const goalStatement = allFilled ? buildGoalStatement(data) : '';

  const handleCopy = () => {
    navigator.clipboard.writeText(goalStatement).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleReset = () => {
    setData({ specific: '', measurable: '', achievable: '', relevant: '', timeBound: '' });
    setConfirmed(false);
  };

  /* ── RESULT VIEW ─────────────────────────────────────────── */
  if (confirmed && allFilled) {
    return (
      <div className="smart-result-view">
        {/* Header card */}
        <div className="smart-rv-header">
          <span className="smart-rv-icon">🎯</span>
          <div>
            <h4>Mục tiêu SMART của bạn</h4>
            <p>Cam kết với bản thân và bắt đầu ngay hôm nay!</p>
          </div>
        </div>

        {/* Statement */}
        <blockquote className="smart-rv-statement">
          {goalStatement}
        </blockquote>

        {/* Breakdown */}
        <div className="smart-rv-breakdown">
          {FIELDS.map(field => (
            <div key={field.key} className="smart-rv-row">
              <span className="smart-rv-dot" style={{ background: field.color }} />
              <span className="smart-rv-label" style={{ color: field.color }}>
                {field.emoji} {field.shortLabel}
              </span>
              <span className="smart-rv-val">{data[field.key]}</span>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div className="smart-rv-actions">
          <button className="smart-rv-copy-btn" onClick={handleCopy}>
            {copied ? <><Check size={15} /> Đã copy!</> : <><Copy size={15} /> Copy mục tiêu</>}
          </button>
          <button className="smart-rv-reset-btn" onClick={handleReset}>
            <RotateCcw size={15} /> Đặt lại
          </button>
        </div>
      </div>
    );
  }

  /* ── FORM VIEW ───────────────────────────────────────────── */
  return (
    <div className="smart-builder">
      {/* Progress */}
      <div className="smart-progress-bar">
        <div className="smart-progress-fill" style={{ width: `${(filledCount / 5) * 100}%` }} />
      </div>
      <p className="smart-progress-label">Đã điền {filledCount}/5 trường</p>

      {/* Fields */}
      <div className="smart-fields">
        {FIELDS.map(field => (
          <div key={field.key} className={`smart-field ${data[field.key] ? 'filled' : ''}`}>
            <label className="smart-field-label">
              <span style={{ color: field.color }}>{field.emoji}</span>
              <span className="smart-field-name">{field.label}</span>
              <span className="smart-hint">{field.hint}</span>
            </label>
            <input
              className="smart-input"
              placeholder={field.placeholder}
              value={data[field.key]}
              onChange={e => setData(prev => ({ ...prev, [field.key]: e.target.value }))}
            />
          </div>
        ))}
      </div>

      {/* Confirm */}
      {allFilled && (
        <button className="smart-confirm-btn" onClick={() => setConfirmed(true)}>
          <Sparkles size={16} />
          Xem mục tiêu SMART của tôi
          <ChevronRight size={16} />
        </button>
      )}
    </div>
  );
}
