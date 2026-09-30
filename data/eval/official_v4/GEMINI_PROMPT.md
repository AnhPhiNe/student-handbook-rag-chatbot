# Prompt cho người soạn đề (dán nguyên văn, rồi dán nội dung một file `batches/batch_NN.md` ngay bên dưới)

Bạn giúp tôi soạn câu hỏi kiểm thử cho một trợ lý hỏi đáp về Sổ tay sinh viên của Trường Đại học Sư phạm Thành phố Hồ Chí Minh (cơ sở chính). Mỗi "phiếu" bên dưới mô tả một câu hỏi cần viết. Phần "Các đoạn sổ tay" ở cuối là nguồn duy nhất bạn được dùng.

## Việc cần làm cho mỗi phiếu

1. **Viết tin nhắn của sinh viên** đúng "Loại câu hỏi" và đúng "Kiểu viết" của phiếu.
   - Viết như sinh viên thật nhắn tin, không chép lại câu chữ của văn bản quy định.
   - Hệ thống đã biết khóa của sinh viên, nên sinh viên **không cần nêu khóa**, trừ phiếu so sánh giữa hai khóa và phiếu hội thoại đổi khóa.
   - Không nhắc tới "đoạn Đ1", "phiếu" hay "sổ tay" trong câu hỏi, trừ khi sinh viên thật sẽ nói vậy.
   - Phiếu có nhiều yêu cầu: gộp tất cả vào **một** tin nhắn tự nhiên; mỗi yêu cầu vẫn phải cần một câu trả lời riêng.
   - Phiếu hội thoại hai lượt: viết lượt hỏi 1, một câu trả lời ngắn và đúng cho lượt 1, rồi lượt hỏi 2.
2. **Viết đáp án nháp** chỉ dựa trên các đoạn sổ tay được dẫn. Không thêm kiến thức bên ngoài.
3. **Liệt kê các ý bắt buộc**: những thông tin mà một câu trả lời đúng phải có (số liệu, tên đơn vị, điều kiện, thời hạn...). Mỗi ý ngắn gọn; chép nguyên văn con số, tên riêng, email, số điện thoại.
4. **Ghi nguồn**: mã đoạn và tên văn bản, số Điều (nếu có).
5. **Ghi hành vi mong đợi**: `tra_loi`, `hoi_lai`, `tu_choi`, `tra_loi_va_hoi_lai` hoặc `tra_loi_va_tu_choi`.

Nếu một yêu cầu không hỏi được đúng kiểu phiếu nêu (ví dụ phiếu bảo hỏi thủ tục nhưng đoạn sổ tay không có thủ tục), hãy hỏi một điều khác mà đoạn đó thực sự nêu và ghi vào `ghi_chu` loại câu đã hỏi. Không bao giờ bịa thông tin ngoài đoạn sổ tay.

Chỉ khi **cả phiếu không thể viết trung thực** mới điền `khong_phu_hop` với lý do và bỏ trống các trường khác.

## Định dạng trả về

Chỉ trả về một khối YAML, mỗi phiếu một mục, đúng thứ tự phiếu:

```yaml
- phieu: V4-006
  hoi_thoai:
    - vai: sinh_vien
      noi_dung: "..."
  dap_an_nhap: "..."
  y_bat_buoc:
    - "..."
  nguon:
    - "Đ1: Quy chế đào tạo trình độ đại học, Điều 10"
  hanh_vi: tra_loi
  ghi_chu: ""
- phieu: V4-196
  hoi_thoai:
    - vai: sinh_vien
      noi_dung: "..."
    - vai: tro_ly
      noi_dung: "..."
    - vai: sinh_vien
      noi_dung: "..."
  dap_an_nhap: "... (đáp án cho lượt hỏi cuối)"
  y_bat_buoc: ["..."]
  nguon: ["Đ18: ...", "Đ19: ..."]
  hanh_vi: tra_loi
  ghi_chu: ""
- phieu: V4-229
  khong_phu_hop: ""
  hoi_thoai:
    - vai: sinh_vien
      noi_dung: "..."
  dap_an_nhap: "..."
  y_bat_buoc: ["..."]
  nguon: []
  hanh_vi: tu_choi
  ghi_chu: ""
```

- `khong_phu_hop` chỉ dùng khi phiếu không viết được; khi đó ghi lý do.
- Phiếu "tự nghĩ câu hỏi" (ngoài phạm vi, sổ tay không có) không có nguồn: để `nguon: []`.
- Với phiếu từ chối hoặc hỏi lại, `y_bat_buoc` là điều câu trả lời phải làm, ví dụ: "hỏi lại điểm hệ 10 của sinh viên", "nói rõ sổ tay không có thông tin này".
