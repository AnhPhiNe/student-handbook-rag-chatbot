import re


def count_tokens_approx(text: str) -> int:
    """Estimate multilingual token count from words and punctuation."""
    if not text:
        return 0

    tokens = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
    return len(tokens)


def split_text_by_paragraph(
    text: str,
    max_tokens: int,
    overlap_tokens: int = 0,
) -> list[str]:
    """Split on paragraphs first, then sentences when a paragraph is too long."""
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
    """Greedily group sentences under an approximate token limit."""

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
