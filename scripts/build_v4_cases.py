"""Convert the authored official_v4 set into the answers-suite case file.

Reads the tickets, Gemini's authored YAML (via check_v4_authored.load_authored)
and gold_adjustments.yaml, and writes data/eval/official_v4/generated_answer_cases.json
for `scripts/run_official_answers.py --suite answers --bundle official_v4`.
Questions are copied as authored; only the scoring fields named in
gold_adjustments.yaml are replaced, and its cohort migration moves the cases of a
retired cohort (K48-K49) to the cohort that replaced it (K49). Clusters are
computed from the authored gold.
"""
import json
import re
import unicodedata
from pathlib import Path

import yaml

from scripts.check_v4_authored import load_authored

ROOT = Path(__file__).resolve().parents[1]
V4 = ROOT / "data/eval/official_v4"
BATCHES = 13
CLUSTER_THRESHOLD = 0.8

BEHAVIOUR = {
    "tra_loi": "direct_answer",
    "tra_loi_va_hoi_lai": "direct_answer",
    "tra_loi_va_tu_choi": "direct_answer",
    "hoi_lai": "clarify_or_scope",
    "tu_choi": "abstain",
}
ROLES = {"sinh_vien": "user", "tro_ly": "assistant"}

BASE_NOTE = (
    "Chấm tương đương ngữ nghĩa, không khớp nguyên văn gold. Phải trả lời mọi ý được hỏi; "
    "thông tin thêm đúng thì không trừ điểm. Với nhiều khóa hoặc nhiều đơn vị, mỗi kết quả phải "
    "gắn đúng đối tượng. Chấp nhận số viết tương đương (06 = 6, 3,5 = 3.5)."
)
CELL_NOTES = {
    "B.over_limit": "Câu hỏi có hơn ba yêu cầu: trả lời hết, hoặc đề nghị sinh viên chọn tối đa ba ý, đều đúng.",
    "F.clarify": "Thiếu một thông tin để có một đáp án: hỏi lại thông tin còn thiếu, hoặc trả lời mọi trường hợp kèm điều kiện, đều đúng.",
    "F.partial_clarify": "Trả lời ý đủ dữ kiện; với ý thiếu dữ kiện, hỏi lại hoặc trả lời theo từng trường hợp đều đúng.",
    "F.out_of_domain": "Câu hỏi ngoài phạm vi sổ tay: từ chối lịch sự là đúng; không bịa thông tin.",
    "F.mixed_domain": "Trả lời ý thuộc sổ tay; từ chối ý ngoài phạm vi.",
}
FAMILY_NOTES = {
    "E": "Chỉ chấm câu trả lời cho lượt hỏi cuối; các lượt trước là ngữ cảnh hội thoại.",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text).casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(re.findall(r"\w+", text))


def _trigrams(facts: list[str]) -> set[tuple]:
    words = _norm(" | ".join(facts)).split()
    return {tuple(words[i:i + 3]) for i in range(len(words) - 2)}


def clusters(required: dict[str, list[str]]) -> dict[str, str]:
    """Cases whose required facts share >= 80% word 3-grams (Jaccard) form one cluster."""
    ids = sorted(required)
    grams = {case_id: _trigrams(required[case_id]) for case_id in ids}
    parent = {case_id: case_id for case_id in ids}

    def root(case_id):
        while parent[case_id] != case_id:
            case_id = parent[case_id]
        return case_id

    for i, left in enumerate(ids):
        for right in ids[i + 1:]:
            a, b = grams[left], grams[right]
            if a and b and len(a & b) / len(a | b) >= CLUSTER_THRESHOLD:
                parent[root(right)] = root(left)
    return {case_id: root(case_id) for case_id in ids}


def _citations(ticket: dict, migration: dict | None = None) -> list[dict]:
    citations = []
    for request in ticket["requests"]:
        source = request.get("source") or {}
        if source.get("kind") != "article":
            continue
        source_id, cohort = source["id"], source["cohort"]
        if migration and cohort == migration["from"]:
            source_id, cohort = _migrated_parent(source_id, migration), migration["to"]
        if not source_id.startswith(cohort):
            source_id = f"{cohort}_{source_id}"
        citations.append({"parent_section_id": source_id, "cohort": cohort})
    return citations


def _migrated_parent(source_id: str, migration: dict) -> str:
    """The parent replacing a retired cohort's parent: named, or the same id under the new prefix."""
    if source_id in migration.get("parents", {}):
        return migration["parents"][source_id]
    for prefix in migration["id_prefixes"]:
        if source_id.startswith(prefix):
            return f"{migration['to']}_{source_id.removeprefix(prefix)}"
    raise ValueError(f"No migrated parent for {source_id}")


def _relabel(text: str, pairs: list[list[str]]) -> str:
    for old, new in pairs:
        text = re.sub(rf"(?<![\w-]){re.escape(old)}(?![\w-])", new, text)
    return text


def _relabel_all(texts: list[str], pairs: list[list[str]]) -> list[str]:
    return [_relabel(text, pairs) for text in texts]


def _replace(texts: list[str], pairs: list[list[str]], case_id: str) -> list[str]:
    for old, new in pairs:
        if not any(old in text for text in texts):
            raise ValueError(f"{case_id}: replace text not found: {old!r}")
        texts = [text.replace(old, new) for text in texts]
    return texts


def build() -> list[dict]:
    tickets = {t["id"]: t for t in json.loads((V4 / "tickets.json").read_text(encoding="utf-8"))["tickets"]}
    authored = {case["phieu"]: case for batch in range(BATCHES) for case in load_authored(batch)}
    adjustments = yaml.safe_load((V4 / "gold_adjustments.yaml").read_text(encoding="utf-8"))
    adjusted = adjustments["cases"]
    migration = adjustments.get("cohort_migration")
    rule_notes = {case_id: rule["rule"] for rule in adjustments["rules"].values() for case_id in rule["cases"]}
    cluster_of = clusters({case_id: case["y_bat_buoc"] for case_id, case in authored.items()})

    cases = []
    for case_id in sorted(tickets):
        ticket, case = tickets[case_id], authored[case_id]
        turns = [t["noi_dung"] for t in case["hoi_thoai"]]
        behaviour = "clarify_or_scope" if ticket["cell"] == "B.over_limit" else BEHAVIOUR[case["hanh_vi"]]
        required, ground_truth = case["y_bat_buoc"], case["dap_an_nhap"]
        notes = [BASE_NOTE, FAMILY_NOTES.get(ticket["family"]), CELL_NOTES.get(ticket["cell"]), rule_notes.get(case_id)]
        cohorts = [ticket["cohort"]] + ([ticket["compare_cohort"]] if ticket.get("compare_cohort") else [])
        migrated = bool(migration) and migration["from"] in cohorts
        if migrated:
            cohorts = [migration["to"] if c == migration["from"] else c for c in cohorts]
            turns, required = (_relabel_all(x, migration["labels"]) for x in (turns, required))
            ground_truth = _relabel(ground_truth, migration["labels"])
        if case_id in adjusted:
            entry = adjusted[case_id]
            if entry.get("replace"):
                n_turns, n_required = len(turns), len(required)
                texts = _replace([*turns, *required, ground_truth], entry["replace"], case_id)
                turns, required, ground_truth = texts[:n_turns], texts[n_turns:n_turns + n_required], texts[-1]
            if "y_bat_buoc" in entry:
                required = entry["y_bat_buoc"]
                ground_truth = "Đáp án đã điều chỉnh trước khi chạy: " + " | ".join(required)
            when = "for the K49 handbook" if migrated else "before any run"
            notes.append(f"Gold adjusted {when}: " + " ".join(entry["reason"].split()))
        cases.append({
            "id": case_id,
            "suite": "answers",
            "query": turns[-1],
            "cohort": cohorts[0],
            "history": [{"role": ROLES[t["vai"]], "content": text} for t, text in zip(case["hoi_thoai"], turns[:-1])],
            "topic": ticket["family"],
            "case_type": ticket["cell"],
            "cluster": cluster_of[case_id],
            "expected_path": None,
            "expected_answer_behavior": behaviour,
            "answerability": "unanswerable" if case["hanh_vi"] == "tu_choi" else "answerable",
            "question_style": ticket["style"],
            "eval_split": "realistic",
            "tags": ["official_v4", ticket["family"], ticket["cell"], ticket["style"]],
            "ground_truth": ground_truth,
            "required_facts": required,
            "forbidden_claims": [],
            "expected_citations": _citations(ticket, migration),
            "sources": case.get("nguon") or [],
            "requested_cohorts": cohorts,
            "cohort_sensitivity": "multi_cohort_risk" if len(cohorts) > 1 else "single_cohort",
            "question_specificity": "ambiguous" if behaviour == "clarify_or_scope" else "specific",
            "lexical_fact_check_applicable": False,
            "evaluation_notes": " ".join(note for note in notes if note),
            "gold_adjusted": case_id in adjusted,
            "review_status": "author_reviewed",
            "review_method": "Authored by Gemini 3.8 Flash from handbook excerpts; gold reviewed by the system author with Claude; not independent human review",
            "frozen": True,
            "independent_holdout": True,
        })
    return cases


def main() -> None:
    cases = build()
    (V4 / "generated_answer_cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    multi = sum(1 for c in {case["cluster"] for case in cases} if sum(case["cluster"] == c for case in cases) > 1)
    print(f"{len(cases)} cases, {len({case['cluster'] for case in cases})} clusters ({multi} with more than one case)")


if __name__ == "__main__":
    main()
