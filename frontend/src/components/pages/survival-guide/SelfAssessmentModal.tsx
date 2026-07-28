import { useState, useEffect, useRef } from 'react';
import { X, ChevronLeft, ChevronRight, CheckCircle2, RotateCcw, AlertCircle, BookOpen } from 'lucide-react';
import { 
  type CurrentProblem, type ImprovementGoal, type ContentType, type TimeAvailable, 
  type AssessmentAnswers, type EvaluationResult, evaluateStudyHabits 
} from '../../../utils/studyHabitEvaluator';
import { survivalGuideTips } from '../../../data/survivalGuide';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenTip?: (tipId: string) => void;
}

type RadioSelection =
  | ['goal', ImprovementGoal]
  | ['content', ContentType]
  | ['time', TimeAvailable];

const PROBLEMS: { id: CurrentProblem; label: string }[] = [
  { id: 'procrastinate', label: '🥱 Hay trì hoãn, khó bắt đầu' },
  { id: 'distracted', label: '📱 Dễ xao nhãng, mất tập trung' },
  { id: 'low-efficiency', label: '🐢 Học lâu nhưng kém hiệu quả' },
  { id: 'memory-issues', label: '🧠 Học trước quên sau' },
  { id: 'practice-issues', label: '🤔 Hiểu lý thuyết, bí bài tập' },
  { id: 'time-issues', label: '🗓️ Không biết sắp xếp lịch học' },
  { id: 'give-up', label: '🏳️ Có mục tiêu, thường bỏ cuộc' },
  { id: 'too-many-subjects', label: '📚 Quá nhiều môn, khó ưu tiên' },
  { id: 'comprehension-issues', label: '🤯 Khó hiểu nội dung phức tạp' },
  { id: 'note-taking-issues', label: '📝 Ghi chép tràn lan đại hải' },
];

const GOALS: { id: ImprovementGoal; label: string }[] = [
  { id: 'focus', label: '🎯 Tập trung tốt hơn' },
  { id: 'memory', label: '🧠 Nhớ lâu hơn' },
  { id: 'deep-understanding', label: '💡 Hiểu bài sâu hơn' },
  { id: 'exercises', label: '✍️ Làm bài tập tốt hơn' },
  { id: 'deadline', label: '⏰ Hoàn thành đúng hạn' },
  { id: 'exam-prep', label: '🎓 Chuẩn bị cho kỳ thi' },
];

const CONTENTS: { id: ContentType; label: string }[] = [
  { id: 'theory', label: '📖 Môn học thuộc' },
  { id: 'logic', label: '🧮 Môn tư duy logic' },
  { id: 'mixed', label: '🍱 Đan xen cả hai' },
];

const TIMES: { id: TimeAvailable; label: string }[] = [
  { id: 'under-30', label: '⚡ Dưới 30 phút' },
  { id: '30-60', label: '⏳ 30 – 60 phút' },
  { id: 'over-60', label: '🕰️ Trên 60 phút' },
];

export function SelfAssessmentModal({ isOpen, onClose, onOpenTip }: ModalProps) {
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1);
  const [answers, setAnswers] = useState<AssessmentAnswers>({
    problems: [],
    goal: null,
    content: null,
    time: null
  });
  const [result, setResult] = useState<EvaluationResult | null>(null);
  const [activeMethodId, setActiveMethodId] = useState<string | null>(null);
  
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Prevent scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => { document.body.style.overflow = 'unset'; };
  }, [isOpen]);

  if (!isOpen) return null;

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  const toggleProblem = (id: CurrentProblem) => {
    setAnswers(prev => {
      const isSelected = prev.problems.includes(id);
      if (!isSelected && prev.problems.length >= 3) return prev;
      const newProblems = isSelected
        ? prev.problems.filter(p => p !== id)
        : [...prev.problems, id];

      // Auto-advance if exactly 3 are selected
      if (newProblems.length === 3) {
        setTimeout(() => setStep(2), 400); // 400ms delay for visual feedback
      }

      return { ...prev, problems: newProblems };
    });
  };

  const handleNext = () => {
    if (step === 1 && answers.problems.length > 0) setStep(2);
    else if (step === 2 && answers.goal) setStep(3);
    else if (step === 3 && answers.content) setStep(4);
    else if (step === 4 && answers.time) {
      const res = evaluateStudyHabits(answers);
      setResult(res);
      setActiveMethodId(res.primaryMethodId);
      setStep(5);
    }
  };

  const handleRadioSelect = (...[field, value]: RadioSelection) => {
    if (field === 'goal') {
      setAnswers(prev => ({ ...prev, goal: value }));
    } else if (field === 'content') {
      setAnswers(prev => ({ ...prev, content: value }));
    } else {
      setAnswers(prev => ({ ...prev, time: value }));
    }
    // Auto advance after a brief delay for UX
    setTimeout(() => {
      if (field === 'goal') setStep(3);
      if (field === 'content') setStep(4);
      if (field === 'time') {
        const res = evaluateStudyHabits({ ...answers, time: value });
        setResult(res);
        setActiveMethodId(res.primaryMethodId);
        setStep(5);
      }
    }, 300);
  };

  const resetForm = () => {
    setAnswers({ problems: [], goal: null, content: null, time: null });
    setResult(null);
    setActiveMethodId(null);
    setStep(1);
  };

  const activeMethodData = result?.allMethods.find(m => m.id === (activeMethodId || result.primaryMethodId));
  const activeTip = activeMethodData ? survivalGuideTips.find(t => t.id === activeMethodData.id) : null;
  const supportTips = result ? result.allMethods.filter(m => m.id !== activeMethodData?.id).map(m => survivalGuideTips.find(t => t.id === m.id)).filter(Boolean) : [];

  return (
    <div className="sg-modal-overlay" onClick={handleOverlayClick} role="dialog" aria-modal="true">
      <div className="sg-modal-content assessment-modal" ref={modalRef}>
        <div className="sg-modal-header">
          <h2 className="sg-title" style={{ marginBottom: 0 }}>Tự đánh giá thói quen học tập</h2>
          <div className="sg-modal-actions" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <button className="sg-modal-close" onClick={onClose} aria-label="Đóng">
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Step Progress Bar */}
        {step < 5 && (
          <div className="sg-step-progress">
            {[1, 2, 3, 4].map(s => (
              <div key={s} className={`sg-step-dot ${step >= s ? 'active' : ''} ${step > s ? 'done' : ''}`}>
                <span>{s}</span>
              </div>
            ))}
            <div className="sg-step-label">Bước {step}/4</div>
          </div>
        )}

        <div className="sg-modal-body">
          {/* STEP 1: Problems */}
          {step === 1 && (
            <div className="assessment-step animate-in">
              <div className="step-header">
                <h3><span className="step-num">1</span> Vấn đề bạn đang gặp phải là gì?</h3>
                <span className={`selection-counter ${answers.problems.length > 0 ? 'active' : ''} ${answers.problems.length === 3 ? 'maxed' : ''}`}>
                  {answers.problems.length === 0 ? 'Đã chọn: 0/3' : `${answers.problems.length} lựa chọn`}
                </span>
              </div>
              <p className="step-desc">Chọn tối đa 3 tình trạng mô tả đúng nhất về bạn hiện tại.</p>
              
              <div className="options-grid">
                {PROBLEMS.map(p => {
                  const isSelected = answers.problems.includes(p.id);
                  const isDisabled = !isSelected && answers.problems.length >= 3;
                  return (
                    <label 
                      key={p.id} 
                      className={`option-card checkbox-card ${isSelected ? 'selected' : ''} ${isDisabled ? 'disabled' : ''}`}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        disabled={isDisabled}
                        onChange={() => toggleProblem(p.id)}
                        className="sr-only"
                      />
                      <div className="option-content">
                        <div className="checkbox-indicator">
                          {isSelected && <CheckCircle2 size={16} />}
                        </div>
                        <span>{p.label}</span>
                      </div>
                    </label>
                  );
                })}
              </div>

              <div className="step-footer">
                {answers.problems.length === 0 && (
                  <div className="validation-msg">
                    <AlertCircle size={16} /> Vui lòng chọn ít nhất 1 vấn đề
                  </div>
                )}
                <button 
                  className="btn-primary" 
                  onClick={handleNext}
                  disabled={answers.problems.length === 0}
                >
                  Tiếp tục <ChevronRight size={18} />
                </button>
              </div>
            </div>
          )}

          {/* STEP 2: Goal */}
          {step === 2 && (
            <div className="assessment-step animate-in">
              <div className="step-header">
                <h3><span className="step-num">2</span> Bạn đang muốn cải thiện điều gì nhất?</h3>
                <span className="selection-counter">1 lựa chọn</span>
              </div>
              
              <div className="options-grid">
                {GOALS.map(g => {
                  const isSelected = answers.goal === g.id;
                  return (
                    <label key={g.id} className={`option-card radio-card ${isSelected ? 'selected' : ''}`}>
                      <input 
                        type="radio" 
                        name="goal"
                        checked={isSelected}
                        onChange={() => handleRadioSelect('goal', g.id)}
                        className="sr-only"
                      />
                      <div className="option-content">
                        <div className="radio-indicator">
                          {isSelected && <div className="radio-inner" />}
                        </div>
                        <span>{g.label}</span>
                      </div>
                    </label>
                  );
                })}
              </div>

              <div className="step-footer space-between">
                <button className="btn-secondary" onClick={() => setStep(1)}>
                  <ChevronLeft size={18} /> Quay lại
                </button>
                <button 
                  className="btn-primary" 
                  onClick={handleNext}
                  disabled={!answers.goal}
                >
                  Tiếp tục <ChevronRight size={18} />
                </button>
              </div>
            </div>
          )}

          {/* STEP 3: Content */}
          {step === 3 && (
            <div className="assessment-step animate-in">
              <div className="step-header">
                <h3><span className="step-num">3</span> Bạn thường học nội dung nào?</h3>
                <span className="selection-counter">1 lựa chọn</span>
              </div>
              
              <div className="options-grid">
                {CONTENTS.map(c => {
                  const isSelected = answers.content === c.id;
                  return (
                    <label key={c.id} className={`option-card radio-card ${isSelected ? 'selected' : ''}`}>
                      <input 
                        type="radio" 
                        name="content"
                        checked={isSelected}
                        onChange={() => handleRadioSelect('content', c.id)}
                        className="sr-only"
                      />
                      <div className="option-content">
                        <div className="radio-indicator">
                          {isSelected && <div className="radio-inner" />}
                        </div>
                        <span>{c.label}</span>
                      </div>
                    </label>
                  );
                })}
              </div>

              <div className="step-footer space-between">
                <button className="btn-secondary" onClick={() => setStep(2)}>
                  <ChevronLeft size={18} /> Quay lại
                </button>
                <button 
                  className="btn-primary" 
                  onClick={handleNext}
                  disabled={!answers.content}
                >
                  Tiếp tục <ChevronRight size={18} />
                </button>
              </div>
            </div>
          )}

          {/* STEP 4: Time */}
          {step === 4 && (
            <div className="assessment-step animate-in">
              <div className="step-header">
                <h3><span className="step-num">4</span> Bạn thường có bao nhiêu thời gian?</h3>
                <span className="selection-counter">1 lựa chọn</span>
              </div>
              
              <div className="options-grid">
                {TIMES.map(t => {
                  const isSelected = answers.time === t.id;
                  return (
                    <label key={t.id} className={`option-card radio-card ${isSelected ? 'selected' : ''}`}>
                      <input 
                        type="radio" 
                        name="time"
                        checked={isSelected}
                        onChange={() => handleRadioSelect('time', t.id)}
                        className="sr-only"
                      />
                      <div className="option-content">
                        <div className="radio-indicator">
                          {isSelected && <div className="radio-inner" />}
                        </div>
                        <span>{t.label}</span>
                      </div>
                    </label>
                  );
                })}
              </div>

              <div className="step-footer space-between">
                <button className="btn-secondary" onClick={() => setStep(3)}>
                  <ChevronLeft size={18} /> Quay lại
                </button>
                <button 
                  className="btn-primary" 
                  onClick={handleNext}
                  disabled={!answers.time}
                >
                  Xem kết quả <CheckCircle2 size={18} />
                </button>
              </div>
            </div>
          )}

          {/* STEP 5: Result */}
          {step === 5 && result && activeTip && activeMethodData && (
            <div className="assessment-step result-step animate-in">
              <div className="result-banner" style={{ marginTop: '0.75rem' }}>
                <span className="result-badge">
                  {activeMethodId === result.primaryMethodId ? "Phương pháp tốt nhất cho bạn" : "Phương pháp bạn đang xem"}
                </span>
                <div className="primary-method" style={{ '--sg-color': activeTip.color } as React.CSSProperties}>
                  <div className="primary-icon"><activeTip.icon size={28} /></div>
                  <div className="primary-info" style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.15rem' }}>
                      <h2 style={{ margin: 0 }}>{activeTip.title}</h2>
                      <button className="restart-text-btn" onClick={resetForm} style={{ padding: '0.5rem 1rem', fontSize: '0.95rem' }}>
                        <RotateCcw size={16} /> Đánh giá lại
                      </button>
                    </div>
                    <p>{activeTip.shortDesc}</p>
                  </div>
                </div>
                
                <div className="action-plan-box">
                  <h4><div className="sec-icon">🚀</div> Action Plan</h4>
                  <div className="action-plan-content" style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                    {activeMethodData.actionPlan.split('\n').map((line, idx) => {
                      const firstSpace = line.indexOf(' ');
                      if (firstSpace !== -1 && (line.substring(0, firstSpace).includes('️⃣') || line.substring(0, firstSpace).match(/^\d+$/))) {
                        const icon = line.substring(0, firstSpace);
                        const text = line.substring(firstSpace + 1);
                        return (
                          <div key={idx} style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                            <span style={{ flexShrink: 0 }}>{icon}</span>
                            <span style={{ color: 'var(--text-primary)', lineHeight: 1.6, fontSize: '0.95rem' }}>{text}</span>
                          </div>
                        );
                      }
                      return <p key={idx} style={{ margin: 0, color: 'var(--text-primary)', lineHeight: 1.6, fontSize: '0.95rem' }}>{line}</p>;
                    })}
                  </div>
                </div>

                <div className="reasons-list compact">
                  {activeMethodData.reasons.map((r, idx) => (
                    <div key={idx} className="reason-item">
                      <CheckCircle2 size={16} className="text-primary" />
                      <span>{r}</span>
                    </div>
                  ))}
                </div>

                {onOpenTip && (
                  <button
                    className="sg-view-detail-btn"
                    onClick={() => onOpenTip(activeMethodId || result.primaryMethodId)}
                  >
                    <BookOpen size={16} /> Xem chi tiết &amp; thử tool tương tác
                  </button>
                )}
              </div>

              {supportTips.length > 0 && (
                <div className="support-methods-section compact">
                  <h3><div className="sec-icon">🤝</div> Phương pháp {activeMethodId === result.primaryMethodId ? "hỗ trợ" : "khác"}</h3>
                  <div className="support-list">
                    {supportTips.map(tip => (
                      tip && <div 
                        key={tip.id} 
                        className="support-item clickable" 
                        style={{ '--sg-color': tip.color } as React.CSSProperties}
                        onClick={() => setActiveMethodId(tip.id)}
                      >
                        <div className="sup-icon-wrap"><tip.icon size={16} className="sup-icon" /></div>
                        <div className="sup-info">
                          <h4>{tip.title}</h4>
                          <p>{tip.shortDesc}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
