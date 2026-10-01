export const MAX_QUERY_CHARS = 2000;
const WARNING_QUERY_CHARS = 1600;

/** Count code points in the exact question submitted to the API. */
export function queryLengthState(text: string) {
  const normalizedText = text.trim();
  const charCount = Array.from(normalizedText).length;
  return {
    normalizedText,
    charCount,
    isNearLimit: charCount >= WARNING_QUERY_CHARS,
    isOverLimit: charCount > MAX_QUERY_CHARS,
  };
}
