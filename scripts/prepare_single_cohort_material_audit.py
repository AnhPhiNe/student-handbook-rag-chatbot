"""Create the pre-registered blinded material-hallucination audit packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.evaluation.material_hallucination import build_material_audit_packet


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--external-packet-output",
        type=Path,
        help="Write the blinded packet safe to send to an external LLM.",
    )
    parser.add_argument("--controls", type=int, default=10)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    cases = []
    for suite in ("dev", "hidden"):
        cases.extend(
            json.loads(
                (Path("data/eval/single_cohort_v2") / f"{suite}.json").read_text(
                    encoding="utf-8"
                )
            )
        )
    packet = build_material_audit_packet(
        cases,
        report.get("answers") or [],
        report.get("answer_judgments") or [],
        answers_report_hash=_sha256(args.report),
        commit=str(report.get("commit") or ""),
        control_count=max(0, args.controls),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.external_packet_output:
        args.external_packet_output.write_text(
            json.dumps(
                {
                    "schema_version": packet["schema_version"],
                    "materiality_dimensions": packet["materiality_dimensions"],
                    "entries": packet["audit_packet"]["entries"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(
        "Wrote "
        f"{args.output} ({len(packet['audit_packet']['entries'])} blinded audit entries)."
    )


if __name__ == "__main__":
    main()
