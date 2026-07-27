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
      return "1️⃣ Chọn DUY NHẤT một nhiệm vụ cần làm.\n2️⃣ Đặt đồng hồ 25 phút. Tắt WiFi điện thoại, cất ra xa.\n3️⃣ Học tập trung 100% đến khi chuông reo (không dừng giữa chừng).\n4️⃣ Đứng dậy nghỉ ngơi 5 phút (uống nước, vươn vai). Lặp lại vòng mới.";
    case 'parkinson':
      return "1️⃣ Khối lượng bài tập này bình thường làm mất bao lâu? (VD: 60 phút).\n2️⃣ Cắt bỏ 30% thời gian, tự ra hạn chót giả (Fake Deadline) là 40 phút.\n3️⃣ Đặt đồng hồ đếm ngược 40 phút và bắt đầu chạy đua với thời gian.\n(Áp lực đếm ngược sẽ triệt tiêu hoàn toàn sự xao nhãng của bạn).";
    case 'eat-that-frog':
      return "1️⃣ Trước khi đi ngủ, xác định '1 Con Ếch' (Bài tập khó nhất, ngán nhất).\n2️⃣ Sáng hôm sau thức dậy, khoan lướt điện thoại hay check tin nhắn.\n3️⃣ Ngồi vào bàn và 'ăn' con ếch đó ngay lập tức trong 1 giờ đầu tiên.\n4️⃣ Xong việc khó nhất, cả ngày còn lại tâm lý của bạn sẽ cực kỳ thư thái.";
    case 'smart-goals':
      return "Thay vì nói 'Tuần này sẽ học Tiếng Anh', hãy viết theo công thức:\n1️⃣ Cụ thể: Học thuộc 50 từ vựng chuyên ngành IT.\n2️⃣ Đo lường: Test đạt 45/50 từ trên Quizlet.\n3️⃣ Thời gian: Hoàn thành trước 9h tối thứ Bảy tuần này.\n👉 Viết mục tiêu này ra giấy và dán ngay trước mặt bàn học.";
    case 'if-then-planning':
      return "Lập trình sẵn hành động cho bộ não bằng cú pháp NẾU - THÌ:\n1️⃣ NẾU ăn tối xong lúc 19h ➡️ THÌ tôi sẽ ngồi ngay vào bàn mở sách Toán.\n2️⃣ NẾU đang học mà thèm cầm điện thoại ➡️ THÌ tôi sẽ uống 1 ngụm nước và hít thở sâu 3 lần.\n👉 Ghi chú 2 câu này dán lên màn hình máy tính.";
    case 'spaced-repetition':
      return "1️⃣ Tải ứng dụng Anki (trên điện thoại hoặc máy tính).\n2️⃣ Tạo các thẻ Flashcard cho kiến thức bạn vừa học hôm nay.\n3️⃣ Mỗi ngày chỉ cần mở app ra ôn tập 15 phút. App sẽ tự động tính toán để lặp lại thẻ nhớ vào đúng khoảnh khắc bạn sắp quên nó (1 ngày, 3 ngày, 7 ngày).";
    case 'active-recall':
      return isShortTime
        ? "1️⃣ Đọc tài liệu thật tập trung trong 15 phút.\n2️⃣ Gấp sách lại (tuyệt đối không được nhìn lén).\n3️⃣ Lấy giấy nháp, cố gắng nhớ và tự viết ra 3 ý quan trọng nhất.\n4️⃣ Mở sách ra dò lại, dùng bút đỏ đánh dấu vào những chỗ mình quên để học lại."
        : "1️⃣ Đọc xong một chương, khoan đọc qua chương mới.\n2️⃣ Gấp sách lại. Ghi ra lề vở các câu hỏi (VD: Tại sao A lại dẫn đến B?).\n3️⃣ Đóng vai giáo viên, tự trả lời to thành tiếng các câu hỏi đó.\n4️⃣ Chỗ nào ấp úng, lập tức mở tài liệu ra coi lại đúng chỗ đó.";
    case 'interleaving':
      return "1️⃣ Đừng bao giờ ngồi giải 10 bài toán cùng 1 dạng liên tiếp nhau.\n2️⃣ Hãy chia nhỏ: Làm 3 bài Đại số, chuyển sang 3 bài Hình học, rồi làm 3 bài Lý.\n3️⃣ Việc liên tục chuyển đổi môn học sẽ khiến não bộ phải 'khởi động' lại nhiều lần, từ đó giúp kiến thức bám sâu vào trí nhớ dài hạn hơn.";
    case 'worked-examples':
      return "1️⃣ Tìm một bài giải mẫu chuẩn xác (có giải thích từng bước).\n2️⃣ Khoan cắm đầu vào giải. Hãy đọc và phân tích kỹ: Tại sao bước 1 lại dẫn đến bước 2? Dấu hiệu nào để dùng công thức này?\n3️⃣ Khi đã hiểu logic gốc, đóng bài mẫu lại và tự giải một bài tương tự.";
    case 'feynman':
      return "1️⃣ Chọn một khái niệm rất khó mà bạn đang mơ hồ.\n2️⃣ Lấy giấy trắng, giả vờ bạn đang soạn bài để giảng lại cho một đứa trẻ lớp 5.\n3️⃣ Viết bằng ngôn từ đời thường nhất, tuyệt đối không dùng từ chuyên ngành.\n4️⃣ Nếu thấy bí hoặc viết rườm rà ➡️ Bạn chưa hiểu sâu, hãy mở sách học lại.";
    case 'blurting':
      return "1️⃣ Dành 15 phút đọc kỹ tài liệu.\n2️⃣ Gấp tài liệu lại, lấy một tờ giấy A4 trắng tinh.\n3️⃣ 'Đổ tràn' (Blurt) tất cả mọi thứ bạn nhớ trong đầu ra giấy (từ khóa, sơ đồ, hình vẽ) một cách nhanh nhất.\n4️⃣ Mở sách ra, dùng bút đỏ bổ sung những phần còn thiếu vào tờ giấy.";
    case 'dual-coding':
      return "1️⃣ Chia tờ giấy note làm 2 cột.\n2️⃣ Cột trái: Ghi chép các khái niệm bằng chữ (text).\n3️⃣ Cột phải: Ngay lập tức phác thảo một hình vẽ, biểu đồ hoặc icon vui nhộn mô tả cho khái niệm đó.\n(Sự kết hợp Hình + Chữ sẽ kích hoạt cả 2 bán cầu não cùng lúc).";
    case 'mind-map':
      return "1️⃣ Lấy một tờ giấy A4 nằm ngang. Viết tên Môn học / Chương vào chính giữa.\n2️⃣ Vẽ tối đa 4-5 nhánh lớn túa ra xung quanh cho các ý chính.\n3️⃣ Tuyệt đối chỉ dùng TỪ KHÓA ngắn gọn trên các nhánh, không viết cả câu dài.\n4️⃣ Dùng ít nhất 3 màu bút khác nhau để kích thích thị giác.";
    case 'cornell-notes':
      return '1️⃣ Kẻ trang giấy thành 3 phần: cột trái nhỏ (Câu hỏi), cột phải lớn (Ghi chú), phần cuối (Tóm tắt).\n2️⃣ Trong giờ học: chỉ viết vào cột PHẢI, ghi ý chính bằng từ khóa – không chép nguyên văn.\n3️⃣ Trong vòng 24h sau buổi học: điền cột TRÁI với các câu hỏi về nội dung vừa ghi.\n4️⃣ Viết phần tóm tắt cuối trang bằng ngôn ngữ của chính bạn (1-3 câu ngắn gọn).';
    case 'two-minute-rule':
      return '1️⃣ Nhìn vào task khó nhất bạn đang né tránh.\n2️⃣ Xác định "hành động đầu tiên" nhỏ nhất của nó (VD: Mở file, Gõ tiêu đề, Đọc 1 trang).\n3️⃣ Dùng timer bên dưới, đặt 2 phút và làm NGAY hành động đó.\n4️⃣ Khi chuông reo, não bạn đã "vào số" – hãy tiếp tục, bạn sẽ không muốn dừng lại nữa!';
    case 'retrieval-practice':
      return isShortTime
        ? '1️⃣ Lấy đề thi năm trước hoặc tự viết 5 câu hỏi về nội dung vừa học.\n2️⃣ Đặt giờ 20 phút, cố gắng trả lời không nhìn sách.\n3️⃣ Hết giờ, mở sách đối chiếu và ghi lại những chỗ còn sai.'
        : '1️⃣ Tìm đề thi năm trước của môn cần ôn.\n2️⃣ Đặt đồng hồ bằng đúng thời gian thi thật (90-120 phút).\n3️⃣ Làm bài KHÔNG MỞ SÁCH, KHÔNG TRA GOOGLE – chỗ nào không biết thì bỏ qua.\n4️⃣ Hết giờ: chấm điểm, ghi lại lỗi sai. Đó chính là danh sách ôn tập ưu tiên của bạn.';
    default:
      return "1️⃣ Chọn một phần nội dung bạn đang cần học nhất.\n2️⃣ Chia nhỏ nó ra thành các đầu việc nhỏ.\n3️⃣ Bắt đầu hành động ngay lập tức trong 25 phút tiếp theo mà không suy nghĩ thêm.";
  }
}
