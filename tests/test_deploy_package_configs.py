"""Configs read by the deployed backend must be included in the HF package."""
import re
from pathlib import Path

from src.common.runtime_artifacts import RUNTIME_FILES

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIRS = ("src/api", "src/common", "src/generation", "src/retrieval", "src/services")
NOT_READ = {"program_overrides.yaml": "a provenance label in structured_result_presenter"}


def _configs_named_in_runtime_code() -> set[str]:
    names: set[str] = set()
    for folder in RUNTIME_DIRS:
        for path in (ROOT / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            names.update(re.findall(r"configs/([\w.-]+\.ya?ml)", text))
            names.update(re.findall(r'"configs"\s*/\s*"([\w.-]+\.ya?ml)"', text))
    return names


def test_every_runtime_config_is_deployed():
    script = (ROOT / "scripts/deploy_hf_backend.ps1").read_text(encoding="utf-8")
    copied = set(re.findall(r'Copy-RequiredFile "configs\\([\w.-]+\.ya?ml)"', script))
    assert not _configs_named_in_runtime_code() - copied - set(NOT_READ)


def test_currency_notes_are_checked_by_runtime_health():
    assert "handbook_currency.yaml" in _configs_named_in_runtime_code()
    assert "configs/handbook_currency.yaml" in RUNTIME_FILES


def test_readiness_rejects_missing_currency_notes(monkeypatch):
    from src.api.routes import health

    monkeypatch.setattr(Path, "is_file", lambda path: path.as_posix() != "configs/handbook_currency.yaml")
    monkeypatch.setattr(health, "_env_value", lambda name: "configured")
    monkeypatch.setattr(health, "_build_manifest_matches_environment", lambda: True)
    monkeypatch.setattr(health, "get_dependency_runtime_statuses", lambda: {
        "qdrant": {"status": "ready"}, "mongodb": {"status": "ready"},
    })
    monkeypatch.setattr(health, "get_bm25_runtime_status", lambda: {"status": "ready", "attempts": 1})
    result = health.readiness()
    assert not result.ready and result.missing_count == 1
