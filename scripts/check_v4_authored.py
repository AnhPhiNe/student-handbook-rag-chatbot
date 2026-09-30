"""Check one authored official_v4 batch against its tickets.

Reports, per case: tickets the author could not write, the writing style
against the ticket's, the expected behaviour, excerpts cited from a cohort the
ticket does not cover, and every number, email, phone or web address in the
draft answer and required facts that its excerpts do not contain. It changes
nothing: the report says what to look at; dropping a case needs a stated
reason (SPEC.md, rule 4).
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata

import yaml

from scripts.draw_v4_tickets import OUT, _source_key

BEHAVIOUR = {  # ticket expectation -> author labels accepted for it
    "answer": {"tra_loi"},
    "clarify": {"hoi_lai"},
    "refuse": {"tu_choi"},
    "answer_and_clarify": {"tra_loi_va_hoi_lai"},
    "answer_and_refuse": {"tra_loi_va_tu_choi"},
    "answer_or_ask_to_choose": {"tra_loi", "hoi_lai", "tra_loi_va_hoi_lai"},
}
INFORMAL_MARKERS = re.compile(
    r"(?i)\b(xíu|z|ạ\?|ko|k|dc|đc|ktx|hb|hbkkht|đrl|drl|sđt|sdt|sv|ad|mn|nha|nhé|vậy|zới|oi|ơi|e)\b")
FACT_TOKEN = re.compile(
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"          # email
    r"|(?:https?://)?[\w-]+(?:\.[\w-]+)*\.(?:edu|com|gov|org)\.vn\S*"  # web address
    r"|\(0\d{2,3}\)\s?\d[\d .]{5,}\d"        # phone
    r"|\d+(?:[.,]\d+)*"                       # number
)


def _labels(batch: list[dict]) -> dict[str, tuple]:
    """Đ labels in the order render_batch assigns them."""
    labels: dict[tuple, str] = {}
    for ticket in sorted(batch, key=lambda t: t["id"]):
        for request in ticket["requests"]:
            key = _source_key(request["source"])
            labels.setdefault(key, f"Đ{len(labels) + 1}")
    return {label: key for key, label in labels.items()}


def _has_diacritics(text: str) -> bool:
    return any(unicodedata.decomposition(c) for c in text if c.isalpha() and ord(c) > 127 and c not in "đĐ")


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text).replace(",", ".").lower()


def check(batch_number: int) -> list[str]:
    tickets = json.loads((OUT / "tickets.json").read_text(encoding="utf-8"))["tickets"]
    batch = [t for t in tickets if t["batch"] == batch_number]
    by_id = {t["id"]: t for t in batch}
    labels = _labels(batch)
    sources = {_source_key(r["source"]): r["source"] for t in batch for r in t["requests"]}
    authored = yaml.safe_load((OUT / "authored" / f"batch_{batch_number:02d}.yaml").read_text(encoding="utf-8"))

    report: list[str] = []
    ids = [case["phieu"] for case in authored]
    expected_ids = sorted(by_id)
    if ids != expected_ids:
        report.append(f"ids differ: missing {sorted(set(expected_ids) - set(ids))}, "
                      f"extra {sorted(set(ids) - set(expected_ids))}")
    for case in authored:
        ticket = by_id.get(case["phieu"])
        if ticket is None:
            continue
        notes: list[str] = []
        if case.get("khong_phu_hop"):
            report.append(f"{ticket['id']} {ticket['cell']}: NOT WRITTEN - {case['khong_phu_hop']}")
            continue
        student = [turn["noi_dung"] for turn in case["hoi_thoai"] if turn["vai"] == "sinh_vien"]
        question = " ".join(student)
        style = ticket["style"]
        if style == "no_diacritics_or_typos" and _has_diacritics(question):
            notes.append("style: diacritics in a no-diacritics ticket")
        if style == "long_context" and len(student[0]) < 250:
            notes.append(f"style: long_context but {len(student[0])} chars")
        if style == "informal" and not INFORMAL_MARKERS.search(question):
            notes.append("style: no informal marker")
        if style == "natural" and len(ticket["requests"]) <= 1 and len(student[-1]) > 350:
            notes.append(f"style: natural but {len(student[-1])} chars")
        if ticket["turns"] == 2 and len(case["hoi_thoai"]) != 3:
            notes.append(f"turns: {len(case['hoi_thoai'])} instead of 3")
        if case.get("hanh_vi") not in BEHAVIOUR[ticket["expected_behavior"]]:
            notes.append(f"behaviour: {case.get('hanh_vi')} for {ticket['expected_behavior']}")

        cited = {m for entry in case.get("nguon") or [] for m in re.findall(r"Đ\d+", entry)}
        allowed_cohorts = {ticket["cohort"], ticket.get("compare_cohort")}
        ticket_keys = {_source_key(r["source"]) for r in ticket["requests"]}
        for label in sorted(cited):
            key = labels.get(label)
            if key is None:
                notes.append(f"cites {label}, which is not in the batch")
            elif key[2] not in allowed_cohorts:
                notes.append(f"cites {label} from {key[2]}")
            elif key not in ticket_keys:
                notes.append(f"cites {label}, another ticket's excerpt")
        evidence = _squash(" ".join(sources[k]["text"] for k in ticket_keys | {labels[c] for c in cited if c in labels}
                                    if k in sources))
        claims = re.sub(r"Đ\d+", "", " ".join([case.get("dap_an_nhap") or "", *(case.get("y_bat_buoc") or [])]))
        asked = _squash(question)
        missing = sorted({tok for tok in FACT_TOKEN.findall(claims)
                          if _squash(tok) not in evidence and _squash(tok) not in asked
                          and not re.fullmatch(r"\d", tok)})
        if missing and ticket["requests"]:
            notes.append(f"not in its excerpts: {missing}")
        if case.get("ghi_chu"):
            notes.append(f"author note: {case['ghi_chu']}")
        report.append(f"{ticket['id']} {ticket['cell']} [{style}]: " + ("; ".join(notes) if notes else "ok"))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batch", type=int)
    args = parser.parse_args()
    print("\n".join(check(args.batch)))


if __name__ == "__main__":
    main()
