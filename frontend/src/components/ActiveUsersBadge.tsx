import { useState, useEffect } from 'react';

// Hàm tạo session ID đơn giản nếu chưa có
function getSessionId() {
  let sessionId = localStorage.getItem('hcmue-session-id');
  if (!sessionId) {
    sessionId = Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    localStorage.setItem('hcmue-session-id', sessionId);
  }
  return sessionId;
}

export function ActiveUsersBadge() {
  const [activeUsers, setActiveUsers] = useState<number>(1);
  const [isHovered, setIsHovered] = useState(false);
  
  // Tổng số hiển thị trực tiếp ra màn hình, tách biệt với số mục tiêu để làm hiệu ứng chạy từ từ
  const [displayUsers, setDisplayUsers] = useState<number>(0);
  
  // Thủ thuật 2: Cộng thêm số nền (Base Offset) ngẫu nhiên từ 15 đến 85 để tạo hiệu ứng đám đông
  const [baseOffset, setBaseOffset] = useState(() => Math.floor(Math.random() * (85 - 15 + 1)) + 15);

  // Hiệu ứng dao động ngẫu nhiên (lên/xuống 3-12 người) mỗi 8 giây để tạo cảm giác thực tế
  useEffect(() => {
    const driftInterval = setInterval(() => {
      setBaseOffset(prev => {
        // Tăng/giảm một khoảng ngẫu nhiên từ 3 đến 12 người
        const changeAmount = Math.floor(Math.random() * (12 - 3 + 1)) + 3; 
        const isUp = Math.random() > 0.5;
        const change = isUp ? changeAmount : -changeAmount;
        
        let next = prev + change;
        // Giới hạn trong khoảng 15 đến 150
        if (next < 15) next = 15;
        if (next > 150) next = 150;
        return next;
      });
    }, 8000); // 8 giây

    return () => clearInterval(driftInterval);
  }, []);

  // Tính toán số lượng mục tiêu cần hướng tới
  const targetUsers = activeUsers + baseOffset;

  // Hiệu ứng đếm dần (Count up/down animation)
  useEffect(() => {
    // Nếu lần đầu (0), thì gán thẳng luôn tránh đếm từ 0 lâu
    if (displayUsers === 0) {
      setDisplayUsers(targetUsers);
      return;
    }
    
    if (displayUsers === targetUsers) return;

    // Khoảng thời gian giữa các lần nhảy số (nhanh hay chậm)
    const animationDelay = 150; 

    const timer = setTimeout(() => {
      setDisplayUsers(prev => (prev < targetUsers ? prev + 1 : prev - 1));
    }, animationDelay);

    return () => clearTimeout(timer);
  }, [displayUsers, targetUsers]);

  useEffect(() => {
    const sessionId = getSessionId();
    
    // Hàm gọi API
    const fetchActiveUsers = async () => {
      try {
        const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        const response = await fetch(`${apiUrl}/api/metrics/active-users?session_id=${sessionId}`);
        if (response.ok) {
          const data = await response.json();
          if (data && typeof data.active_users === 'number') {
            setActiveUsers(data.active_users);
          }
        }
      } catch (error) {
        console.error("Failed to fetch active users:", error);
      }
    };

    // Gọi lần đầu
    void fetchActiveUsers();

    // Gọi định kỳ mỗi 30 giây
    const interval = setInterval(fetchActiveUsers, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div 
      className="active-users-badge"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title="Số người đang truy cập hệ thống"
    >
      <div className="pulsing-dot"></div>
      <span className="count-text">
        {isHovered ? `${displayUsers} đang online` : displayUsers}
      </span>
    </div>
  );
}
