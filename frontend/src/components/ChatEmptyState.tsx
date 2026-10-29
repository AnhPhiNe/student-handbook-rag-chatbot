import { ArrowRight, Sparkles } from 'lucide-react';
import { OwlMascot } from './OwlMascot';
import { ChatInput } from './ChatInput';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { useState } from 'react';

type Topic = { id: string; label: string; tone: string; questions: string[] };

const TOPICS: Topic[] = [
  { id: 'study', label: 'Học tập', tone: 'blue', questions: ['Đăng ký học phần tối thiểu bao nhiêu tín chỉ?', 'Học cải thiện tính điểm thế nào?', 'Phúc khảo bài thi ở đâu?', 'Hoãn thi cuối kỳ cần điều kiện gì?'] },
  { id: 'scholarship', label: 'Học bổng', tone: 'amber', questions: ['Học bổng Xuất sắc cần điều kiện gì?', 'Mức học bổng khuyến khích học tập được quy định thế nào?', 'Ai thuộc diện miễn, giảm học phí?', 'Học kỳ cuối cần bao nhiêu tín chỉ để xét học bổng?'] },
  { id: 'conduct', label: 'Rèn luyện', tone: 'mint', questions: ['Điểm rèn luyện được đánh giá như thế nào?', 'Điểm rèn luyện bao nhiêu được xếp loại Xuất sắc?', 'Sinh viên được khen thưởng trong những trường hợp nào?', 'Các hình thức kỷ luật sinh viên là gì?'] },
  { id: 'graduation', label: 'Tốt nghiệp', tone: 'violet', questions: ['Điều kiện xét tốt nghiệp là gì?', 'Rớt bao nhiêu tín chỉ thì bị hạ bằng?', 'Thời gian học tối đa được quy định thế nào?', 'Điều kiện xin bảo lưu kết quả học tập là gì?'] },
  { id: 'contact', label: 'Liên hệ', tone: 'rose', questions: ['Số điện thoại của Phòng Đào tạo là gì?', 'Phòng Công tác sinh viên nằm ở đâu?', 'Lỗi tài khoản sinh viên liên hệ phòng nào?', 'Liên hệ phòng nào để hỏi về học phí?'] },
];

const POPULAR = ['Học bổng Xuất sắc cần điều kiện gì?', 'Rớt bao nhiêu tín chỉ thì bị hạ bằng?', 'Đăng ký học phần tối thiểu bao nhiêu tín chỉ?', 'Phúc khảo bài thi ở đâu?'];
const QUESTION_TONES = ['amber', 'rose', 'blue', 'mint'];

interface EmptyChatProps {
  cohort: string;
  topic: string | null;
  onTopicChange: (topic: string | null) => void;
  onAsk: (question: string) => void;
  onNavigate?: (tab: string) => void;
  draft?: { id: number; text: string } | null;
  isTyping: boolean;
  hasError: boolean;
}

/** Claude v3 desktop: hero → composer → topics → 2×2 prompts.
 * Claude v2 mobile: hero → topics → three prompts, with the composer pinned below. */
export function ChatEmptyState({ cohort, topic, onTopicChange, onAsk, onNavigate, draft, isTyping, hasError }: EmptyChatProps) {
  const desktop = useMediaQuery('(min-width: 901px)');
  // The composer moves across the breakpoint; its draft must not disappear on resize.
  const [text, setText] = useState(draft?.text ?? '');
  const active = TOPICS.find((item) => item.id === topic);
  const questions = active?.questions ?? POPULAR;
  return (
    <>
      <div className="ce-scroll">
        <div className="ce-inner">
          <div className="ce-hero">
            <OwlMascot state="idle" size={desktop ? 92 : 108} className="ce-owl" showFrame={false} />
            <h1>Hỏi mình <span>về Sổ tay nè</span></h1>
            <p>Mình trả lời theo Sổ tay khóa {cohort.replace('K', '')}, có dẫn Điều, Khoản.</p>
          </div>

          {desktop && <div className="ce-desktop-composer">
            <ChatInput key={draft?.id ?? 'desktop-composer'} initialText={text} onTextChange={setText} placeholderText="Nhắn cho Sổ tay…" onSend={onAsk} disabled={isTyping} hasError={hasError} />
          </div>}

          <div className="ce-topics" role="group" aria-label="Chủ đề trong Sổ tay">
            {TOPICS.map((item) => (
              <button key={item.id} type="button" className={`ce-topic ce-${item.tone}`}
                aria-pressed={topic === item.id}
                onClick={() => onTopicChange(topic === item.id ? null : item.id)}>
                {item.label}
              </button>
            ))}
          </div>

          <section className="ce-popular" aria-labelledby="ce-popular-title">
            <h2 id="ce-popular-title"><Sparkles size={14} aria-hidden="true" />{active ? `Hỏi về ${active.label.toLocaleLowerCase('vi')}` : 'Bạn bè hay hỏi'}</h2>
            <div className="ce-questions">
              {questions.map((question, index) => (
                <button type="button" key={question} className={`ce-question${index === 3 ? ' ce-fourth-question' : ''}`}
                  onClick={() => onAsk(question)}>
                  <span className={`ce-number ce-${active?.tone ?? QUESTION_TONES[index]}`} aria-hidden="true">{index + 1}</span>
                  <span className="ce-question-text">{question}</span>
                  <ArrowRight size={16} aria-hidden="true" />
                </button>
              ))}
            </div>
            {onNavigate && (
              <div className="ce-more">
                <button type="button" className="ce-rose" onClick={() => onNavigate('scholarship')}>
                  <span><b>Tính điểm học bổng</b><small>Tự tính mức của bạn</small></span><ArrowRight size={16} aria-hidden="true" />
                </button>
                <button type="button" className="ce-mint" onClick={() => onNavigate('danh-ba')}>
                  <span><b>Danh bạ</b><small>Gọi đúng phòng</small></span><ArrowRight size={16} aria-hidden="true" />
                </button>
              </div>
            )}
          </section>
        </div>
      </div>
      {!desktop && <div className="ce-mobile-composer">
        <ChatInput key={draft?.id ?? 'mobile-composer'} initialText={text} onTextChange={setText} placeholderText="Nhắn cho Sổ tay…" onSend={onAsk} disabled={isTyping} hasError={hasError} />
      </div>}
    </>
  );
}
