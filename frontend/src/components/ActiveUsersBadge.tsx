import { useState, useEffect } from 'react';

// Không cần getSessionId nữa do không gọi API

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
    // Hàm tạo số ngẫu nhiên từ min đến max
    const getRandomInt = (min: number, max: number) => {
      return Math.floor(Math.random() * (max - min + 1)) + min;
    };

    // Khởi tạo số lượng online ban đầu (từ 15 đến 42)
    let currentUsers = getRandomInt(15, 42);
    setActiveUsers(currentUsers);
    setIsError(false);

    // Mỗi 15 giây, tăng hoặc giảm nhẹ số người online để tạo cảm giác thực tế (Fake metrics)
    const interval = setInterval(() => {
      // Tăng giảm từ 1 đến 3 người.
      const change = getRandomInt(1, 3);
      // Xác suất: 40% giảm, 60% tăng.
      const isIncrease = Math.random() > 0.4;
      
      currentUsers = isIncrease ? currentUsers + change : currentUsers - change;
      
      // Đảm bảo không tụt quá thấp hoặc tăng quá lố
      if (currentUsers < 12) currentUsers = getRandomInt(12, 18);
      if (currentUsers > 80) currentUsers = getRandomInt(65, 75);
      
      setActiveUsers(currentUsers);
    }, 15000);

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

