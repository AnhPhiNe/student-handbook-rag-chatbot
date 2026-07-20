export type SchoolYear = '2024-2025' | '2025-2026' | '2026-2027';

export type TuitionProgram = {
  code: string;
  name: string;
  annual: Record<SchoolYear, number>;
  perCredit: Record<SchoolYear, number>;
};

export const SCHOOL_YEARS: SchoolYear[] = ['2024-2025', '2025-2026', '2026-2027'];

export const TUITION_RATES: TuitionProgram[] = [
  p('5140201', 'Giáo dục Mầm non (cao đẳng)', [13280000, 13600000, 16000000], [375000, 385000, 455000]),
  p('7140101', 'Giáo dục học', [14100000, 15900000, 17900000], [436000, 500000, 561000]),
  p('7140104', 'Quản lý giáo dục', [14100000, 15900000, 17900000], [436000, 500000, 561000]),
  p('7140217', 'Sư phạm Ngữ văn', [14100000, 15900000, 17900000], [436000, 500000, 561000]),
  p('7140219', 'Sư phạm Địa lý', [16215000, 18285000, 20585000], [515000, 579000, 649000]),
  p('7140231', 'Sư phạm Tiếng Anh', [14100000, 15900000, 17900000], [436000, 500000, 561000]),
  p('7140201', 'Giáo dục Mầm non (đại học)', [14100000, 15900000, 17900000], [428000, 492000, 551000]),
  p('7140202', 'Giáo dục Tiểu học', [16920000, 19080000, 21480000], [531000, 608000, 682000]),
  p('7140203', 'Giáo dục Đặc biệt', [14100000, 15900000, 17900000], [428000, 492000, 551000]),
  p('7140204', 'Giáo dục công dân', [14100000, 15900000, 17900000], [428000, 492000, 551000]),
  p('7140205', 'Giáo dục chính trị', [14100000, 15900000, 17900000], [428000, 492000, 551000]),
  p('7140206', 'Giáo dục Thể chất', [14100000, 15900000, 17900000], [428000, 492000, 551000]),
  p('7140208', 'Giáo dục Quốc phòng - An ninh', [14100000, 15900000, 17900000], [428000, 492000, 551000]),
  p('7140209', 'Sư phạm Toán học', [14100000, 15900000, 17900000], [428000, 492000, 551000]),
  p('7140210', 'Sư phạm Tin học', [14100000, 15900000, 17900000], [428000, 492000, 551000]),
  p('7140211', 'Sư phạm Vật lý', [16920000, 19080000, 21480000], [531000, 608000, 682000]),
  p('7140212', 'Sư phạm Hóa học', [16920000, 19080000, 21480000], [531000, 608000, 682000]),
  p('7140213', 'Sư phạm Sinh học', [16215000, 18285000, 20585000], [506000, 579000, 649000]),
  p('7140218', 'Sư phạm Lịch sử', [16215000, 18285000, 20585000], [506000, 579000, 649000]),
  p('7140246', 'Sư phạm Công nghệ', [14100000, 15900000, 17900000], [428000, 492000, 551000]),
  p('7140247', 'Sư phạm Khoa học Tự nhiên', [14100000, 15900000, 17900000], [428000, 492000, 551000]),
  p('7140249', 'Sư phạm Lịch sử - Địa lý', [14100000, 15900000, 17900000], [436000, 500000, 561000]),
  p('7140232', 'Sư phạm Tiếng Nga', [14100000, 15900000, 17900000], [413000, 474000, 531000]),
  p('7140233', 'Sư phạm Tiếng Pháp', [14100000, 15900000, 17900000], [413000, 474000, 531000]),
  p('7140234', 'Sư phạm Tiếng Trung Quốc', [14100000, 15900000, 17900000], [413000, 474000, 531000]),
  p('7220201', 'Ngôn ngữ Anh', [18000000, 20280000, 22920000], [582000, 665000, 749000]),
  p('7220202', 'Ngôn ngữ Nga', [15000000, 16900000, 19100000], [445000, 510000, 574000]),
  p('7220203', 'Ngôn ngữ Pháp', [18000000, 20280000, 22920000], [551000, 629000, 709000]),
  p('7220204', 'Ngôn ngữ Trung Quốc', [18000000, 20280000, 22920000], [551000, 629000, 709000]),
  p('7220209', 'Ngôn ngữ Nhật', [15000000, 16900000, 19100000], [445000, 510000, 574000]),
  p('7220210', 'Ngôn ngữ Hàn Quốc', [15000000, 16900000, 19100000], [445000, 510000, 574000]),
  p('7229030', 'Văn học', [15000000, 16900000, 19100000], [461000, 528000, 595000]),
  p('7310401', 'Tâm lý học', [18000000, 20280000, 22920000], [571000, 652000, 735000]),
  p('7310402', 'Tâm lý học giáo dục', [15000000, 16900000, 19100000], [461000, 528000, 595000]),
  p('7310501', 'Địa lý học', [15000000, 16900000, 19100000], [470000, 538000, 606000]),
  p('7310601', 'Quốc tế học', [15000000, 16900000, 19100000], [461000, 528000, 595000]),
  p('7310630', 'Việt Nam học', [17250000, 19435000, 21965000], [544000, 621000, 700000]),
  p('7420203', 'Sinh học ứng dụng', [15200000, 17100000, 19300000], [468000, 551000, 602000]),
  p('7440102', 'Vật lý học', [15200000, 17100000, 19300000], [456000, 536000, 602000]),
  p('7440112', 'Hóa học', [15200000, 17100000, 19300000], [456000, 536000, 602000]),
  p('7480201', 'Công nghệ Thông tin', [19680000, 22200000, 25080000], [627000, 736000, 829000]),
  p('7760101', 'Công tác xã hội', [15000000, 16900000, 19100000], [470000, 538000, 606000]),
  p('7810101', 'Du lịch', [15000000, 16900000, 19100000], [470000, 538000, 606000]),
];

function p(code: string, name: string, annual: [number, number, number], perCredit: [number, number, number]): TuitionProgram {
  return {
    code,
    name,
    annual: {
      '2024-2025': annual[0],
      '2025-2026': annual[1],
      '2026-2027': annual[2],
    },
    perCredit: {
      '2024-2025': perCredit[0],
      '2025-2026': perCredit[1],
      '2026-2027': perCredit[2],
    },
  };
}

function normalizeSearch(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

export function searchTuitionPrograms(query: string): TuitionProgram[] {
  const normalizedQuery = normalizeSearch(query);
  if (!normalizedQuery) return TUITION_RATES.slice(0, 8);

  return TUITION_RATES
    .map((program) => {
      const name = normalizeSearch(program.name);
      const code = normalizeSearch(program.code);
      const startsWith = name.startsWith(normalizedQuery) || code.startsWith(normalizedQuery);
      const includes = name.includes(normalizedQuery) || code.includes(normalizedQuery);
      return { program, score: startsWith ? 2 : includes ? 1 : 0 };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.program.name.localeCompare(b.program.name, 'vi'))
    .map((item) => item.program)
    .slice(0, 8);
}

export function formatVnd(value: number): string {
  return new Intl.NumberFormat('vi-VN').format(value) + ' đ';
}
