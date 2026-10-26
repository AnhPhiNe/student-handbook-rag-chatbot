import type { DirectoryUnit } from '../data/directory';

/** Lower-case, strip Vietnamese diacritics and map đ to d, so "hoc phi" finds "Học phí". */
export function foldText(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[đĐ]/g, 'd')
    .toLowerCase();
}

function matchesQuery(unit: DirectoryUnit, folded: string): boolean {
  if (foldText(unit.name).includes(folded)) return true;
  if (unit.aliases.some((alias) => foldText(alias).includes(folded))) return true;
  if (unit.campus && foldText(unit.campus).includes(folded)) return true;
  if (unit.services.some((service) => foldText(service).includes(folded))) return true;
  // A keyword also matches inside a longer question: "toi can phuc khao" contains "phuc khao".
  return unit.keywords.some((keyword) => {
    const foldedKeyword = foldText(keyword);
    return foldedKeyword.includes(folded) || folded.includes(foldedKeyword);
  });
}

/** Units whose name, aliases, services or keywords match the query. An empty query returns all. */
export function searchUnits(units: DirectoryUnit[], query: string): DirectoryUnit[] {
  const folded = foldText(query.trim());
  if (!folded) return units;
  return units.filter((unit) => matchesQuery(unit, folded));
}

/** Units whose name contains the task's unit name, e.g. "Khảo thí". */
export function unitsForTask(units: DirectoryUnit[], match: string): DirectoryUnit[] {
  return units.filter((unit) => unit.name.includes(match));
}

/** A dialable link: main number, then a comma pause and the internal extension. */
export function telHref(phone: string, ext?: string): string {
  const digits = phone.replace(/\D/g, '');
  return `tel:${digits}${ext ? `,${ext}` : ''}`;
}

/** The text copied by "Sao chép": unit name, phone with extensions, then the emails. */
export function contactText(unit: DirectoryUnit): string {
  const phone = unit.phones[0];
  const phoneText = phone ? `${phone}${unit.ext.length > 0 ? ` (nhánh ${unit.ext.join(', ')})` : ''}` : '';
  const contact = [phoneText, ...unit.emails].filter(Boolean).join(' · ');
  return `${unit.name}: ${contact}`;
}

/**
 * Where the query sits in the text, ignoring diacritics, as [start, end) offsets into the
 * original text. Folding is done character by character so the offsets stay valid.
 */
export function findHighlight(text: string, query: string): [number, number] | null {
  const folded = foldText(query.trim());
  if (!folded) return null;
  const source = text.normalize('NFC');
  const haystack = Array.from(source, (char) => {
    const single = foldText(char);
    return single.length === 1 ? single : char.toLowerCase();
  }).join('');
  if (haystack.length !== source.length) return null;
  const start = haystack.indexOf(folded);
  return start < 0 ? null : [start, start + folded.length];
}
