/** Keeps digits and a single decimal point; a typed comma becomes a dot. */
export function sanitizeDecimal(raw: string): string {
  const normalized = raw.replace(/,/g, '.').replace(/[^\d.]/g, '');
  const [whole, ...fraction] = normalized.split('.');
  return fraction.length > 0 ? `${whole}.${fraction.join('')}` : whole;
}

/** Keeps digits only. */
export function sanitizeInteger(raw: string): string {
  return raw.replace(/\D/g, '');
}
