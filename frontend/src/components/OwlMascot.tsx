import React from 'react';

export type OwlState = 'idle' | 'reading' | 'eureka';

export interface OwlMascotProps {
  state?: OwlState;
  size?: number;
  className?: string;
  style?: React.CSSProperties;
  showFrame?: boolean;
}

export const OwlMascot: React.FC<OwlMascotProps> = ({
  state = 'idle',
  size = 48,
  className = '',
  style = {},
  showFrame = true,
}) => {
  // Lựa chọn class hào quang viền nền trắng theo 3 trạng thái độc lập
  const frameClass =
    state === 'reading'
      ? 'avatar-frame-reading-white'
      : state === 'eureka'
      ? 'avatar-frame-eureka-white'
      : 'avatar-frame-idle-white';

  const svgContent = (
    <svg
      viewBox="0 0 100 100"
      className="w-full h-full"
      style={{ overflow: 'visible' }}
      aria-label={`Mascot Cú Sư Phạm (${state})`}
    >
      <defs>
        {/* Thân Cú xanh Sư Phạm */}
        <linearGradient id="owlBodyGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="50%" stopColor="#2563eb" />
          <stop offset="100%" stopColor="#1d4ed8" />
        </linearGradient>

        {/* Bụng trắng kem mềm */}
        <linearGradient id="owlBellyGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#f0f9ff" />
        </linearGradient>

        {/* Gọng kính & tua rua vàng */}
        <linearGradient id="goldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#fef08a" />
          <stop offset="50%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#d97706" />
        </linearGradient>

        {/* Mũ cử nhân navy đậm */}
        <linearGradient id="capGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#1e3a8a" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>

        {/* Mỏ cam tươi */}
        <linearGradient id="beakGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#fb923c" />
          <stop offset="100%" stopColor="#ea580c" />
        </linearGradient>

        {/* Bóng đèn Eureka vàng ấm dịu */}
        <linearGradient id="bulbGlassGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="30%" stopColor="#fef9c3" />
          <stop offset="75%" stopColor="#fde047" />
          <stop offset="100%" stopColor="#eab308" />
        </linearGradient>

        {/* Hào quang tri thức sách */}
        <linearGradient id="bookLightGrad" x1="0%" y1="100%" x2="0%" y2="0%">
          <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#60a5fa" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* TOÀN BỘ CƠ THỂ CÚ */}
      <g className="anim-body-breath">
        {/* Đổ bóng tiếp xúc dưới chân trên nền trắng */}
        <ellipse cx="50" cy="88" rx="22" ry="4" fill="#e2e8f0" opacity="0.85" />

        {/* Tai lông vểnh 2 bên có cử động nhúc nhích chăm chú */}
        <g className="anim-ear-left">
          <path d="M22,38 Q14,24 28,28 Z" fill="#2563eb" />
        </g>
        <g className="anim-ear-right">
          <path d="M78,38 Q86,24 72,28 Z" fill="#2563eb" />
        </g>

        {/* Thân tròn xanh Sư Phạm rõ nét */}
        <ellipse
          cx="50"
          cy="56"
          rx="34"
          ry="30"
          fill="url(#owlBodyGrad)"
          stroke="#1e40af"
          strokeWidth="0.8"
        />

        {/* Bụng trắng kem mềm */}
        <ellipse
          cx="50"
          cy="62"
          rx="23"
          ry="21"
          fill="url(#owlBellyGrad)"
          stroke="#e0f2fe"
          strokeWidth="0.8"
        />
        <path d="M42,56 Q45,59 48,56" fill="none" stroke="#bae6fd" strokeWidth="1.8" strokeLinecap="round" />
        <path d="M52,56 Q55,59 58,56" fill="none" stroke="#bae6fd" strokeWidth="1.8" strokeLinecap="round" />
        <path d="M47,64 Q50,67 53,64" fill="none" stroke="#bae6fd" strokeWidth="1.8" strokeLinecap="round" />

        {/* Hai chân cam */}
        <ellipse cx="40" cy="85" rx="6.5" ry="3.5" fill="#f97316" />
        <ellipse cx="60" cy="85" rx="6.5" ry="3.5" fill="#f97316" />

        {/* ================= BỘ CÁNH ================= */}
        {/* Cánh trái */}
        <g>
          {state === 'idle' && (
            <path d="M24,46 Q10,56 16,72 Q26,76 30,60 Z" fill="#1e40af" stroke="#2563eb" strokeWidth="0.8" />
          )}
          {state === 'reading' && (
            <path d="M24,48 Q20,66 32,70 Q36,64 30,56 Z" fill="#1e40af" stroke="#2563eb" strokeWidth="0.8" />
          )}
          {state === 'eureka' && (
            <path d="M24,48 Q15,58 22,68 Q30,66 30,56 Z" fill="#1e40af" stroke="#2563eb" strokeWidth="0.8" />
          )}
        </g>

        {/* Cánh phải */}
        <g>
          {state === 'idle' && (
            <path d="M76,46 Q90,56 84,72 Q74,76 70,60 Z" fill="#1e40af" stroke="#2563eb" strokeWidth="0.8" />
          )}
          {state === 'reading' && (
            <g className="anim-hand-turn-page">
              <path d="M76,52 Q76,68 64,70 Q60,62 68,54 Z" fill="#1e40af" stroke="#2563eb" strokeWidth="1" />
            </g>
          )}
          {state === 'eureka' && (
            <g className="anim-wing-point">
              <path d="M74,50 Q86,36 80,21 Q75,19 72,27 Q68,36 70,48 Z" fill="#1e40af" stroke="#2563eb" strokeWidth="1" />
              <path d="M78,24 Q80,18 81,15 Q82,18 80,24" fill="#3b82f6" />
            </g>
          )}
        </g>

        {/* ================= PHỤ KIỆN MINH HỌA ================= */}
        {/* 1. Sổ tay khi Reading */}
        {state === 'reading' && (
          <g>
            <polygon points="34,62 67,62 74,48 27,48" fill="url(#bookLightGrad)" className="anim-book-glow" />
            <circle cx="44" cy="54" r="1.5" fill="#bae6fd" className="anim-particle-1" />
            <circle cx="58" cy="52" r="1.2" fill="#38bdf8" className="anim-particle-2" />
            <rect x="32" y="60" width="36" height="20" rx="2.5" fill="#1e3a8a" stroke="#2563eb" strokeWidth="1" />
            <rect x="34" y="62" width="15" height="16" rx="1" fill="#f8fafc" />
            <line x1="36" y1="66" x2="46" y2="66" stroke="#94a3b8" strokeWidth="1" />
            <line x1="36" y1="70" x2="44" y2="70" stroke="#94a3b8" strokeWidth="1" />
            <line x1="36" y1="74" x2="45" y2="74" stroke="#94a3b8" strokeWidth="1" />
            <rect x="51" y="62" width="15" height="16" rx="1" fill="#f8fafc" />
            <line x1="53" y1="66" x2="63" y2="66" stroke="#94a3b8" strokeWidth="1" />
            <line x1="53" y1="70" x2="61" y2="70" stroke="#94a3b8" strokeWidth="1" />
            <g className="anim-page-curl">
              <rect x="50" y="62" width="15" height="16" rx="1" fill="#ffffff" stroke="#cbd5e1" strokeWidth="0.8" />
            </g>
          </g>
        )}

        {/* 2. Bóng đèn Eureka khi Thành công */}
        {state === 'eureka' && (
          <g>
            <circle cx="82" cy="18" r="14" fill="none" stroke="#8b5cf6" className="anim-shockwave" />
            <g className="anim-star-1">
              <path d="M64,5 L65.5,8 L68,8.5 L65.5,10 L64,13 L62.5,10 L60,8.5 L62.5,8 Z" fill="#f59e0b" />
            </g>
            <g className="anim-star-2">
              <path d="M94,25 L95,27 L97,27.5 L95,29 L94,31 L93,29 L91,27.5 L93,27 Z" fill="#f59e0b" />
            </g>
            <g className="anim-bulb-glow">
              <g className="anim-bulb-rays" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round">
                <line x1="82" y1="2" x2="82" y2="6" />
                <line x1="94" y1="7" x2="91" y2="10" />
                <line x1="98" y1="18" x2="93" y2="18" />
                <line x1="93" y1="28" x2="89" y2="25" />
                <line x1="70" y1="7" x2="73" y2="10" />
                <line x1="66" y1="18" x2="71" y2="18" />
              </g>
              <circle cx="82" cy="18" r="14" fill="#fef08a" opacity="0.3" />
              <path
                d="M75,23 C72,20 72,13 76,9 C80,5 84,5 88,9 C92,13 92,20 89,23 C87.5,25.5 86.5,27 86.5,29 L77.5,29 C77.5,27 76.5,25.5 75,23 Z"
                fill="url(#bulbGlassGrad)"
                stroke="#d97706"
                strokeWidth="1.5"
              />
              <path
                d="M78.5,19 L80.5,14 L83.5,14 L85.5,19"
                fill="none"
                stroke="#b45309"
                strokeWidth="1.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <rect x="78" y="29" width="8" height="3" rx="1" fill="#94a3b8" stroke="#64748b" strokeWidth="0.8" />
              <line x1="78.5" y1="30.5" x2="85.5" y2="30.5" stroke="#cbd5e1" strokeWidth="0.8" />
              <ellipse cx="82" cy="33" rx="2.5" ry="1.2" fill="#475569" />
              <ellipse cx="78" cy="11" rx="1.5" ry="3.5" transform="rotate(-30 78 11)" fill="#ffffff" opacity="0.85" />
            </g>
          </g>
        )}

        {/* ================= KHUÔN MẶT & MẮT ================= */}
        <g className={state === 'eureka' ? 'anim-head-eureka' : ''}>
          {/* Mắt tròn */}
          <g className="anim-eyes-blink">
            <ellipse cx="37" cy="46" rx="12.5" ry="13.5" fill="#ffffff" stroke="#cbd5e1" strokeWidth="0.8" />
            <ellipse cx="63" cy="46" rx="12.5" ry="13.5" fill="#ffffff" stroke="#cbd5e1" strokeWidth="0.8" />
            <g
              className={
                state === 'reading'
                  ? 'anim-eyes-scanning'
                  : state === 'eureka'
                  ? 'eyes-look-bulb'
                  : 'anim-pupils'
              }
            >
              <ellipse cx="38" cy="46" rx="8" ry="9" fill="#0f172a" />
              <ellipse cx="62" cy="46" rx="8" ry="9" fill="#0f172a" />
              <circle cx="41" cy="43" r="3.2" fill="#ffffff" />
              <circle cx="65" cy="43" r="3.2" fill="#ffffff" />
              <circle cx="36" cy="49" r="1.5" fill="#ffffff" />
              <circle cx="60" cy="49" r="1.5" fill="#ffffff" />
            </g>
          </g>

          {/* Gọng kính vàng & vệt sáng lướt qua */}
          <g>
            <circle cx="37" cy="46" r="13.5" fill="none" stroke="url(#goldGrad)" strokeWidth="2.6" />
            <circle cx="63" cy="46" r="13.5" fill="none" stroke="url(#goldGrad)" strokeWidth="2.6" />
            <path d="M50.5,45.5 Q50,43.5 49.5,45.5" fill="none" stroke="url(#goldGrad)" strokeWidth="2.6" strokeLinecap="round" />
            <line x1="28" y1="40" x2="42" y2="48" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" className="anim-glasses-sheen" />
            <line x1="54" y1="40" x2="68" y2="48" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" className="anim-glasses-sheen" />
          </g>

          {/* Má hồng */}
          <ellipse cx="23" cy="54" rx="4.5" ry="2.5" fill="#f43f5e" opacity="0.5" />
          <ellipse cx="77" cy="54" rx="4.5" ry="2.5" fill="#f43f5e" opacity="0.5" />

          {/* Mỏ cam */}
          <path d="M46,50 Q50,58 54,50 Q50,48 46,50 Z" fill="url(#beakGrad)" />

          {/* Mũ cử nhân */}
          <g>
            <polygon points="50,14 18,24 50,31 82,24" fill="url(#capGrad)" stroke="#1e3a8a" strokeWidth="0.8" />
            <path d="M34,26 Q50,30 66,26 L64,31 Q50,35 36,31 Z" fill="#0f172a" />
            <circle cx="50" cy="22.5" r="2.8" fill="url(#goldGrad)" />
            <g className="anim-tassel-sway">
              <path d="M50,22.5 Q32,24 32,36" fill="none" stroke="url(#goldGrad)" strokeWidth="2" />
              <rect x="29.5" y="34" width="5" height="10" rx="2" fill="url(#goldGrad)" />
              <line x1="30" y1="44" x2="34" y2="44" stroke="#b45309" strokeWidth="1" />
            </g>
          </g>
        </g>
      </g>
    </svg>
  );

  if (!showFrame) {
    return (
      <div
        className={`relative inline-flex items-center justify-center ${className}`}
        style={{ width: `${size}px`, height: `${size}px`, ...style }}
      >
        {svgContent}
      </div>
    );
  }

  return (
    <div
      className={`owl-mascot-avatar ${frameClass} ${className}`}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        borderRadius: '50%',
        overflow: 'hidden',
        backgroundColor: '#ffffff',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1px',
        flexShrink: 0,
        ...style,
      }}
    >
      {svgContent}
    </div>
  );
};

export default OwlMascot;
