import React, { useState } from 'react';
import { X, BookOpen, Sparkles, Wrench, ArrowLeft } from 'lucide-react';
import type { StudyTip } from '../../../data/survivalGuide';
import { PomodoroTimer } from './PomodoroTimer';
import { TwoMinuteTimer } from './TwoMinuteTimer';
import { ParkinsonsCalculator } from './ParkinsonsCalculator';
import { SmartGoalBuilder } from './SmartGoalBuilder';
import { BlurtingNotepad } from './BlurtingNotepad';

const TOOL_MAP: Record<string, React.ComponentType> = {
  'pomodoro': PomodoroTimer,
  'two-minute-rule': TwoMinuteTimer,
  'parkinson': ParkinsonsCalculator,
  'smart-goals': SmartGoalBuilder,
  'blurting': BlurtingNotepad,
};

interface TipDetailModalProps {
  tip: StudyTip;
  onClose: () => void;
}

export const TipDetailModal = React.memo(function TipDetailModal({ tip, onClose }: TipDetailModalProps) {
  const ToolComponent = TOOL_MAP[tip.id] ?? null;
  const [view, setView] = useState<'description' | 'tool'>('description');

  return (
    <div
      className="sg-modal-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={tip.title}
    >
      <div className="sg-modal-content" onClick={e => e.stopPropagation()}>

        {/* ── DESCRIPTION VIEW ─────────────────────────── */}
        {view === 'description' && (
          <div className="sg-modal-view sg-view-description">
            {/* Header */}
            <div className="sg-modal-header">
              <div
                className="sg-icon-wrapper"
                style={{ marginBottom: 0, '--sg-color': tip.color } as React.CSSProperties}
              >
                <tip.icon size={22} />
              </div>
              <h2 className="sg-title" style={{ marginBottom: 0, fontSize: '1.4rem' }}>
                {tip.title}
              </h2>
              <button className="sg-modal-close" onClick={onClose} aria-label="Đóng">
                <X size={20} />
              </button>
            </div>

            {/* Scrollable body */}
            <div className={`sg-modal-body ${ToolComponent ? 'sg-modal-body--has-footer' : ''}`}>
              <div className="sg-section">
                <h3><BookOpen size={16} /> Phương pháp này là gì?</h3>
                <p>{tip.description}</p>
              </div>

              <div className="sg-section">
                <h3><Sparkles size={16} /> Cách ứng dụng</h3>
                <p style={{ whiteSpace: 'pre-line' }}>{tip.howToApply}</p>
              </div>

              <div className="sg-section">
                <h3>🎯 Ví dụ thực chiến tại HCMUE</h3>
                <div
                  className="sg-example-box"
                  style={{ '--primary': tip.color } as React.CSSProperties}
                >
                  <p>"{tip.hcmueExample}"</p>
                </div>
              </div>
            </div>

            {/* Sticky tool CTA footer */}
            {ToolComponent && (
              <div className="sg-modal-tool-footer">
                <button
                  className="sg-open-tool-btn"
                  style={{ '--sg-color': tip.color } as React.CSSProperties}
                  onClick={() => setView('tool')}
                >
                  <Wrench size={17} />
                  <span>🛠️ Thử ngay công cụ tương tác</span>
                  <span className="sg-open-tool-arrow">→</span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── TOOL VIEW ────────────────────────────────── */}
        {view === 'tool' && ToolComponent && (
          <div className="sg-modal-view sg-view-tool">
            {/* Tool header */}
            <div className="sg-modal-header sg-tool-header">
              <button
                className="sg-back-btn"
                onClick={() => setView('description')}
                aria-label="Quay lại"
              >
                <ArrowLeft size={18} />
              </button>
              <div
                className="sg-icon-wrapper"
                style={{ marginBottom: 0, '--sg-color': tip.color } as React.CSSProperties}
              >
                <tip.icon size={20} />
              </div>
              <div className="sg-tool-header-text">
                <span className="sg-tool-header-label">🛠️ Công cụ tương tác</span>
                <span className="sg-tool-header-title">{tip.title}</span>
              </div>
              <button className="sg-modal-close" onClick={onClose} aria-label="Đóng">
                <X size={20} />
              </button>
            </div>

            {/* Tool body */}
            <div className="sg-modal-body">
              <ToolComponent />
            </div>
          </div>
        )}

      </div>
    </div>
  );
});
