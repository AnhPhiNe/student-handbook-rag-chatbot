import {
  Calculator,
  Clock3,
  GraduationCap,
  MessageSquare,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';

const logoHcmue = '/logo_hcmue.png?v=2';

interface HomePageProps {
  onNavigate: (tab: string) => void;
  recentTools: string[];
}

interface HomeAction {
  id: string;
  title: string;
  description: string;
  icon: LucideIcon;
  tone: 'blue' | 'orange' | 'violet' | 'cyan';
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
    id: 'gpa',
    title: 'Tính GPA',
    description: 'Quy đổi điểm và tính GPA học kỳ theo đúng khóa đang chọn.',
    icon: GraduationCap,
    tone: 'violet',
  },
  {
    id: 'tuition',
    title: 'Ước tính học phí',
    description: 'Tra theo ngành, năm học và số tín chỉ dự kiến đăng ký.',
    icon: Calculator,
    tone: 'orange',
  },
  {
    id: 'survival-guide',
    title: 'Phương pháp học tập',
    description: 'Khám phá cách ghi nhớ, tập trung và quản lý mục tiêu hiệu quả.',
    icon: Sparkles,
    tone: 'cyan',
  },
];

const ACTION_BY_ID = new Map(HOME_ACTIONS.map((action) => [action.id, action]));

export function HomePage({ onNavigate, recentTools }: HomePageProps) {
  const quickActions = (recentTools.length > 0 ? recentTools : ['chat', 'gpa', 'tuition'])
    .map((id) => ACTION_BY_ID.get(id))
    .filter((action): action is HomeAction => Boolean(action))
    .slice(0, 3);

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

        <section className="home-quick-section" aria-labelledby="home-quick-title">
          <div className="home-section-heading">
            <div>
              <span className="home-section-kicker">
                <Clock3 size={15} aria-hidden="true" />
                {recentTools.length > 0 ? 'Dùng gần đây' : 'Gợi ý bắt đầu'}
              </span>
              <h2 id="home-quick-title">Tiếp tục công việc của bạn</h2>
            </div>
          </div>
          <div className="home-quick-actions">
            {quickActions.map((action) => {
              const Icon = action.icon;
              return (
                <button
                  key={action.id}
                  type="button"
                  className="home-quick-action"
                  onClick={() => onNavigate(action.id)}
                >
                  <Icon size={17} aria-hidden="true" />
                  <span>{action.title}</span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="home-actions-section" aria-labelledby="home-actions-title">
          <div className="home-section-heading">
            <div>
              <span className="home-section-kicker">Thao tác chính</span>
              <h2 id="home-actions-title">Bạn muốn làm gì?</h2>
            </div>
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
                  <span className="home-action-arrow" aria-hidden="true">→</span>
                </button>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
