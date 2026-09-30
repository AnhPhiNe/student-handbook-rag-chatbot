"""Draw the official_v4 authoring tickets and write the batches for the external author.

Each ticket fixes, before any question exists, what one evaluation case will be
about: its cell (question kind), cohort, writing style and the handbook text it
draws on. The facts are sampled at random with a fixed seed, so neither the
system's author nor the external model picks easy or hard facts.

Outputs, under data/eval/official_v4/:
- tickets.json: every ticket, with source ids for the gold check (not shown to
  the external author);
- batches/batch_NN.md: the tickets as the external author sees them, with the
  handbook excerpts they need and nothing about the system.

Only public handbook content goes into a batch. Branch-campus content is left
out: the chatbot serves the main campus.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed"
OUT = ROOT / "data/eval/official_v4"
SEED = 20260930
COHORTS = ("K48-K49", "K50", "K51")

# Cell -> number of tickets. The design and its reasons are in official_v4/SPEC.md.
ALLOCATION = {
    "A.table.scoring": 6, "A.table.foreign_language": 6, "A.table.study_duration": 6,
    "A.table.scholarship": 6, "A.table.formula": 6, "A.directory.office": 6,
    "A.directory.faculty": 6, "A.directory.program": 6, "A.directory.student_service": 6,
    "A.regulation.policy": 10, "A.regulation.procedure": 10,
    "A.regulation.consequence": 10, "A.regulation.open": 6,
    "B.table_regulation": 18, "B.regulation_regulation": 18, "B.table_table": 18,
    "B.three_requests": 6, "B.over_limit": 6,
    "C.cohorts_table": 9, "C.cohorts_regulation": 9, "C.same_table": 6,
    "D.program_faculty": 6, "D.service_contact": 6,
    "E.cohort_switch": 6, "E.entity_switch": 6, "E.pronoun": 6, "E.topic_switch": 6,
    "F.clarify": 6, "F.partial_clarify": 6, "F.refuse_in_domain": 8,
    "F.out_of_domain": 6, "F.mixed_domain": 4,
}
VARIANT_PAIRS = 36  # base tickets from A and B that later get one rewritten variant each

STYLES = {  # style -> share of the base tickets
    "natural": 0.50, "informal": 0.20, "no_diacritics_or_typos": 0.15, "long_context": 0.15,
}
STYLE_TEXT = {
    "natural": "Tự nhiên, như sinh viên nhắn hỏi bình thường (có dấu, câu ngắn gọn).",
    "informal": "Văn nói, tiếng lóng hoặc viết tắt của sinh viên (vd: \"ktx\", \"hb\", \"đrl\", \"sđt\", \"cho em hỏi xíu\").",
    "no_diacritics_or_typos": "Gõ không dấu hoặc có lỗi gõ, như nhắn vội trên điện thoại.",
    "long_context": "Dài, kể hoàn cảnh của bản thân trước rồi mới hỏi; có thể có chi tiết thừa.",
}
TABLE_FAMILIES = {
    "scoring": {"grade_scale", "letter_to_grade4", "pass_fail_ungraded",
                "academic_classification", "conduct_classification"},
    "foreign_language": {"foreign_language_equivalency"},
    "study_duration": {"study_duration"},
    "scholarship": {"scholarship_amount", "scholarship_classification", "scholarship_eligibility"},
}
REGULATION_ASK = {
    "policy": "hỏi một quy định hoặc điều kiện nêu trong đoạn",
    "procedure": "hỏi thủ tục: cần làm gì, hồ sơ gì, nộp ở đâu, trong bao lâu",
    "consequence": "hỏi hệ quả nếu vi phạm hoặc không đáp ứng, hoặc một trường hợp ngoại lệ",
    "open": "câu hỏi mở, rộng về chủ đề của đoạn (vd: \"quy định về ... thế nào?\")",
}
DIRECTORY_FIELDS = ("số điện thoại", "email", "địa chỉ văn phòng")
OFFICE_DUTIES = "đơn vị này hỗ trợ sinh viên những việc gì"  # only office records list duties
MIN_ARTICLE_CHARS = 300
# Articles no student asks about: scope, entry into force, duties of ministries or
# units, budgeting. The rule looks at the article title only.
ADMIN_TITLE = re.compile(
    r"(?i)tổ chức thực hiện|hiệu lực|thi hành|phạm vi điều chỉnh|phạm vi và đối tượng|giải thích từ ngữ"
    r"|trách nhiệm của (các|ủy ban|cơ sở)|^trách nhiệm$|dự toán|kinh phí thực hiện|xác định nhu cầu đào tạo"
)
# Readable labels for the columns of the derived tables, whose keys are English.
COLUMN_LABELS = {
    "scholarship_level": "Loại học bổng", "criterion": "Tiêu chí", "requirement": "Yêu cầu",
    "formula": "Công thức", "language": "Ngôn ngữ", "certificate": "Chứng chỉ",
    "level_or_scale": "Thang điểm hoặc cấp độ", "equivalent_level_3": "Tương đương bậc 3",
    "equivalent_level_4": "Tương đương bậc 4", "multiplier": "Hệ số", "tuition_basis": "Căn cứ học phí",
    "label": "Mục", "scholarship_score_range": "Khoảng điểm học bổng",
    "academic_score_range": "Khoảng điểm học tập", "conduct_score_condition": "Điều kiện điểm rèn luyện",
    "academic_classification": "Xếp loại học tập",
    "conduct_classification_condition": "Điều kiện xếp loại rèn luyện", "output": "Kết quả",
    "academic_score_scale": "Thang điểm học tập", "conduct_score_scale": "Thang điểm rèn luyện",
    "input_requirements": "Yêu cầu đầu vào",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _is_branch(text: str) -> bool:
    lowered = text.lower()
    return "phân hiệu" in lowered or "long an" in lowered


class Pool:
    """Draws items without replacement, per cohort, refilling when a cohort runs out."""

    def __init__(self, rng: random.Random, items_by_cohort: dict[str, list]):
        self.rng = rng
        self.source = {c: list(items) for c, items in items_by_cohort.items() if items}
        self.left = {c: [] for c in self.source}

    def cohorts(self) -> list[str]:
        return sorted(self.source)

    def draw(self, cohort: str):
        if cohort not in self.source:
            cohort = self.rng.choice(self.cohorts())
        if not self.left[cohort]:
            self.left[cohort] = self.rng.sample(self.source[cohort], len(self.source[cohort]))
        return cohort, self.left[cohort].pop()


class Handbook:
    """The public handbook content the tickets draw on."""

    def __init__(self):
        self.articles: dict[str, dict] = {}
        for cohort in COHORTS:
            for item in _load(DATA / f"chunks/{cohort}_docstore_items.json"):
                self.articles[item["_id"]] = {**item["metadata"], "id": item["_id"], "content": item["content"]}
        self.tables = [t for t in _load(DATA / "tables/structured_tables_registry.json")
                       if self.article_id(t["source_parent_id"], t["cohort"])]
        self.formulas = [{**rule, "cohort": cohort}
                         for cohort in COHORTS
                         for rule in _load(DATA / f"tables/{cohort}_formula_rules.json")]
        self.directories = {
            kind: {cohort: [r for r in _load(DATA / f"directories/{cohort}_{kind}_directory.json")
                            if not _is_branch(json.dumps(r, ensure_ascii=False))]
                   for cohort in COHORTS}
            for kind in ("office", "faculty", "program")
        }
        self.services = [s for s in _load(DATA / "directories/student_service_directory.json")
                         if not _is_branch(json.dumps(s, ensure_ascii=False))]
        table_parents = {self.article_id(t["source_parent_id"], t["cohort"]) for t in self.tables}
        self.regulations = defaultdict(list)
        for article in self.articles.values():
            if (article["id"] in table_parents or len(article["content"]) < MIN_ARTICLE_CHARS
                    or ADMIN_TITLE.search(article.get("title") or "")
                    or _is_branch(article.get("title", "") + article.get("document_title", ""))):
                continue
            self.regulations[article["cohort"]].append(article["id"])

    def article_id(self, parent_id: str, cohort: str) -> str | None:
        for candidate in (parent_id, parent_id.removeprefix(f"{cohort}_")):
            if candidate in self.articles:
                return candidate
        return None

    def article_excerpt(self, article_id: str) -> dict:
        article = self.articles[article_id]
        label = " ".join(x for x in (article.get("article"), article.get("title")) if x)
        return {"kind": "article", "id": article_id, "cohort": article["cohort"],
                "heading": f"{article.get('document_title', '')} — {label}".strip(" —"),
                "text": article["content"]}


def _row_text(row: dict, columns: list[str] | None = None) -> str:
    """The row's printed columns only; lookup fields such as aliases stay out of the ticket."""
    keys = columns or [k for k, v in row.items() if isinstance(v, (str, int, float))]
    return "; ".join(f"{COLUMN_LABELS.get(k, k)} = {row[k]}" for k in keys if row.get(k) not in (None, ""))


def _contact_part(raw_text: str) -> str:
    """A faculty or office record up to the programmes and career text that follow its contacts."""
    lines = raw_text.splitlines()
    end = next((i for i, line in enumerate(lines) if line.isupper() and line.startswith("NGÀNH")), len(lines))
    return "\n".join(lines[:end])


def _by_cohort(items, key="cohort"):
    grouped = defaultdict(list)
    for item in items:
        grouped[item[key]].append(item)
    return grouped


class Drawer:
    def __init__(self, handbook: Handbook, rng: random.Random):
        self.hb = handbook
        self.rng = rng
        self.table_pools = {
            family: Pool(rng, _by_cohort([t for t in handbook.tables if t["table_subtype"] in subtypes]))
            for family, subtypes in TABLE_FAMILIES.items()
        }
        self.formula_pool = Pool(rng, _by_cohort(handbook.formulas))
        self.directory_pools = {kind: Pool(rng, by_cohort) for kind, by_cohort in handbook.directories.items()}
        self.service_pool = Pool(rng, _by_cohort(handbook.services))
        self.regulation_pool = Pool(rng, dict(handbook.regulations))

    # One "request": a piece of handbook content plus what the student should ask about it.
    def table_request(self, family: str, cohort: str) -> dict:
        if family == "formula":
            cohort, rule = self.formula_pool.draw(cohort)
            article = self.hb.article_id(rule["source_parent_id"], cohort)
            return {"source": self.hb.article_excerpt(article),
                    "ask": f"hỏi cách tính theo công thức \"{rule['rule_name']}\"; có thể đưa số liệu "
                           "của bản thân để nhờ tính"}
        cohort, table = self.table_pools[family].draw(cohort)
        row = self.rng.choice(table["rows"])
        shown = _row_text(row, table.get("columns"))
        article = self.hb.article_id(table["source_parent_id"], cohort)
        return {"source": self.hb.article_excerpt(article),
                "ask": f"hỏi một giá trị trong bảng \"{table.get('table_name') or table.get('title')}\", "
                       f"ở dòng: {shown}. Sinh viên nêu phần mình đã biết và hỏi phần còn lại"}

    def directory_request(self, kind: str, cohort: str) -> dict:
        cohort, record = self.directory_pools[kind].draw(cohort)
        name = record.get("unit_name") or record.get("faculty_or_unit_name") or record.get("program_name")
        if kind == "program":
            ask = f"hỏi ngành \"{record['program_name']}\" thuộc khoa nào, hoặc hỏi liên hệ của khoa quản lý ngành đó"
            text = f"Ngành {record['program_name']} thuộc {record.get('faculty_name', '')}."
        else:
            fields = DIRECTORY_FIELDS + ((OFFICE_DUTIES,) if kind == "office" else ())
            ask = f"hỏi {self.rng.choice(fields)} của \"{name.split('. ', 1)[-1]}\""
            text = _contact_part(record["raw_text"])
        return {"source": {"kind": kind, "id": record.get("record_id"), "cohort": cohort,
                           "heading": f"Danh bạ trong Sổ tay sinh viên {cohort}", "text": text},
                "ask": ask}

    def service_request(self, cohort: str) -> dict:
        cohort, service = self.service_pool.draw(cohort)
        contact = "\n".join(f"{label}: {service.get(key)}" for label, key in
                            (("Đơn vị", "unit_name"), ("Điện thoại", "phone"), ("Email", "email"),
                             ("Địa chỉ", "office")) if service.get(key))
        return {"source": {"kind": "service", "id": service["service_id"], "cohort": cohort,
                           "heading": f"Danh bạ trong Sổ tay sinh viên {cohort}",
                           "text": f"Công việc hỗ trợ sinh viên: {service['service']}\n{contact}"},
                "ask": "sinh viên kể nhu cầu bằng lời thường (không nêu tên đơn vị) và hỏi nên liên hệ ai, ở đâu",
                "service": service}

    def regulation_request(self, intent: str, cohort: str) -> dict:
        _, article_id = self.regulation_pool.draw(cohort)
        return {"source": self.hb.article_excerpt(article_id), "ask": REGULATION_ASK[intent]}

    def any_table(self, cohort: str) -> dict:
        families = [f for f, pool in self.table_pools.items() if cohort in pool.cohorts()]
        return self.table_request(self.rng.choice([*families, "formula"]), cohort)

    def any_structured(self, cohort: str) -> dict:
        roll = self.rng.random()
        if roll < 0.5:
            return self.any_table(cohort)
        if roll < 0.8:
            return self.directory_request(self.rng.choice(["office", "faculty", "program"]), cohort)
        return self.service_request(cohort)

    def any_regulation(self, cohort: str) -> dict:
        return self.regulation_request(self.rng.choice(list(REGULATION_ASK)), cohort)

    def cohort_pair(self, cohort: str, other: str, *, table: bool) -> tuple[list[dict], str, str]:
        """The same content in two cohorts: a table of one family, or the same article."""
        if table:
            family = self.rng.choice([f for f, p in self.table_pools.items() if len(p.cohorts()) > 1])
            first, second = self.rng.sample(self.table_pools[family].cohorts(), 2)
            return [self.table_request(family, first), self.table_request(family, second)], first, second
        for _ in range(50):
            request = self.any_regulation(cohort)
            match = self.matching_article(request["source"]["id"], other)
            if match:
                return [request, {"source": self.hb.article_excerpt(match), "ask": request["ask"]}], cohort, other
        raise RuntimeError(f"no article shared by {cohort} and {other}")

    def matching_article(self, article_id: str, other_cohort: str) -> str | None:
        """The same document and article in another cohort's handbook, if it exists."""
        a = self.hb.articles[article_id]
        for candidate in self.hb.regulations.get(other_cohort, []):
            b = self.hb.articles[candidate]
            if b.get("document_title") == a.get("document_title") and b.get("article") == a.get("article"):
                return candidate
        return None


CELL_TEXT = {
    "A.table": "Câu hỏi đơn: một yêu cầu tra một giá trị trong bảng.",
    "A.directory": "Câu hỏi đơn: một yêu cầu tra danh bạ.",
    "A.regulation": "Câu hỏi đơn: một yêu cầu về quy định.",
    "B": "Một tin nhắn chứa nhiều yêu cầu độc lập; mỗi yêu cầu cần một đáp án riêng, không gộp được thành một.",
    "B.over_limit": "Một tin nhắn chứa {n} yêu cầu độc lập (nhiều hơn 3).",
    "C.cohorts": "So sánh giữa hai khóa: sinh viên nêu rõ cả hai khóa và hỏi điểm khác nhau hoặc giống nhau.",
    "C.same_table": "So sánh hai dòng trong cùng một bảng.",
    "D.program_faculty": "Sinh viên chỉ nêu tên ngành và hỏi liên hệ (email, điện thoại hoặc văn phòng) của khoa quản lý ngành đó; không nêu tên khoa.",
    "D.service_contact": "Sinh viên kể một việc cần làm và hỏi số điện thoại hoặc email của đơn vị phụ trách; không nêu tên đơn vị.",
    "E": "Hội thoại hai lượt. Viết lượt hỏi 1, một câu trả lời ngắn và đúng cho lượt 1 (dựa trên đoạn sổ tay), rồi lượt hỏi 2. Chỉ lượt 2 được chấm.",
    "E.cohort_switch": "Lượt 2 hỏi đúng nội dung đó nhưng cho khóa khác (vd: \"còn khóa {other} thì sao?\"), không nhắc lại nội dung.",
    "E.entity_switch": "Lượt 2 hỏi cùng loại thông tin cho một đối tượng khác, câu hỏi ngắn và dựa vào lượt 1 (vd: \"thế còn ... ?\").",
    "E.pronoun": "Lượt 2 hỏi thêm về cùng đối tượng nhưng chỉ dùng đại từ (\"nó\", \"chỗ đó\", \"phòng đó\"...), không nhắc lại tên.",
    "E.topic_switch": "Lượt 2 chuyển sang chủ đề mới hoàn toàn, không liên quan lượt 1; câu trả lời đúng không được dùng gì từ lượt 1.",
    "F.clarify": "Sinh viên hỏi nhưng thiếu thông tin bắt buộc để trả lời (vd: không nói điểm, không nói loại chứng chỉ). Đáp án đúng là hỏi lại đúng thông tin còn thiếu.",
    "F.partial_clarify": "Hai yêu cầu: yêu cầu 1 trả lời được từ đoạn sổ tay; yêu cầu 2 thiếu thông tin bắt buộc. Đáp án đúng: trả lời yêu cầu 1 và hỏi lại cho yêu cầu 2.",
    "F.refuse_in_domain": "Câu hỏi về việc học ở trường nhưng sổ tay không thể trả lời: dữ liệu cá nhân (\"em có tên trong danh sách chưa\", \"điểm của em bao nhiêu\"), mốc thời gian hoặc số tiền của năm học cụ thể, tên người cụ thể... Tự nghĩ câu hỏi; đáp án đúng là nói sổ tay không có và gợi ý hỏi đơn vị phù hợp nếu có.",
    "F.out_of_domain": "Câu hỏi không liên quan đến quy định và dịch vụ sinh viên của trường (vd: thời tiết, nấu ăn, bài tập lập trình). Tự nghĩ câu hỏi; đáp án đúng là từ chối lịch sự.",
    "F.mixed_domain": "Hai yêu cầu: một yêu cầu trả lời được từ đoạn sổ tay, một yêu cầu ngoài phạm vi trường. Đáp án đúng: trả lời phần trong phạm vi, từ chối phần ngoài phạm vi.",
}


def _cell_family(cell: str) -> str:
    return cell.split(".", 1)[0]


def build_ticket(drawer: Drawer, cell: str, cohort: str) -> dict:
    rng = drawer.rng
    requests: list[dict] = []
    task, history_turns, expected = CELL_TEXT.get(cell, ""), 1, "answer"
    other = rng.choice([c for c in COHORTS if c != cohort])

    if cell.startswith("A.table."):
        task = CELL_TEXT["A.table"]
        requests = [drawer.table_request(cell.rsplit(".", 1)[1], cohort)]
    elif cell == "A.directory.student_service":
        task = CELL_TEXT["A.directory"]
        requests = [drawer.service_request(cohort)]
    elif cell.startswith("A.directory."):
        task = CELL_TEXT["A.directory"]
        requests = [drawer.directory_request(cell.rsplit(".", 1)[1], cohort)]
    elif cell.startswith("A.regulation."):
        task = CELL_TEXT["A.regulation"]
        requests = [drawer.regulation_request(cell.rsplit(".", 1)[1], cohort)]
    elif cell == "B.table_regulation":
        task, requests = CELL_TEXT["B"], [drawer.any_structured(cohort), drawer.any_regulation(cohort)]
    elif cell == "B.regulation_regulation":
        task, requests = CELL_TEXT["B"], [drawer.any_regulation(cohort), drawer.any_regulation(cohort)]
    elif cell == "B.table_table":
        task, requests = CELL_TEXT["B"], [drawer.any_structured(cohort), drawer.any_structured(cohort)]
    elif cell == "B.three_requests":
        draws = [drawer.any_structured, drawer.any_regulation, rng.choice([drawer.any_structured, drawer.any_regulation])]
        task, requests = CELL_TEXT["B"], [draw(cohort) for draw in draws]
    elif cell == "B.over_limit":
        n = rng.choice([4, 5])
        task = CELL_TEXT["B.over_limit"].format(n=n)
        requests = [rng.choice([drawer.any_structured, drawer.any_regulation])(cohort) for _ in range(n)]
        expected = "answer_or_ask_to_choose"  # both are acceptable; see SPEC.md
    elif cell in ("C.cohorts_table", "C.cohorts_regulation"):
        task = CELL_TEXT["C.cohorts"]
        requests, cohort, other = drawer.cohort_pair(cohort, other, table=cell == "C.cohorts_table")
    elif cell == "C.same_table":
        task = CELL_TEXT["C.same_table"]
        family = rng.choice(["scoring", "scholarship", "study_duration"])
        cohort, table = drawer.table_pools[family].draw(cohort)
        rows = rng.sample(table["rows"], 2) if len(table["rows"]) > 1 else table["rows"]
        shown = " | ".join(_row_text(r, table.get("columns")) for r in rows)
        requests = [{"source": drawer.hb.article_excerpt(drawer.hb.article_id(table["source_parent_id"], cohort)),
                     "ask": f"so sánh hai dòng của bảng \"{table.get('table_name') or table.get('title')}\": {shown}"}]
    elif cell == "D.program_faculty":
        task = CELL_TEXT["D.program_faculty"]
        program = drawer.directory_request("program", cohort)
        faculty_name = next((r for r in drawer.hb.directories["program"][program["source"]["cohort"]]
                             if r.get("record_id") == program["source"]["id"]), {}).get("faculty_name", "")
        faculty = next((r for r in drawer.hb.directories["faculty"][program["source"]["cohort"]]
                        if faculty_name and faculty_name in r.get("faculty_or_unit_name", "")), None)
        requests = [program]
        if faculty:
            requests.append({"source": {"kind": "faculty", "id": faculty["record_id"], "cohort": program["source"]["cohort"],
                                        "heading": "Danh bạ khoa", "text": _contact_part(faculty["raw_text"])},
                             "ask": "liên hệ của khoa quản lý ngành trên"})
    elif cell == "D.service_contact":
        task, requests = CELL_TEXT["D.service_contact"], [drawer.service_request(cohort)]
    elif cell.startswith("E."):
        task = CELL_TEXT["E"] + " " + CELL_TEXT[cell].format(other=other)
        history_turns = 2
        if cell == "E.cohort_switch":
            requests, cohort, other = drawer.cohort_pair(cohort, other, table=rng.random() < 0.5)
            task = CELL_TEXT["E"] + " " + CELL_TEXT[cell].format(other=other)
        elif cell == "E.entity_switch":
            kind_ = rng.choice(["office", "faculty", "program"])
            requests = [drawer.directory_request(kind_, cohort), drawer.directory_request(kind_, cohort)]
        elif cell == "E.pronoun":
            requests = [rng.choice([drawer.any_structured, drawer.any_regulation])(cohort)]
        else:
            requests = [drawer.any_structured(cohort), drawer.any_regulation(cohort)]
    elif cell == "F.clarify":
        task, requests, expected = CELL_TEXT[cell], [drawer.any_table(cohort)], "clarify"
    elif cell == "F.partial_clarify":
        task, expected = CELL_TEXT[cell], "answer_and_clarify"
        requests = [drawer.any_structured(cohort), drawer.any_table(cohort)]
    elif cell == "F.refuse_in_domain":
        task, expected = CELL_TEXT[cell], "refuse"
    elif cell == "F.out_of_domain":
        task, expected = CELL_TEXT[cell], "refuse"
    elif cell == "F.mixed_domain":
        task, expected = CELL_TEXT[cell], "answer_and_refuse"
        requests = [rng.choice([drawer.any_structured, drawer.any_regulation])(cohort)]
    for request in requests:
        request.pop("service", None)
    # A cohort without the drawn table (only K50 has the language table) gives the ticket its source's cohort.
    source_cohorts = {r["source"]["cohort"] for r in requests}
    if len(source_cohorts) == 1 and not cell.startswith(("C.cohorts", "E.cohort_switch")):
        cohort = source_cohorts.pop()
    return {"cell": cell, "family": _cell_family(cell), "cohort": cohort,
            "compare_cohort": other if cell.startswith(("C.cohorts", "E.cohort_switch")) else None,
            "task": task, "turns": history_turns, "expected_behavior": expected, "requests": requests}


def draw_all(seed: int) -> list[dict]:
    rng = random.Random(seed)
    drawer = Drawer(Handbook(), rng)
    tickets = []
    for cell, count in ALLOCATION.items():
        cohorts = [COHORTS[i % 3] for i in range(count)]
        rng.shuffle(cohorts)
        for cohort in cohorts:
            tickets.append(build_ticket(drawer, cell, cohort))
    # Styles: exact quotas over all base tickets, assigned at random.
    styles = [s for s, share in STYLES.items() for _ in range(round(share * len(tickets)))]
    styles += ["natural"] * (len(tickets) - len(styles))
    rng.shuffle(styles)
    for index, (ticket, style) in enumerate(zip(tickets, styles), start=1):
        ticket["id"] = f"V4-{index:03d}"
        ticket["style"] = style
    # Variant pairs: base tickets from A and B written naturally get one rewrite later.
    candidates = [t for t in tickets if t["family"] in ("A", "B") and t["style"] == "natural"]
    variant_styles = ["informal", "no_diacritics_or_typos", "long_context"] * (VARIANT_PAIRS // 3)
    for ticket, style in zip(rng.sample(candidates, VARIANT_PAIRS), variant_styles):
        ticket["variant_style"] = style
    return tickets


def _source_key(source: dict) -> tuple:
    return source["kind"], source["id"], source["cohort"]


def _batch_chars(batch: list[dict]) -> int:
    sources = {_source_key(r["source"]): r["source"] for t in batch for r in t["requests"]}
    return sum(len(s["text"]) for s in sources.values()) + 600 * len(batch)


def split_batches(tickets: list[dict], max_chars: int, max_tickets: int) -> list[list[dict]]:
    """Consecutive tickets up to a size budget, counting each shared excerpt once."""
    batches: list[list[dict]] = [[]]
    for ticket in tickets:
        candidate = batches[-1] + [ticket]
        if batches[-1] and (len(candidate) > max_tickets or _batch_chars(candidate) > max_chars):
            batches.append([ticket])
        else:
            batches[-1] = candidate
    return batches


def render_batch(number: int, batch: list[dict]) -> str:
    """The tickets, then each handbook excerpt once, labelled Đ1, Đ2... in order of first use."""
    labels: dict[tuple, str] = {}
    excerpts: list[str] = []
    cards: list[str] = []
    for ticket in sorted(batch, key=lambda t: t["id"]):
        lines = [f"### {ticket['id']}",
                 f"- Khóa của sinh viên: {ticket['cohort']}"
                 + (f" (so sánh với khóa {ticket['compare_cohort']})" if ticket.get("compare_cohort") else ""),
                 f"- Loại câu hỏi: {ticket['task']}",
                 f"- Kiểu viết: {STYLE_TEXT[ticket['style']]}"]
        for index, request in enumerate(ticket["requests"], start=1):
            source = request["source"]
            key = _source_key(source)
            if key not in labels:
                labels[key] = f"Đ{len(labels) + 1}"
                excerpts.append(f"### {labels[key]} ({source['cohort']}) {source['heading']}\n"
                                f"```text\n{source['text'].strip()}\n```")
            lines.append(f"- Yêu cầu {index}: {request['ask']}. Dựa trên đoạn {labels[key]}.")
        cards.append("\n".join(lines))
    return (f"# Đợt {number:02d}: {len(batch)} phiếu\n\n## Phiếu\n\n" + "\n\n".join(cards)
            + "\n\n## Các đoạn sổ tay\n\n" + "\n\n".join(excerpts) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--pilot", type=int, default=15, help="Tickets in batch 00, one or more per family.")
    parser.add_argument("--max-chars", type=int, default=60_000, help="Size budget of one batch.")
    parser.add_argument("--max-tickets", type=int, default=30)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing draw.")
    args = parser.parse_args()
    if (OUT / "tickets.json").exists() and not args.force:
        raise SystemExit("official_v4/tickets.json exists; the draw is frozen. Use --force only before authoring starts.")

    tickets = draw_all(args.seed)
    rng = random.Random(args.seed + 1)
    by_family = defaultdict(list)
    for t in tickets:
        by_family[t["family"]].append(t)
    pilot = [rng.choice(group) for group in by_family.values()]
    pilot += rng.sample([t for t in tickets if t not in pilot], args.pilot - len(pilot))
    remaining = sorted((t for t in tickets if t not in pilot), key=lambda t: (t["family"], t["cell"], t["cohort"]))
    batches = [pilot] + split_batches(remaining, args.max_chars, args.max_tickets)
    for number, batch in enumerate(batches):
        for t in batch:
            t["batch"] = number

    (OUT / "batches").mkdir(parents=True, exist_ok=True)
    for old in (OUT / "batches").glob("batch_*.md"):
        old.unlink()
    (OUT / "tickets.json").write_text(json.dumps({"seed": args.seed, "allocation": ALLOCATION, "tickets": tickets},
                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    for number, batch in enumerate(batches):
        (OUT / "batches" / f"batch_{number:02d}.md").write_text(render_batch(number, batch), encoding="utf-8")
    print(f"{len(tickets)} tickets, {len(batches)} batches (pilot {len(pilot)}) -> {OUT.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
