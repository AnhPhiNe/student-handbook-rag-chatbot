import torch
from sentence_transformers import CrossEncoder

model = CrossEncoder("itdainb/PhoRanker", max_length=256)
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
print("Sigmoid scores:", torch.sigmoid(torch.tensor(scores)).tolist())
