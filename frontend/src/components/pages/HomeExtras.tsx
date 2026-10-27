import type { CSSProperties } from 'react';
import { ArrowRight } from 'lucide-react';
import { EXPERIENCE } from '../../data/experience';
import { OFFICES } from '../../data/directory';
import { noteColor } from '../../utils/experience';

interface ExtrasProps {
  onNavigate: (tab: string) => void;
}

// Each note is held up differently, so the row reads like a real board, not a grid.
const FASTENERS = ['tape', 'pin', 'tape-corner'] as const;
const TILTS = [-1.6, 1.2, -0.8];

/** Three tips from the experience page, pinned and taped like notes on a board. */
export function TipBoard({ onNavigate }: ExtrasProps) {
  const tips = EXPERIENCE.tips.slice(0, 3);
  if (tips.length === 0) return null;
  return (
    <section className="hp-extra" aria-labelledby="hp-tips-title">
      <div className="hp-extra-head">
        <h2 id="hp-tips-title">Mẹo từ bạn đi trước</h2>
        <button type="button" className="hp-extra-link" onClick={() => onNavigate('kinh-nghiem')}>
          Đọc thêm <ArrowRight size={14} aria-hidden="true" />
        </button>
      </div>
      <div className="hp-tips">
        {tips.map((tip, i) => (
          <button
            key={tip.id}
            type="button"
            className={`hp-tip hp-tip-${FASTENERS[i % FASTENERS.length]}`}
            style={{ '--paper': noteColor(i), '--tilt': `${TILTS[i % TILTS.length]}deg` } as CSSProperties}
            onClick={() => onNavigate('kinh-nghiem')}
          >
            <span className="hp-tip-fastener" aria-hidden="true" />
            <q>{tip.quote}</q>
            <small>{tip.author.name} · {tip.author.meta}</small>
          </button>
        ))}
      </div>
    </section>
  );
}

// The three offices students call most: courses and graduation, scholarships and
// student status, tuition. Matched by name so the directory data stays the source.
const QUICK_OFFICES = [
  { name: 'Phòng Đào tạo', short: 'Phòng Đào tạo', hint: 'Đăng ký học phần, tốt nghiệp', badge: 'ĐT', color: '#2251CC' },
  { name: 'Phòng Công tác chính trị và Học sinh, sinh viên', short: 'Phòng CTSV', hint: 'Học bổng, rèn luyện, thẻ SV', badge: 'CT', color: '#D7263D' },
  { name: 'Phòng Kế hoạch – Tài chính', short: 'Phòng Tài chính', hint: 'Học phí, biên lai, hoàn phí', badge: 'TC', color: '#1E8A55' },
];

/** Office phone numbers from the handbook directory, for when the experience page is off. */
export function QuickContacts({ onNavigate }: ExtrasProps) {
  const rows = QUICK_OFFICES.flatMap((item) => {
    const unit = OFFICES.find((office) => office.name === item.name);
    return unit?.phones[0] ? [{ ...item, phone: unit.phones[0], ext: unit.ext[0] }] : [];
  });
  if (rows.length === 0) return null;
  return (
    <section className="hp-extra" aria-labelledby="hp-contacts-title">
      <div className="hp-extra-head">
        <h2 id="hp-contacts-title">Liên hệ nhanh</h2>
        <button type="button" className="hp-extra-link" onClick={() => onNavigate('danh-ba')}>
          Mở Danh bạ <ArrowRight size={14} aria-hidden="true" />
        </button>
      </div>
      <div className="hp-contacts">
        {rows.map((row) => (
          <a
            key={row.name}
            className="hp-contact"
            href={`tel:${row.phone.replace(/[^\d+]/g, '')}${row.ext ? `,${row.ext}` : ''}`}
            style={{ '--c': row.color } as CSSProperties}
          >
            <i aria-hidden="true">{row.badge}</i>
            <span>
              <b>{row.short}</b>
              <small>{row.hint}</small>
              <span className="hp-contact-phone">{row.phone}{row.ext ? ` · máy lẻ ${row.ext}` : ''}</span>
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}
