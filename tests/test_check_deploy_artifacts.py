import hashlib
import json
from pathlib import Path

from scripts.check_deploy_artifacts import validate_artifact, validate_build_manifest


ROOT = Path(__file__).resolve().parents[1]


def test_hf_deploy_allowlist_includes_retrieval_runtime_config() -> None:
    """Prevent deploys that omit the config required by retrieval health probes."""

    deploy_script = (ROOT / "scripts" / "deploy_hf_backend.ps1").read_text(
        encoding="utf-8"
    )

    assert (
        'Copy-RequiredFile "configs\\retrieval.yaml" "configs\\retrieval.yaml"'
        in deploy_script
    )


def test_deploy_audit_rejects_repeated_header_in_content(tmp_path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(
        json.dumps({"raw_text": "Nội dung\n174 SỔ TAY SINH VIÊN KHÓA 50"}),
        encoding="utf-8",
    )

    assert validate_artifact(artifact, "file") == (
        "repeated PDF header leaked into content: "
        "174 SỔ TAY SINH VIÊN KHÓA 50"
    )


def test_deploy_audit_allows_handbook_name_in_regular_sentence(tmp_path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(
        json.dumps({"raw_text": "Nguồn là Sổ tay Sinh viên khóa 51 của Trường."}),
        encoding="utf-8",
    )

    assert validate_artifact(artifact, "file") is None


def test_deploy_audit_checks_manifest_hash_and_count(tmp_path) -> None:
    artifact = tmp_path / "items.json"
    artifact.write_text('[{"id": 1}]\n', encoding="utf-8")
    manifest = tmp_path / "build_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "artifacts": {
                    "items": {
                        "path": str(artifact),
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                        "count": 1,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert validate_build_manifest(manifest) == []

    artifact.write_text('[{"id": 1}, {"id": 2}]\n', encoding="utf-8")
    errors = validate_build_manifest(manifest)

    assert any("sha256 mismatch" in error for error in errors)
    assert any("count mismatch" in error for error in errors)
