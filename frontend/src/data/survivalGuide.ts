import { 
  Clock, Zap, Target, CalendarDays, Lightbulb, Brain, 
  Coffee, PenTool, Network, Shuffle, FileCheck, ListTodo, ImageIcon,
  Columns2, AlarmClock, ClipboardList, BookOpen, Layers
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
    howToApply: '👉 Bước 1: Viết tên 1 bài tập duy nhất lên giấy nháp.\n👉 Bước 2: Lấy điện thoại ra, mở app Báo thức và đặt hẹn giờ 25 phút, sau đó cất vào ngăn kéo.\n👉 Bước 3: Khi chuông reo, lập tức đứng dậy khỏi ghế, vươn vai đi lấy ly nước đúng 5 phút rồi quay lại.',
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
    howToApply: '👉 Bước 1: Mở group chat môn học xem ngày giờ nộp bài chính thức.\n👉 Bước 2: Dùng bút đỏ khoanh tròn một ngày trên lịch bàn sớm hơn deadline thật 2-3 ngày.\n👉 Bước 3: Bấm điện thoại cài báo thức nộp bài vào đúng ngày giả định đó.',
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
    howToApply: '👉 Bước 1: Lấy sổ tay, dùng bút đỏ viết to tên 1 bài tập khó nhất trang đầu tiên.\n👉 Bước 2: Sáng ngủ dậy, tắt ngay wifi điện thoại trước khi bước xuống giường.\n👉 Bước 3: Lấy đúng cuốn sách đó ra bàn, mở bút và giải ngay bài tập đó.',
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
    howToApply: '👉 Bước 1: Mở file Excel, gõ con số điểm hoặc số trang chính xác bạn muốn đạt được.\n👉 Bước 2: Gõ thêm cột ngày giờ hoàn thành (ví dụ: 20:00 ngày 15/10).\n👉 Bước 3: In tờ Excel đó ra dán lên tường trước mặt bàn học.',
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
    howToApply: '👉 Bước 1: Lấy điện thoại mở app Ghi chú, gõ tên một việc bạn làm mỗi ngày (VD: đánh răng xong).\n👉 Bước 2: Gõ tiếp hành động học ngay sau đó (VD: ngồi vào bàn mở laptop).\n👉 Bước 3: Cài màn hình khóa điện thoại với dòng chữ: NẾU đánh răng xong, THÌ mở laptop.',
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
    howToApply: '👉 Bước 1: Lấy điện thoại, tải và mở app Anki hoặc Quizlet.\n👉 Bước 2: Gõ các khái niệm vừa học vào làm thẻ flashcard ngay lập tức.\n👉 Bước 3: Mỗi sáng thức dậy, mở app bấm lướt đúng 15 phút thẻ nào hiện lên thì ôn.',
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
    howToApply: '👉 Bước 1: Dùng tay gập hẳn cuốn sách giáo trình lại và cất vào ngăn kéo.\n👉 Bước 2: Lấy bút bi và một tờ giấy A4 trắng tinh, tự viết ra 5 câu hỏi về bài vừa đọc.\n👉 Bước 3: Cầm bút viết câu trả lời ra giấy, tuyệt đối không mở ngăn kéo lấy sách.',
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
    howToApply: '👉 Bước 1: Lấy kéo cắt 10 bài tập ở 3 chương khác nhau thành từng mảnh giấy nhỏ.\n👉 Bước 2: Bỏ tất cả mảnh giấy vào 1 cái hộp, xóc đều lên.\n👉 Bước 3: Thò tay bốc 1 tờ, trải lên bàn và dùng bút giải ngay bài đó.',
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
    howToApply: '👉 Bước 1: Mở vở bài tập, tìm bài mẫu thầy đã giải trên bảng.\n👉 Bước 2: Cầm bút highlight tô màu xanh vào dòng công thức, màu vàng vào dòng thế số.\n👉 Bước 3: Gập vở lại, lấy tờ nháp trắng và cầm bút viết lại từ đầu đến cuối y hệt bài mẫu.',
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
    howToApply: '👉 Bước 1: Lấy bút viết tên khái niệm khó nhất lên bảng trắng hoặc giấy nháp.\n👉 Bước 2: Bật ghi âm trên điện thoại lên, cầm điện thoại như micro.\n👉 Bước 3: Mở miệng nói to thành tiếng giải thích khái niệm đó như đang kể chuyện cho con nít nghe.',
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
    howToApply: '👉 Bước 1: Lướt mắt đọc tài liệu 5 phút rồi ném sách ra xa khỏi tầm tay.\n👉 Bước 2: Lấy 1 tờ giấy A4 và cây bút mực xanh, viết điên cuồng mọi chữ nảy ra trong đầu.\n👉 Bước 3: Lấy sách lại, cầm cây bút màu đỏ chót gạch chân và điền thêm các chữ bị thiếu vào tờ A4.',
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
    howToApply: '👉 Bước 1: Cầm bút highlight tô màu vàng các từ khóa trong đoạn văn.\n👉 Bước 2: Lấy bút chì vẽ 1 hình que (stickman) hoặc biểu tượng đơn giản bên lề giấy ứng với từ đó.\n👉 Bước 3: Lấy tay che phần chữ lại, chỉ nhìn hình vẽ và đọc to từ khóa lên.',
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
    howToApply: '👉 Bước 1: Xoay ngang tờ A4 trắng, cầm bút dạ viết thật to tên bài học vào ngay tâm giấy.\n👉 Bước 2: Đổi 3 cây bút 3 màu khác nhau, vẽ 3 nét cong tủa ra làm 3 nhánh chính.\n👉 Bước 3: Tại mỗi nhánh, viết 1 từ khóa duy nhất lên trên đường cong vừa vẽ.',
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
    howToApply: '👉 Bước 1: Dùng thước kẻ 1 đường dọc cách lề trái 5cm, kẻ 1 đường ngang cách đáy 5cm trên trang vở.\n👉 Bước 2: Cầm bút viết các ý thầy đọc vào khoảng trống to nhất bên phải.\n👉 Bước 3: Viết 2-3 câu hỏi ôn tập vào cột hẹp bên trái.\n👉 Bước 4: Viết 2 dòng tóm tắt vào ô chữ nhật dưới cùng trang.',
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
    howToApply: '👉 Bước 1: Mở danh sách bài tập ra, chỉ tay vào dòng đầu tiên.\n👉 Bước 2: Mở laptop lên, tạo 1 file Word trắng và gõ đúng cái Tựa bài vào đó.\n👉 Bước 3: Lưu file lại. Nếu muốn nghỉ thì tắt máy nghỉ, nếu tay đang tiện trên bàn phím thì gõ dòng tiếp theo.\n👉 Bước 4: Dùng timer bên dưới bấm chạy 2 phút để thử ngay!',
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
    howToApply: '👉 Bước 1: In 1 đề thi năm ngoái ra giấy, cầm bút và máy tính lên bàn.\n👉 Bước 2: Bấm đồng hồ đếm ngược 90 phút và cất hết giáo trình vào balo.\n👉 Bước 3: Cầm bút giải đề trực tiếp lên giấy. Không tra điện thoại.\n👉 Bước 4: Hết giờ đồng hồ kêu, buông bút xuống, lấy bút đỏ lôi sách ra chấm điểm ngay lập tức.',
    hcmueExample: 'Trước kỳ thi: Lên mạng tải đề thi năm ngoái về. Canh đồng hồ đúng 90 phút và tự giải y như đang ngồi trong phòng thi thật.'
  },
  {
    id: 'eisenhower-matrix',
    category: 'focus',
    title: 'Ma trận Eisenhower',
    icon: Layers,
    color: '#F43F5E',
    shortDesc: 'Giúp sắp xếp độ ưu tiên (Quan trọng/Cấp bách).',
    description: 'Phân loại công việc theo 4 nhóm: Quan trọng & Cấp bách (Làm ngay), Quan trọng & Không cấp bách (Lên lịch), Không quan trọng & Cấp bách (Giao người khác/Làm nhanh), Không quan trọng & Không cấp bách (Bỏ qua).',
    howToApply: '👉 Bước 1: Lấy một tờ giấy nháp, kẻ 1 đường ngang và 1 đường dọc để chia giấy làm 4 ô vuông.\n👉 Bước 2: Viết tên 4 ô: Gấp & Quan trọng (Làm ngay) | Không gấp & Quan trọng (Lên lịch) | Gấp & Không quan trọng (Làm thật nhanh) | Không gấp & Không quan trọng (Bỏ qua).\n👉 Bước 3: Điền tất cả deadline bài tập, công việc của bạn vào 4 ô này.\n👉 Bước 4: Chỉ tập trung giải quyết ô "Làm ngay".',
    hcmueExample: 'Giữa việc làm tiểu luận ngày mai nộp (Quan trọng, Cấp bách) và việc xem phim (Không quan trọng, Không cấp bách), bạn sẽ biết phải chọn việc nào.'
  },
  {
    id: 'sq3r',
    category: 'memory',
    title: 'SQ3R',
    icon: BookOpen,
    color: '#0EA5E9',
    shortDesc: 'Đọc giáo trình (Survey, Question, Read, Recite, Review).',
    description: 'Phương pháp đọc sách chủ động giúp ghi nhớ lâu. Thay vì đọc từ đầu đến cuối một cách thụ động, bạn sẽ đi qua 5 bước để khai thác tối đa nội dung tài liệu học tập.',
    howToApply: '👉 Bước 1 (Survey): Lướt nhanh toàn bộ chương sách trong 3 phút. Chỉ xem tiêu đề in đậm, hình ảnh và bảng biểu.\n👉 Bước 2 (Question): Dùng bút chì đổi các tiêu đề in đậm thành câu hỏi (VD: "Cấu trúc dữ liệu là gì?").\n👉 Bước 3 (Read): Bắt đầu đọc kỹ từng trang để tìm đáp án cho các câu hỏi vừa ghi.\n👉 Bước 4 (Recite): Đọc xong 1 đoạn, ngẩng đầu lên và tự trả lời to câu hỏi đó.\n👉 Bước 5 (Review): Cuối tuần, xem lướt lại các câu hỏi để không bị quên.',
    hcmueExample: 'Đọc giáo trình: Xem mục lục trước, đặt câu hỏi "Khái niệm này là gì?", sau đó đọc bài để tìm câu trả lời và nhẩm lại.'
  }
];

