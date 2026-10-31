import { useEffect, useRef, useState, useCallback } from 'react';
import '../welcome-curtain.css';

export interface WelcomeCurtainProps {
  onComplete: () => void;
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  color: string;
  rotation: number;
  rotationSpeed: number;
  opacity: number;
}

const CONFETTI_COLORS = ['#3b82f6', '#fbbf24', '#ec4899', '#10b981', '#8b5cf6', '#f97316'];

export function WelcomeCurtain({ onComplete }: WelcomeCurtainProps) {
  const [beat, setBeat] = useState<'preloader' | 'draping' | 'letter'>('preloader');
  const [isExiting, setIsExiting] = useState(false);
  const [progressWidth, setProgressWidth] = useState('0%');
  const [preloaderStatus, setPreloaderStatus] = useState('Đang nạp quy chế & sổ tay K49 · K50 · K51 · K52...');

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const particlesRef = useRef<Particle[]>([]);
  const animFrameIdRef = useRef<number | null>(null);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Bắn pháo hoa từ 2 góc dưới màn hình
  const shootDualConfetti = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const w = canvas.width;
    const h = canvas.height;

    // Góc trái
    for (let i = 0; i < 48; i++) {
      particlesRef.current.push({
        x: 20,
        y: h - 20,
        vx: Math.random() * 8 + 3,
        vy: -(Math.random() * 12 + 6),
        size: Math.random() * 7 + 4,
        color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
        rotation: Math.random() * 360,
        rotationSpeed: Math.random() * 10 - 5,
        opacity: 1,
      });
    }

    // Góc phải
    for (let i = 0; i < 48; i++) {
      particlesRef.current.push({
        x: w - 20,
        y: h - 20,
        vx: -(Math.random() * 8 + 3),
        vy: -(Math.random() * 12 + 6),
        size: Math.random() * 7 + 4,
        color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
        rotation: Math.random() * 360,
        rotationSpeed: Math.random() * 10 - 5,
        opacity: 1,
      });
    }

    const loop = () => {
      const cvs = canvasRef.current;
      if (!cvs) return;
      const ctx = cvs.getContext('2d');
      if (!ctx) return;

      ctx.clearRect(0, 0, cvs.width, cvs.height);

      for (let i = 0; i < particlesRef.current.length; i++) {
        const p = particlesRef.current[i];
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.35; // Trọng lực
        p.vx *= 0.985;
        p.rotation += p.rotationSpeed;
        p.opacity -= 0.007;

        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotation * Math.PI) / 180);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = Math.max(0, p.opacity);
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
        ctx.restore();
      }

      particlesRef.current = particlesRef.current.filter((p) => p.opacity > 0 && p.y < cvs.height + 50);

      if (particlesRef.current.length > 0) {
        animFrameIdRef.current = requestAnimationFrame(loop);
      } else {
        animFrameIdRef.current = null;
      }
    };

    if (!animFrameIdRef.current) {
      animFrameIdRef.current = requestAnimationFrame(loop);
    }
  }, []);

  // Xử lý thoát và kích hoạt bước tiếp theo
  const handleDismiss = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    setIsExiting(true);
    shootDualConfetti();

    const t = setTimeout(() => {
      onComplete();
    }, 350);
    timersRef.current.push(t);
  }, [onComplete, shootDualConfetti]);

  // Điều phối chuỗi 4 nhịp
  useEffect(() => {
    // Resize canvas
    const handleResize = () => {
      if (canvasRef.current) {
        canvasRef.current.width = window.innerWidth;
        canvasRef.current.height = window.innerHeight;
      }
    };
    handleResize();
    window.addEventListener('resize', handleResize);

    // Lắng nghe phím ESC để bỏ qua nhanh
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleDismiss();
      }
    };
    window.addEventListener('keydown', handleKeyDown);

    // Nhịp 1: Preloader chạy thanh tiến trình
    const t1 = setTimeout(() => {
      setProgressWidth('100%');
    }, 50);

    const t2 = setTimeout(() => {
      setPreloaderStatus('Hoàn tất! Chuẩn bị chào đón sinh viên...');
    }, 700);

    // Nhịp 2: Vén rèm vòng cung & pháo hoa
    const t3 = setTimeout(() => {
      setBeat('draping');
      shootDualConfetti();
    }, 1100);

    // Nhịp 3: Hiện Bức Thư Trang Nhã sau khi rèm vén cao hẳn
    const t4 = setTimeout(() => {
      setBeat('letter');
    }, 2450);

    timersRef.current.push(t1, t2, t3, t4);

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('keydown', handleKeyDown);
      timersRef.current.forEach(clearTimeout);
      if (animFrameIdRef.current) {
        cancelAnimationFrame(animFrameIdRef.current);
      }
    };
  }, [handleDismiss, shootDualConfetti]);

  return (
    <div
      className={`welcome-entrance-overlay ${isExiting ? 'exiting' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label="Thư chào đón tân sinh viên"
    >
      {/* Nút Bỏ qua nhanh ở góc trên */}
      <button
        onClick={handleDismiss}
        className="absolute top-5 right-5 z-50 px-3 py-1.5 rounded-full bg-slate-900/80 hover:bg-slate-800 border border-slate-700/60 text-slate-300 hover:text-white text-xs font-medium backdrop-blur-md transition flex items-center gap-1.5 shadow-lg group focus:outline-none focus:ring-2 focus:ring-amber-400"
        title="Bỏ qua hiệu ứng chào mừng (Esc)"
      >
        <span>Bỏ qua</span>
        <kbd className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-400 font-mono border border-slate-700">Esc</kbd>
        <span className="group-hover:translate-x-0.5 transition-transform">→</span>
      </button>

      {/* Canvas pháo hoa */}
      <canvas ref={canvasRef} className="welcome-confetti-canvas" />

      {/* Nhịp 1: Preloader thanh vàng trên nền rèm */}
      <div className={`welcome-preloader-box ${beat !== 'preloader' ? 'hidden' : ''}`}>
        <div className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-full bg-slate-900/80 border border-amber-500/30 backdrop-blur-md shadow-xl">
          <img src="/logo_hcmue.png" className="w-4 h-4 object-contain" alt="Logo HCMUE" />
          <span className="welcome-shimmer-text">HCMUE · KHỞI TẠO SỔ TAY SINH VIÊN</span>
        </div>
        <div className="welcome-progress-track">
          <div className="welcome-progress-fill" style={{ width: progressWidth }} />
        </div>
        <div className="text-[10.5px] text-slate-300/80 tracking-wide font-medium">
          {preloaderStatus}
        </div>
      </div>

      {/* Nhịp 2: Màn rèm nhung xanh (vén vòng cung tự nhiên, không viền vàng) */}
      <div className={`welcome-curtain-container ${isExiting ? 'cleared' : ''}`}>
        <div className={`welcome-curtain-drape welcome-drape-left ${beat !== 'preloader' ? 'opened' : ''}`} />
        <div className={`welcome-curtain-drape welcome-drape-right ${beat !== 'preloader' ? 'opened' : ''}`} />
        <div className="welcome-curtain-rod" />
      </div>

      {/* Nhịp 3: Bức thư ngỏ thanh thoát (Pure Parchment Letter) */}
      <div className={`welcome-letter-wrapper ${beat === 'letter' ? 'shown' : ''} ${isExiting ? 'exiting' : ''}`}>
        <div className="welcome-pure-sheet">
          <div className="welcome-letter-frame">
            
            {/* Nút đóng thư nhỏ kín đáo */}
            <button
              onClick={handleDismiss}
              className="absolute top-2.5 right-2.5 w-6 h-6 rounded-full bg-stone-200/50 hover:bg-stone-300/80 flex items-center justify-center text-stone-500 hover:text-stone-800 text-xs transition z-20 focus:outline-none"
              title="Đóng thư"
            >
              ✕
            </button>

            {/* Header: Logo trường chính thức & Huy hiệu Khóa 52 mạ vàng */}
            <div className="flex items-center justify-between mb-3 border-b border-amber-900/15 pb-2.5 pr-8">
              <div className="flex items-center gap-2">
                <img src="/logo_hcmue.png" className="w-6 h-6 object-contain drop-shadow-xs" alt="Logo HCMUE" />
                <div>
                  <h2 className="text-[11px] font-bold tracking-wider text-amber-950 uppercase font-serif">
                    ĐẠI HỌC SƯ PHẠM TP. HỒ CHÍ MINH
                  </h2>
                  <div className="text-[9px] text-amber-800/70 tracking-widest uppercase">Thư Chào Đón Tân Sinh Viên</div>
                </div>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-amber-100 border border-amber-300 text-amber-900 text-[9.5px] font-bold tracking-wide">
                Khóa 52 · 2026
              </span>
            </div>

            {/* Tiêu đề thư */}
            <h1 className="text-lg sm:text-xl font-bold text-amber-950 welcome-font-serif tracking-tight mb-0.5 text-center">
              Chào Mừng Bạn Đến Với Sổ Tay Sinh Viên
            </h1>
            <div className="text-center text-[10.5px] text-amber-900/70 italic mb-2.5">
              (Dành cho Tân sinh viên Khóa 52 và đồng hành cùng K49 · K50 · K51)
            </div>

            {/* Nội dung thư tinh gọn */}
            <div className="welcome-font-body text-[11.5px] sm:text-[12px] text-stone-800 space-y-2 leading-relaxed">
              <p>
                Chào bạn, cánh cổng trường đã chính thức mở rộng đón bạn! Để đồng hành cùng bạn suốt những năm tháng giảng đường, mình đã phát triển <strong className="text-stone-900">Sổ Tay Sinh Viên AI</strong> với các tính năng cốt lõi:
              </p>

              <ul className="space-y-1.5 pl-0.5 text-stone-800 text-[11.5px]">
                <li className="flex items-start gap-2">
                  <span className="text-amber-700 font-bold leading-none mt-0.5">✦</span>
                  <div>
                    <strong className="text-stone-900">Trợ lý Chatbot AI 24/7:</strong> Giải đáp tức thì quy chế tín chỉ, học phí NĐ 116 — trích dẫn chính xác Điều, Khoản theo đúng khóa học của bạn.
                  </div>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-amber-700 font-bold leading-none mt-0.5">✦</span>
                  <div>
                    <strong className="text-stone-900">Bộ công cụ học vụ:</strong> Tự động tính điểm GPA, mục tiêu điểm thi, xét học bổng KKHT và kiểm tra hạn mức tín chỉ.
                  </div>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-amber-700 font-bold leading-none mt-0.5">✦</span>
                  <div>
                    <strong className="text-stone-900">Danh bạ thông minh:</strong> Tra cứu nhanh số máy nhánh và email của toàn bộ phòng ban, khoa viện trong trường.
                  </div>
                </li>
              </ul>

              <p className="italic text-stone-700 pt-0.5">
                Chúc bạn có một hành trình đại học thật rực rỡ và nhiều kỷ niệm đẹp!
              </p>
            </div>

            {/* Chữ ký bút máy của Anh Phi */}
            <div className="mt-3.5 pt-2 border-t border-amber-900/15 flex items-end justify-between">
              <div className="text-[10px] text-stone-400 welcome-font-body italic">
                Sài Gòn, mùa tựu trường
              </div>
              <div className="text-right">
                <div className="text-xl sm:text-2xl welcome-font-signature font-bold text-blue-900 tracking-wide transform -rotate-3 leading-none mb-0.5">
                  Anh Phi
                </div>
                <div className="text-[9.5px] font-semibold text-stone-600 uppercase tracking-wider">
                  Khoa Công nghệ Thông tin
                </div>
              </div>
            </div>

            {/* Nút Mở Sổ Tay & Khám Phá Ngay */}
            <div className="mt-3.5">
              <button
                onClick={handleDismiss}
                className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-blue-700 via-indigo-700 to-blue-800 hover:from-blue-800 hover:to-indigo-800 text-amber-50 font-bold text-xs sm:text-sm shadow-md shadow-blue-900/20 flex items-center justify-center gap-2 transition-all transform hover:-translate-y-0.5 active:translate-y-0 border border-amber-400/30 focus:outline-none focus:ring-2 focus:ring-amber-400"
              >
                <span>Mở Sổ Tay & Khám Phá Ngay</span>
                <svg className="w-3.5 h-3.5 text-amber-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </button>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
