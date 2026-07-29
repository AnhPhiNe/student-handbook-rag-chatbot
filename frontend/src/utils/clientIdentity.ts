const CLIENT_ID_STORAGE_KEY = 'hcmue_anonymous_client_id';
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

let volatileClientId: string | null = null;

function createClientId(): string {
  if (typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const value = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return [
    value.slice(0, 8),
    value.slice(8, 12),
    value.slice(12, 16),
    value.slice(16, 20),
    value.slice(20),
  ].join('-');
}

export function getAnonymousClientId(): string {
  if (volatileClientId) return volatileClientId;

  try {
    const stored = localStorage.getItem(CLIENT_ID_STORAGE_KEY);
    if (stored && UUID_PATTERN.test(stored)) {
      volatileClientId = stored;
      return stored;
    }

    volatileClientId = createClientId();
    localStorage.setItem(CLIENT_ID_STORAGE_KEY, volatileClientId);
  } catch {
    volatileClientId = createClientId();
  }

  return volatileClientId;
}

export function getApiClientHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'X-Client-ID': getAnonymousClientId(),
  };
}
