import torch
from sentence_transformers import CrossEncoder

print("Đang tải mô hình namdp-ptit/ViRanker...")
model = CrossEncoder("namdp-ptit/ViRanker", max_length=256)
query = "trường có những loại học bổng nào"
docs = [
    "Điều 28. Tiêu chuẩn, mức, quỹ học bổng khuyến khích học tập\n...",
    "Điều 5. Các hình thức khuyến khích. 2. Học bổng hỗ trợ phát triển tài năng",
    "Bảng điểm chữ: A, B, C",
    "Đây là câu văn không liên quan gì đến học bổng cả"
]

pairs = [(query, doc) for doc in docs]
scores = model.predict(pairs)
print("Raw scores:", scores)

# Kiểm tra xem mô hình có xuất Logit (cần sigmoid) hay xuất Probability (không cần sigmoid)
if min(scores) >= 0 and max(scores) <= 1.0:
    print("Mô hình nhả ra Xác suất (Probability). Không cần Sigmoid.")
else:
    print("Mô hình nhả ra Logit. Điểm sau Sigmoid:")
    print(torch.sigmoid(torch.tensor(scores)).tolist())
