import { MessageSquare, Wrench, ShieldAlert, Navigation, FileText } from 'lucide-react';

export function GuidePage() {
  return (
    <div className="page-container">
      <div className="article-layout">
        <div className="page-header center">
        <h1 className="article-title">Chào người mới! 👋</h1>
        <p className="article-meta">Hướng dẫn "cầm tay chỉ việc" để bạn làm chủ toàn bộ website ngay từ lần đầu tiên.</p>
      </div>

      <div className="article-content">
        <p className="lead-paragraph" style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
          Đây là <strong>Sổ tay Sinh viên Thông minh</strong> (HCMUE). Thay vì phải tự mài mò đọc hàng trăm trang tài liệu nhàm chán, trang web này sẽ giúp bạn giải đáp luật lệ trường, tự động tính điểm, và cung cấp biểu mẫu chỉ trong chớp mắt!
        </p>

        <div className="tip-box" style={{ flexDirection: 'column', alignItems: 'flex-start', backgroundColor: 'var(--bg-secondary)', marginBottom: '2.5rem', padding: '1.5rem' }}>
          <h4 style={{ margin: '0 0 0.75rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--primary)', fontSize: '1.1rem' }}>
            <Navigation size={20} /> Cách di chuyển trong Web
          </h4>
          <p style={{ margin: 0, fontSize: '1rem', lineHeight: '1.6' }}>
            Bạn hãy chú ý đến <strong>Thanh Menu</strong> (nằm ở bên trái nếu dùng Laptop, hoặc nằm ở dưới cùng nếu dùng Điện thoại). Trang web có 4 chức năng chính: <strong>Chat</strong>, <strong>Biểu mẫu</strong>, <strong>Công cụ</strong>, và <strong>Hướng dẫn</strong>. Bấm vào bất kỳ nút nào để sử dụng.
          </p>
        </div>

        <h2><MessageSquare size={22} className="inline-icon text-primary"/> 1. Trợ lý AI (Mục "Chat")</h2>
        <p>
          Đây là nơi bạn có thể "nhắn tin" với AI giống như hỏi một người anh/chị khóa trên. AI đã học thuộc lòng toàn bộ Quy chế của trường.
        </p>
        <ul>
          <li><strong>Cách dùng:</strong> Chọn mục <strong>Chat</strong>, gõ thắc mắc của bạn (VD: về học bổng, KTX, điểm rèn luyện, đăng ký học phần) và ấn gửi.</li>
          <li><strong>Kiểm chứng:</strong> AI thỉnh thoảng có thể nhầm lẫn. Vì vậy, dưới mỗi câu trả lời luôn có phần <strong>Nguồn tham khảo</strong>. Hãy bấm vào đó để đọc lại đoạn văn bản gốc của trường để chắc chắn 100%!</li>
        </ul>
        <div className="tip-box" style={{ flexDirection: 'column', gap: '0.75rem' }}>
          <p style={{ margin: 0 }}>✅ <strong>Nên hỏi rõ ràng:</strong> "Trường hợp nào thì sinh viên bị buộc thôi học?"</p>
          <p style={{ margin: 0 }}>❌ <strong>Tránh hỏi cộc lốc:</strong> "Thôi học?" (AI sẽ không hiểu bạn đang muốn hỏi điều kiện, thủ tục hay là quy định, dẫn đến trả lời lan man).</p>
        </div>

        <h2><Wrench size={22} className="inline-icon text-accent"/> 2. Tiện ích Tự động (Mục "Công cụ")</h2>
        <p>
          Thay vì tự bấm máy tính cầm tay hay lập file Excel phức tạp, chúng tôi cung cấp sẵn 6 công cụ tự động siêu tiện lợi. Chuyển sang mục <strong>Công cụ</strong> và chọn cái bạn cần:
        </p>
        
        <ul style={{ listStyleType: 'none', paddingLeft: 0, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <li style={{ background: 'var(--bg-secondary)', padding: '1.25rem', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: 'var(--shadow-sm)' }}>
            <strong>🎓 Tính GPA & Mục tiêu GPA:</strong><br />
            Nhập điểm các môn bạn đã học để biết ngay điểm Trung bình (GPA). Hoặc dùng "Mục tiêu GPA" để xem kỳ này cần được mấy phẩy mới vớt được điểm trung bình lên loại Giỏi.
          </li>
          <li style={{ background: 'var(--bg-secondary)', padding: '1.25rem', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: 'var(--shadow-sm)' }}>
            <strong>🎯 Mục tiêu môn học:</strong><br />
            Môn này điểm quá trình bạn thấp. Bạn muốn môn này tổng kết được điểm B? Hãy nhập vào đây, công cụ sẽ tính chính xác cuối kỳ bạn phải thi được bao nhiêu điểm.
          </li>
          <li style={{ background: 'var(--bg-secondary)', padding: '1.25rem', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: 'var(--shadow-sm)' }}>
            <strong>💰 Tính học bổng & Ước tính học phí:</strong><br />
            Nhập điểm học tập và rèn luyện để xem bạn có khả năng đạt học bổng loại gì, và ước tính nhận được bao nhiêu tiền. Hoặc tra cứu học phí đóng mỗi kỳ của ngành bạn học.
          </li>
          <li style={{ background: 'var(--bg-secondary)', padding: '1.25rem', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: 'var(--shadow-sm)' }}>
            <strong>⚠️ Kiểm tra rủi ro hạ bằng:</strong><br />
            Nếu rớt môn quá nhiều (quá 5% tổng số tín chỉ), bạn sẽ bị hạ mức bằng Tốt nghiệp (VD: từ Giỏi bị rớt xuống Khá). Hãy nhập số tín chỉ rớt vào đây để hệ thống cảnh báo sớm cho bạn.
          </li>
        </ul>

        <h2 style={{ marginTop: '2.5rem' }}><FileText size={22} className="inline-icon text-primary"/> 3. Tải Giấy tờ (Mục "Biểu mẫu")</h2>
        <p>
          Nơi tập hợp sẵn tất cả các file Word/PDF như đơn xin nghỉ học, giấy xác nhận sinh viên, phiếu thanh toán ra trường...
        </p>
        <ul>
          <li><strong>Cách dùng:</strong> Chọn mục <strong>Biểu mẫu</strong>, gõ từ khóa vào ô tìm kiếm (VD: gõ "xác nhận" hoặc "đăng ký").</li>
          <li>Bấm vào nút <strong>Tải xuống</strong> để lưu file về máy tính hoặc điện thoại ngay lập tức mà không cần đi tìm link vòng vo trên nhóm lớp!</li>
        </ul>

        <hr style={{ margin: '3rem 0 2rem 0' }} />
        <div className="tip-box" style={{ borderColor: 'var(--warning)', backgroundColor: 'var(--bg-secondary)', alignItems: 'flex-start', margin: 0 }}>
          <ShieldAlert size={24} className="text-warning" style={{ flexShrink: 0, marginTop: '2px' }} />
          <p style={{ margin: 0, fontSize: '0.95rem' }}>
            <strong>Lưu ý cuối cùng:</strong> Trợ lý AI và các công cụ tính toán mang tính chất <strong>tham khảo và hỗ trợ</strong>. Đối với các quyết định cực kỳ quan trọng (như bảo lưu, khiếu nại điểm, điều kiện ra trường), hãy luôn xác nhận lại với Cố vấn học tập hoặc các Phòng ban trực tiếp của trường nhé!
          </p>
        </div>
      </div>
      </div>
    </div>
  );
}
