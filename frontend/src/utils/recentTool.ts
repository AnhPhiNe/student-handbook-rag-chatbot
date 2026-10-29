/** localStorage key holding the id of the calculator tool opened last. */
export const RECENT_TOOL_KEY = 'hcmue-recent-tool';

/** Ids of the calculator tools the "Gần nhất" card can point at. */
export const RECENT_TOOL_IDS = ['gpa', 'target-gpa', 'course-target', 'scholarship', 'tuition', 'credits'] as const;

/** A stored value can be anything after an old or hand-edited save: accept a known tool id only. */
export function readRecentTool(raw: unknown): string | null {
  return typeof raw === 'string' && (RECENT_TOOL_IDS as readonly string[]).includes(raw) ? raw : null;
}
