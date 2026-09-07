import json

import pytest

from scripts import prepare_official_eval as snapshot


def test_verify_detects_frozen_file_drift(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("original", encoding="utf-8")
    (bundle / "runtime_freeze.json").write_text(json.dumps({
        "file_hashes": {"artifact.txt": snapshot.digest(artifact)},
    }), encoding="utf-8")
    monkeypatch.setattr(snapshot, "ROOT", tmp_path)
    monkeypatch.setattr(snapshot, "BUNDLE", bundle)
    snapshot.verify()
    artifact.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen files changed"):
        snapshot.verify()


def test_snapshot_writer_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "BUNDLE", tmp_path)
    snapshot.write_new("identity.json", {"commit": "first"})
    with pytest.raises(FileExistsError):
        snapshot.write_new("identity.json", {"commit": "second"})
    assert json.loads((tmp_path / "identity.json").read_text()) == {"commit": "first"}
