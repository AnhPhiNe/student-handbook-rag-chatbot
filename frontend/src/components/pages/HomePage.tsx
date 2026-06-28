import { MessageSquare, Wrench, FileText, Navigation, CircleHelp } from 'lucide-react';
import logoHcmue from '../../assets/logo_hcmue.png';

interface HomePageProps {
  onNavigate: (tab: string) => void;
}

export function HomePage({ onNavigate }: HomePageProps) {
  return (
    <div className="page-container home-page" style={{ display: 'flex', flexDirection: 'column' }}>
      <div className="article-layout" style={{ margin: 'auto', maxWidth: '1200px', width: '100%' }}>
        <div className="page-header center" style={{ paddingBottom: '0', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '0' }}>
            <img src={logoHcmue} alt="HCMUE Logo" className="animated-logo" style={{ width: '140px', height: '140px', objectFit: 'contain' }} />
          </div>
          <h1 className="article-title" style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>Sổ tay Sinh viên HCMUE</h1>
          <p className="article-meta" style={{ fontSize: '0.95rem', maxWidth: '800px', margin: '0 auto', lineHeight: '1.5' }}>
            Trợ lý AI và bộ công cụ tự động giúp bạn dễ dàng theo dõi điểm số, học phí và giải đáp mọi thắc mắc về quy chế của trường.
          </p>
        </div>

        <div className="article-content" style={{ marginTop: 0 }}>
          <div className="action-cards-grid" style={{ marginBottom: 0, gap: '0.75rem' }}>
            
            <div className="action-card" onClick={() => onNavigate('chat')} style={{ flexDirection: 'column', padding: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
                <div style={{ background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6', padding: '0.5rem', borderRadius: '10px' }}>
                  <MessageSquare size={20} />
                </div>
                <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Trợ lý AI (Chat)</h3>
              </div>
              <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: '1.4' }}>Hỏi đáp mọi vấn đề về quy chế, học bổng, ký túc xá, điểm rèn luyện... AI sẽ trích xuất nguồn từ Sổ tay sinh viên.</p>
            </div>

            <div className="action-card" onClick={() => onNavigate('tools')} style={{ flexDirection: 'column', padding: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
                <div style={{ background: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b', padding: '0.5rem', borderRadius: '10px' }}>
                  <Wrench size={20} />
                </div>
                <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Tiện ích Tự động</h3>
              </div>
              <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: '1.4' }}>Không cần bấm máy tính! Hệ thống tự động tính GPA, dự đoán học bổng, cảnh báo rớt môn và ước tính học phí chỉ trong chớp mắt.</p>
            </div>

            <div className="action-card" onClick={() => onNavigate('bieu-mau')} style={{ flexDirection: 'column', padding: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
                <div style={{ background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', padding: '0.5rem', borderRadius: '10px' }}>
                  <FileText size={20} />
                </div>
                <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Kho Biểu mẫu</h3>
              </div>
              <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: '1.4' }}>Tìm kiếm và tải xuống nhanh chóng các loại đơn từ, giấy xác nhận, mẫu nghiên cứu khoa học.</p>
            </div>

            <div className="action-card" onClick={() => onNavigate('faq')} style={{ flexDirection: 'column', padding: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
                <div style={{ background: 'rgba(14, 165, 233, 0.1)', color: '#0ea5e9', padding: '0.5rem', borderRadius: '10px' }}>
                  <CircleHelp size={20} />
                </div>
                <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Câu hỏi phổ biến</h3>
              </div>
              <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: '1.4' }}>Xem nhanh các câu hỏi hay gặp theo Khóa đang chọn, hoặc gửi câu hỏi đó vào AI để nhận câu trả lời có nguồn.</p>
            </div>

            <div className="action-card" onClick={() => onNavigate('huong-dan')} style={{ flexDirection: 'column', padding: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
                <div style={{ background: 'rgba(139, 92, 246, 0.1)', color: '#8b5cf6', padding: '0.5rem', borderRadius: '10px' }}>
                  <Navigation size={20} />
                </div>
                <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Hướng dẫn sử dụng</h3>
              </div>
              <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.95rem' }}>Bạn mới đến đây lần đầu? Hãy đọc qua hướng dẫn "cầm tay chỉ việc" để sử dụng web hiệu quả nhất.</p>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
