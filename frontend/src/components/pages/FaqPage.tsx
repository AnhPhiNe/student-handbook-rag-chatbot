import { useMemo, useState } from 'react';
import { ChevronDown, MessageSquareText, Search, Sparkles } from 'lucide-react';
import { getFaqCategoriesForCohort, getFaqItemsForCohort } from '../../data/faq';
import type { Cohort } from '../../utils/gradeScale';

interface FaqPageProps {
  cohort: Cohort;
  onAskQuestion: (question: string) => void;
}

export function FaqPage({ cohort, onAskQuestion }: FaqPageProps) {
  const [activeCategory, setActiveCategory] = useState('Tất cả');
  const [openId, setOpenId] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  const categories = useMemo(() => ['Tất cả', ...getFaqCategoriesForCohort(cohort)], [cohort]);
  const allItems = useMemo(() => getFaqItemsForCohort(cohort), [cohort]);
  const items = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase();
    return allItems.filter((item) => {
      const matchesCategory = activeCategory === 'Tất cả' || item.category === activeCategory;
      const matchesSearch =
        !normalizedSearch ||
        `${item.question} ${item.shortAnswer} ${item.aiPrompt} ${item.category}`.toLowerCase().includes(normalizedSearch);
      return matchesCategory && matchesSearch;
    });
  }, [activeCategory, allItems, searchTerm]);

  const featuredIds =
    cohort === 'K50-K51'
      ? ['pass-score-k50', 'd-plus-k50', 'retake-final-grade-k50']
      : ['pass-score-k48', 'grade-4-conversion', 'retake-final-grade'];
  const featuredItems = featuredIds
    .map((id) => allItems.find((item) => item.id === id))
    .filter((item): item is NonNullable<typeof item> => Boolean(item));

  const openFeaturedItem = (id: string, category: string) => {
    setSearchTerm('');
    setActiveCategory(category);
    setOpenId(id);
    window.requestAnimationFrame(() => {
      document.getElementById(`faq-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  };

  return (
    <div className="page-container faq-page">
      <div className="page-header">
        <h1>Câu hỏi phổ biến</h1>
        <p>Chọn nhanh câu hỏi theo {cohort}, xem tóm tắt hoặc gửi thẳng vào HCMUE AI để nhận câu trả lời có nguồn.</p>
      </div>

      <section className="faq-spotlight" aria-label="Câu hỏi nổi bật">
        <div className="faq-spotlight-main">
          <div className="faq-spotlight-icon">
            <Sparkles size={20} />
          </div>
          <div>
            <span>Câu hỏi nổi bật</span>
            <h2>{allItems.length} câu hỏi phổ biến cho {cohort}</h2>
            <p>Các câu hỏi thường cần tra nhanh về điểm số, học lại, học bổng, học phí, biểu mẫu và phòng ban phụ trách.</p>
          </div>
        </div>
        <div className="faq-spotlight-list">
          {featuredItems.map((item) => (
            <button key={item.id} onClick={() => openFeaturedItem(item.id, item.category)}>
              <span>{item.category}</span>
              {item.question}
            </button>
          ))}
        </div>
      </section>

      <div className="faq-toolbar">
        <label className="faq-search-box">
          <Search size={18} />
          <input
            value={searchTerm}
            onChange={(event) => {
              setSearchTerm(event.target.value);
              setOpenId(null);
            }}
            placeholder="Tìm theo điểm, học bổng, KTX, phúc khảo..."
          />
        </label>
        <div className="faq-category-pills">
          {categories.map((category) => (
            <button
              key={category}
              className={`faq-category-pill ${activeCategory === category ? 'active' : ''}`}
              onClick={() => {
                setActiveCategory(category);
                setOpenId(null);
              }}
            >
              {category}
            </button>
          ))}
        </div>
      </div>

      <div className="faq-list-panel">
        <div className="faq-results-meta">
          <span>{items.length} kết quả</span>
          {activeCategory !== 'Tất cả' && <em>{activeCategory}</em>}
        </div>
        {items.length === 0 && (
          <div className="faq-empty-state">
            <Search size={22} />
            <h2>Chưa có câu hỏi khớp</h2>
            <p>Thử đổi từ khóa hoặc chọn lại nhóm câu hỏi khác.</p>
          </div>
        )}
        {items.map((item) => {
          const isOpen = openId === item.id;
          return (
            <article key={item.id} id={`faq-${item.id}`} className={`faq-card ${isOpen ? 'open' : ''}`}>
              <button className="faq-card-header" onClick={() => setOpenId(isOpen ? null : item.id)}>
                <div>
                  <span className="faq-card-category">{item.category}</span>
                  <h2>{item.question}</h2>
                </div>
                <ChevronDown size={18} className="faq-chevron" />
              </button>

              <div className="faq-card-body">
                <div className="faq-card-inner">
                  <p>{item.shortAnswer}</p>
                  <button className="tool-btn primary faq-ask-btn" onClick={() => onAskQuestion(item.aiPrompt)}>
                    <MessageSquareText size={16} />
                    <span>Hỏi AI chi tiết</span>
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
