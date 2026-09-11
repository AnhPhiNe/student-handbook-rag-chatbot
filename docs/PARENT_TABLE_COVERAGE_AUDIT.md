# PDF-to-parent table coverage audit

Date: 2026-09-06. Read-only audit; no runtime, source PDF, corpus, database,
embedding or deployment changes. This report concerns full parent documents,
not a proposal to embed table rows.

## Conclusion

The 23 reviewed regions in the separation candidate are **not an exhaustive
inventory of the handbooks**. The original and candidate parent snapshots both
omit additional source tables. Most confirmed omissions are text-readable
appendices or standalone notices, not raster-table extraction failures.

Do not describe either snapshot as a complete reproduction of all handbook
tables. Missing standalone documents must not be appended to an unrelated last
article merely because its current page metadata spans those documents.

## Method and bounds

- Screened layouts of all 640 PDF pages using rendered contact sheets:
  K48-K49 188, K50 220, K51 232 pages.
- Inspected all 43 embedded image occurrences: 34 QR codes, five formulas,
  three logos and one blank table form. Formula-image fidelity is outside this
  table audit; their presence does not establish whether formula text is complete.
- Ran local ruled-table detection on every page: 88 candidate regions across
  78 pages. This includes forms, directory layouts and split-page tables; it is
  **not** a count of 88 unique policy tables or 88 missing tables.
- Compared extracted cells with page-bound original/candidate parent content;
  searched all parent fields for distinctive missing phrases to rule out simple
  placement under another parent. Source mismatches caused by dashes, whitespace,
  merged cells or display projections are not automatically marked as data loss.
- Opened full-page renders for representative confirmed omissions and source
  layouts, in addition to the earlier registered-table source review. This is
  coverage screening plus targeted verification, **not a new cell-by-cell
  certification of every row in all PDFs**.
- Compared the 462-parent original local snapshot and the 462-parent candidate.
  No new live MongoDB read was performed in this audit. The previous 16/16 live
  comparison cannot be generalized to all 462 live parents.

All page numbers below are one-based PDF pages.

## Confirmed gaps and scope exclusions

| Source group | PDF pages | Parent finding | Interpretation |
|---|---|---|---|
| Detailed conduct evaluation appendix | K48-K49 82-86; K50 103-107; K51 99-103 | No corresponding parent coverage; distinctive detailed criteria absent from both snapshots | Source-scope omission. This is the detailed activity/point rubric, not the existing Article 9 classification table. |
| Tuition exemption/reduction: beneficiaries and required documents | K50 153-157; K51 157-161 | Table text absent from both snapshots despite an unrelated last article claiming these pages | Standalone notices need their own identity if included; not part of Article 15. |
| Study-cost support: beneficiaries, support level and documents | K50 163-164; K51 167-168 | Same absence and overbroad last-article page binding | A second standalone policy-table group, distinct from tuition exemption. |
| Research form catalogue | K48-K49 103-104 | Catalogue labels absent from both parent snapshots | Non-article appendix not represented as a parent; not an OCR issue. |
| Dormitory admission workflow table | K50 169; K51 173 | Workflow table absent from parent snapshots | K51 is explicitly classified as `ktx_procedure_archive`; absence alone does not establish a new runtime regression. |
| Raster table: off-campus student list template | K48-K49 167 | No parent; PDF extraction returns footer/page text, not the form headings/cells | Genuine image-only table, but a **blank form**, not a missing grade/tuition rule. |
| Other blank forms containing tables | K48-K49 169-174, 185 | Not regulation parents | Archive/form scope decision; do not automatically turn blank forms into lookup data. |
| College-level early-childhood training tables | K50 34, 38, 43, 45, 46; K51 33, 37, 42, 44, 45 | Excluded from parents | Intentional college-scope exclusion, verified in parser and regression test. Do not reintroduce as university rules. |
| Directory/service and contact layouts | K50 192, 206-207; K51 221-224 | Outside regulation-parent representation | Separate catalog contract. This audit does not certify every corresponding catalog row. |

The 21 remaining detector pages are associated with registered regulation-table
parents. Their literal cell differences require reading the source projection;
for example, `8,5 – 10` versus `8,5 - 10` is not a missing range. The previous
23-region candidate retains historical/amended tables and accompanying notes
within its reviewed scope; it does not restore the gaps listed above.

### Direct evidence probes

Whitespace-normalized searches over every field of all original and candidate
parents returned zero matches for each of these source phrases:

- `Chuẩn bị bài tốt` (detailed conduct rubric).
- `thân nhân của người có công` (tuition notice table).
- `60% mức lương cơ sở` (study-cost support table).
- `Mẫu 1 - SV NCKH` (research-form catalogue).
- `Kiểm tra tình trạng và số lượng chỗ nội trú` (dormitory workflow).

These probes support the concrete omissions. They are not a substitute for a
complete semantic comparison of all source cells.

## Why this happens

1. `src/preprocessing/structure_parser.py:498` creates article sections only
   when a page/article pair exists in the curated lookup. It skips `CaoDang`
   deliberately. It does not generally create standalone notice/appendix parents.
2. `configs/document_sections*.yaml` gives scoring forms a separate content type.
   `build_regulation_parents()` in `src/chunking/regulation_parents.py` builds parents only for
   `regulation_text`. Therefore the source can be extracted successfully and
   still never become a regulation parent.
3. `clean_regulation_source_content()` cuts trailing notices/other documents
   away from the preceding article. This prevents mixing document identities,
   but no replacement parent is created for those notices here.
4. After that trim, `source_pages` is still built from the original section range
   (`build_regulation_parents()`). Two confirmed examples:
   - `K50_NghiDinhHoTroHocPhiSinhHoatPhiSinhVienSuPham_Chuong4_Dieu15`:
     pages 152-170, only 616 characters of parent content.
   - `K51_QuyDinhChinhSachPhatTrienNguoiHocTaiNang_Chuong4_Dieu15`:
     pages 155-170, only 577 characters of parent content.
   The later tuition/support notices are not the contents of those articles.

There is also a source-map boundary to review: the K50 scoring-form range is
configured as 103-105 although the rubric continues through 107. K51's range
99-105 extends beyond its rubric ending on 103. Do not fix this by broadening
an unrelated article's page range.

## Minimal follow-up, if restoration is approved

1. Fix parent source-page provenance after document separation/trim.
2. Explicitly inventory which appendices and standalone notices belong in the
   source archive. Give admitted documents their own parent IDs, titles, cohorts,
   source pages and document/appendix relationship. Do not fabricate an Article.
3. Preserve their complete table plus surrounding heading, notes and conditions
   in the full parent. Handle the single image-only blank form as an archive
   attachment if needed; no need for a new general OCR/agent subsystem.
4. Keep the chosen embedding exclusion policy. Full parent restoration alone
   does **not** guarantee that the current retrieval pipeline can discover a
   new standalone table or answer questions about it. Any new lookup capability
   is a separate scope decision, not part of this read-only audit.
5. Validate row/column linkage and exact source binding before promotion.

No fixes, new capabilities or embedding changes were implemented in this audit.
The omissions and overbroad metadata exist in the original snapshot as well as
the candidate; the 23-region separation did not introduce them.

## Reproducible local evidence

`work/parent_pdf_table_audit/` (ignored audit outputs) contains:

- `inventory.json`: all 640 pages, detected tables/cells, image/page bindings.
- `images.json`: every embedded image occurrence, without the large-image filter.
- `summary.json`: hashes, detector-page dispositions and absence probes.
- Rendered page contact sheets, image inventories and selected full pages.

Scratch audit commands (read source files, write only audit outputs):

```powershell
.\.venv\Scripts\python.exe -X utf8 work/audit_parent_pdf_tables.py
.\.venv\Scripts\python.exe -X utf8 work/audit_pdf_image_inventory.py
.\.venv\Scripts\python.exe -X utf8 work/summarize_parent_table_audit.py
```

The scripts and detector output are diagnostic, not a production parser or a
human-reviewed completeness metric. No external LLM/OCR service was called.

## Follow-up implementation

The two page-range defects identified here are corrected in the new local paired
build through content-hash-bound review metadata. The supported-table scope is
unchanged; notices and appendices outside that scope were not added. See
[PARENT_CHILD_BUILD_CONTRACT.md](PARENT_CHILD_BUILD_CONTRACT.md) for build results
and publication guards. The original/live v32 snapshot has not been overwritten.
