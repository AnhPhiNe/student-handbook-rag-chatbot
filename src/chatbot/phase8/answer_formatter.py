import re
from typing import Any

from .citation_formatter import format_sources_text


SOURCE_SECTION_PATTERN = re.compile(
    r"(?ims)\n?\s*(?:#+\s*)?(?:nguồn|nguon|sources?)\s*:\s*.*$"
)


def clean_answer(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:\w+)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_existing_sources_section(answer: str) -> str:
    answer = clean_answer(answer)
    return SOURCE_SECTION_PATTERN.sub("", answer).strip()


def append_sources(answer: str, sources_text: str) -> str:
    answer = remove_existing_sources_section(answer)
    sources_text = clean_answer(sources_text)

    if not sources_text:
        return answer

    return f"{answer}\n\n{sources_text}".strip()


def format_final_answer(answer: str, selected_citations: list[dict[str, Any]] | None) -> str:
    sources_text = format_sources_text(selected_citations)
    return append_sources(answer, sources_text)


def format_final_response(
    answer: str,
    sources_text: str = "",
    ambiguity_note: str = "",
) -> str:
    answer = remove_existing_sources_section(answer)

    if ambiguity_note:
        answer = f"{clean_answer(ambiguity_note)}\n\n{answer}".strip()

    return append_sources(answer, sources_text)
