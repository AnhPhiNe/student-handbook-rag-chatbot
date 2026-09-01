import re
from typing import Any

SOURCE_SECTION_PATTERN = re.compile(
    r"(?ims)\n?\s*(?:#+\s*)?(?:nguồn|nguon|tham khảo|tham khao|sources?)\s*:\s*.*$"
)
ARTICLE_ANCHOR_PATTERN = re.compile(
    r"(?<![A-Za-zÀ-ỹ])(?:điều|dieu)[\s_-]*(\d+[a-z]?)\b", re.IGNORECASE
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
    return clean_stream_fragment(text).strip()


def remove_existing_sources_section(answer: str) -> str:
    answer = clean_answer(answer)
    return SOURCE_SECTION_PATTERN.sub("", answer).strip()


def normalize_unlabeled_enumeration_references(answer: str) -> str:
    """Keep a list reference readable when the LLM omitted its numeric labels.

    This intentionally handles only the unambiguous "mục 1, 2, 3" phrasing.
    Rewriting arbitrary legal sub-item references without their source structure
    could change the rule's meaning.
    """
    return UNNUMBERED_FIRST_THREE_PATTERN.sub("ba trường hợp đầu nêu trên", answer)


def append_sources(answer: str, sources_text: str) -> str:
    answer = remove_existing_sources_section(answer)
    sources_text = clean_answer(sources_text)

    if not sources_text:
        return answer

    return f"{answer}\n\n{sources_text}".strip()


def format_final_answer(
    answer: str, selected_citations: list[dict[str, Any]] | None
) -> str:
    # UI đã hiển thị nguồn bằng citation card, nên nội dung trả lời không lặp lại
    # khối "Nguồn:" dạng văn bản thô.
    return remove_existing_sources_section(answer)


def missing_primary_article_anchors(
    answer: str, primary_citations: list[dict[str, Any]] | None
) -> list[str]:
    """Return article anchors present in Primary metadata but absent from the answer.

    Only title and source_section are inspected.  Citation content may mention
    a different article as a cross-reference, so using it here could attach an
    incorrect legal anchor to the answer.
    """
    primary_anchors: list[str] = []
    seen: set[str] = set()
    for citation in primary_citations or []:
        if not isinstance(citation, dict):
            continue
        for field in ("source_section", "title"):
            value = citation.get(field)
            if not value:
                continue
            for match in ARTICLE_ANCHOR_PATTERN.finditer(str(value)):
                anchor = f"Điều {match.group(1).lower()}"
                normalized = anchor.casefold()
                if normalized not in seen:
                    seen.add(normalized)
                    primary_anchors.append(anchor)

    mentioned = {
        f"Điều {match.group(1).lower()}".casefold()
        for match in ARTICLE_ANCHOR_PATTERN.finditer(answer or "")
    }
    return [anchor for anchor in primary_anchors if anchor.casefold() not in mentioned]


def ensure_primary_article_anchors(
    answer: str, primary_citations: list[dict[str, Any]] | None
) -> str:
    """Return answer cleaned without appending redundant citation anchors."""
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
