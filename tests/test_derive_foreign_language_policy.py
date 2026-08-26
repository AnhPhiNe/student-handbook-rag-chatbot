import json
import tempfile
import unittest
from pathlib import Path

from scripts.derive_foreign_language_policy import derive_foreign_language_policy
from scripts.build_child_parent_index import build_child_parent_chunks


def _source_item(article: int) -> dict:
    item_id = f"K50_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu{article}"
    return {
        "_id": item_id,
        "cohort": "K50",
        "document_id": "so_tay_sinh_vien_khoa_50",
        "content": (
            "Tài liệu: Quy định tổ chức dạy học và công nhận đạt chuẩn đầu ra ngoại ngữ\n"
            f"Nội dung:\nĐiều {article}. Nội dung SỔ TAY SINH VIÊN KHÓA 50"
        ),
        "metadata": {
            "cohort": "K50",
            "document_id": "so_tay_sinh_vien_khoa_50",
            "document_title": (
                "Quy định tổ chức dạy học và công nhận đạt chuẩn đầu ra ngoại ngữ "
                "cho sinh viên tốt nghiệp các ngành đào tạo trình độ đại học của "
                "Trường Đại học Sư phạm Thành phố Hồ Chí Minh"
            ),
            "article": f"Điều {article}.",
            "title": f"Điều {article}",
            "content_type": "regulation_text",
            "source_pages": [110],
        },
    }


class DeriveForeignLanguagePolicyTest(unittest.TestCase):
    def test_annotates_source_policy_with_registry_derived_applicability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "docstore.json"
            path.write_text(json.dumps([_source_item(1)], ensure_ascii=False), encoding="utf-8")

            report = derive_foreign_language_policy(path, None)
            items = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(report["derived_section_count"], 0)
            self.assertEqual(report["annotated_section_count"], 1)
            self.assertEqual(len(items), 1)
            source = items[0]
            self.assertEqual(source["metadata"]["source_cohort"], "K50")
            self.assertEqual(
                source["metadata"]["applicable_cohorts"],
                ["K48-K49", "K50", "K51"],
            )
            self.assertTrue(source["metadata"]["applicability_validated"])
            self.assertIn("SỔ TAY SINH VIÊN KHÓA 50", source["content"])

            chunks = build_child_parent_chunks(items)
            self.assertTrue(chunks)
            self.assertTrue(
                all(
                    chunk["metadata"]["applicable_cohorts"]
                    == ["K48-K49", "K50", "K51"]
                    for chunk in chunks
                )
            )

    def test_idempotent_for_existing_derived_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "docstore.json"
            path.write_text(json.dumps([_source_item(1)], ensure_ascii=False), encoding="utf-8")

            derive_foreign_language_policy(path, None)
            derive_foreign_language_policy(path, None)
            items = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(len(items), 1)
            self.assertEqual(len({item["_id"] for item in items}), 1)

    def test_real_target_policy_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "docstore.json"
            real_k51 = _source_item(1)
            real_k51["_id"] = "K51_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu1"
            real_k51["cohort"] = "K51"
            real_k51["document_id"] = "so_tay_sinh_vien_khoa_51"
            real_k51["metadata"]["cohort"] = "K51"
            real_k51["metadata"]["document_id"] = "so_tay_sinh_vien_khoa_51"
            path.write_text(
                json.dumps([_source_item(1), real_k51], ensure_ascii=False),
                encoding="utf-8",
            )

            report = derive_foreign_language_policy(path, None)
            items = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(len(items), 2)
            self.assertEqual(report["annotated_section_count"], 1)
            real_target = next(item for item in items if item["cohort"] == "K51")
            self.assertNotIn("applicable_cohorts", real_target["metadata"])


if __name__ == "__main__":
    unittest.main()
