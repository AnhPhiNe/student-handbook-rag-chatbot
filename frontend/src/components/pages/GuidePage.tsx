import { MessageSquare, Wrench, ShieldAlert, Navigation, FileText, Bug, CheckCircle2, Zap, Target, Calculator, Award, GraduationCap } from 'lucide-react';

export function GuidePage() {
  return (
    <div className="page-container" style={{ animation: 'fadeIn 0.5s ease-out' }}>
      <div className="article-layout" style={{ maxWidth: '900px', margin: '0 auto', paddingBottom: '3rem' }}>
        
        {/* Header Section */}
        <div className="page-header center" style={{ marginBottom: '3rem', textAlign: 'center' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '80px', height: '80px', borderRadius: '50%', background: 'linear-gradient(135deg, var(--primary-light), var(--primary))', color: 'white', marginBottom: '1.5rem', boxShadow: '0 10px 25px rgba(59, 130, 246, 0.3)' }}>
            <Navigation size={40} />
          </div>
          <h1 className="article-title" style={{ fontSize: '2.5rem', background: 'linear-gradient(to right, var(--primary), #8b5cf6)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', marginBottom: '1rem' }}>
            Hướng dẫn sử dụng toàn tập
          </h1>
          <p className="article-meta" style={{ fontSize: '1.1rem', maxWidth: '650px', margin: '0 auto', lineHeight: '1.6' }}>
            Khám phá cách tối ưu hóa trải nghiệm của bạn trên Sổ tay Sinh viên HCMUE. Nắm bắt thông tin, tính toán điểm số và giải đáp thắc mắc chỉ trong vài cú click!
          </p>
        </div>

        <div className="article-content" style={{ display: 'flex', flexDirection: 'column', gap: '3.5rem' }}>
          
          {/* Section 1: Chat AI */}
          <section className="guide-section">
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
              <div style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6' }}>
                <MessageSquare size={28} />
              </div>
              <h2 style={{ margin: 0, fontSize: '1.75rem' }}>1. Trợ lý AI Thông minh (Chat)</h2>
            </div>
            
            <p style={{ fontSize: '1.05rem', lineHeight: '1.7', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
              Trợ lý AI là "bách khoa toàn thư" sống về quy chế đào tạo, học bổng, điểm rèn luyện và các quy định của trường. Bạn có thể hỏi đáp tự nhiên như đang trò chuyện với một chuyên viên tư vấn.
            </p>
            
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem' }}>
              <div className="feature-card" style={{ padding: '1.5rem', borderRadius: '16px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, marginBottom: '1rem', color: 'var(--success)', fontSize: '1.1rem' }}>
                  <CheckCircle2 size={20} /> Mẹo hỏi AI chuẩn xác
                </h4>
                <ul style={{ paddingLeft: '1.25rem', margin: 0, color: 'var(--text-secondary)', lineHeight: '1.7', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <li><strong>Cụ thể và rõ ràng:</strong> Thay vì hỏi ngắn gọn "Học bổng?", hãy hỏi chi tiết "Điều kiện xét học bổng khuyến khích học tập là gì?"</li>
                  <li><strong>Luôn kiểm tra nguồn:</strong> Chú ý phần <strong>Nguồn tham khảo</strong> dưới mỗi câu trả lời để đối chiếu với văn bản gốc. Chatbot sẽ tham khảo nhiều nguồn nhưng chỉ trả lời dựa trên tài liệu liên quan nên đừng lo nhé !!!</li>
                </ul>
              </div>
              
              <div className="feature-card" style={{ padding: '1.5rem', borderRadius: '16px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, marginBottom: '1rem', color: 'var(--primary)', fontSize: '1.1rem' }}>
                  <Zap size={20} /> Các tính năng hỗ trợ
                </h4>
                <ul style={{ paddingLeft: '1.25rem', margin: 0, color: 'var(--text-secondary)', lineHeight: '1.7', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <li><strong>Tái tạo câu trả lời:</strong> Bấm nút thử lại nếu bạn chưa hài lòng với kết quả.</li>
                  <li><strong>Sao chép nội dung:</strong> Nhanh chóng copy câu trả lời của AI với một nút bấm.</li>
                  <li><strong>Đánh giá (Like/Dislike):</strong> Góp ý chất lượng câu trả lời để giúp AI học hỏi và hoàn thiện hơn mỗi ngày.</li>
                </ul>
              </div>
            </div>
          </section>

          {/* Section 2: Tools */}
          <section className="guide-section">
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
              <div style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b' }}>
                <Wrench size={28} />
              </div>
              <h2 style={{ margin: 0, fontSize: '1.75rem' }}>2. Bộ Công cụ Tự động</h2>
            </div>
            
            <p style={{ fontSize: '1.05rem', lineHeight: '1.7', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
              Quên đi những bảng Excel tính điểm phức tạp. Bộ công cụ tự động giúp bạn lập kế hoạch học tập hoàn hảo chỉ trong nháy mắt.
            </p>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {[
                { icon: GraduationCap, title: 'Tính điểm GPA', desc: 'Nhập điểm các môn học để tính toán chính xác điểm trung bình tích lũy hệ 4 và hệ 10.', color: '#3b82f6' },
                { icon: Target, title: 'Mục tiêu GPA & Môn học', desc: 'Hệ thống sẽ tính toán và "kê đơn" cho bạn cần đạt bao nhiêu điểm trong kỳ tới để đạt được mức GPA mục tiêu (VD: Bằng Giỏi, Xuất sắc).', color: '#10b981' },
                { icon: Award, title: 'Tính điểm học bổng', desc: 'Dự đoán khả năng đạt học bổng và ước tính số tiền nhận được dựa trên điểm học tập và điểm rèn luyện của bạn.', color: '#f59e0b' },
                { icon: Calculator, title: 'Ước tính học phí', desc: 'Tra cứu nhanh mức học phí tín chỉ tùy theo ngành học và khóa học của bạn một cách chính xác.', color: '#8b5cf6' },
                { icon: ShieldAlert, title: 'Cảnh báo rủi ro hạ bằng', desc: 'Kiểm tra xem số tín chỉ học lại của bạn đã vượt quá giới hạn 5% dẫn đến nguy cơ bị hạ bậc bằng tốt nghiệp hay chưa.', color: '#ef4444' }
              ].map((tool, idx) => (
                <div key={idx} className="hover-card" style={{ display: 'flex', alignItems: 'flex-start', gap: '1.25rem', padding: '1.25rem 1.5rem', background: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-color)', transition: 'all 0.2s', cursor: 'default' }}>
                  <div style={{ padding: '0.6rem', background: `rgba(${tool.color === '#3b82f6' ? '59, 130, 246' : tool.color === '#10b981' ? '16, 185, 129' : tool.color === '#f59e0b' ? '245, 158, 11' : tool.color === '#8b5cf6' ? '139, 92, 246' : '239, 68, 68'}, 0.1)`, color: tool.color, borderRadius: '10px' }}>
                    <tool.icon size={22} />
                  </div>
                  <div>
                    <h4 style={{ margin: '0 0 0.35rem 0', fontSize: '1.15rem' }}>{tool.title}</h4>
                    <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.95rem', lineHeight: '1.5' }}>{tool.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Section 3: Forms */}
          <section className="guide-section">
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
              <div style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981' }}>
                <FileText size={28} />
              </div>
              <h2 style={{ margin: 0, fontSize: '1.75rem' }}>3. Thư viện Biểu mẫu</h2>
            </div>
            
            <div style={{ padding: '1.75rem', background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.05), rgba(16, 185, 129, 0.15))', borderRadius: '16px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
              <p style={{ margin: '0 0 1.25rem 0', fontSize: '1.05rem', lineHeight: '1.6' }}>
                Không cần vất vả tìm kiếm link tải trên các nhóm lớp nữa. Toàn bộ các loại đơn từ, giấy xác nhận, mẫu nghiên cứu khoa học đều được tập hợp sẵn tại mục <strong>Biểu mẫu</strong>.
              </p>
              <ul style={{ margin: 0, paddingLeft: '1.5rem', lineHeight: '1.7', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <li><strong>Tìm kiếm siêu tốc:</strong> Gõ từ khóa như "đăng ký", "xác nhận" để lọc ngay biểu mẫu bạn cần trong nháy mắt.</li>
                <li><strong>Tải xuống 1-click:</strong> Hỗ trợ tải trực tiếp các file định dạng chuẩn (.doc, .docx, .pdf) về máy tính/điện thoại ngay lập tức.</li>
              </ul>
            </div>
          </section>

          {/* Section 4: Bug Report */}
          <section className="guide-section">
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
              <div style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' }}>
                <Bug size={28} />
              </div>
              <h2 style={{ margin: 0, fontSize: '1.75rem' }}>4. Báo lỗi & Góp ý</h2>
            </div>
            
            <p style={{ fontSize: '1.05rem', lineHeight: '1.7', color: 'var(--text-secondary)' }}>
              Hệ thống đang trong giai đoạn thử nghiệm (BETA), do đó không tránh khỏi những sai sót. Sự đóng góp của bạn là vô giá để chúng tôi hoàn thiện ứng dụng.
            </p>
            
            <div className="tip-box" style={{ background: 'var(--bg-primary)', borderLeft: '4px solid var(--danger)', margin: '1.5rem 0 0 0', padding: '1.25rem' }}>
              <p style={{ margin: 0, fontSize: '1rem', lineHeight: '1.6' }}>
                Bất cứ lúc nào bạn gặp lỗi hiển thị, lỗi tính toán hoặc muốn đóng góp ý tưởng, hãy nhấn vào biểu tượng <strong>Côn trùng (Bug) màu đỏ</strong> ở góc phải màn hình, hoặc chọn nút <strong>Báo lỗi / Góp ý</strong> ở thanh menu bên trái. Đội ngũ phát triển luôn sẵn sàng lắng nghe!
              </p>
            </div>
          </section>

          {/* Final Warning */}
          <hr style={{ border: 'none', borderTop: '1px solid var(--border-color)', margin: '1rem 0' }} />
          
          <div style={{ background: 'rgba(245, 158, 11, 0.05)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '16px', padding: '1.5rem', display: 'flex', gap: '1.25rem', alignItems: 'flex-start' }}>
            <ShieldAlert size={32} className="text-warning" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>
              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '1.15rem', color: 'var(--warning)' }}>Miễn trừ trách nhiệm</h4>
              <p style={{ margin: 0, fontSize: '0.95rem', lineHeight: '1.6', color: 'var(--text-secondary)' }}>
                Trợ lý AI và các công cụ trên nền tảng mang tính chất tham khảo, dựa trên các tài liệu đã được cung cấp. AI vẫn có thể sinh ra thông tin ảo hoặc tính toán sai lệch trong một số trường hợp đặc thù. Đối với các quyết định mang tính quyết định đến quá trình học tập (như bảo lưu, cảnh báo học vụ, xét tốt nghiệp), bạn <strong>bắt buộc</strong> phải liên hệ và xác nhận lại với Cố vấn học tập hoặc các Phòng ban trực tiếp của nhà trường nhé!
              </p>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  );
}
