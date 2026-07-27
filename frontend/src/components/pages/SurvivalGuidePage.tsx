import { useState, useEffect, useRef, useCallback } from 'react';
import { Sparkles, Bookmark, ClipboardCheck } from 'lucide-react';
import { survivalGuideTips, type StudyTip, type TipCategory } from '../../data/survivalGuide';
import { HorizontalScrollHint } from '../HorizontalScrollHint';
import { SelfAssessmentModal } from './survival-guide/SelfAssessmentModal';
import { TipDetailModal } from './survival-guide/TipDetailModal';

const TOOL_IDS = new Set(['pomodoro', 'two-minute-rule', 'parkinson', 'smart-goals', 'blurting']);

type FilterTab = 'all' | TipCategory | 'saved';

const TABS: { id: FilterTab; label: string }[] = [
  { id: 'all', label: '✨ Tất cả' },
  { id: 'memory', label: '🧠 Ghi nhớ' },
  { id: 'focus', label: '⏳ Tập trung' },
  { id: 'goals', label: '🎯 Mục tiêu' },
  { id: 'saved', label: '⭐ Đã lưu' },
];

const SAVED_KEY = 'sg_bookmarks';

function getSaved(): string[] {
  try { return JSON.parse(localStorage.getItem(SAVED_KEY) || '[]'); } catch { return []; }
}
function toggleSaved(id: string): string[] {
  const saved = getSaved();
  const next = saved.includes(id) ? saved.filter(s => s !== id) : [...saved, id];
  localStorage.setItem(SAVED_KEY, JSON.stringify(next));
  return next;
}

export function SurvivalGuidePage() {
  const [selectedTip, setSelectedTip] = useState<StudyTip | null>(null);
  const [isAssessmentOpen, setIsAssessmentOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<FilterTab>('all');
  const [saved, setSaved] = useState<string[]>(getSaved);
  const tabFilterRef = useRef<HTMLDivElement | null>(null);
  const sectionRefs = useRef<(HTMLElement | null)[]>([]);
  const observerRef = useRef<IntersectionObserver | null>(null);

  // Scroll fade-in: re-observe after every render so newly mounted sections get picked up
  const attachObserver = useCallback(() => {
    if (observerRef.current) observerRef.current.disconnect();
    observerRef.current = new IntersectionObserver(
      entries => entries.forEach(e => {
        if (e.isIntersecting) e.target.classList.add('sg-visible');
      }),
      { threshold: 0, rootMargin: '0px 0px 200px 0px' }
    );
    sectionRefs.current.forEach(el => el && observerRef.current!.observe(el));
  }, []);

  useEffect(() => {
    // Small delay so React has committed DOM nodes before we observe
    const id = setTimeout(attachObserver, 50);
    return () => { clearTimeout(id); observerRef.current?.disconnect(); };
  }, [activeTab, attachObserver]);


  const handleBookmark = useCallback((e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setSaved(toggleSaved(id));
  }, []);

  const filteredTips = survivalGuideTips.filter(t => {
    if (activeTab === 'all') return true;
    if (activeTab === 'saved') return saved.includes(t.id);
    return t.category === activeTab;
  });

  // Group by category for "all" view, flat list for filtered view
  const memoryTips = filteredTips.filter(t => t.category === 'memory');
  const focusTips = filteredTips.filter(t => t.category === 'focus');
  const goalsTips = filteredTips.filter(t => t.category === 'goals');

  const renderCard = (tip: StudyTip) => {
    const IconComponent = tip.icon;
    const isSaved = saved.includes(tip.id);
    return (
      <div
        key={tip.id}
        className="sg-card"
        style={{ '--sg-color': tip.color } as React.CSSProperties}
        onClick={() => setSelectedTip(tip)}
      >
        <div className="sg-glow" />
        <button
          className={`sg-bookmark-btn ${isSaved ? 'active' : ''}`}
          onClick={e => handleBookmark(e, tip.id)}
          title={isSaved ? 'Bỏ lưu' : 'Lưu phương pháp này'}
        >
          <Bookmark size={15} fill={isSaved ? 'currentColor' : 'none'} />
        </button>
        <div className="sg-card-content">
          <div className="sg-icon-wrapper">
            <IconComponent size={24} />
          </div>
          <h3 className="sg-title">{tip.title}</h3>
          <p className="sg-desc">{tip.shortDesc}</p>
          {TOOL_IDS.has(tip.id) && <span className="sg-tool-badge">🛠️ Có tool tương tác</span>}
        </div>
      </div>
    );
  };

  const renderSection = (title: string, tips: StudyTip[], idx: number) => {
    if (tips.length === 0) return null;
    return (
      <section
        key={title}
        className="sg-category-section sg-fade-section"
        ref={el => { sectionRefs.current[idx] = el; }}
      >
        <h2 className="sg-category-title">{title}</h2>
        <div className="sg-grid">{tips.map(renderCard)}</div>
      </section>
    );
  };



  return (
    <div className="survival-guide-container">
      <div className="sg-header">
        <h1><Sparkles size={28} className="text-primary" /> Phương pháp học tập ở HCMUE</h1>
        <p>Kho tàng phương pháp học tập khoa học giúp bạn tối ưu hóa thời gian và công sức!</p>
      </div>

      {/* CTA Banner */}
      <div className="sg-cta-banner" onClick={() => setIsAssessmentOpen(true)}>
        <div className="sg-cta-inner">
          <div className="sg-cta-icon">🧭</div>
          <div className="sg-cta-text">
            <strong>Chưa biết bắt đầu từ đâu?</strong>
            <span>Làm bài tự đánh giá 4 câu hỏi – AI sẽ gợi ý phương pháp phù hợp nhất với bạn!</span>
          </div>
          <button className="sg-cta-btn">
            <ClipboardCheck size={18} /> Thử ngay
          </button>
        </div>
      </div>

      {/* Tab Filter */}
      <div className="sg-tab-filter" ref={tabFilterRef}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`sg-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.id === 'saved' && saved.length > 0 && (
              <span className="sg-tab-badge">{saved.length}</span>
            )}
          </button>
        ))}
      </div>
      <HorizontalScrollHint targetRef={tabFilterRef} />

      {/* Content */}
      <div className="sg-sections-container">
        {activeTab === 'saved' && saved.length === 0 ? (
          <div className="sg-empty-saved">
            <span>🔖</span>
            <p>Bạn chưa lưu phương pháp nào. Bấm icon <Bookmark size={14} /> trên card để lưu lại!</p>
          </div>
        ) : activeTab === 'all' ? (
          <>
            {renderSection('🧠 Học và ghi nhớ hiệu quả', memoryTips, 0)}
            {renderSection('⏳ Tập trung & Quản lý thời gian', focusTips, 1)}
            {renderSection('🎯 Mục tiêu và hành động', goalsTips, 2)}
          </>
        ) : activeTab === 'saved' ? (
          <div className="sg-grid sg-flat-grid">{filteredTips.map(renderCard)}</div>
        ) : (
          <section
            className="sg-category-section sg-fade-section"
            ref={el => { sectionRefs.current[0] = el; }}
          >
            <div className="sg-grid">{filteredTips.map(renderCard)}</div>
          </section>
        )}
      </div>

      {selectedTip && (
        <TipDetailModal
          tip={selectedTip}
          onClose={() => setSelectedTip(null)}
        />
      )}

      <SelfAssessmentModal
        isOpen={isAssessmentOpen}
        onClose={() => setIsAssessmentOpen(false)}
        onOpenTip={(tipId) => {
          const tip = survivalGuideTips.find(t => t.id === tipId);
          if (tip) { setIsAssessmentOpen(false); setSelectedTip(tip); }
        }}
      />
    </div>
  );
}
