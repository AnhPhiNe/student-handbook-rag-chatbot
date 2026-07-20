# HCMUE Student Handbook - Web UI

Giao diện người dùng (Frontend) chính thức cho dự án **HCMUE Student Handbook RAG Assistant**, được xây dựng bằng công nghệ web hiện đại để mang lại trải nghiệm tra cứu mượt mà, tốc độ cao.

## 🚀 Công nghệ sử dụng
- **Framework:** React 19 + Vite (Nhanh, tối ưu hóa Build time)
- **Ngôn ngữ:** TypeScript (Đảm bảo an toàn kiểu dữ liệu, dễ bảo trì)
- **Styling:** CSS thuần (Vanilla CSS với CSS Variables) được thiết kế theo phong cách UI hiện đại, hỗ trợ chế độ Light/Dark Mode.
- **Icons:** `lucide-react`
- **Markdown Rendering:** `react-markdown`

## ⚙️ Cài đặt & Chạy Local

### Yêu cầu hệ thống
- Node.js (phiên bản 18 trở lên)
- npm hoặc yarn

### Các bước cài đặt
1. Di chuyển vào thư mục frontend:
   ```bash
   cd frontend
   ```
2. Cài đặt các gói phụ thuộc:
   ```bash
   npm install
   ```
3. Khởi động môi trường phát triển (Development Server):
   ```bash
   npm run dev
   ```
4. Truy cập giao diện tại: `http://localhost:5173`

## 🌐 Kết nối với Backend API
Giao diện này được thiết kế theo kiến trúc **Decoupled** và hoạt động như một Client độc lập giao tiếp với REST API Backend (FastAPI).

Theo mặc định, UI sẽ gọi API tới `http://127.0.0.1:8000/chat`.
Đảm bảo bạn đã khởi động Backend Server trước khi chat:
```bash
# Tại thư mục gốc của toàn bộ dự án
python -m uvicorn src.api.main:app --reload
```

## ✨ Các tính năng nổi bật
- **Giao diện Chat trực quan:** Hỗ trợ render Markdown đa dạng (bảng, danh sách, mã code) giúp câu trả lời của AI dễ đọc và chuyên nghiệp.
- **Truy cập nhanh (Quick Access):** Hệ thống thẻ truy cập nhanh sử dụng cơ chế *Hardcoded Responses* để hiển thị thông tin ngay lập tức mà không tiêu hao quota API của LLM.
- **Dark/Light Mode:** Hỗ trợ chuyển đổi chủ đề màu sắc mượt mà.
- **Phản hồi theo thời gian thực:** Cập nhật trạng thái hệ thống và hiển thị thời gian phản hồi (ms) của API.
- **Responsive:** Layout tự động thích ứng trên các màn hình nhỏ.

## 📄 License
MIT License
