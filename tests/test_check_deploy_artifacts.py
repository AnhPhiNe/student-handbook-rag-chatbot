import json

from scripts.check_deploy_artifacts import validate_artifact


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
