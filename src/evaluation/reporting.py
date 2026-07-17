from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_report_bundle(report: dict[str, Any], output_path: Path) -> dict[str, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    csv_path = output_path.with_suffix(".csv")
    markdown_path = output_path.with_suffix(".md")
    _write_cases_csv(report.get("cases") or [], csv_path)
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    return {
        "json": str(output_path),
        "csv": str(csv_path),
        "markdown": str(markdown_path),
    }


def _write_cases_csv(cases: list[dict[str, Any]], path: Path) -> None:
    if not cases:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for case in cases for key in case})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, default=str)
                    if isinstance(value, dict | list)
                    else value
                    for key, value in case.items()
                }
            )


def _markdown_summary(report: dict[str, Any]) -> str:
    title = str(report.get("evaluation") or report.get("suite") or "Evaluation report")
    summary = report.get("summary") or {}
    provenance = report.get("provenance") or {}
    lines = [f"# {title}", "", "## Summary", ""]
    for key, value in summary.items():
        if isinstance(value, dict | list):
            lines.append(
                f"- **{key}:** `{json.dumps(value, ensure_ascii=False, default=str)}`"
            )
        else:
            lines.append(f"- **{key}:** {value}")
    completeness = report.get("completeness") or {}
    if completeness:
        lines.extend(["", "## Completeness", ""])
        for key, value in completeness.items():
            lines.append(f"- **{key}:** {value}")
    gates = report.get("gates") or {}
    if gates:
        lines.extend(["", "## Gates", "", f"- **passed:** {gates.get('passed')}"])
        for key, value in (gates.get("checks") or {}).items():
            lines.append(
                f"- **{key}:** actual={value.get('actual')}, "
                f"required {value.get('operator')} {value.get('threshold')}, "
                f"passed={value.get('passed')}"
            )
    breakdowns = report.get("breakdowns") or {}
    if breakdowns:
        lines.extend(
            [
                "",
                "## Breakdowns",
                "",
                "```json",
                json.dumps(breakdowns, ensure_ascii=False, indent=2, default=str),
                "```",
            ]
        )
    human_audit = report.get("human_audit") or {}
    if human_audit:
        lines.extend(["", "## Human Audit", ""])
        for key, value in human_audit.items():
            if key != "template":
                lines.append(f"- **{key}:** {value}")
    lines.extend(["", "## Provenance", ""])
    for key, value in provenance.items():
        if isinstance(value, dict | list):
            value = json.dumps(value, ensure_ascii=False, default=str)
        lines.append(f"- **{key}:** {value}")
    lines.append("")
    return "\n".join(lines)
