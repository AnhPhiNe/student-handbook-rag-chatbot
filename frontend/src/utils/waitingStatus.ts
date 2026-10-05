// What the answer bubble says while the student waits for the first word.
// Planning and retrieval take 5–15 s and composing a regulation answer another
// 20–40 s (measured 2026-10-04), so the bubble names the step the backend
// reports, how long it has been, and the articles found so far.

export interface SourceLike {
  article_label?: string;
  title?: string;
  cohort?: string;
}

const TITLE_LIMIT = 36;

/** Seconds waited, shown from the third second on. */
export function elapsedLabel(elapsedMs: number): string {
  const seconds = Math.floor(elapsedMs / 1000);
  return seconds >= 3 ? `${seconds} giây` : '';
}

/** A reassurance once the wait is longer than a lookup usually takes. */
export function waitingHint(elapsedMs: number): string {
  if (elapsedMs >= 60000) return 'Câu trả lời vẫn đang được soạn, cảm ơn bạn đã kiên nhẫn chờ.';
  if (elapsedMs >= 20000) return 'Câu này cần đối chiếu nhiều quy định nên thường mất khoảng 30–40 giây.';
  return '';
}

/** Short labels of the handbook articles found, e.g. "Điều 27 · Tiêu chuẩn, mức, quỹ học…". */
export function sourceLabels(sources: SourceLike[], max = 3): { labels: string[]; more: number } {
  const seen = new Set<string>();
  const labels: string[] = [];
  for (const source of sources) {
    const article = source.article_label?.trim();
    if (!article) continue;  // directory records are shown with the answer instead
    const key = `${source.cohort ?? ''}|${article}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const title = source.title?.trim() ?? '';
    const short = title.length > TITLE_LIMIT ? `${title.slice(0, TITLE_LIMIT).trimEnd()}…` : title;
    labels.push(short ? `${article} · ${short}` : article);
  }
  return { labels: labels.slice(0, max), more: Math.max(0, labels.length - max) };
}
