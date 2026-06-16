import { useState } from 'react';
import { Download, FileText, Search } from 'lucide-react';

const CATEGORIES = [
  { id: 'ctct_hssv', name: 'Công tác Chính trị - HSSV' },
  { id: 'doan_luanvan', name: 'Đồ án - Luận văn' },
  { id: 'nckh', name: 'Nghiên cứu Khoa học' },
  { id: 'spnc_hstn', name: 'Hồ sơ Tốt nghiệp' },
  { id: 'thuctap_cntt', name: 'Thực tập CNTT' }
];

type FormItem = {
  id: string;
  name: string;
  type: 'WORD';
  size: string;
  date: string;
  file: string;
};

const FORMS_DATA: Record<string, FormItem[]> = {
  "ctct_hssv": [
    { "id": "CTCT_HSSV_01", "name": "Đơn đề nghị cấp học bổng và hỗ trợ kinh phí", "type": "WORD", "size": "16 KB", "date": "Cập nhật mới", "file": "mau-don-de-nghi-cap-hoc-bong-va-ho-tro-kinh-phi-mua-do-dung-hoc-tap-dung-rieng.docx" },
    { "id": "CTCT_HSSV_02", "name": "Đơn đề nghị hỗ trợ chi phí học tập", "type": "WORD", "size": "19 KB", "date": "Cập nhật mới", "file": "mau-don-de-nghi-ho-tro-chi-phi-hoc-tap.docx" },
    { "id": "CTCT_HSSV_03", "name": "Đơn đề nghị miễn giảm học phí", "type": "WORD", "size": "16 KB", "date": "Cập nhật mới", "file": "mau-don-de-nghi-mien-giam-hoc-phi.docx" },
    { "id": "CTCT_HSSV_04", "name": "Đơn xin chuyển trường", "type": "WORD", "size": "24 KB", "date": "Cập nhật mới", "file": "mau-don-xin-chuyen-truong.docx" },
    { "id": "CTCT_HSSV_05", "name": "Đơn xin học bổng", "type": "WORD", "size": "17 KB", "date": "Cập nhật mới", "file": "mau-don-xin-hoc-bong.docx" },
    { "id": "CTCT_HSSV_06", "name": "Đơn xin nhận trợ cấp xã hội", "type": "WORD", "size": "20 KB", "date": "Cập nhật mới", "file": "mau-don-xin-nhan-tro-cap-xa-hoi.docx" },
    { "id": "CTCT_HSSV_07", "name": "Đơn xin tạm nghỉ học", "type": "WORD", "size": "17 KB", "date": "Cập nhật mới", "file": "mau-don-xin-tam-nghi-hoc.docx" },
    { "id": "CTCT_HSSV_08", "name": "Đơn xin thôi học", "type": "WORD", "size": "17 KB", "date": "Cập nhật mới", "file": "mau-don-xin-thoi-hoc.docx" },
    { "id": "CTCT_HSSV_09", "name": "Đơn xin vào ở ký túc xá", "type": "WORD", "size": "17 KB", "date": "Cập nhật mới", "file": "mau-don-xin-vao-o-ky-tuc-xa.docx" },
    { "id": "CTCT_HSSV_10", "name": "Đơn xin xác nhận điểm rèn luyện sinh viên", "type": "WORD", "size": "17 KB", "date": "Cập nhật mới", "file": "mau-don-xin-xac-nhan-diem-ren-luyen-sinh-vien.docx" },
    { "id": "CTCT_HSSV_11", "name": "Giấy giới thiệu thực tập", "type": "WORD", "size": "18 KB", "date": "Cập nhật mới", "file": "mau-giay-gioi-thieu-thuc-tap.docx" }
  ],
  "doan_luanvan": [
    { "id": "DOAN_LUANVAN_01", "name": "KhoaCntt TotNghiep BaoVe", "type": "WORD", "size": "94 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_BaoVe.doc" },
    { "id": "DOAN_LUANVAN_02", "name": "KhoaCntt TotNghiep HuongDan", "type": "WORD", "size": "115 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_HuongDan.doc" },
    { "id": "DOAN_LUANVAN_03", "name": "KhoaCntt TotNghiep Mau01", "type": "WORD", "size": "44 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau01.doc" },
    { "id": "DOAN_LUANVAN_04", "name": "KhoaCntt TotNghiep Mau02", "type": "WORD", "size": "45 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau02.doc" },
    { "id": "DOAN_LUANVAN_05", "name": "KhoaCntt TotNghiep Mau03", "type": "WORD", "size": "44 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau03.doc" },
    { "id": "DOAN_LUANVAN_06", "name": "KhoaCntt TotNghiep Mau04", "type": "WORD", "size": "44 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau04.doc" },
    { "id": "DOAN_LUANVAN_07", "name": "KhoaCntt TotNghiep Mau05", "type": "WORD", "size": "92 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau05.doc" },
    { "id": "DOAN_LUANVAN_08", "name": "KhoaCntt TotNghiep Mau06 BiaNgoai", "type": "WORD", "size": "23 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau06_BiaNgoai.doc" },
    { "id": "DOAN_LUANVAN_09", "name": "KhoaCntt TotNghiep Mau07 TrangPhuBia", "type": "WORD", "size": "24 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau07_TrangPhuBia.doc" },
    { "id": "DOAN_LUANVAN_10", "name": "KhoaCntt TotNghiep Mau08", "type": "WORD", "size": "32 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau08.doc" },
    { "id": "DOAN_LUANVAN_11", "name": "KhoaCntt TotNghiep Mau09 BiaNgoai", "type": "WORD", "size": "23 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau09_BiaNgoai.doc" },
    { "id": "DOAN_LUANVAN_12", "name": "KhoaCntt TotNghiep Mau10 TrangPhuBia", "type": "WORD", "size": "24 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau10_TrangPhuBia.doc" },
    { "id": "DOAN_LUANVAN_13", "name": "KhoaCntt TotNghiep Mau11", "type": "WORD", "size": "36 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau11.doc" },
    { "id": "DOAN_LUANVAN_14", "name": "KhoaCntt TotNghiep Mau12", "type": "WORD", "size": "32 KB", "date": "Cập nhật mới", "file": "KhoaCntt_TotNghiep_Mau12.doc" }
  ],
  "nckh": [
    { "id": "NCKH_01", "name": "Mau 10 NCKH SV KQ Nghien cuu", "type": "WORD", "size": "56 KB", "date": "Cập nhật mới", "file": "Mau_10_-_NCKH_SV_-_KQ_Nghien_cuu.doc" },
    { "id": "NCKH_02", "name": "Mau 11 NCKH SV Thong tin SV", "type": "WORD", "size": "56 KB", "date": "Cập nhật mới", "file": "Mau_11_-_NCKH_SV_-_Thong_tin_SV.doc" },
    { "id": "NCKH_03", "name": "Mau 1 NCKH SV Don dang ky Tham gia", "type": "WORD", "size": "58 KB", "date": "Cập nhật mới", "file": "Mau_1_-_NCKH_SV_-_Don_dang_ky_Tham_gia.doc" },
    { "id": "NCKH_04", "name": "Mau 2 NCKH SV De xuat De tai NC", "type": "WORD", "size": "108 KB", "date": "Cập nhật mới", "file": "Mau_2_-_NCKH_SV_-_De_xuat_De_tai_NC.doc" },
    { "id": "NCKH_05", "name": "Mau 4 NCKH SV Bao cao Tien do", "type": "WORD", "size": "58 KB", "date": "Cập nhật mới", "file": "Mau_4_-_NCKH_SV_-_Bao_cao_Tien_do.doc" },
    { "id": "NCKH_06", "name": "Mau 5 NCKH SV Phieu Danh Gia", "type": "WORD", "size": "63 KB", "date": "Cập nhật mới", "file": "Mau_5_-_NCKH_SV_-_Phieu_Danh_Gia.doc" },
    { "id": "NCKH_07", "name": "Mau 6 NCKH SV Bien ban", "type": "WORD", "size": "59 KB", "date": "Cập nhật mới", "file": "Mau_6_-_NCKH_SV_-_Bien_ban.doc" },
    { "id": "NCKH_08", "name": "Mau 7 NCKH SV Tong hop DS Dang ky", "type": "WORD", "size": "58 KB", "date": "Cập nhật mới", "file": "Mau_7_-_NCKH_SV_-_Tong_hop_DS_Dang_ky.doc" },
    { "id": "NCKH_09", "name": "Mau 8 NCKH SV Trang bia", "type": "WORD", "size": "53 KB", "date": "Cập nhật mới", "file": "Mau_8_-_NCKH_SV_-_Trang_bia.doc" },
    { "id": "NCKH_10", "name": "Mau 9 NCKH SV Trang phu bia", "type": "WORD", "size": "55 KB", "date": "Cập nhật mới", "file": "Mau_9_-_NCKH_SV_-_Trang_phu_bia.doc" }
  ],
  "spnc_hstn": [
    { "id": "SPNC_HSTN_01", "name": "SPNC HSTN 01 Bien ban tiep nhan", "type": "WORD", "size": "34 KB", "date": "Cập nhật mới", "file": "SPNC_HSTN_01_Bien_ban_tiep_nhan.doc" },
    { "id": "SPNC_HSTN_02", "name": "SPNC HSTN 02 Phieu cham", "type": "WORD", "size": "38 KB", "date": "Cập nhật mới", "file": "SPNC_HSTN_02_Phieu_cham.doc" },
    { "id": "SPNC_HSTN_03", "name": "SPNC HSTN 03 Danh muc minh chung", "type": "WORD", "size": "37 KB", "date": "Cập nhật mới", "file": "SPNC_HSTN_03_Danh_muc_minh_chung.doc" },
    { "id": "SPNC_HSTN_04", "name": "SPNC HSTN 04 Phieu nhan xet", "type": "WORD", "size": "33 KB", "date": "Cập nhật mới", "file": "SPNC_HSTN_04_Phieu_nhan_xet.doc" }
  ],
  "thuctap_cntt": [
    { "id": "THUCTAP_CNTT_01", "name": "01TT Mau bao cao", "type": "WORD", "size": "31 KB", "date": "Cập nhật mới", "file": "01TT_Mau_bao_cao.doc" },
    { "id": "THUCTAP_CNTT_02", "name": "02TT Phieu danh gia cua CBHD cua co so thuc tap", "type": "WORD", "size": "37 KB", "date": "Cập nhật mới", "file": "02TT_Phieu_danh_gia_cua_CBHD_cua_co_so_thuc_tap.doc" },
    { "id": "THUCTAP_CNTT_03", "name": "03TT Mau bia bao cao", "type": "WORD", "size": "105 KB", "date": "Cập nhật mới", "file": "03TT_Mau_bia_bao_cao.doc" },
    { "id": "THUCTAP_CNTT_04", "name": "04TT Phieu danh gia cua GV cua Khoa", "type": "WORD", "size": "42 KB", "date": "Cập nhật mới", "file": "04TT_Phieu_danh_gia_cua_GV_cua_Khoa.doc" },
    { "id": "THUCTAP_CNTT_05", "name": "05TT Mau Lich lam viec", "type": "WORD", "size": "32 KB", "date": "Cập nhật mới", "file": "05TT_Mau_Lich_lam_viec.doc" },
    { "id": "THUCTAP_CNTT_06", "name": "Mau gioi thieu thuc tap", "type": "WORD", "size": "34 KB", "date": "Cập nhật mới", "file": "Mau-gioi-thieu-thuc-tap.doc" }
  ]
};

const FRIENDLY_NAMES: Record<string, string> = {
  // Doan luan van
  "KhoaCntt TotNghiep BaoVe": "Mẫu 00 — Biên bản bảo vệ",
  "KhoaCntt TotNghiep HuongDan": "Hướng dẫn làm đồ án tốt nghiệp",
  "KhoaCntt TotNghiep Mau01": "Mẫu 01 — Đơn đăng ký đề tài",
  "KhoaCntt TotNghiep Mau02": "Mẫu 02 — Phiếu giao đề tài",
  "KhoaCntt TotNghiep Mau03": "Mẫu 03 — Bản giải trình đề cương",
  "KhoaCntt TotNghiep Mau04": "Mẫu 04 — Kế hoạch thực hiện",
  "KhoaCntt TotNghiep Mau05": "Mẫu 05 — Phiếu theo dõi tiến độ",
  "KhoaCntt TotNghiep Mau06 BiaNgoai": "Mẫu 06 — Bìa ngoài",
  "KhoaCntt TotNghiep Mau07 TrangPhuBia": "Mẫu 07 — Trang phụ bìa",
  "KhoaCntt TotNghiep Mau08": "Mẫu 08 — Nhận xét của giảng viên hướng dẫn",
  "KhoaCntt TotNghiep Mau09 BiaNgoai": "Mẫu 09 — Bìa ngoài (Hội đồng)",
  "KhoaCntt TotNghiep Mau10 TrangPhuBia": "Mẫu 10 — Trang phụ bìa (Hội đồng)",
  "KhoaCntt TotNghiep Mau11": "Mẫu 11 — Nhận xét của phản biện",
  "KhoaCntt TotNghiep Mau12": "Mẫu 12 — Biên bản họp hội đồng",
  // NCKH
  "Mau 10 NCKH SV KQ Nghien cuu": "Mẫu 10 — Kết quả nghiên cứu",
  "Mau 11 NCKH SV Thong tin SV": "Mẫu 11 — Thông tin sinh viên",
  "Mau 1 NCKH SV Don dang ky Tham gia": "Mẫu 01 — Đơn đăng ký tham gia NCKH",
  "Mau 2 NCKH SV De xuat De tai NC": "Mẫu 02 — Đề xuất đề tài nghiên cứu",
  "Mau 4 NCKH SV Bao cao Tien do": "Mẫu 04 — Báo cáo tiến độ NCKH",
  "Mau 5 NCKH SV Phieu Danh Gia": "Mẫu 05 — Phiếu đánh giá NCKH",
  "Mau 6 NCKH SV Bien ban": "Mẫu 06 — Biên bản nghiệm thu NCKH",
  "Mau 7 NCKH SV Tong hop DS Dang ky": "Mẫu 07 — Tổng hợp danh sách đăng ký",
  "Mau 8 NCKH SV Trang bia": "Mẫu 08 — Trang bìa NCKH",
  "Mau 9 NCKH SV Trang phu bia": "Mẫu 09 — Trang phụ bìa NCKH",
  // SPNC HSTN
  "SPNC HSTN 01 Bien ban tiep nhan": "Mẫu 01 — Biên bản tiếp nhận hồ sơ",
  "SPNC HSTN 02 Phieu cham": "Mẫu 02 — Phiếu chấm",
  "SPNC HSTN 03 Danh muc minh chung": "Mẫu 03 — Danh mục minh chứng",
  "SPNC HSTN 04 Phieu nhan xet": "Mẫu 04 — Phiếu nhận xét",
  // Thuc tap CNTT
  "01TT Mau bao cao": "Mẫu 01 — Báo cáo thực tập",
  "02TT Phieu danh gia cua CBHD cua co so thuc tap": "Mẫu 02 — Phiếu đánh giá của cơ sở thực tập",
  "03TT Mau bia bao cao": "Mẫu 03 — Bìa báo cáo thực tập",
  "04TT Phieu danh gia cua GV cua Khoa": "Mẫu 04 — Phiếu đánh giá của giảng viên Khoa",
  "05TT Mau Lich lam viec": "Mẫu 05 — Lịch làm việc thực tập",
  "Mau gioi thieu thuc tap": "Giấy giới thiệu thực tập (CNTT)"
};

export function FormPage() {
  const [activeCategory, setActiveCategory] = useState(CATEGORIES[0].id);
  const [searchQuery, setSearchQuery] = useState('');

  const getFilteredForms = () => {
    if (!searchQuery.trim()) {
      return { forms: FORMS_DATA[activeCategory] || [], isCrossSearch: false };
    }
    
    // Cross-search if >= 3 chars
    if (searchQuery.length >= 3) {
      const allResults: (FormItem & { categoryName: string })[] = [];
      for (const cat of CATEGORIES) {
        const forms = FORMS_DATA[cat.id] || [];
        const matches = forms.filter(f => {
          const friendlyName = FRIENDLY_NAMES[f.name] || f.name;
          return friendlyName.toLowerCase().includes(searchQuery.toLowerCase());
        });
        matches.forEach(f => allResults.push({ ...f, categoryName: cat.name }));
      }
      return { forms: allResults, isCrossSearch: true };
    }
    
    // Default search within active category
    const forms = (FORMS_DATA[activeCategory] || []).filter(f => {
      const friendlyName = FRIENDLY_NAMES[f.name] || f.name;
      return friendlyName.toLowerCase().includes(searchQuery.toLowerCase());
    });
    return { forms, isCrossSearch: false };
  };

  const { forms: filteredForms, isCrossSearch } = getFilteredForms();

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Biểu mẫu & Đơn từ</h1>
        <p>Danh sách 45 mẫu đơn thông dụng chia theo 5 danh mục phòng ban.</p>
      </div>

      <div className="category-tabs">
        {CATEGORIES.map(cat => (
          <button 
            key={cat.id} 
            onClick={() => {
              setActiveCategory(cat.id);
              if (isCrossSearch) setSearchQuery(''); // Clear search when switching tabs manually
            }}
            className={`cat-tab-btn ${activeCategory === cat.id && !isCrossSearch ? 'active' : ''}`}
          >
            {cat.name}
          </button>
        ))}
      </div>

      <div className="form-controls">
        <div className="search-box">
          <Search size={18} className="search-icon" />
          <input 
            type="text" 
            placeholder="Tìm kiếm biểu mẫu..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>
      
      <p className="search-hint">
        Nhập từ 3 ký tự để tìm kiếm trên tất cả danh mục
      </p>

      {/* Desktop Table View */}
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Mã BM</th>
              <th>Tên biểu mẫu</th>
              {isCrossSearch && <th>Danh mục</th>}
              <th>Định dạng</th>
              <th>Ngày cập nhật</th>
              <th className="text-right">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {filteredForms.map((form: FormItem & { categoryName?: string }) => (
              <tr key={form.id}>
                <td className="font-medium text-secondary">{form.id}</td>
                <td>
                  <div className="form-name">
                    <FileText size={16} className="text-accent" />
                    <span>{FRIENDLY_NAMES[form.name] || form.name}</span>
                  </div>
                </td>
                {isCrossSearch && <td className="text-secondary" style={{ fontSize: '0.8125rem' }}>{form.categoryName}</td>}
                <td>
                  <span className={`badge ${form.type.toLowerCase()}`}>{form.type}</span>
                </td>
                <td className="text-secondary">{form.date}</td>
                <td className="text-right">
                  <a href={`/forms/${form.categoryName ? CATEGORIES.find(c => c.name === form.categoryName)?.id : activeCategory}/${form.file}`} download className="download-btn">
                    <Download size={16} />
                    <span>Tải xuống</span>
                  </a>
                </td>
              </tr>
            ))}
            {filteredForms.length === 0 && (
              <tr>
                <td colSpan={isCrossSearch ? 6 : 5} style={{textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)'}}>
                  <div className="empty-search-state">
                    <FileText size={48} style={{ opacity: 0.2, margin: '0 auto 1rem' }} />
                    <p>Không tìm thấy biểu mẫu nào khớp với "{searchQuery}"</p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="form-card-list">
        {filteredForms.map((form: FormItem & { categoryName?: string }) => (
          <div key={form.id} className="form-card">
            <div className="form-card-header">
              <div className="form-card-title">
                <FileText size={18} className="text-accent" style={{ flexShrink: 0, marginTop: '2px' }} />
                <span>{FRIENDLY_NAMES[form.name] || form.name}</span>
              </div>
            </div>
            
            <div className="form-card-meta">
              <span>{form.id}</span>
              {isCrossSearch && <span style={{ color: 'var(--primary)', fontWeight: 500 }}>{form.categoryName}</span>}
              <span className={`badge ${form.type.toLowerCase()}`}>{form.type}</span>
            </div>
            
            <a href={`/forms/${form.categoryName ? CATEGORIES.find(c => c.name === form.categoryName)?.id : activeCategory}/${form.file}`} download className="download-btn" style={{ justifyContent: 'center', marginTop: '0.5rem' }}>
              <Download size={16} />
              <span>Tải xuống biểu mẫu</span>
            </a>
          </div>
        ))}
        {filteredForms.length === 0 && (
          <div className="empty-search-state">
            <FileText size={48} style={{ opacity: 0.2, margin: '0 auto 1rem' }} />
            <p>Không tìm thấy biểu mẫu nào khớp với "{searchQuery}"</p>
          </div>
        )}
      </div>
    </div>
  );
}
