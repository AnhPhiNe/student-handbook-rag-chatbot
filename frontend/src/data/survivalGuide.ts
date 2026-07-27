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
    description: 'Kỹ thuật Pomodoro giúp duy trì sự tập trung cao độ bằng cách chia nhỏ thời gian học thành các phiên (block) tập trung, xen kẽ với các khoảng nghỉ ngắn để não phục hồi.',
    howToApply: '👉 Bước 1: Chọn 1 nhiệm vụ duy nhất cần làm.\n👉 Bước 2: Hẹn giờ 25 phút và cất điện thoại sang phòng khác.\n👉 Bước 3: Chuông reo, bắt buộc đứng lên vươn vai đi lại đúng 5 phút rồi lặp lại.',
    hcmueExample: 'Ôn thi Tư tưởng Hồ Chí Minh: Đặt giờ 25 phút → cất điện thoại sang góc khác → đọc và gạch chân ý chính trong 1 mục. Chuông reo thì đứng dậy đi lại 5 phút rồi làm tiếp. 2 tiếng kiểu này hiệu quả hơn ngồi 5 tiếng vừa đọc vừa lướt điện thoại.'
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
    hcmueExample: 'Thầy giao bài tập lớn nộp Chủ Nhật → nhóm tự đặt deadline nội bộ là tối thứ Sáu → thứ Bảy chỉ đọc lại và sửa lỗi chính tả. Tránh được cảnh 11 giờ đêm Chủ Nhật cả nhóm vẫn đang gõ lạch cạch.'
  },
  {
    id: 'eat-that-frog',
    category: 'focus',
    title: 'Ăn con ếch',
    icon: Coffee,
    color: '#14B8A6',
    shortDesc: 'Hoàn thành nhiệm vụ quan trọng hoặc khó nhất trước.',
    description: 'Mark Twain từng nói: "Nếu việc của bạn là ăn một con ếch sống, hãy ăn nó vào buổi sáng". Hãy giải quyết nhiệm vụ khó khăn và quan trọng nhất (Con ếch) vào lúc bạn có nhiều năng lượng nhất.',
    howToApply: '👉 Bước 1: Từ tối hôm trước, khoanh tròn 1 việc khó/quan trọng nhất cần làm.\n👉 Bước 2: Sáng dậy, không check tin nhắn hay lướt web.\n👉 Bước 3: Ngồi vào bàn "xử lý" công việc đó đầu tiên.',
    hcmueExample: 'Tối hôm trước ghi ra: "Con ếch hôm nay là viết phần đặt vấn đề của tiểu luận". Sáng dậy không xem điện thoại → ngồi vào bàn làm ngay → xong rồi mới làm việc dễ hơn. Não tỉnh táo nhất vào buổi sáng, đừng lãng phí vào TikTok.'
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
    hcmueExample: 'Môn Tiếng Anh: Tôi sẽ học 10 từ vựng mỗi tối và làm 1 bài đọc hiểu → đạt 7.5 điểm cuối kỳ → bắt đầu từ hôm nay đến trước thi 1 tuần. Cụ thể, đo được, và có deadline rõ ràng.'
  },
  {
    id: 'if-then-planning',
    category: 'goals',
    title: 'Kế hoạch Nếu-Thì',
    icon: ListTodo,
    color: '#84CC16',
    shortDesc: 'Gắn hành động học với một thời điểm cụ thể.',
    description: 'SMART giúp xác định muốn đạt gì, còn If-Then giúp biến mục tiêu thành hành động thực tế. Các kế hoạch chỉ rõ khi nào, ở đâu và sẽ làm gì giúp giảm khoảng cách giữa ý định và hành động.',
    howToApply: '👉 Bước 1: Liệt kê các thói quen hoặc khung giờ cố định trong ngày (VD: ăn cơm tối xong).\n👉 Bước 2: Ráp công thức: "NẾU [Thói quen cũ], THÌ [Hành động học]".\n👉 Bước 3: Cài nhắc nhở lên điện thoại.',
    hcmueExample: '"Nếu ăn cơm tối xong và ngồi vào bàn, thì tôi mở ngay vở môn Tâm lý học và tự trả lời 5 câu hỏi ôn bài." – Không cần ý chí, chỉ cần gắn việc học vào thói quen ăn cơm có sẵn mỗi ngày.'
  },

  // --- MEMORY & LEARNING ---
  {
    id: 'spaced-repetition',
    category: 'memory',
    title: 'Lặp lại ngắt quãng',
    icon: CalendarDays,
    color: '#3B82F6',
    shortDesc: 'Ôn tập theo chu kỳ giãn cách.',
    description: 'Bộ não con người sẽ quên 70% kiến thức mới sau 24h. Phương pháp này phân bố việc học theo thời gian. Thay vì nhồi nhét trước lúc thi, hãy ôn tập lại vào các mốc thời gian tăng dần.',
    howToApply: '👉 Bước 1: Lên lịch ôn lại bài giảng sau: 1 ngày, 3 ngày, và 1 tuần.\n👉 Bước 2: Tải app Anki hoặc tạo file Excel để ghi chú các mốc ngày cần ôn.\n👉 Bước 3: Tới ngày hẹn, chỉ mở ra đọc lướt 15 phút là đủ.',
    hcmueExample: 'Học 20 từ vựng Tiếng Anh hôm nay → 3 ngày sau lấy ra test lại (che phần nghĩa, chỉ nhìn tiếng Anh đoán nghĩa) → 1 tuần sau test lần nữa. Lặp đúng lịch này, tới ngày thi nhớ như in mà không cần thức khuya nhồi bài.'
  },
  {
    id: 'active-recall',
    category: 'memory',
    title: 'Nhớ chủ động',
    icon: Brain,
    color: '#EC4899',
    shortDesc: 'Tự test bản thân bằng câu hỏi hoặc flashcard.',
    description: 'Đọc đi đọc lại bài giảng tạo ra ảo giác "mình đã thuộc". Active Recall ép bộ não tự "truy xuất" thông tin bằng cách liên tục tự đặt câu hỏi và tự trả lời.',
    howToApply: '👉 Bước 1: Khi đọc xong 1 chương tài liệu, hãy gấp sách lại.\n👉 Bước 2: Dùng bút viết ra giấy mọi câu hỏi liên quan đến nội dung vừa đọc.\n👉 Bước 3: Tự suy nghĩ câu trả lời mà không được mở sách xem.',
    hcmueExample: 'Ôn chương 2 môn Tâm lý học: Đọc xong 1 mục → gập vở lại → lấy tờ nháp tự viết ra các khái niệm nhớ được → mở vở kiểm tra, chỗ nào bỏ trống là chỗ cần đọc lại. Hiệu quả hơn đọc đi đọc lại 10 lần.'
  },
  {
    id: 'interleaving',
    category: 'memory',
    title: 'Luyện tập đan xen',
    icon: Shuffle,
    color: '#F97316',
    shortDesc: 'Xen kẽ nhiều dạng bài để nhận biết cách giải.',
    description: 'Khác với lặp lại ngắt quãng, interleaving là việc trộn lẫn các dạng kiến thức/bài tập liên quan trong cùng một buổi học để tăng khả năng phân biệt và vận dụng linh hoạt.',
    howToApply: '👉 Bước 1: Gom bài tập của 2-3 chương môn học lại.\n👉 Bước 2: Nhắm mắt bốc ngẫu nhiên từng bài ra làm.\n👉 Bước 3: Luyện phản xạ: "Nhìn cái đề này là biết phải dùng công thức của chương nào".',
    hcmueExample: 'Ôn thi môn Xác suất Thống kê: Không làm hết bài chương 1 rồi mới qua chương 2 → trộn lẫn bài của cả 2 chương trong cùng 1 buổi → luyện phản xạ nhận ra ngay dạng bài. Thi thật ra đề kiểu gì cũng không bị bỡ ngỡ.'
  },
  {
    id: 'worked-examples',
    category: 'memory',
    title: 'Học qua ví dụ mẫu',
    icon: FileCheck,
    color: '#06B6D4',
    shortDesc: 'Xem cách giải mẫu rồi tự hoàn thành từng bước.',
    description: 'Rất hợp với Toán, lập trình, xác suất và các môn kỹ thuật (nhất là khi mới học). Ví dụ mẫu giúp giảm tải trí nhớ làm việc trước khi người học tự giải bài.',
    howToApply: '👉 Bước 1: Chọn một bài tập mẫu thầy cô đã giải chuẩn.\n👉 Bước 2: Dùng bút dạ quang đánh dấu và giải thích tại sao từ dòng A lại ra được dòng B.\n👉 Bước 3: Đóng vở bài mẫu, mở giấy nháp và tự giải lại 1 bài y chang.',
    hcmueExample: 'Học code C++ môn Kỹ thuật lập trình: Đọc code mẫu của thầy -> Hiểu từng dòng `for`, `if` -> Đóng code thầy lại và tự gõ lại thuật toán.'
  },
  {
    id: 'feynman',
    category: 'memory',
    title: 'Kỹ thuật Feynman',
    icon: Lightbulb,
    color: '#8B5CF6',
    shortDesc: 'Tự giải thích kiến thức bằng ngôn ngữ đơn giản.',
    description: 'Cách tốt nhất để kiểm tra xem bạn đã thực sự hiểu bài hay chưa là cố gắng giải thích lại nó một cách đơn giản nhất cho người khác, không dùng từ ngữ học thuật chuyên sâu.',
    howToApply: '👉 Bước 1: Đọc và nắm một khái niệm khó.\n👉 Bước 2: Tưởng tượng bạn phải giải thích khái niệm đó cho học sinh lớp 8.\n👉 Bước 3: Nói to ra thành tiếng, nếu chỗ nào bạn ấp úng hoặc dùng từ quá hàn lâm thì mở sách ôn lại.',
    hcmueExample: 'Học xong khái niệm "Vùng phát triển gần" môn Tâm lý học → lôi bạn cùng phòng ra giải thích bằng 1 câu đơn giản, không dùng từ trong sách → chỗ nào giải thích bị lúng túng là chỗ mình chưa thực sự hiểu, cần đọc lại.'
  },
  {
    id: 'blurting',
    category: 'memory',
    title: 'Xả lũ kiến thức (Blurting)',
    icon: PenTool,
    color: '#D946EF',
    shortDesc: 'Viết ra mọi thứ nhớ được rồi đối chiếu và bổ sung.',
    description: 'Phương pháp kiểm tra trí nhớ mạnh mẽ: Đọc qua tài liệu, đóng lại, lấy giấy trắng và ép bản thân đổ bóng (viết/vẽ ra) MỌI THỨ có thể nhớ được về chủ đề đó.',
    howToApply: '👉 Bước 1: Đọc lướt qua tài liệu 1 lần để hình dung bức tranh tổng thể.\n👉 Bước 2: Đóng sách lại, lấy 1 tờ nháp và vẽ/viết ra bằng sạch tất cả các dàn ý.\n👉 Bước 3: Mở sách ra, dùng bút đỏ điền thêm những ý bị thiếu.',
    hcmueExample: 'Trước thi môn Giáo dục học: Đóng vở lại → lấy 1 tờ nháp và tự viết ra mọi thứ nhớ được về chương vừa ôn trong 10 phút → mở vở đối chiếu và tô đỏ những chỗ còn trống. Đó chính xác là danh sách cần đọc lại trước khi vào phòng thi.'
  },
  {
    id: 'dual-coding',
    category: 'memory',
    title: 'Mã hóa kép',
    icon: ImageIcon,
    color: '#6366F1',
    shortDesc: 'Kết hợp từ khóa với hình ảnh và sơ đồ.',
    description: 'Nghiên cứu về multimedia learning cho thấy người học có thể ghi nhớ hiệu quả từ sự kết hợp hợp lý giữa lời và hình (lưu ý hình ảnh phải hỗ trợ nội dung, không phải icon trang trí).',
    howToApply: '👉 Bước 1: Nhặt ra các từ khóa quan trọng trong đoạn văn dài chữ.\n👉 Bước 2: Mã hóa nó thành sơ đồ, mũi tên, hoặc hình vẽ minh họa ngay kế bên.\n👉 Bước 3: Học bằng cách nhìn hình và tự đọc lại đoạn chữ.',
    hcmueExample: 'Môn Sinh lý học: Thay vì đọc 3 trang chữ mô tả vòng tuần hoàn máu → tự vẽ sơ đồ mũi tên đơn giản: Tim → Cơ thể → Tim → Phổi → Tim. Nhìn 1 hình này là nhớ toàn bộ bài, không cần đọc lại đống chữ.'
  },
  {
    id: 'mind-map',
    category: 'memory',
    title: 'Sơ đồ tư duy',
    icon: Network,
    color: '#F43F5E',
    shortDesc: 'Tổ chức và kết nối các ý chính bằng sơ đồ.',
    description: 'Sơ đồ tư duy (Mind Map) dùng từ khóa, hình ảnh và nhánh để tổ chức kiến thức. Lưu ý đây là công cụ hỗ trợ tổ chức hệ thống thông tin, giúp nhìn thấy bức tranh tổng thể chứ không thần thánh hóa trí nhớ.',
    howToApply: '👉 Bước 1: Viết Tên chương môn học ở chính giữa giấy A4 (nằm ngang).\n👉 Bước 2: Vẽ các cành to tủa ra cho các mục I, II, III. Dùng 3 màu bút khác nhau.\n👉 Bước 3: Phân nhánh nhỏ hơn cho các ví dụ.',
    hcmueExample: 'Ôn thi môn Văn học: Viết tên tác phẩm vào giữa tờ A4 → vẽ 3 nhánh to: Hoàn cảnh ra đời, Nội dung chính, Nghệ thuật → điền chi tiết vào từng nhánh. Nhìn 1 tờ thấy ngay toàn bộ bài, không cần lật từng trang sách.'
  },

  // --- NEW METHODS ---
  {
    id: 'cornell-notes',
    category: 'memory',
    title: 'Ghi chép Cornell',
    icon: Columns2,
    color: '#0EA5E9',
    shortDesc: 'Chia trang vở thành 3 vùng: Ghi chú, Câu hỏi và Tóm tắt.',
    description: 'Hệ thống ghi chép Cornell chia trang giấy thành 3 vùng rõ ràng: cột phải (rộng) để ghi chú trong lúc nghe giảng, cột trái (hẹp) để viết từ khóa và câu hỏi sau buổi học, và phần dưới để tóm tắt bằng ngôn ngữ của chính mình. Đây là cách ghi chép chủ động thay vì chép từng chữ thụ động.',
    howToApply: '👉 Bước 1: Kẻ trang vở thành 3 phần: cột trái nhỏ (Câu hỏi/Từ khóa), cột phải lớn (Ghi chú), phần cuối trang (Tóm tắt).\n👉 Bước 2: Trong giờ học, chỉ ghi chú vào cột PHẢI – ghi ý chính, không chép nguyên văn.\n👉 Bước 3: Sau buổi học (trong vòng 24h), điền cột TRÁI: đặt câu hỏi về nội dung vừa ghi.\n👉 Bước 4: Viết phần TÓM TẮT cuối trang bằng ngôn ngữ của chính bạn (1-3 câu).',
    hcmueExample: 'Giờ Tâm lý học: Cột phải ghi "Nhu cầu Maslow – 5 tầng từ thấp đến cao". Tối về, cột trái đặt câu hỏi "Tầng nào là cao nhất? Cho ví dụ?". Cuối trang tóm 1 câu: "Người ta chỉ học tốt khi đã no, an toàn và được tôn trọng".'
  },
  {
    id: 'two-minute-rule',
    category: 'focus',
    title: 'Quy tắc 2 phút',
    icon: AlarmClock,
    color: '#F59E0B',
    shortDesc: 'Nếu việc mất dưới 2 phút để bắt đầu, hãy làm ngay bây giờ.',
    description: 'Quy tắc 2 phút của David Allen (từ hệ thống GTD – Getting Things Done) giải quyết một trong những nguyên nhân sâu xa nhất của sự trì hoãn: Chúng ta không sợ bản thân công việc, mà sợ cái cảm giác "bắt đầu". Nếu hành động đầu tiên của một nhiệm vụ mất dưới 2 phút, không có lý do gì để không làm ngay.',
    howToApply: '👉 Bước 1: Nhìn vào danh sách task hôm nay.\n👉 Bước 2: Tìm bất kỳ task nào mà "bước đầu tiên" của nó mất dưới 2 phút (VD: Mở file Word, Gõ dòng tiêu đề, Đọc 1 trang đầu).\n👉 Bước 3: Làm NGAY bước đó, không suy nghĩ thêm. Não sẽ tự động muốn tiếp tục khi đã bắt đầu (Hiệu ứng Zeigarnik).\n👉 Bước 4: Dùng timer bên dưới để thử ngay bây giờ!',
    hcmueExample: 'Đang sợ viết báo cáo thực tập dài 30 trang? Bước 2 phút đầu tiên: Mở Word, gõ tiêu đề và tên mình vào. Xong. Bạn sẽ thấy mình không thể dừng lại ở đó.'
  },
  {
    id: 'retrieval-practice',
    category: 'memory',
    title: 'Luyện đề có giờ',
    icon: ClipboardList,
    color: '#DC2626',
    shortDesc: 'Làm đề thi thử trong điều kiện thi thật để rèn phản xạ.',
    description: 'Retrieval Practice (Luyện tập truy xuất) khác với Active Recall ở chỗ: thay vì tự đặt câu hỏi từ tài liệu, bạn làm toàn bộ một đề thi thật hoặc đề cương trong điều kiện mô phỏng phòng thi – có giờ đếm ngược, không được mở sách. Đây là phương pháp hiệu quả nhất để chuẩn bị cho kỳ thi theo nghiên cứu khoa học nhận thức.',
    howToApply: '👉 Bước 1: Tìm đề thi năm trước của môn cần ôn (hỏi thầy cô hoặc nhóm lớp).\n👉 Bước 2: Đặt đồng hồ đúng bằng thời gian thi thật (90 phút hoặc 120 phút).\n👉 Bước 3: Làm bài KHÔNG MỞ SÁCH, KHÔNG TRA GOOGLE. Chỗ nào không biết thì bỏ qua.\n👉 Bước 4: Hết giờ, mở sách chấm điểm và ghi lại những lỗi sai – đó chính là "điểm yếu" cần ôn lại trước ngày thi.',
    hcmueExample: '2 tuần trước thi môn Đường lối Cách mạng: In đề thi năm ngoái → đặt giờ 90 phút và làm bài không mở sách → xong thì chấm điểm và gạch chân câu sai. Chỉ 3 lần luyện thế này là biết ngay phần nào mình còn yếu cần ôn thêm.'
  }
];

