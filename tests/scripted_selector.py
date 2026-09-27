"""A stand-in for the LLM behind the directory selector, for unit tests.

The real `DirectorySelector` renders its prompt and validates the reply; only
the model is replaced. `answers` maps the text a student wrote to what the
model would pick, by catalog name:

    "Name"          -> {"decision": "match", "ids": [id of Name]}
    ["A", "B"]      -> match with several ids (programs of a faculty)
    ("A", "B")      -> {"decision": "ambiguous", ...}
    missing / None  -> {"decision": "none", "ids": []}

A name missing from the catalog shown is dropped, so the cohort filter stays
under test. `raw` replaces the reply entirely (malformed output, unknown ids).
"""
from __future__ import annotations

import json
import re
from typing import Any

from src.retrieval.core.directory_selector import DirectorySelector


class ScriptedClient:
    def __init__(self, answers: dict[str, Any] | None = None, *, raw: str | None = None,
                 fail: bool = False) -> None:
        self.answers = answers or {}
        self.raw = raw
        self.fail = fail
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> dict[str, Any]:
        self.prompts.append(prompt)
        if self.fail:
            return {"ok": False, "text": "", "error_type": "timeout"}
        if self.raw is not None:
            return {"ok": True, "text": self.raw}
        value = re.search(r': "(.*)"\s*$', prompt).group(1)
        ids_by_name: dict[str, list[str]] = {}
        for record_id, name in re.findall(r"^(S\d+) \| ([^|\n]+?) \|", prompt, flags=re.M):
            ids_by_name.setdefault(name.strip(), []).append(record_id)
        answer = self.answers.get(value)
        names = [answer] if isinstance(answer, str) else list(answer or [])
        ids = [record_id for name in names for record_id in ids_by_name.get(name, [])[:1]]
        decision = "none" if not ids else "ambiguous" if isinstance(answer, tuple) else "match"
        return {"ok": True, "text": json.dumps({"decision": decision, "ids": ids})}


def scripted_selector(answers: dict[str, Any] | None = None, **options: Any) -> DirectorySelector:
    return DirectorySelector(ScriptedClient(answers, **options))
