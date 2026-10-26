import type { ExperienceTip } from '../data/experience';

/** Pastel paper colours. Any 3 consecutive entries differ, so grid neighbours never match. */
export const NOTE_COLORS = ['#dbeafe', '#fce7f3', '#d1fae5', '#fef3c7', '#ede9fe', '#ffedd5'] as const;

/** Tips of one topic; 'all' keeps every tip. */
export function filterTips<T extends Pick<ExperienceTip, 'topic'>>(tips: readonly T[], topicId: string): T[] {
  return topicId === 'all' ? [...tips] : tips.filter((tip) => tip.topic === topicId);
}

/** Paper colour by display position, so colours stay varied when the list is filtered. */
export function noteColor(index: number): string {
  const size = NOTE_COLORS.length;
  return NOTE_COLORS[((index % size) + size) % size];
}
