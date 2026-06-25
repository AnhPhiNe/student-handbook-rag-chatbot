import { MessageSquare, Wrench, FileText, Navigation } from 'lucide-react';

interface HomePageProps {
  onNavigate: (tab: string) => void;
}

export function HomePage({ onNavigate }: HomePageProps) {
  return (
    <div className="page-container home-page" style={{ display: 'flex', flexDirection: 'column' }}>
      <div className="article-layout" style={{ margin: 'auto', maxWidth: '1200px', width: '100%' }}>
        <div className="page-header" style={{ paddingBottom: '0', marginBottom: '2rem' }}>
          <h1 className="article-title" style={{ fontSize: '2.5rem', marginBottom: '0.75rem', textAlign: 'left', fontWeight: 800 }}>Chào mừng đến với Hệ thống</h1>
          <p className="article-meta" style={{ fontSize: '1.15rem', maxWidth: '800px', lineHeight: '1.6', textAlign: 'left', color: 'var(--text-secondary)' }}>
            Khám phá Sổ tay Sinh viên thông minh và bộ công cụ tự động giúp bạn dễ dàng theo dõi điểm số, học phí và giải đáp mọi thắc mắc.
          </p>
        </div>

        <div className="article-content" style={{ marginTop: 0 }}>
          <div className="category-grid" style={{ marginBottom: 0, margin: '0' }}>
            
            <div className="category-card" onClick={() => onNavigate('chat')} role="button" tabIndex={0}>
              <div className="category-icon" style={{ color: '#3b82f6', backgroundColor: 'rgba(59, 130, 246, 0.15)' }}>
                <MessageSquare size={24} />
              </div>
              <h2 className="category-title">Trợ lý AI (Chat)</h2>
              <p className="category-desc">Hỏi đáp mọi vấn đề về quy chế, học bổng, ký túc xá, điểm rèn luyện... AI sẽ tự động trích xuất nguồn từ Sổ tay sinh viên.</p>
            </div>

            <div className="category-card" onClick={() => onNavigate('tools')} role="button" tabIndex={0}>
              <div className="category-icon" style={{ color: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.15)' }}>
                <Wrench size={24} />
              </div>
              <h2 className="category-title">Tiện ích Tự động</h2>
              <p className="category-desc">Không cần bấm máy tính! Hệ thống tự động tính GPA, dự đoán học bổng, cảnh báo rớt môn và ước tính học phí nhanh chóng.</p>
            </div>

            <div className="category-card" onClick={() => onNavigate('bieu-mau')} role="button" tabIndex={0}>
              <div className="category-icon" style={{ color: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.15)' }}>
                <FileText size={24} />
              </div>
              <h2 className="category-title">Kho Biểu mẫu</h2>
              <p className="category-desc">Tìm kiếm và tải xuống nhanh chóng các loại đơn từ, giấy xác nhận, mẫu nghiên cứu khoa học.</p>
            </div>

            <div className="category-card" onClick={() => onNavigate('huong-dan')} role="button" tabIndex={0}>
              <div className="category-icon" style={{ color: '#8b5cf6', backgroundColor: 'rgba(139, 92, 246, 0.15)' }}>
                <Navigation size={24} />
              </div>
              <h2 className="category-title">Hướng dẫn sử dụng</h2>
              <p className="category-desc">Bạn mới đến đây lần đầu? Hãy đọc qua hướng dẫn "cầm tay chỉ việc" để sử dụng hệ thống hiệu quả nhất.</p>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
