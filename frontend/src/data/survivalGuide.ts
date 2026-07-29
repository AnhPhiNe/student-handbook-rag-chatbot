import { 
  Clock, Zap, Target, CalendarDays, Lightbulb, Brain, 
  Coffee, PenTool, Network, Shuffle, FileCheck, ListTodo, ImageIcon,
  Columns2, AlarmClock, ClipboardList
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export type TipCategory = 'memory' | 'focus' | 'goals';

export interface StudyTip {
  id: string;
  category: TipCategory;
  title: string;
  icon: LucideIcon;
  color: string;
  shortDesc: string;
  description: string;
  howToApply: string;
  hcmueExample: string;
}

export const survivalGuideTips: StudyTip[] = [
  // --- FOCUS & TIME MANAGEMENT ---
  {
    id: 'pomodoro',
    category: 'focus',
    title: 'Pomodoro',
    icon: Clock,
    color: '#EF4444',
    shortDesc: 'Học theo phiên tập trung, xen kẽ thời gian nghỉ.',
    description: 'Chia thời gian học thành các đợt ngắn (thường là 25 phút), xen kẽ với 5 phút nghỉ giải lao để não bộ không bị quá tải.',
    howToApply: '👉 Bước 1: Chọn 1 nhiệm vụ duy nhất cần làm.\n👉 Bước 2: Hẹn giờ 25 phút và cất điện thoại sang phòng khác.\n👉 Bước 3: Chuông reo, bắt buộc đứng lên vươn vai đi lại đúng 5 phút rồi lặp lại.',
    hcmueExample: 'Học Triết: Cài giờ 25 phút đọc sách, cất điện thoại đi. Hết 25 phút, đứng lên đi uống nước 5 phút. Sau đó quay lại làm tiếp.'
  },
  {
    id: 'parkinson',
    category: 'focus',
    title: 'Định luật Parkinson',
    icon: Zap,
    color: '#EAB308',
    shortDesc: 'Đặt giới hạn thời gian hợp lý để tránh kéo dài công việc.',
    description: 'Công việc sẽ tự động giãn nở ra chiếm trọn thời gian bạn dành cho nó. Nếu bạn cho mình 1 tuần để làm tiểu luận, bạn sẽ mất 1 tuần. Nếu cho 2 ngày, bạn sẽ làm xong trong 2 ngày.',
    howToApply: '👉 Bước 1: Xem deadline thật của môn học.\n👉 Bước 2: Trừ lùi đi 20-30% thời gian (ví dụ tuần sau nộp thì chốt hạn nộp giả vào thứ 6).\n👉 Bước 3: Ghi hạn chót giả này vào lịch và cam kết làm như deadline thật.',
    hcmueExample: 'Làm tiểu luận nhóm: Thầy cho 1 tháng nộp, nhưng cả nhóm thống nhất "phải xong trong 2 tuần". Thế là 2 tuần sau xong thật, không bị dồn việc đến sát hạn chót.'
  },
  {
    id: 'eat-that-frog',
    category: 'focus',
    title: 'Ăn con ếch',
    icon: Coffee,
    color: '#14B8A6',
    shortDesc: 'Hoàn thành nhiệm vụ quan trọng hoặc khó nhất trước.',
    description: 'Hãy làm việc khó nhất và quan trọng nhất vào đầu ngày, lúc bạn còn nhiều năng lượng nhất. Làm xong việc này, cả ngày còn lại sẽ rất nhẹ nhàng.',
    howToApply: '👉 Bước 1: Từ tối hôm trước, khoanh tròn 1 việc khó/quan trọng nhất cần làm.\n👉 Bước 2: Sáng dậy, không check tin nhắn hay lướt web.\n👉 Bước 3: Ngồi vào bàn "xử lý" công việc đó đầu tiên.',
    hcmueExample: 'Môn Toán rất khó. Thay vì để đến tối muộn mệt mỏi mới làm bài tập Toán, hãy làm nó ngay vào buổi sáng lúc vừa ngủ dậy.'
  },

  // --- GOALS & ACTION ---
  {
    id: 'smart-goals',
    category: 'goals',
    title: 'Mục tiêu SMART',
    icon: Target,
    color: '#10B981',
    shortDesc: 'Cụ thể – Đo lường được – Khả thi – Liên quan – Có thời hạn.',
    description: 'Đừng đặt mục tiêu chung chung kiểu "Học kì này mình sẽ chăm hơn". SMART giúp chuyển từ "tôi muốn học tốt" sang những mục tiêu rõ ràng và có thể hành động được.',
    howToApply: '👉 Bước 1: Viết số liệu đo lường cụ thể (VD: được 8.0, dịch được 10 trang).\n👉 Bước 2: Viết rõ mốc thời gian hoàn thành.\n👉 Bước 3: Đảm bảo mục tiêu đó phù hợp với năng lực hiện tại của bạn.',
    hcmueExample: 'Thay vì nói chung chung "Mình sẽ học giỏi Tiếng Anh", hãy nói "Mỗi tối lúc 8 giờ, mình sẽ học thuộc 10 từ vựng mới".'
  },
  {
    id: 'if-then-planning',
    category: 'goals',
    title: 'Kế hoạch Nếu-Thì',
    icon: ListTodo,
    color: '#84CC16',
    shortDesc: 'Gắn hành động học với một thời điểm cụ thể.',
    description: 'Biến mục tiêu thành hành động bằng cách gắn việc học vào một thói quen có sẵn. Công thức rất đơn giản: NẾU [điều kiện xảy ra], THÌ [tôi sẽ làm việc này].',
    howToApply: '👉 Bước 1: Liệt kê các thói quen hoặc khung giờ cố định trong ngày (VD: ăn cơm tối xong).\n👉 Bước 2: Ráp công thức: "NẾU [Thói quen cũ], THÌ [Hành động học]".\n👉 Bước 3: Cài nhắc nhở lên điện thoại.',
    hcmueExample: '"Nếu ăn cơm tối xong, mình sẽ ngồi vào bàn làm bài tập ngay lập tức". Cứ lặp lại như vậy để tạo thành thói quen.'
  },

  // --- MEMORY & LEARNING ---
  {
    id: 'spaced-repetition',
    category: 'memory',
    title: 'Lặp lại ngắt quãng',
    icon: CalendarDays,
    color: '#3B82F6',
    shortDesc: 'Ôn tập theo chu kỳ giãn cách.',
    description: 'Thay vì nhồi nhét học một lần rồi quên, hãy chia nhỏ ra và ôn lại nhiều lần với khoảng cách thời gian ngày càng xa nhau (ví dụ: sau 1 ngày, 3 ngày, 1 tuần).',
    howToApply: '👉 Bước 1: Lên lịch ôn lại bài giảng sau: 1 ngày, 3 ngày, và 1 tuần.\n👉 Bước 2: Tải app Anki hoặc tạo file Excel để ghi chú các mốc ngày cần ôn.\n👉 Bước 3: Tới ngày hẹn, chỉ mở ra đọc lướt 15 phút là đủ.',
    hcmueExample: 'Học từ vựng: Hôm nay học 20 từ. Ngày mai đem ra kiểm tra lại. 3 ngày sau lại kiểm tra. 1 tuần sau kiểm tra lại. Bạn sẽ nhớ rất dai.'
  },
  {
    id: 'active-recall',
    category: 'memory',
    title: 'Nhớ chủ động',
    icon: Brain,
    color: '#EC4899',
    shortDesc: 'Tự test bản thân bằng câu hỏi hoặc flashcard.',
    description: 'Thay vì cứ đọc đi đọc lại bài giảng, hãy tự đặt câu hỏi và tự cố gắng nhớ lại câu trả lời. Việc ép não phải suy nghĩ sẽ giúp bạn nhớ bài lâu hơn rất nhiều.',
    howToApply: '👉 Bước 1: Khi đọc xong 1 chương tài liệu, hãy gấp sách lại.\n👉 Bước 2: Dùng bút viết ra giấy mọi câu hỏi liên quan đến nội dung vừa đọc.\n👉 Bước 3: Tự suy nghĩ câu trả lời mà không được mở sách xem.',
    hcmueExample: 'Học môn Lịch sử Đảng: Đọc xong 1 trang sách, hãy gập sách lại và tự nhẩm lại xem trang đó viết về cái gì.'
  },
  {
    id: 'interleaving',
    category: 'memory',
    title: 'Luyện tập đan xen',
    icon: Shuffle,
    color: '#F97316',
    shortDesc: 'Xen kẽ nhiều dạng bài để nhận biết cách giải.',
    description: 'Đừng chỉ làm mãi một dạng bài tập. Hãy trộn lẫn nhiều bài của các chương khác nhau để học cách nhận diện dạng bài và luyện phản xạ nhanh nhạy.',
    howToApply: '👉 Bước 1: Gom bài tập của 2-3 chương môn học lại.\n👉 Bước 2: Nhắm mắt bốc ngẫu nhiên từng bài ra làm.\n👉 Bước 3: Luyện phản xạ: "Nhìn cái đề này là biết phải dùng công thức của chương nào".',
    hcmueExample: 'Giải bài tập Giải tích: Đừng làm 10 bài đạo hàm liên tục. Hãy làm 1 bài đạo hàm, 1 bài tích phân, 1 bài giới hạn đan xen nhau.'
  },
  {
    id: 'worked-examples',
    category: 'memory',
    title: 'Học qua ví dụ mẫu',
    icon: FileCheck,
    color: '#06B6D4',
    shortDesc: 'Xem cách giải mẫu rồi tự hoàn thành từng bước.',
    description: 'Thay vì tự mày mò giải bài tập khó ngay từ đầu, hãy xem kỹ cách người khác (hoặc thầy cô) giải bài mẫu từng bước, sau đó đóng lại và tự làm y chang.',
    howToApply: '👉 Bước 1: Chọn một bài tập mẫu thầy cô đã giải chuẩn.\n👉 Bước 2: Dùng bút dạ quang đánh dấu và giải thích tại sao từ dòng A lại ra được dòng B.\n👉 Bước 3: Đóng vở bài mẫu, mở giấy nháp và tự giải lại 1 bài y chang.',
    hcmueExample: 'Học code C++: Đọc code mẫu của thầy -> Hiểu từng dòng -> Đóng màn hình lại và tự gõ lại y chang thuật toán đó.'
  },
  {
    id: 'feynman',
    category: 'memory',
    title: 'Kỹ thuật Feynman',
    icon: Lightbulb,
    color: '#8B5CF6',
    shortDesc: 'Tự giải thích kiến thức bằng ngôn ngữ đơn giản.',
    description: 'Cách tốt nhất để kiểm tra bạn đã hiểu bài chưa là thử giải thích lại nó cho một người không biết gì (hoặc học sinh cấp 2) bằng ngôn ngữ bình dân nhất có thể.',
    howToApply: '👉 Bước 1: Đọc và nắm một khái niệm khó.\n👉 Bước 2: Tưởng tượng bạn phải giải thích khái niệm đó cho học sinh lớp 8.\n👉 Bước 3: Nói to ra thành tiếng, nếu chỗ nào bạn ấp úng hoặc dùng từ quá hàn lâm thì mở sách ôn lại.',
    hcmueExample: 'Học môn Tâm lý: Học xong 1 bài, rủ đứa bạn cùng phòng ra và kể lại bài đó cho nó nghe bằng ngôn ngữ bình dân như đang kể chuyện.'
  },
  {
    id: 'blurting',
    category: 'memory',
    title: 'Xả lũ kiến thức (Blurting)',
    icon: PenTool,
    color: '#D946EF',
    shortDesc: 'Viết ra mọi thứ nhớ được rồi đối chiếu và bổ sung.',
    description: 'Đọc bài một lượt, sau đó đóng sách lại, lấy một tờ giấy trắng và viết ra TẤT CẢ những gì bạn có thể nhớ được. Xong rồi mới mở sách ra để xem mình quên gì.',
    howToApply: '👉 Bước 1: Đọc lướt qua tài liệu 1 lần để hình dung bức tranh tổng thể.\n👉 Bước 2: Đóng sách lại, lấy 1 tờ nháp và vẽ/viết ra bằng sạch tất cả các dàn ý.\n👉 Bước 3: Mở sách ra, dùng bút đỏ điền thêm những ý bị thiếu.',
    hcmueExample: 'Ôn thi cuối kỳ: Lấy một tờ giấy trắng, nhớ lại và viết ra bằng sạch tất cả những gì bạn còn nhớ về bài học đó.'
  },
  {
    id: 'dual-coding',
    category: 'memory',
    title: 'Mã hóa kép',
    icon: ImageIcon,
    color: '#6366F1',
    shortDesc: 'Kết hợp từ khóa với hình ảnh và sơ đồ.',
    description: 'Kết hợp từ ngữ với hình ảnh, sơ đồ hoặc biểu đồ. Hình ảnh sẽ giúp não bộ hình dung và ghi nhớ thông tin chữ viết tốt hơn rất nhiều.',
    howToApply: '👉 Bước 1: Nhặt ra các từ khóa quan trọng trong đoạn văn dài chữ.\n👉 Bước 2: Mã hóa nó thành sơ đồ, mũi tên, hoặc hình vẽ minh họa ngay kế bên.\n👉 Bước 3: Học bằng cách nhìn hình và tự đọc lại đoạn chữ.',
    hcmueExample: 'Học Giải phẫu: Thay vì học thuộc lòng chữ, hãy vẽ một cái hình đơn giản ra giấy và ghi chú lên hình để dễ hình dung.'
  },
  {
    id: 'mind-map',
    category: 'memory',
    title: 'Sơ đồ tư duy',
    icon: Network,
    color: '#F43F5E',
    shortDesc: 'Tổ chức và kết nối các ý chính bằng sơ đồ.',
    description: 'Dùng từ khóa và các nhánh cây để vẽ lại toàn bộ bài học. Cách này giúp bạn nhìn thấy bức tranh tổng thể của môn học mà không bị ngợp bởi một đống chữ.',
    howToApply: '👉 Bước 1: Viết Tên chương môn học ở chính giữa giấy A4 (nằm ngang).\n👉 Bước 2: Vẽ các cành to tủa ra cho các mục I, II, III. Dùng 3 màu bút khác nhau.\n👉 Bước 3: Phân nhánh nhỏ hơn cho các ví dụ.',
    hcmueExample: 'Tóm tắt bài học: Viết tên bài ở giữa giấy. Vẽ các cành cây tủa ra xung quanh như: tác giả, nội dung chính, ý nghĩa.'
  },

  // --- NEW METHODS ---
  {
    id: 'cornell-notes',
    category: 'memory',
    title: 'Ghi chép Cornell',
    icon: Columns2,
    color: '#0EA5E9',
    shortDesc: 'Chia trang vở thành 3 vùng: Ghi chú, Câu hỏi và Tóm tắt.',
    description: 'Chia trang vở làm 3 phần: cột phải to để ghi bài giảng, cột trái nhỏ để ghi câu hỏi ôn tập, và phần dưới cùng để viết tóm tắt. Đây là cách ghi chép khoa học và dễ ôn bài nhất.',
    howToApply: '👉 Bước 1: Kẻ trang vở thành 3 phần: cột trái nhỏ (Câu hỏi/Từ khóa), cột phải lớn (Ghi chú), phần cuối trang (Tóm tắt).\n👉 Bước 2: Trong giờ học, chỉ ghi chú vào cột PHẢI – ghi ý chính, không chép nguyên văn.\n👉 Bước 3: Sau buổi học (trong vòng 24h), điền cột TRÁI: đặt câu hỏi về nội dung vừa ghi.\n👉 Bước 4: Viết phần TÓM TẮT cuối trang bằng ngôn ngữ của chính bạn (1-3 câu).',
    hcmueExample: 'Khi nghe giảng trên lớp: Bên phải vở ghi bài thầy đọc. Bên trái ghi các câu hỏi quan trọng. Dưới cùng chừa 2 dòng ghi tóm tắt bài.'
  },
  {
    id: 'two-minute-rule',
    category: 'focus',
    title: 'Quy tắc 2 phút',
    icon: AlarmClock,
    color: '#F59E0B',
    shortDesc: 'Nếu việc mất dưới 2 phút để bắt đầu, hãy làm ngay bây giờ.',
    description: 'Chúng ta hay lười vì sợ phải "bắt đầu" một việc gì đó khó khăn. Quy tắc này rất dễ: Hãy chia nhỏ việc ra, và nếu bước đầu tiên có thể làm xong trong dưới 2 phút, hãy làm NGAY BÂY GIỜ.',
    howToApply: '👉 Bước 1: Nhìn vào danh sách task hôm nay.\n👉 Bước 2: Tìm bất kỳ task nào mà "bước đầu tiên" của nó mất dưới 2 phút (VD: Mở file Word, Gõ dòng tiêu đề, Đọc 1 trang đầu).\n👉 Bước 3: Làm NGAY bước đó, không suy nghĩ thêm. Não sẽ tự động muốn làm tiếp khi bạn đã vượt qua được sự lười biếng ban đầu.\n👉 Bước 4: Dùng timer bên dưới để thử ngay bây giờ!',
    hcmueExample: 'Lười mở laptop ra làm bài? Hãy tự nhủ "Mình chỉ bật máy lên và gõ cái tên của mình vào file Word thôi". Khi đã mở lên, bạn sẽ tự động muốn làm tiếp.'
  },
  {
    id: 'retrieval-practice',
    category: 'memory',
    title: 'Luyện đề có giờ',
    icon: ClipboardList,
    color: '#DC2626',
    shortDesc: 'Làm đề thi thử trong điều kiện thi thật để rèn phản xạ.',
    description: 'Thay vì chỉ đọc sách, hãy lấy một đề thi năm ngoái ra làm thử như đang thi thật: có bấm giờ và không mở tài liệu. Đây là cách thực tế nhất để biết bạn đã sẵn sàng đi thi hay chưa.',
    howToApply: '👉 Bước 1: Tìm đề thi năm trước của môn cần ôn (hỏi thầy cô hoặc nhóm lớp).\n👉 Bước 2: Đặt đồng hồ đúng bằng thời gian thi thật (90 phút hoặc 120 phút).\n👉 Bước 3: Làm bài KHÔNG MỞ SÁCH, KHÔNG TRA GOOGLE. Chỗ nào không biết thì bỏ qua.\n👉 Bước 4: Hết giờ, mở sách chấm điểm và ghi lại những lỗi sai – đó chính là "điểm yếu" cần ôn lại trước ngày thi.',
    hcmueExample: 'Trước kỳ thi: Lên mạng tải đề thi năm ngoái về. Canh đồng hồ đúng 90 phút và tự giải y như đang ngồi trong phòng thi thật.'
  }
];

