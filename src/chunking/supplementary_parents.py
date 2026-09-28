"""Build parent documents for handbook texts that have no articles.

The article parser indexes regulations Điều by Điều. Notices, guides,
procedures, link pages, the conduct score framework and the forms have no
articles, so they are listed in configs/supplementary_documents.yaml with
their pages and read here straight from the PDF.

Prose keeps its own wording; only the page frame (running header, page
number, letterhead, signature) is dropped. A ruled table is read cell by cell
(src/ingestion/ruled_tables.py) and each row is written as one self-contained
line that names its table, group and columns (table-to-text), so a retrieved
line still says which item and which column a value belongs to. Every line is
built from the PDF text by fixed templates; nothing is paraphrased.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz

from src.common.io import load_yaml
from src.ingestion.ruled_tables import extract_ruled_table, table_areas
from src.preprocessing.structure_parser import classify_line

from .regulation_parents import build_section_content

CONFIG_PATH = Path("configs/supplementary_documents.yaml")

PAGE_FRAME = re.compile(r"^(?:\d+\s+)?(?:SỔ TAY SINH VIÊN KHÓA\s+\d+|Sổ tay Sinh viên năm học.*)(?:\s+\d+)?$|^\d{1,3}$",
                        re.IGNORECASE)
SECTION_HEADING = re.compile(r"^(?P<code>[IVX]+)\.\s+(?P<title>\S.*)$")
STEP = re.compile(r"^Bước\s+\d+\s*:")
NUMBERED_ITEM = re.compile(r"(?<=\s)(\d+)\.\s+(?=[A-ZĐÀ-Ỹ])")
ROMAN = re.compile(r"^[IVX]+\.?$")
LETTER = re.compile(r"^[a-zđ]\)?$")
# A form's tick-box row ("XUẤT SẮC c TỐT c KHÁ c ..."): the boxes read as "c".
CHECKBOX = re.compile(r"(?<=\s)[c□☐❑](?=\s|$)")


def _is_checkbox_row(text: str) -> bool:
    return len(CHECKBOX.findall(text)) >= 3

# The answer cannot show a QR code, so a pointer to one is rewritten: dropped
# where the same sentence gives the link, kept as a page reference where the
# QR code is the only way in.
QR_WITH_LINK = (
    (re.compile(r"\s+hoặc\s+quét\s+mã\s+QR\s+(?:kế\s+bên|bên\s+dưới)"), ""),
    (re.compile(r"quét\s+mã\s+QR\s+hoặc\s+(?=truy\s+cập)"), ""),
)
QR_ONLY = re.compile(r"bằng\s+cách\s+quét\s+mã\s+QR\s+kế\s+bên")


def _without_qr_pointers(text: str, pages: list[int]) -> str:
    for pattern, replacement in QR_WITH_LINK:
        text = pattern.sub(replacement, text)
    where = f"trang {pages[0]}" if len(pages) == 1 else f"trang {pages[0]}–{pages[-1]}"
    text = QR_ONLY.sub(f"qua mã QR in trong Sổ tay sinh viên ({where})", text)
    if re.search(r"quét\s+mã\s+QR", text, re.IGNORECASE):
        raise ValueError(f"Unhandled QR pointer: {text[:200]}")
    return text


def _sentence_case(text: str) -> str:
    """"ĐÁNH GIÁ VỀ Ý THỨC (Tối đa 20 điểm)" -> "Đánh giá về ý thức (Tối đa 20 điểm)"."""
    head, bracket, tail = text.strip().partition(" (")
    if head.isupper():
        head = head[:1] + head[1:].lower()
    return head + (bracket + tail if bracket else "")


def _inline_numbering(text: str) -> str:
    """"1. Đơn ... 2. Bản sao ..." -> "(1) Đơn ...; (2) Bản sao ..." inside one line.

    Keeps a cell's numbered list inside the row line: the child builder
    starts a new chunk at a leading "1." and would cut the row apart.
    """
    text = re.sub(r"^(\d+)\.\s+", r"(\1) ", text.strip())
    return NUMBERED_ITEM.sub(lambda m: f"({m.group(1)}) ", text)


def _prose_lines(document: fitz.Document, pages: list[int], skip_areas: dict[int, fitz.Rect]) -> list[tuple[int, str]]:
    """Text lines of the pages in reading order, without page frame or table areas."""
    lines: list[tuple[int, str]] = []
    for number in pages:
        page = document[number - 1]
        area = skip_areas.get(number)
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = " ".join("".join(span["text"] for span in line["spans"]).split())
                if not text:
                    continue
                box = fitz.Rect(line["bbox"])
                if area is not None and area.contains(fitz.Point(box.x0 + 1, (box.y0 + box.y1) / 2)):
                    continue
                if PAGE_FRAME.match(text):
                    continue
                lines.append((number, text))
    return lines


def _join_wrapped(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Join a URL the PDF wrapped onto the next line (".../Quytrinh_" + "bieumau_daotao")."""
    joined: list[tuple[int, str]] = []
    for number, text in lines:
        if joined and re.search(r"https?://\S*[_/-]$", joined[-1][1]) and not text.startswith(("http", "–", "-", "+")):
            head, _, tail = text.partition(" ")
            joined[-1] = (joined[-1][0], joined[-1][1] + head + (" " + tail if tail else ""))
            continue
        joined.append((number, text))
    return joined


def _body_lines(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop letterhead and everything after the signature, as the article parser does."""
    body, after_signature = [], False
    for number, text in lines:
        kind = classify_line(text)
        if kind in {"administrative", "notice_title"}:
            continue
        if kind == "signature":
            after_signature = True
            continue
        if after_signature:
            continue
        body.append((number, text))
    return body


def _prose_sections(title: str, lines: list[tuple[int, str]]) -> list[dict[str, Any]]:
    """Split prose at top-level roman headings (I., II.); a document without them is one section."""
    sections: list[dict[str, Any]] = [{"title": title, "lines": [], "pages": []}]
    for number, text in lines:
        heading = SECTION_HEADING.match(text)
        if heading:
            sections.append({"title": f"{heading['code']}. {_sentence_case(heading['title'])}",
                             "lines": [], "pages": [number]})
            continue
        if STEP.match(text):
            text = f"- {text}"
        sections[-1]["lines"].append(text)
        sections[-1]["pages"].append(number)
    return [s for s in sections if s["lines"]]


def _row_lines(table: dict[str, Any], rows: list[list[str]]) -> list[str]:
    """A table with a header row: one line per data cell, naming its group, row and column."""
    header, *body = rows
    title = table["title"]
    group = ""
    lines = []
    for cells in body:
        code = cells[0].strip()
        filled = [cell for cell in cells if cell]
        if code and len(filled) == 2 and len(cells) < len(header) or code and len(filled) == 2 and not cells[-1]:
            group = next(cell for cell in cells[1:] if cell)  # "1 | Đối tượng được miễn 100% học phí"
            continue
        if len(cells) != len(header):
            continue
        subject = cells[1]
        label = f"mục {code}" if code else "mục"
        context = f"{title}{' – ' + group if group else ''}"
        lines.append(f"- {context} – {label}: {_inline_numbering(subject)}")
        short = re.split(r"[:;.]", subject, maxsplit=1)[0].strip()
        for column, value in zip(header[2:], cells[2:]):
            if value:
                lines.append(f"- {context} – {column} cho {label} ({short}): {_inline_numbering(value)}")
    return lines


def _framework_sections(table: dict[str, Any], rows: list[list[str]]) -> list[dict[str, Any]]:
    """The conduct score framework: one section per part (I-V), one line per scored item.

    Rows are an outline: part (I-V) > criterion (a, b, ...) > "–" item > "+" item.
    A row without points heads the rows below it; a row with points is written
    as one line carrying its whole path, e.g. "Phần II ... › a) ... ›
    Chấp hành quy định tham gia bảo hiểm y tế › Không tham gia ...: -5 điểm".
    """
    title = table["title"]
    sections: list[dict[str, Any]] = []
    notes: list[str] = []
    part = criterion = dash = plus = ""
    pending_criterion = ""  # a criterion with a range and, so far, no scored rows
    penalty_header: list[str] | None = None  # "Hình thức | Lần đầu | Lần thứ 2 trở lên | ..."
    penalty_width = 0

    def emit(leaf: str, points: str) -> None:
        nonlocal pending_criterion
        path = " › ".join(step for step in (part, criterion, dash, plus, leaf) if step)
        sections[-1]["lines"].append(f"- {title} › {path}: {points}")
        pending_criterion = ""

    def flush_pending() -> None:
        nonlocal pending_criterion
        if pending_criterion and sections:
            sections[-1]["lines"].append(f"- {title} › {part} › {pending_criterion}")
        pending_criterion = ""

    for raw in rows:
        cells = [cell.strip() for cell in raw]
        if "NỘI DUNG ĐÁNH GIÁ" in cells[:2]:  # header repeated on each page
            continue
        if _is_checkbox_row(" " + " ".join(cells)):
            continue
        if len(cells) == 1:  # footnote row: "Tổng điểm của phần 1 là 20 điểm, ..."
            notes.append(f"- {title} – {cells[0]}")
            continue
        if "Lần đầu" in cells:  # penalty sub-table: form | first time | repeat | note
            penalty_header, penalty_width = cells[1:], len(cells)
            continue
        if penalty_header and len(cells) == penalty_width:
            body = cells[1:]
            if sections:
                emit(body[0], f"{penalty_header[1].lower()} {body[1]}, {penalty_header[2].lower()} {body[2]} ({body[3]})")
            continue
        penalty_header = None
        # Code | content | points; evaluation columns (SV, LỚP, KHOA) are blank.
        code, text, points = (cells + ["", "", ""])[:3]
        text = text.rstrip(":").rstrip(".").strip() if points else text.rstrip(":").strip()
        if ROMAN.match(code):
            flush_pending()
            part = f"Phần {code.rstrip('.')}. {_sentence_case(text)}" + (f" ({points})" if points else "")
            sections.append({"title": part, "lines": []})
            criterion = dash = plus = ""
            continue
        if not sections:
            continue
        if LETTER.match(code):
            flush_pending()
            letter = code.rstrip(")")
            dash = plus = ""
            if points and "đến" not in points:  # a criterion scored as a whole
                criterion = ""
                emit(f"{letter}) {text}", points)
                criterion = f"{letter}) {text}"
                continue
            criterion = f"{letter}) {text}" + (f" ({points})" if points else "")
            pending_criterion = f"{criterion}" if points else ""
            continue
        marker = text[:1]
        leaf = text.lstrip("–+- ").strip()
        if marker == "+":
            if points:
                emit(leaf, points)
            else:
                plus = leaf
            continue
        # "–" item or an unmarked line (e.g. "Kết quả học tập của học kỳ đạt")
        plus = ""
        if points:
            dash = ""
            emit(leaf, points)
        else:
            dash = leaf
    flush_pending()
    if notes:
        sections.append({"title": "Quy định về tổng điểm", "lines": notes})
    return sections


FORM_TITLE = re.compile(r"^(ĐƠN|BIÊN BẢN|BẢNG|GIẤY|PHIẾU|DANH SÁCH|BẢN CAM KẾT|HỢP ĐỒNG)\b")
PLACEHOLDER = re.compile(r"…{2,}|\.{3,}")


def _form_lines(document: fitz.Document, pages: list[int]) -> list[str]:
    """One line per blank form: its title, qualifier and addressees, as printed."""
    lines = []
    for number in pages:
        text = [" ".join(line.split()) for line in document[number - 1].get_text().splitlines()]
        text = [line for line in text if line and not PAGE_FRAME.match(line)]
        index = next((i for i, line in enumerate(text) if FORM_TITLE.match(line)), None)
        if index is None:
            continue
        title = PLACEHOLDER.sub("", text[index]).strip()
        qualifier = text[index + 1] if index + 1 < len(text) else ""
        if not (qualifier.startswith("(") or qualifier[:1].isupper() and not qualifier.startswith(("Kính gửi", "HỌC KỲ", "Học kỳ"))):
            qualifier = ""
        follow = index + 2
        # A qualifier wrapped onto the next lines: an open bracket or a trailing comma.
        while qualifier and follow < len(text) and (qualifier.count("(") > qualifier.count(")") or qualifier.endswith(",")):
            qualifier += " " + text[follow]
            follow += 1
        qualifier = PLACEHOLDER.sub("", qualifier).strip(" :")
        recipients = []
        for i, line in enumerate(text):
            if line.startswith("Kính gửi"):
                first = line.partition(":")[2].strip()
                recipients += [first] if first else []
                for follow in text[i + 1:i + 4]:
                    if not follow.startswith("-"):
                        break
                    recipients.append(follow.lstrip("- ").strip())
                break
        recipients = [PLACEHOLDER.sub("", r).strip(" ;.:") for r in recipients]
        recipients = [r for r in recipients if r and r != "Đồng kính gửi"]
        line = f"- Mẫu {title}" + (f" ({qualifier.strip('()')})" if qualifier else "") + f", trang {number}"
        if recipients:
            line += f"; kính gửi: {'; '.join(recipients)}"
        lines.append(line + ".")
    return lines


def _parent(cohort_doc_id: str, index: int, document: dict[str, Any], section: dict[str, Any]) -> dict[str, Any]:
    pages = sorted(set(section.get("pages") or document["page_list"]))
    body = _without_qr_pointers("\n".join(section["lines"]), pages)
    content = build_section_content({"document_title": document["title"], "title": section["title"]}, body)
    return {
        "_id": f"{cohort_doc_id}_Phan{index}",
        "content": content,
        "normalized_content": content,
        "tables": [],
        "highlights": [],
        "metadata": {
            "source_type": "supplementary_document",
            "source_kind": document["kind"],
            "document_title": document["title"],
            "part": None,
            "chapter": None,
            "article": None,
            "title": section["title"],
            "source_pages": pages,
            "content_type": "regulation_text",
            "has_table": bool(document.get("tables")),
            "has_formula": False,
            "has_scoring_rule": document["kind"] == "score_framework",
            "has_thresholds": False,
        },
    }


def build_supplementary_parents(cohort: str, pdf_path: str | Path,
                                config_path: Path = CONFIG_PATH) -> list[dict[str, Any]]:
    """Parents for one cohort's supplementary documents (empty if none are configured)."""
    documents = (load_yaml(config_path).get("cohorts") or {}).get(cohort) or []
    pdf = fitz.open(str(pdf_path))
    parents: list[dict[str, Any]] = []
    for document in documents:
        first, last = document["pages"]
        pages = [p for p in range(first, last + 1) if p not in set(document.get("skip_pages") or [])]
        document = {**document, "page_list": pages}
        tables = document.get("tables") or []
        areas: dict[int, fitz.Rect] = {}
        sections: list[dict[str, Any]] = []
        for table in tables:
            table_pages = list(range(table["pages"][0], table["pages"][1] + 1))
            areas.update(table_areas(str(pdf_path), table_pages))
            rows = [row.cells for row in extract_ruled_table(str(pdf_path), table_pages)]
            if table["render"] == "score_framework":
                framework = _framework_sections(table, rows)
                for section in framework:
                    section["pages"] = table_pages
                sections.extend(framework)
            else:
                sections.append({"title": table["title"], "lines": _row_lines(table, rows), "pages": table_pages})
        if document["kind"] == "forms":
            sections = [{"title": document["title"], "lines": _form_lines(pdf, pages), "pages": pages}]
        elif document.get("prose", True):
            lines = _join_wrapped(_prose_lines(pdf, pages, areas))
            if document.get("start_at"):  # the text shares its page with the end of another document
                start = next(i for i, (_, text) in enumerate(lines) if document["start_at"] in text)
                lines = lines[start:]
            sections = _prose_sections(document["title"], _body_lines(lines)) + sections
        doc_id = f"{cohort}_{document['id']}"
        parents.extend(_parent(doc_id, index, document, section)
                       for index, section in enumerate(sections, 1) if section["lines"])
    return parents
