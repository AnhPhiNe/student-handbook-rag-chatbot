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
  const [activeUsers, setActiveUsers] = useState<number | null>(null);
  const [isHovered, setIsHovered] = useState(false);
  const [displayUsers, setDisplayUsers] = useState<number>(0);
  const [isError, setIsError] = useState(false);

  // Tính toán số lượng mục tiêu cần hướng tới (sử dụng số liệu thật 100%)
  const targetUsers = activeUsers !== null ? activeUsers : 0;

  // Hiệu ứng đếm dần (Count up/down animation) để UI mượt mà
  useEffect(() => {
    if (activeUsers === null || isError) return;
    
    // Nếu lần đầu (0), thì gán thẳng luôn tránh đếm từ 0 lâu
    if (displayUsers === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
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
  }, [displayUsers, targetUsers, activeUsers, isError]);

  useEffect(() => {
    const sessionId = getSessionId();
    
    // Hàm gọi API
    const fetchActiveUsers = async () => {
      try {
        const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api';
        const response = await fetch(`${baseUrl}/api/metrics/active-users?session_id=${sessionId}`);
        if (response.ok) {
          const data = await response.json();
          if (data && typeof data.active_users === 'number') {
            setActiveUsers(data.active_users);
            setIsError(false);
          } else {
            setIsError(true);
          }
        } else {
          setIsError(true);
        }
      } catch (error) {
        console.error("Failed to fetch active users:", error);
        setIsError(true);
      }
    };

    // Gọi lần đầu
    void fetchActiveUsers();

    // Gọi định kỳ mỗi 30 giây
    const interval = setInterval(fetchActiveUsers, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fallback state khi lỗi mạng hoặc chưa tải xong
  if (isError || activeUsers === null) {
    return (
      <div 
        className="active-users-badge"
        title="Hệ thống đang kết nối hoặc tải số lượng"
      >
        <div className="pulsing-dot" style={{ backgroundColor: '#F59E0B' }}></div>
        <span className="count-text">
          Đang kết nối...
        </span>
      </div>
    );
  }

  return (
    <div 
      className="active-users-badge"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title="Số người đang truy cập hệ thống (Thời gian thực)"
    >
      <div className="pulsing-dot"></div>
      <span className="count-text">
        {isHovered ? `${displayUsers} đang online` : displayUsers}
      </span>
    </div>
  );
}

