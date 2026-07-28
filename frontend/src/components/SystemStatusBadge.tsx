import { useEffect, useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
const HEALTH_CHECK_INTERVAL_MS = 60_000;
const HEALTH_CHECK_TIMEOUT_MS = 6_000;

type SystemStatus = 'checking' | 'online' | 'offline';

export function SystemStatusBadge() {
  const [status, setStatus] = useState<SystemStatus>('checking');

  useEffect(() => {
    let disposed = false;
    let activeController: AbortController | null = null;

    const checkHealth = async () => {
      activeController?.abort();
      const controller = new AbortController();
      activeController = controller;
      const timeout = window.setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT_MS);

      try {
        const response = await fetch(`${API_BASE_URL}/health`, {
          method: 'GET',
          headers: { Accept: 'application/json' },
          signal: controller.signal,
        });
        const payload = response.ok ? await response.json() as { status?: string } : null;
        if (!disposed) {
          setStatus(response.ok && payload?.status === 'ok' ? 'online' : 'offline');
        }
      } catch {
        if (!disposed) setStatus('offline');
      } finally {
        window.clearTimeout(timeout);
      }
    };

    void checkHealth();
    const interval = window.setInterval(() => void checkHealth(), HEALTH_CHECK_INTERVAL_MS);

    return () => {
      disposed = true;
      activeController?.abort();
      window.clearInterval(interval);
    };
  }, []);

  const label = status === 'online'
    ? 'Hệ thống hoạt động'
    : status === 'offline'
      ? 'Tạm thời gián đoạn'
      : 'Đang kết nối';

  return (
    <div
      className={`system-status-badge ${status}`}
      role="status"
      aria-live="polite"
      title={status === 'offline' ? 'Không thể kết nối tới dịch vụ HCMUE AI' : label}
    >
      <span className="system-status-dot" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
