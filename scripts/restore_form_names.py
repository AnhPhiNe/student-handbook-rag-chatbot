import json
import os

def restore_names():
    mapping = {
        "Danh mục biểu mẫu thủ tục hành chính dành cho sinh viên": "CÁC MẪU ĐƠN VÀ BIỂU MẪU",
        "Biên bản họp lớp đánh giá kết quả rèn luyện sinh viên": "BIÊN BẢN HỌP LỚP ……",
        "Bảng tổng hợp kết quả đánh giá rèn luyện sinh viên cấp Khoa": "BẢNG KẾT QUẢ ĐÁNH GIÁ RÈN LUYỆN SINH VIÊN",
        "Biên bản họp Hội đồng đánh giá kết quả rèn luyện sinh viên cấp Khoa": "BIÊN BẢN HỌP HỘI ĐỒNG",
        "Đơn xin chuyển trường sang cơ sở giáo dục đại học khác": "ĐƠN XIN CHUYỂN TRƯỜNG",
        "Đơn xin tạm nghỉ học (kèm bảng điểm tích lũy)": "ĐƠN XIN TẠM NGHỈ HỌC",
        "Đơn xin trở lại học tập sau thời gian tạm nghỉ": "ĐƠN XIN HỌC LẠI",
        "Đơn xin thôi học và giải quyết thủ tục hành chính sinh viên": "ĐƠN XIN THÔI HỌC",
        "Đơn đề nghị xét hưởng trợ cấp xã hội dành cho sinh viên": "ĐƠN XIN TRỢ CẤP XÃ HỘI",
        "Đơn đăng ký xét duyệt vào ở ký túc xá sinh viên": "ĐƠN XIN VÀO Ở KÝ TÚC XÁ",
        "Giấy xác nhận sinh viên vay vốn ngân hàng": "GIẤY XÁC NHẬN",
        "Đơn đề nghị miễn, giảm học phí theo Nghị định 81/2021/NĐ-CP": "ĐƠN ĐỀ NGHỊ MIỄN, GIẢM HỌC PHÍ",
        "Đơn đề nghị cấp học bổng và hỗ trợ kinh phí học tập cho sinh viên khuyết tật": "ĐƠN ĐỀ NGHỊ",
        "Đơn đề nghị hỗ trợ chi phí học tập theo chính sách ưu đãi giáo dục": "ĐƠN ĐỀ NGHỊ HỖ TRỢ CHI PHÍ HỌC TẬP",
        "Phiếu theo dõi và đánh giá kết quả học tập sinh viên": "PHIẾU THEO DÕI TIẾN ĐỘ HỌC TẬP"
    }
    
    filepath = os.path.join("data", "processed", "forms", "clean_form_templates.json")
    with open(filepath, "r", encoding="utf-8") as f:
        forms = json.load(f)
        
    for form in forms:
        current_name = form["form_name"]
        if current_name in mapping:
            form["form_name"] = mapping[current_name]
            print(f"Restored: {current_name} -> {mapping[current_name]}")
            
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(forms, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    restore_names()
