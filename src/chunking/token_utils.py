import re


def count_tokens_approx(text: str) -> int:
    """
    Ước lượng token đơn giản.
    Với tiếng Việt, tạm dùng số word/punctuation.
    Có thể thay bằng tokenizer chính xác hơn như tiktoken nếu cần.
    """
    if not text:
        return 0

    tokens = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
    return len(tokens)


def split_text_by_paragraph(
    text: str,
    max_tokens: int,
    overlap_tokens: int = 0,
) -> list[str]:
    """
    Split theo paragraph trước.
    Nếu paragraph quá dài thì split tiếp theo câu.
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current = []

    for paragraph in paragraphs:
        candidate = "\n".join(current + [paragraph])

        if count_tokens_approx(candidate) <= max_tokens:
            current.append(paragraph)
        else:
            if current:
                chunks.append("\n".join(current))

            if count_tokens_approx(paragraph) > max_tokens:
                chunks.extend(split_text_by_sentence(paragraph, max_tokens))
                current = []
            else:
                current = [paragraph]

    if current:
        chunks.append("\n".join(current))

    return chunks


def split_text_by_sentence(text: str, max_tokens: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?。])\s+", text)
    chunks = []
    current = []

    for sentence in sentences:
        candidate = " ".join(current + [sentence])

        if count_tokens_approx(candidate) <= max_tokens:
            current.append(sentence)
        else:
            if current:
                chunks.append(" ".join(current))
            current = [sentence]

    if current:
        chunks.append(" ".join(current))

    return chunks
