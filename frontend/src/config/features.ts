/**
 * CẤU HÌNH TÍNH NĂNG ỨNG DỤNG (FEATURE FLAGS)
 * ============================================
 * 
 * 🛠️ CHẾ ĐỘ BẢO TRÌ TÍNH NĂNG CHAT AI (IS_CHAT_MAINTENANCE):
 * - false: TẮT bảo trì -> Sinh viên sử dụng Chat AI bình thường.
 * - true: BẬT bảo trì -> Khi bấm vào Chat sẽ hiện Modal thông báo đang bảo trì,
 *   gợi ý các công cụ tính toán khác và hiển thị badge "Bảo trì" trên menu.
 * 
 * 👉 Các cách bật/tắt linh hoạt:
 * 1. Đổi giá trị DEFAULT_CHAT_MAINTENANCE bên dưới thành `true` hoặc `false`.
 * 2. Đặt biến môi trường trong file `.env` (hoặc Vercel Environment Variables):
 *    `VITE_CHAT_MAINTENANCE=true` hoặc `VITE_CHAT_MAINTENANCE=false`.
 * 3. Hoặc thêm tham số trên URL trình duyệt để test nhanh: `?maintenance=true` / `?maintenance=false`.
 */

// Đổi true / false ở dòng này để bật / tắt bảo trì mặc định:
const DEFAULT_CHAT_MAINTENANCE = false;

export const IS_CHAT_MAINTENANCE: boolean = (() => {
  // 1. Ưu tiên kiểm tra tham số URL (tiện kiểm thử trực tiếp trên trình duyệt)
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    if (params.has('maintenance')) {
      return params.get('maintenance') === 'true';
    }
  }

  // 2. Kiểm tra biến môi trường Vite (.env)
  if (import.meta.env.VITE_CHAT_MAINTENANCE !== undefined) {
    return import.meta.env.VITE_CHAT_MAINTENANCE === 'true';
  }

  // 3. Sử dụng giá trị cấu hình mặc định
  return DEFAULT_CHAT_MAINTENANCE;
})();

/**
 * 📝 TRANG "KINH NGHIỆM HỌC BỔNG" (SHOW_EXPERIENCE_PAGE):
 * Nội dung hiện vẫn là bản mẫu (xem `src/data/experience.ts`), nên trang chỉ hiện khi:
 * 1. Chạy chế độ phát triển (`npm run dev`), hoặc
 * 2. Đặt biến môi trường `VITE_SHOW_EXPERIENCE=true`, hoặc
 * 3. Thêm `?experience=true` vào URL để xem thử.
 * Khi false, mục menu biến mất và không thể mở trang.
 */
export const SHOW_EXPERIENCE_PAGE: boolean = (() => {
  if (import.meta.env.DEV) return true;
  if (import.meta.env.VITE_SHOW_EXPERIENCE === 'true') return true;
  if (typeof window !== 'undefined') {
    return new URLSearchParams(window.location.search).get('experience') === 'true';
  }
  return false;
})();
