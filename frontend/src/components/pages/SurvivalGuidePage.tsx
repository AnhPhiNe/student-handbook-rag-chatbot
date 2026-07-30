import { useState, useEffect, useRef, useCallback } from 'react';
import { Sparkles, Bookmark, Lightbulb } from 'lucide-react';
import { survivalGuideTips, type StudyTip } from '../../data/survivalGuide';
import { HorizontalScrollHint } from '../HorizontalScrollHint';
import { TipDetailModal } from './survival-guide/TipDetailModal';

const TOOL_IDS = new Set(['pomodoro', 'two-minute-rule', 'parkinson', 'smart-goals', 'blurting']);

type CurrentProblem = 'procrastinate' | 'distracted' | 'memory-issues' | 'note-taking-issues' | 'practice-issues';
type FilterTab = 'all' | CurrentProblem | 'saved';

const TABS: { id: FilterTab; label: string }[] = [
  { id: 'all', label: '✨ Tất cả' },
  { id: 'procrastinate', label: '🥱 Hay trì hoãn' },
  { id: 'distracted', label: '📱 Dễ xao nhãng' },
  { id: 'memory-issues', label: '🧠 Mau quên' },
  { id: 'note-taking-issues', label: '📝 Học vẹt' },
  { id: 'practice-issues', label: '🤷‍♂️ Thiếu thực hành' },
  { id: 'saved', label: '⭐ Đã lưu' },
];

const problemMappings: Record<CurrentProblem, string[]> = {
  'procrastinate': ['pomodoro', 'eat-that-frog', 'two-minute-rule', 'parkinson', 'eisenhower-matrix'],
  'distracted': ['pomodoro', 'parkinson', 'eisenhower-matrix'],
  'memory-issues': ['spaced-repetition', 'active-recall', 'interleaving', 'retrieval-practice', 'sq3r'],
  'note-taking-issues': ['feynman', 'blurting', 'cornell-notes'],
  'practice-issues': ['feynman', 'blurting', 'retrieval-practice'],
};

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
  const [activeTab, setActiveTab] = useState<FilterTab>('all');
  const [saved, setSaved] = useState<string[]>(getSaved);
  const tabFilterRef = useRef<HTMLDivElement | null>(null);
  const sectionRefs = useRef<(HTMLElement | null)[]>([]);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const lastTipTriggerRef = useRef<HTMLButtonElement | null>(null);

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
    const validIds = problemMappings[activeTab as CurrentProblem] || [];
    return validIds.includes(t.id);
  });

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
      >
        <div className="sg-glow" />
        <button
          type="button"
          className="sg-card-open"
          onClick={(event) => {
            lastTipTriggerRef.current = event.currentTarget;
            setSelectedTip(tip);
          }}
          aria-label={`Xem chi tiết ${tip.title}`}
        >
          <span className="sr-only">Xem chi tiết {tip.title}</span>
        </button>
        <button
          className={`sg-bookmark-btn ${isSaved ? 'active' : ''}`}
          onClick={e => handleBookmark(e, tip.id)}
          title={isSaved ? 'Bỏ lưu' : 'Lưu phương pháp này'}
          aria-label={`${isSaved ? 'Bỏ lưu' : 'Lưu'} ${tip.title}`}
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
    <div className="page-container survival-guide-container">
      <div className="sg-header">
        <h1 className="page-title-with-icon">
          <Sparkles aria-hidden="true" />
          <span>Phương pháp học tập ở HCMUE</span>
        </h1>
        <p>Kho tàng phương pháp học tập khoa học giúp bạn tối ưu hóa thời gian và công sức!</p>
      </div>

      {/* Instructional Banner */}
      <div className="sg-cta-banner" style={{ cursor: 'default' }}>
        <div className="sg-cta-inner" style={{ padding: '0.5rem 1rem' }}>
          <div className="sg-cta-icon" style={{ fontSize: '1.2rem', padding: '0.5rem', background: 'rgba(255,255,255,0.2)', color: 'white', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Lightbulb size={18} /></div>
          <div className="sg-cta-text" style={{ gap: '0.2rem' }}>
            <strong>Mẹo tìm phương pháp nhanh</strong>
            <span style={{ fontSize: '0.9rem', opacity: 0.9 }}>Nhấp vào vấn đề bạn đang gặp phải ở thanh bên dưới để xem các phương pháp giải quyết ngay lập tức!</span>
          </div>
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
        ) : (
          <section
            className="sg-category-section sg-fade-section"
            ref={el => { sectionRefs.current[0] = el; }}
          >
            <div className="sg-grid sg-flat-grid">{filteredTips.map(renderCard)}</div>
          </section>
        )}
      </div>

      {selectedTip && (
        <TipDetailModal
          tip={selectedTip}
          onClose={() => {
            setSelectedTip(null);
            window.requestAnimationFrame(() => lastTipTriggerRef.current?.focus());
          }}
        />
      )}
    </div>
  );
}
