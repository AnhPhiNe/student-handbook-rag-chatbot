import re
from typing import Any

SOURCE_SECTION_PATTERN = re.compile(
    r"(?ims)\n?\s*(?:#+\s*)?(?:nguồn|nguon|tham khảo|tham khao|sources?)\s*:\s*.*$"
)
UNNUMBERED_FIRST_THREE_PATTERN = re.compile(
    r"\b(?:các\s+)?trường\s+hợp\s+(?:tại\s+)?mục\s+1\s*,\s*2\s*(?:,|và)\s*3(?:\s+nêu\s+trên)?\b",
    re.IGNORECASE,
)
AMENDMENT_NOTE_PATTERN = re.compile(
    r"\s*\(\s*(?:được\s+)?(?:sửa\s+đổi[,\s]+)?bổ\s+sung\s+bởi\s+AMENDMENT\s*\d*\s*\)",
    re.IGNORECASE,
)
AMENDMENT_TAG_PATTERN = re.compile(r"\[AMENDMENT\s*\d*\]", re.IGNORECASE)
AMENDMENT_TOKEN_PATTERN = re.compile(r"\bAMENDMENT\s*\d+\b", re.IGNORECASE)
EVIDENCE_LABEL_PATTERN = re.compile(
    r"\s*\(\s*S\d+(?:\s*[,;/]\s*S\d+)*\s*\)",
    re.IGNORECASE,
)
DANGLING_MARKDOWN_TAIL_PATTERN = re.compile(
    r"(?:^|(?<=\s))(?:[*_~`]+\s*\(?|\()\s*$"
)


def _remove_dangling_markdown_tail(text: str) -> str:
    """Drop an unbalanced wrapper left after removing a private source tail."""

    return DANGLING_MARKDOWN_TAIL_PATTERN.sub("", text or "").rstrip()


def clean_stream_fragment(text: str) -> str:
    """Remove public-output artifacts without trimming fragment boundaries."""

    text = AMENDMENT_NOTE_PATTERN.sub("", text or "")
    text = AMENDMENT_TAG_PATTERN.sub("", text)
    text = AMENDMENT_TOKEN_PATTERN.sub("", text)
    text = EVIDENCE_LABEL_PATTERN.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    return normalize_unlabeled_enumeration_references(text)


def clean_stream_start(text: str) -> str:
    """Remove an opening Markdown fence once enough stream text is buffered."""

    return re.sub(r"^```(?:\w+)?\s*", "", text or "", count=1)


def sources_section_start(text: str) -> int | None:
    """Return the start of a model-generated source section, if present."""

    match = SOURCE_SECTION_PATTERN.search(text or "")
    return match.start() if match else None


def clean_answer(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:\w+)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return _remove_dangling_markdown_tail(clean_stream_fragment(text).strip())


def remove_existing_sources_section(answer: str) -> str:
    answer = clean_answer(answer)
    source_section = SOURCE_SECTION_PATTERN.search(answer)
    if source_section is None:
        return answer
    return _remove_dangling_markdown_tail(answer[: source_section.start()].strip())


def normalize_unlabeled_enumeration_references(answer: str) -> str:
    """Keep a list reference readable when the LLM omitted its numeric labels.

    This intentionally handles only the unambiguous "mục 1, 2, 3" phrasing.
    Rewriting arbitrary legal sub-item references without their source structure
    could change the rule's meaning.
    """
    return UNNUMBERED_FIRST_THREE_PATTERN.sub("ba trường hợp đầu nêu trên", answer)


def format_final_answer(
    answer: str, selected_citations: list[dict[str, Any]] | None
) -> str:
    # UI đã hiển thị nguồn bằng citation card, nên nội dung trả lời không lặp lại
    # khối "Nguồn:" dạng văn bản thô.
    return remove_existing_sources_section(answer)


def format_final_response(
    answer: str,
    sources_text: str = "",
    ambiguity_note: str = "",
    primary_citations: list[dict[str, Any]] | None = None,
) -> str:
    answer = remove_existing_sources_section(answer)
    answer = normalize_unlabeled_enumeration_references(answer)

    if ambiguity_note:
        answer = f"{clean_answer(ambiguity_note)}\n\n{answer}".strip()

    return answer
