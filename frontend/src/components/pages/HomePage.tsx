import {
  ArrowRight,
  FileText,
  LayoutGrid,
  MessageSquare,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';

const logoHcmue = '/logo_hcmue.png?v=2';

interface HomePageProps {
  onNavigate: (tab: string) => void;
}

interface HomeAction {
  id: string;
  title: string;
  description: string;
  icon: LucideIcon;
  tone: 'blue' | 'violet' | 'cyan' | 'green';
}

const HOME_ACTIONS: HomeAction[] = [
  {
    id: 'chat',
    title: 'Hỏi AI',
    description: 'Tra quy chế, học bổng, điểm rèn luyện và xem nguồn từ Sổ tay sinh viên.',
    icon: MessageSquare,
    tone: 'blue',
  },
  {
    id: 'tools',
    title: 'Công cụ sinh viên',
    description: 'Tính GPA, lập mục tiêu, ước tính học phí và kiểm tra các điều kiện học tập.',
    icon: LayoutGrid,
    tone: 'violet',
  },
  {
    id: 'survival-guide',
    title: 'Phương pháp học tập',
    description: 'Khám phá cách ghi nhớ, tập trung và quản lý mục tiêu hiệu quả.',
    icon: Sparkles,
    tone: 'cyan',
  },
  {
    id: 'bieu-mau',
    title: 'Biểu mẫu',
    description: 'Tìm kiếm và tải nhanh các biểu mẫu sinh viên hiện có trên hệ thống.',
    icon: FileText,
    tone: 'green',
  },
];

export function HomePage({ onNavigate }: HomePageProps) {
  return (
    <div className="page-container home-page">
      <div className="home-shell">
        <header className="home-hero">
          <img src={logoHcmue} alt="HCMUE" className="animated-logo home-logo" />
          <h1>Sổ tay Sinh viên HCMUE</h1>
          <p>
            Trợ lý AI và bộ công cụ giúp bạn tra cứu quy chế, theo dõi điểm số
            và ước tính các thông tin học tập cần thiết.
          </p>
        </header>

        <section className="home-actions-section" aria-labelledby="home-actions-title">
          <div className="home-section-heading">
            <h2 id="home-actions-title">Bạn muốn làm gì?</h2>
          </div>
          <div className="home-action-grid">
            {HOME_ACTIONS.map((action) => {
              const Icon = action.icon;
              return (
                <button
                  key={action.id}
                  type="button"
                  className={`home-action-card tone-${action.tone}`}
                  onClick={() => onNavigate(action.id)}
                >
                  <span className="home-action-icon">
                    <Icon size={22} aria-hidden="true" />
                  </span>
                  <span className="home-action-copy">
                    <strong>{action.title}</strong>
                    <span>{action.description}</span>
                  </span>
                  <ArrowRight className="home-action-arrow" size={20} aria-hidden="true" />
                </button>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
