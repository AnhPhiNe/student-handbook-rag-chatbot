import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const admissionsPath = path.resolve(__dirname, '../src/data/admissions.ts');
const source = fs.readFileSync(admissionsPath, 'utf8');

const rawScaleMatch = source.match(/export const ADMISSION_RAW_SCORE_SCALE = ([0-9.]+);/);
const rawScoreScale = rawScaleMatch ? Number(rawScaleMatch[1]) : 30;
const scoreMaxMatch = source.match(/export const ADMISSION_SCORE_INPUT_MAX = ([0-9.]+);/);
const scoreMax = scoreMaxMatch ? Number(scoreMaxMatch[1]) : 33;
const rowPattern = /^\s+(thpt2025|historicalThpt)\((.*?)\),$/gm;
const records = [];

function parseArgs(value) {
  return Array.from(value.matchAll(/'([^']*)'|([0-9]+(?:\.[0-9]+)?)/g)).map((match) =>
    match[1] === undefined ? Number(match[2]) : match[1],
  );
}

let match;
while ((match = rowPattern.exec(source))) {
  const fnName = match[1];
  const args = parseArgs(match[2]);
  const year = fnName === 'thpt2025' ? 2025 : Number(args[0]);
  const offset = fnName === 'thpt2025' ? 0 : 1;
  const programName = String(args[offset] ?? '');
  const subjectGroup = String(args[offset + 2] ?? '');
  const cutoffScore = Number(args[offset + 3]);

  records.push({
    year,
    programName,
    subjectGroup,
    cutoffScore,
  });
}

const invalid = records.filter(
  (record) =>
    !record.programName ||
    !record.subjectGroup ||
    !Number.isFinite(record.cutoffScore) ||
    record.cutoffScore < 0 ||
    record.cutoffScore > scoreMax,
);
const overRawScale = records.filter((record) => record.cutoffScore > rawScoreScale);

if (invalid.length > 0) {
  console.error('[admission-data] Invalid cutoff records detected:');
  console.error(JSON.stringify(invalid, null, 2));
  process.exit(1);
}

console.log(
  `[admission-data] ${records.length} cutoff records validated. ` +
    `${overRawScale.length} records are above ${rawScoreScale} and must be highlighted in the UI.`,
);
