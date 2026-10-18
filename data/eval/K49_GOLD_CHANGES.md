# Gold changes for the K49 cohort (2026-10-13)

The K48-K49 cohort (built from the K48 handbook) was replaced by K49, built from
the K49 handbook (2023 – 2024). Every case of the evaluation sets that targeted
K48-K49 was moved to K49 and its gold re-checked against the K49 PDF. This file
lists every gold whose meaning changed; a change of the cohort label alone
("K48-K49" or "K48" becoming "K49" in a question, an earlier turn or a required
fact) and renamed source ids are not listed one by one.

## official_v4 (89 cases; reasons in `official_v4/gold_adjustments.yaml`)

| Case | What changed | K49 source |
|---|---|---|
| V4-088 | Question and draft: notice for school year 2023 – 2024, not 2022 – 2023; the legal basis is the same | p.116 |
| V4-095 | Adviser part rewritten: monthly report from the class officers, class meetings twice a term, working-time frame in Phụ lục 1 (not printed) | p.61–62, Quyết định 3738 Điều 4 |
| V4-096 | Dormitory part rewritten: the K49 papers list, submitted to the dormitory office within the announced period, 351A Lạc Long Quân | p.161–163, p.133 |
| V4-111 | Cheering at an activity: 1 point per activity (K48: 2) | p.79 |
| V4-118 | Adviser tasks from Quyết định 3738 (guiding complaints is no longer listed) | p.60–62 |
| V4-121 | Form labels "Mẫu 3" and "Mẫu 3a" removed (K49 does not number the forms) | p.82 |
| V4-128 | Phòng Tổ chức – Hành chính is not in K49's list of offices: the expected answer says the handbook has no such information | p.127–138 |
| V4-144 | No change: the gold keeps (028) 38391080, the catalog's reviewed correction of K49's misprint "(028) 3891080" (owner decision) | p.129; K48 p.131 |
| V4-145 | "mẫu 2 - SV NCKH" replaced by "thuyết minh đề tài nghiên cứu" | p.87 |
| V4-182 | Faculty name "Khoa Công nghệ Thông tin" (K48: "Công nghệ – Thông tin") | p.139 |
| V4-216 | Earlier assistant turn: K49 lists only hopthusinhvien@hcmue.edu.vn for Phòng CTCT và HSSV; the scored question is unchanged | p.127 |

Checked and unchanged: the other 78, among them every case on Quy chế đào tạo,
Quy chế công tác sinh viên, Quy chế đánh giá rèn luyện, Nghị định 116 and the
notices (same text as K48 but for abbreviations), the score-frame cases V4-061,
073, 083 and 245, the research cases V4-085, 123, 194 and 206, and the 27
directory cases (addresses, phones and e-mails as printed in K49).

## official_v1 and official_v2 (recompiled from the K49 catalogs)

Structured gold is compiled from the catalogs, so these follow the K49
handbook directly:

| Cases | What changed |
|---|---|
| v1 det_067, ans_109 | Ký túc xá address 351A Lạc Long Quân (K48: 351B) |
| v1 det_070, det_115, ans_121, ans_127; v2 det/ans_120 | Thư viện phones (028) 35261042; (028) 38308905; (028) 38352020, internal 231, 234 |
| v1 det_121; v2 det/ans_111 | Phòng CTCT và HSSV e-mail hopthusinhvien@hcmue.edu.vn only, website ctsv.hcmue.edu.vn |
| v1 det_073, det_115, ans_130 | Trung tâm Ngoại ngữ service wording (capitalisation, "N1 – N5") |
| v2 det/ans/ret_106 | Student loans: the K49 directory lists none; the gold is Phòng CTCT và HSSV from Quy chế CTSV Điều 14 khoản 14 |
| v2 det/ans_111 | Student card: anchor "cấp thẻ sinh viên" in Phòng CTCT's duty line (same unit) |
| v2 det/ans_030, 106, 152 | Trạm Y tế's first service "Phối hợp tổ chức khám sức khỏe …" |
| v2 det/ans_031 | Trung tâm Tin học's addresses, now extracted |
| v2 ret_extra_026 | Anchor "xây dựng Sổ tay sinh viên" (capital S in K49) |
| v2 ret_extra_033 | Adviser and class officers: Quyết định 3738 Điều 4 khoản 2 b (monthly report) instead of the 2014 rules' Điều 6 |
| v2 det/ans_124 | Question names K49 instead of K48 |

Other recompiled K49 cases differ only in evidence snapshots (parent text,
hashes, pages) or in the formula's `rounding` field added on 2026-10-01; two
K50 cases (v2 det/ans_028 and 094) pick up that field because they also cite a
K48-K49 record.

## Development sets

`development/*.yaml` and `chunking_targeted_retrieval_cases.json` are
relabelled to K49 with the K49 parent ids. Left on K48-K49, because the K49
handbook prints no equivalent text: `supplementary_questions.yaml` sup_15 (the
forms list), sup_16 (the ten student conduct rules) and sup_19 (the dormitory
priority list).

## Left as it was

`official_v3` (a spent hold-out, neither tested nor run here) still targets
K48-K49 in every case with that UI cohort. Before it is run again, 6 of
them need a K49 decision: 131 (student loans) and 84 (Phòng Tổ chức – Hành
chính's e-mail) have no K49 record, 30 and 64 cite the 2014 adviser rules, and
55 and 106 have anchors whose K49 wording differs.
