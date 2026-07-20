import type { Cohort } from '../utils/gradeScale';

interface CohortSelectionModalProps {
  onSelect: (cohort: Cohort) => void;
}

export function CohortSelectionModal({ onSelect }: CohortSelectionModalProps) {
  return (
    <div className="cohort-modal-overlay">
      <div className="cohort-modal-content">
        <div className="cohort-modal-header">
          {/* Fallback to simple text if logo fails or use a generic icon */}
          <div className="modal-logo-container">
             <span className="modal-logo-icon">🎓</span>
          </div>
          <h2>Chào mừng đến với Sổ tay Sinh viên</h2>
          <p>
            Trợ lý AI và các công cụ tra cứu cần biết bạn thuộc Khóa nào để cung cấp
            quy chế và thông tin chính xác nhất. Vui lòng chọn Khóa của bạn:
          </p>
        </div>
        
        <div className="cohort-modal-options">
          <button 
            className="cohort-option-card"
            onClick={() => onSelect('K48-K49')}
          >
            <div className="cohort-icon">🏛️</div>
            <div className="cohort-info">
              <h3>Khóa 48 - 49</h3>
              <p>Sinh viên nhập học năm 2022 và 2023</p>
            </div>
          </button>
          
          <button 
            className="cohort-option-card"
            onClick={() => onSelect('K50')}
          >
            <div className="cohort-icon">📚</div>
            <div className="cohort-info">
              <h3>Khóa 50</h3>
              <p>Sinh viên nhập học năm 2024</p>
            </div>
          </button>
          
          <button 
            className="cohort-option-card"
            onClick={() => onSelect('K51')}
          >
            <div className="cohort-icon">✨</div>
            <div className="cohort-info">
              <h3>Khóa 51</h3>
              <p>Sinh viên nhập học năm 2025</p>
            </div>
          </button>
        </div>
        
        <div className="cohort-modal-footer">
          <p>💡 Bạn có thể thay đổi Khóa bất kỳ lúc nào ở góc trên bên phải màn hình.</p>
        </div>
      </div>
    </div>
  );
}
