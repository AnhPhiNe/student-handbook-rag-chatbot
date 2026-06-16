import { Award, Calculator, GraduationCap, ShieldCheck, TrendingUp, Target } from 'lucide-react';

interface ToolsPageProps {
  onNavigate: (tab: string) => void;
}

const TOOLS = [
  {
    id: 'gpa',
    title: 'Tính GPA',
    description: 'Tính GPA học kỳ theo tín chỉ, điểm thang 10 hoặc điểm chữ.',
    icon: GraduationCap,
    color: '#3b82f6',
  },
  {
    id: 'target-gpa',
    title: 'Mục tiêu GPA',
    description: 'Tính điểm trung bình cần đạt để kéo GPA tích lũy lên mức mong muốn.',
    icon: TrendingUp,
    color: '#f43f5e',
  },
  {
    id: 'course-target',
    title: 'Mục tiêu môn học',
    description: 'Tính điểm thi cuối kỳ cần đạt dựa trên các cột điểm thành phần linh hoạt.',
    icon: Target,
    color: '#0ea5e9',
  },
  {
    id: 'scholarship',
    title: 'Tính học bổng',
    description: 'Tính điểm học bổng và xếp loại tham khảo.',
    icon: Award,
    color: '#8b5cf6',
  },
  {
    id: 'tuition',
    title: 'Ước tính học phí',
    description: 'Tra học phí theo ngành, năm học và số tín chỉ.',
    icon: Calculator,
    color: '#f59e0b',
  },
  {
    id: 'credits',
    title: 'Kiểm tra hạ bằng',
    description: 'Kiểm tra điều kiện hạ mức bằng tốt nghiệp do học lại.',
    icon: ShieldCheck,
    color: '#10b981',
  },
];

export function ToolsPage({ onNavigate }: ToolsPageProps) {
  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Công cụ sinh viên</h1>
        <p>Các công cụ tính toán nhanh, chạy trực tiếp trên trình duyệt và không dùng chatbot.</p>
      </div>

      <div className="category-grid">
        {TOOLS.map((tool) => {
          const Icon = tool.icon;
          return (
            <button key={tool.id} className="category-card" onClick={() => onNavigate(tool.id)}>
              <div className="category-icon" style={{ color: tool.color, backgroundColor: `${tool.color}15` }}>
                <Icon size={24} />
              </div>
              <h2 className="category-title">{tool.title}</h2>
              <p className="category-desc">{tool.description}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
