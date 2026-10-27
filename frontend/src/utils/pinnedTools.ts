export interface PinnableGroup<T extends { id: string }> {
  title: string;
  tools: T[];
}

/** Stored pins can be anything after an old or hand-edited save: keep unique strings only. */
export function sanitizePinnedIds(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  for (const item of raw) {
    if (typeof item === 'string') seen.add(item);
  }
  return [...seen];
}

export function togglePinnedId(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((existing) => existing !== id) : [...ids, id];
}

/**
 * Pinned tools in pin order (unknown ids ignored), and the groups without them.
 * A group whose tools are all pinned is dropped so no empty heading is left behind.
 */
export function arrangePinnedTools<T extends { id: string }>(
  groups: Array<PinnableGroup<T>>,
  pinnedIds: unknown,
): { pinned: T[]; groups: Array<PinnableGroup<T>> } {
  const byId = new Map<string, T>();
  for (const group of groups) {
    for (const tool of group.tools) byId.set(tool.id, tool);
  }
  const ids = sanitizePinnedIds(pinnedIds).filter((id) => byId.has(id));
  const pinnedSet = new Set(ids);
  return {
    pinned: ids.map((id) => byId.get(id) as T),
    groups: groups
      .map((group) => ({ ...group, tools: group.tools.filter((tool) => !pinnedSet.has(tool.id)) }))
      .filter((group) => group.tools.length > 0),
  };
}
