import json
import tempfile
import unittest
from pathlib import Path

from scripts.derive_foreign_language_policy import derive_foreign_language_policy


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
    def test_derives_distinct_target_cohort_ids_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "docstore.json"
            path.write_text(json.dumps([_source_item(1)], ensure_ascii=False), encoding="utf-8")

            report = derive_foreign_language_policy(path, None)
            items = json.loads(path.read_text(encoding="utf-8"))
            ids = {item["_id"] for item in items}

            self.assertEqual(report["derived_section_count"], 2)
            self.assertIn("K48-K49_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu1", ids)
            self.assertIn("K51_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu1", ids)

            k48 = next(item for item in items if item["_id"].startswith("K48-K49_"))
            self.assertEqual(k48["metadata"]["cohort"], "K48-K49")
            self.assertEqual(k48["metadata"]["document_id"], "so_tay_sinh_vien_khoa_48_49")
            self.assertEqual(k48["metadata"]["derived_from_cohort"], "K50")
            self.assertIn("SỔ TAY SINH VIÊN KHÓA 48-49", k48["content"])
            self.assertNotIn("SỔ TAY SINH VIÊN KHÓA 50", k48["content"])

    def test_idempotent_for_existing_derived_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "docstore.json"
            path.write_text(json.dumps([_source_item(1)], ensure_ascii=False), encoding="utf-8")

            derive_foreign_language_policy(path, None)
            derive_foreign_language_policy(path, None)
            items = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(len(items), 3)
            self.assertEqual(len({item["_id"] for item in items}), 3)

    def test_refuses_to_overwrite_non_derived_target_policy(self) -> None:
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

            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                derive_foreign_language_policy(path, None)


if __name__ == "__main__":
    unittest.main()
