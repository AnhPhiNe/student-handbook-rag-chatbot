import { useEffect, useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
const HF_SPACE_ID = import.meta.env.VITE_HF_SPACE_ID || 'AnhFeee/hcmue-handbook-rag-api';
const HEALTH_CHECK_INTERVAL_MS = 45_000;
const HEALTH_CHECK_TIMEOUT_MS = 6_000;
const HF_RUNTIME_TIMEOUT_MS = 2_500;

type SystemStatus = 'checking' | 'online' | 'degraded' | 'offline';

type ReadinessPayload = {
  status?: string;
  ready?: boolean;
  missing_count?: number;
};

type HuggingFaceRuntimePayload = {
  stage?: string;
  runtime?: {
    stage?: string;
  };
};

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<{ ok: boolean; payload: T | null }> {
  const response = await fetch(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  });
  return {
    ok: response.ok,
    payload: response.ok ? (await response.json() as T) : null,
  };
}

function getHfRuntimeUrl(spaceId: string): string | null {
  const [owner, ...repoParts] = spaceId.split('/');
  const repo = repoParts.join('/');
  if (!owner || !repo) return null;
  return `https://huggingface.co/api/spaces/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/runtime`;
}

function statusFromHfStage(stage: string | undefined): SystemStatus | null {
  const normalizedStage = stage?.toUpperCase();
  if (!normalizedStage || normalizedStage === 'RUNNING') return null;
  if (normalizedStage === 'BUILDING' || normalizedStage === 'RUNNING_BUILDING' || normalizedStage === 'SLEEPING') {
    return 'degraded';
  }
  return 'offline';
}

async function checkHfSpaceStage(parentSignal: AbortSignal): Promise<SystemStatus | null> {
  const runtimeUrl = getHfRuntimeUrl(HF_SPACE_ID);
  if (!runtimeUrl) return null;

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), HF_RUNTIME_TIMEOUT_MS);
  const abort = () => controller.abort();
  parentSignal.addEventListener('abort', abort, { once: true });

  try {
    const runtime = await fetchJson<HuggingFaceRuntimePayload>(runtimeUrl, controller.signal);
    if (!runtime.ok || !runtime.payload) return null;
    return statusFromHfStage(runtime.payload.stage ?? runtime.payload.runtime?.stage);
  } catch {
    return null;
  } finally {
    window.clearTimeout(timeout);
    parentSignal.removeEventListener('abort', abort);
  }
}

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
        const hfStageStatus = await checkHfSpaceStage(controller.signal);
        if (hfStageStatus) {
          if (!disposed) setStatus(hfStageStatus);
          return;
        }

        const readiness = await fetchJson<ReadinessPayload>(
          `${API_BASE_URL}/health/readiness`,
          controller.signal,
        );

        if (readiness.ok && readiness.payload) {
          const nextStatus = readiness.payload.ready === true || readiness.payload.status === 'ok'
            ? 'online'
            : 'degraded';
          if (!disposed) setStatus(nextStatus);
          return;
        }

        const basicHealth = await fetchJson<{ status?: string }>(
          `${API_BASE_URL}/health`,
          controller.signal,
        );
        if (!disposed) {
          setStatus(basicHealth.ok && basicHealth.payload?.status === 'ok' ? 'online' : 'offline');
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

  const labelByStatus: Record<SystemStatus, string> = {
    checking: 'Đang kiểm tra',
    online: 'Hệ thống sẵn sàng',
    degraded: 'Đang cập nhật',
    offline: 'Tạm thời gián đoạn',
  };

  const titleByStatus: Record<SystemStatus, string> = {
    checking: 'Đang kiểm tra kết nối tới HCMUE AI',
    online: 'Backend đã sẵn sàng phục vụ câu hỏi',
    degraded: 'Backend phản hồi nhưng chưa đủ điều kiện sẵn sàng, có thể đang build hoặc cập nhật cấu hình',
    offline: 'Không thể kết nối tới dịch vụ HCMUE AI',
  };

  return (
    <div
      className={`system-status-badge ${status}`}
      role="status"
      aria-live="polite"
      title={titleByStatus[status]}
    >
      <span className="system-status-dot" aria-hidden="true" />
      <span>{labelByStatus[status]}</span>
    </div>
  );
}
