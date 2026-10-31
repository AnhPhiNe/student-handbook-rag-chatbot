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
        className="welcome-skip-btn"
        title="Bỏ qua hiệu ứng chào mừng (Esc)"
      >
        <span>Bỏ qua</span>
        <kbd className="welcome-skip-kbd">Esc</kbd>
        <span>→</span>
      </button>

      {/* Canvas pháo hoa */}
      <canvas ref={canvasRef} className="welcome-confetti-canvas" />

      {/* Nhịp 1: Preloader thanh vàng trên nền rèm */}
      <div className={`welcome-preloader-box ${beat !== 'preloader' ? 'hidden' : ''}`}>
        <div className="welcome-preloader-pill">
          <img src="/logo_hcmue.png" className="welcome-preloader-logo" alt="Logo HCMUE" />
          <span className="welcome-shimmer-text">HCMUE · KHỞI TẠO SỔ TAY SINH VIÊN</span>
        </div>
        <div className="welcome-progress-track">
          <div className="welcome-progress-fill" style={{ width: progressWidth }} />
        </div>
        <div className="welcome-preloader-status">
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
              className="welcome-close-btn"
              title="Đóng thư"
            >
              ✕
            </button>

            {/* Header: Logo trường chính thức & Huy hiệu Khóa 52 mạ vàng */}
            <div className="welcome-letter-header">
              <div className="welcome-school-brand">
                <img src="/logo_hcmue.png" className="welcome-school-logo" alt="Logo HCMUE" />
                <div>
                  <h2 className="welcome-school-title">
                    ĐẠI HỌC SƯ PHẠM TP. HỒ CHÍ MINH
                  </h2>
                  <div className="welcome-school-sub">Thư Chào Đón Tân Sinh Viên</div>
                </div>
              </div>
              <span className="welcome-badge-k52">
                Khóa 52 · 2026
              </span>
            </div>

            {/* Tiêu đề thư */}
            <h1 className="welcome-letter-title">
              Chào Mừng Bạn Đến Với Sổ Tay Sinh Viên
            </h1>
            <div className="welcome-letter-sub">
              (Dành cho Tân sinh viên Khóa 52 và đồng hành cùng K49 · K50 · K51)
            </div>

            {/* Nội dung thư tinh gọn */}
            <div className="welcome-letter-body">
              <p>
                Chào bạn, cánh cổng trường đã chính thức mở rộng đón bạn! Để đồng hành cùng bạn suốt những năm tháng giảng đường, mình đã phát triển <strong>Sổ Tay Sinh Viên AI</strong> với các tính năng cốt lõi:
              </p>

              <ul className="welcome-feature-list">
                <li className="welcome-feature-item">
                  <span className="welcome-feature-bullet">✦</span>
                  <div>
                    <strong>Trợ lý Chatbot AI 24/7:</strong> Giải đáp tức thì quy chế tín chỉ, học phí NĐ 116 — trích dẫn chính xác Điều, Khoản theo đúng khóa học của bạn.
                  </div>
                </li>
                <li className="welcome-feature-item">
                  <span className="welcome-feature-bullet">✦</span>
                  <div>
                    <strong>Bộ công cụ học vụ:</strong> Tự động tính điểm GPA, mục tiêu điểm thi, xét học bổng KKHT và kiểm tra hạn mức tín chỉ.
                  </div>
                </li>
                <li className="welcome-feature-item">
                  <span className="welcome-feature-bullet">✦</span>
                  <div>
                    <strong>Danh bạ thông minh:</strong> Tra cứu nhanh số máy nhánh và email của toàn bộ phòng ban, khoa viện trong trường.
                  </div>
                </li>
              </ul>

              <p className="welcome-letter-wish">
                Chúc bạn có một hành trình đại học thật rực rỡ và nhiều kỷ niệm đẹp!
              </p>
            </div>

            {/* Chữ ký bút máy của Anh Phi */}
            <div className="welcome-signature-row">
              <div className="welcome-signature-date">
                Sài Gòn, mùa tựu trường
              </div>
              <div className="welcome-signature-block">
                <div className="welcome-signature-name">
                  Anh Phi
                </div>
                <div className="welcome-signature-dept">
                  Khoa Công nghệ Thông tin
                </div>
              </div>
            </div>

            {/* Nút Mở Sổ Tay & Khám Phá Ngay */}
            <button
              onClick={handleDismiss}
              className="welcome-cta-btn"
            >
              <span>Mở Sổ Tay & Khám Phá Ngay</span>
              <svg className="welcome-cta-arrow" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </button>

          </div>
        </div>
      </div>
    </div>
  );
}
