"""The streaming output guardrail, fed chunk by chunk without a pipeline."""
from src.generation.answer_pipeline import STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS, StreamAnswerCleaner

BODY = " ".join(f"Ý {i}: sinh viên nộp hồ sơ tại Phòng Đào tạo." for i in range(20))


def _stream(text: str, size: int = 37) -> tuple[list[str], StreamAnswerCleaner]:
    cleaner = StreamAnswerCleaner()
    shown = [piece for start in range(0, len(text), size)
             if (piece := cleaner.feed(text[start:start + size]))]
    if tail := cleaner.finish():
        shown.append(tail)
    return shown, cleaner


def test_text_is_held_back_until_the_buffer_is_full_and_released_at_whitespace() -> None:
    cleaner = StreamAnswerCleaner()
    assert cleaner.feed("x " + "y" * (STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS - 2)) == ""
    # The last 256 characters stay held; the space before them is the release point.
    assert cleaner.feed("yz") == "x "
    assert cleaner.finish() == "y" * (STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS - 1) + "z"


def test_a_long_run_without_whitespace_is_held_up_to_twice_the_buffer() -> None:
    cleaner = StreamAnswerCleaner()
    assert cleaner.feed("x" * (2 * STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS - 1)) == ""
    assert cleaner.feed("x") == "x" * STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS


def test_released_text_is_the_whole_answer_in_order() -> None:
    shown, cleaner = _stream(BODY)
    assert len(shown) > 2
    assert "".join(shown) == cleaner.text == BODY


def test_the_held_back_tail_keeps_the_space_before_it() -> None:
    # Released text ends right before a space; the tail must not be glued on.
    text = "a" * 10 + " " + "b" * (STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS - 1)
    _, cleaner = _stream(text, size=len(text))
    assert cleaner.text == text


def test_a_source_footer_and_everything_after_it_are_cut() -> None:
    shown, cleaner = _stream(BODY + "\n\n### Nguồn:\n- Điều 5\n- Điều 7 " + "z" * 300)
    assert cleaner.text == BODY
    assert "Điều 7" not in "".join(shown)


def test_an_inline_source_word_is_kept() -> None:
    text = BODY + " Kinh phí lấy từ nguồn: ngân sách nhà trường.\n" + BODY
    _, cleaner = _stream(text)
    assert "nguồn: ngân sách" in cleaner.text


def test_an_opening_code_fence_is_removed() -> None:
    _, cleaner = _stream("```markdown\n" + BODY + "\n```")
    assert cleaner.text == BODY
