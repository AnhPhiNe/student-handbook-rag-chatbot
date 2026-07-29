export type CurrentProblem = 
  | 'procrastinate' | 'distracted' | 'low-efficiency' 
  | 'memory-issues' | 'practice-issues' 
  | 'time-issues' | 'give-up' | 'too-many-subjects'
  | 'comprehension-issues' | 'note-taking-issues';

export type ImprovementGoal = 'focus' | 'memory' | 'deep-understanding' | 'exercises' | 'deadline' | 'exam-prep';
export type ContentType = 'theory' | 'logic' | 'mixed';
export type TimeAvailable = 'under-30' | '30-60' | 'over-60';

export interface AssessmentAnswers {
  problems: CurrentProblem[]; // Max 3
  goal: ImprovementGoal | null;
  content: ContentType | null;
  time: TimeAvailable | null;
}

export type MethodResult = {
  id: string;
  reasons: string[];
  actionPlan: string;
};

export type EvaluationResult = {
  primaryMethodId: string;
  supportingMethodIds: string[];
  allMethods: MethodResult[];
};

// Fixed tie-breaker priority array (higher index = lower priority)
const TIE_BREAKER_PRIORITY = [
  'pomodoro', 'active-recall', 'spaced-repetition', 'eat-that-frog',
  'smart-goals', 'parkinson', 'feynman', 'if-then-planning',
  'worked-examples', 'interleaving', 'blurting', 'mind-map', 'dual-coding',
  'cornell-notes', 'two-minute-rule', 'retrieval-practice'
];

export function evaluateStudyHabits(answers: AssessmentAnswers): EvaluationResult {
  const scores: Record<string, number> = {};
  const reasonsMap: Record<string, string[]> = {};

  const addScore = (method: string, points: number, reason: string) => {
    if (!scores[method]) {
      scores[method] = 0;
      reasonsMap[method] = [];
    }
    scores[method] += points;
    if (!reasonsMap[method].includes(reason)) {
      reasonsMap[method].push(reason);
    }
  };

  // 1. Problems (+3 points)
  const problemMappings: Record<CurrentProblem, { methods: string[], reason: string }> = {
    'procrastinate': { methods: ['eat-that-frog', 'if-then-planning', 'pomodoro', 'two-minute-rule'], reason: 'Giúp bạn vượt qua sức ỳ và bắt tay vào việc ngay lập tức.' },
    'distracted': { methods: ['pomodoro', 'parkinson'], reason: 'Tạo sức ép thời gian để bạn duy trì sự tập trung cao độ.' },
    'low-efficiency': { methods: ['pomodoro', 'active-recall'], reason: 'Ngăn ảo giác học tập và ép não bộ làm việc thực sự.' },
    'memory-issues': { methods: ['active-recall', 'spaced-repetition', 'blurting', 'retrieval-practice'], reason: 'Chuyển từ học vẹt thụ động sang truy xuất chủ động để nhớ lâu hơn.' },
    'practice-issues': { methods: ['worked-examples', 'interleaving', 'retrieval-practice'], reason: 'Xây dựng cầu nối giữa lý thuyết suông và kỹ năng giải quyết bài tập.' },
    'time-issues': { methods: ['smart-goals', 'parkinson', 'if-then-planning'], reason: 'Thiết lập mục tiêu rõ ràng và quản lý quỹ thời gian khoa học hơn.' },
    'give-up': { methods: ['smart-goals', 'if-then-planning'], reason: 'Biến mục tiêu xa vời thành những hành động nhỏ, dễ kiểm soát.' },
    'too-many-subjects': { methods: ['parkinson', 'smart-goals', 'eat-that-frog'], reason: 'Thiết lập thứ tự ưu tiên và giải quyết gọn gàng từng môn một.' },
    'comprehension-issues': { methods: ['feynman', 'mind-map', 'dual-coding'], reason: 'Đơn giản hóa và xâu chuỗi các mảng kiến thức phức tạp thành hệ thống.' },
    'note-taking-issues': { methods: ['mind-map', 'dual-coding', 'cornell-notes'], reason: 'Tổ chức lại dữ liệu học tập một cách trực quan, sinh động và dễ nhìn.' }
  };

  answers.problems.forEach(p => {
    const mapping = problemMappings[p];
    if (mapping) {
      mapping.methods.forEach(m => addScore(m, 3, mapping.reason));
    }
  });

  // 2. Goal (+2 points)
  const goalMappings: Record<ImprovementGoal, { methods: string[], reason: string }> = {
    'focus': { methods: ['pomodoro', 'parkinson', 'eat-that-frog', 'two-minute-rule'], reason: 'Rất phù hợp với mục tiêu tăng cường sự tập trung của bạn.' },
    'memory': { methods: ['active-recall', 'spaced-repetition', 'blurting', 'cornell-notes'], reason: 'Được thiết kế đặc biệt để cải thiện trí nhớ dài hạn.' },
    'deep-understanding': { methods: ['feynman', 'mind-map', 'dual-coding'], reason: 'Giúp bạn hiểu sâu bản chất vấn đề thay vì học vẹt.' },
    'exercises': { methods: ['worked-examples', 'interleaving'], reason: 'Tối ưu cho việc thực hành và rèn luyện kỹ năng giải bài tập.' },
    'deadline': { methods: ['parkinson', 'if-then-planning', 'eat-that-frog'], reason: 'Vũ khí sắc bén để tiêu diệt deadline đúng hạn.' },
    'exam-prep': { methods: ['spaced-repetition', 'active-recall', 'interleaving', 'blurting', 'retrieval-practice'], reason: 'Bộ công cụ tiêu chuẩn để bước vào kỳ thi với phong độ cao nhất.' }
  };

  if (answers.goal && goalMappings[answers.goal]) {
    const mapping = goalMappings[answers.goal];
    mapping.methods.forEach(m => addScore(m, 2, mapping.reason));
  }

  // 3. Content Type (+1 point)
  const contentMappings: Record<ContentType, string[]> = {
    'theory': ['active-recall', 'spaced-repetition', 'feynman', 'cornell-notes'],
    'logic': ['worked-examples', 'interleaving', 'mind-map', 'pomodoro'],
    'mixed': ['pomodoro', 'interleaving', 'dual-coding', 'two-minute-rule']
  };

  if (answers.content && contentMappings[answers.content]) {
    contentMappings[answers.content].forEach(m => addScore(m, 1, 'Tương thích tốt với loại tài liệu bạn thường xuyên học.'));
  }

  // 4. Time Available (+1 point)
  const timeMappings: Record<TimeAvailable, string[]> = {
    'under-30': ['pomodoro', 'parkinson', 'two-minute-rule'],
    '30-60': ['active-recall', 'eat-that-frog', 'retrieval-practice'],
    'over-60': ['spaced-repetition', 'blurting', 'feynman', 'mind-map']
  };

  if (answers.time && timeMappings[answers.time]) {
    timeMappings[answers.time].forEach(m => addScore(m, 1, 'Phù hợp với quỹ thời gian hạn hẹp/rộng rãi của bạn.'));
  }

  // Convert scores to array and sort
  const scoredMethods = Object.entries(scores).map(([id, score]) => ({ id, score }));
  
  scoredMethods.sort((a, b) => {
    if (b.score !== a.score) {
      return b.score - a.score; // Sort by score descending
    }
    // Tie-breaker
    const idxA = TIE_BREAKER_PRIORITY.indexOf(a.id);
    const idxB = TIE_BREAKER_PRIORITY.indexOf(b.id);
    return (idxA === -1 ? 99 : idxA) - (idxB === -1 ? 99 : idxB);
  });

  // Handle defaults if nothing selected
  if (scoredMethods.length === 0) {
    return {
      primaryMethodId: 'pomodoro',
      supportingMethodIds: ['active-recall'],
      allMethods: [
        {
          id: 'pomodoro',
          reasons: ['Đây là phương pháp cơ bản và dễ áp dụng nhất cho mọi tình huống.'],
          actionPlan: generateActionPlan('pomodoro', answers.time)
        },
        {
          id: 'active-recall',
          reasons: ['Giúp bạn nhớ lâu hơn.'],
          actionPlan: generateActionPlan('active-recall', answers.time)
        }
      ]
    };
  }

  const primaryMethod = scoredMethods[0];
  const primaryId = primaryMethod.id;
  
  // Get supporting methods (must have at least 3 points, max 2 methods)
  const supportingMethodIds = scoredMethods
    .slice(1, 3)
    .filter(m => m.score >= 3)
    .map(m => m.id);

  const selectedIds = [primaryId, ...supportingMethodIds];
  
  const allMethods: MethodResult[] = selectedIds.map(id => {
    const reasons = reasonsMap[id] || [];
    return {
      id,
      reasons: reasons.slice(0, 2), // Keep max 2 reasons per method
      actionPlan: generateActionPlan(id, answers.time)
    };
  });

  return {
    primaryMethodId: primaryId,
    supportingMethodIds,
    allMethods
  };
}

function generateActionPlan(method: string, time: TimeAvailable | null): string {
  const isShortTime = time === 'under-30';
  
  switch (method) {
    case 'pomodoro':
      return "1️⃣ Đặt đồng hồ 25 phút.\n2️⃣ Tập trung học, không dừng giữa chừng.\n3️⃣ Nghỉ 5 phút và lặp lại.";
    case 'parkinson':
      return "1️⃣ Ước lượng thời gian làm bài (VD: 60 phút).\n2️⃣ Cắt giảm 30% thời gian (còn 40 phút).\n3️⃣ Ép mình hoàn thành trong giới hạn đó.";
    case 'eat-that-frog':
      return "1️⃣ Chọn ra nhiệm vụ khó nhất trong ngày.\n2️⃣ Làm nó ngay đầu tiên vào buổi sáng.\n3️⃣ Tận hưởng cảm giác nhẹ nhõm cả ngày.";
    case 'smart-goals':
      return "1️⃣ Mục tiêu cụ thể: VD 'Học 50 từ vựng'.\n2️⃣ Rõ thời hạn: 'Xong trước 9h tối nay'.\n3️⃣ Đảm bảo mục tiêu đó vừa sức.";
    case 'if-then-planning':
      return "1️⃣ Lập câu điều kiện NẾU - THÌ.\n2️⃣ VD: NẾU ăn cơm xong ➡️ THÌ học bài luôn.\n3️⃣ Gắn việc học vào một thói quen cố định.";
    case 'spaced-repetition':
      return "1️⃣ Tạo flashcard những ý chính vừa học.\n2️⃣ Ôn lại vào ngày hôm sau.\n3️⃣ Ôn lại tiếp sau 3 ngày và 7 ngày.";
    case 'active-recall':
      return isShortTime
        ? "1️⃣ Đọc sách 15 phút rồi gấp lại.\n2️⃣ Tự viết ra giấy 3 ý quan trọng nhất.\n3️⃣ Mở sách dò lại và ghi chú chỗ sai."
        : "1️⃣ Đọc xong 1 chương thì gấp sách lại.\n2️⃣ Tự đặt câu hỏi và tự trả lời to lên.\n3️⃣ Chỗ nào ấp úng mới được mở sách xem.";
    case 'interleaving':
      return "1️⃣ Chọn bài tập của 2-3 chương khác nhau.\n2️⃣ Trộn chúng lại để làm xen kẽ.\n3️⃣ Luyện phản xạ nhận diện dạng bài.";
    case 'worked-examples':
      return "1️⃣ Đọc và phân tích kỹ 1 bài mẫu chuẩn.\n2️⃣ Hiểu logic tại sao có các bước đó.\n3️⃣ Đóng lại và tự giải 1 bài y chang.";
    case 'feynman':
      return "1️⃣ Chọn 1 khái niệm bạn thấy khó.\n2️⃣ Viết lại bằng ngôn ngữ cực kỳ bình dân.\n3️⃣ Nếu bị vấp chữ, bạn cần học lại phần đó.";
    case 'blurting':
      return "1️⃣ Đọc lướt qua tài liệu.\n2️⃣ Lấy nháp trắng, viết ra TẤT CẢ những gì nhớ được.\n3️⃣ Mở sách, dùng bút đỏ bổ sung ý còn thiếu.";
    case 'dual-coding':
      return "1️⃣ Ghi chú khái niệm bằng chữ ở bên trái.\n2️⃣ Tự vẽ 1 sơ đồ/icon minh họa ở bên phải.\n3️⃣ Nhìn hình để gợi nhớ chữ.";
    case 'mind-map':
      return "1️⃣ Viết tên bài học ở giữa giấy.\n2️⃣ Vẽ các nhánh tỏa ra cho từng ý chính.\n3️⃣ Chỉ dùng từ khóa ngắn gọn, không viết dài.";
    case 'cornell-notes':
      return "1️⃣ Cột phải: Ghi bài giảng (chỉ ý chính).\n2️⃣ Cột trái: Đặt câu hỏi ôn tập (ghi sau).\n3️⃣ Dưới cùng: Viết 1-2 câu tóm tắt toàn bài.";
    case 'two-minute-rule':
      return "1️⃣ Tìm 1 việc rất nhỏ (VD: Mở file Word).\n2️⃣ Bắt tay vào làm NGAY bước đó.\n3️⃣ Khi vượt qua bước đầu, bạn sẽ tự động làm tiếp.";
    case 'retrieval-practice':
      return isShortTime
        ? "1️⃣ Lấy đề thi năm ngoái ra giải.\n2️⃣ Đặt giờ 20 phút không mở tài liệu.\n3️⃣ Chấm điểm và học bù chỗ sai."
        : "1️⃣ Tải đề thi thật các năm trước.\n2️⃣ Canh giờ 90 phút và tự giải như thi thật.\n3️⃣ Câu nào sai chính là trọng tâm ôn tập.";
    default:
      return "1️⃣ Chọn một phần nội dung bạn đang cần học nhất.\n2️⃣ Chia nhỏ nó ra thành các đầu việc nhỏ.\n3️⃣ Bắt đầu hành động ngay lập tức trong 25 phút tiếp theo mà không suy nghĩ thêm.";
  }
}
