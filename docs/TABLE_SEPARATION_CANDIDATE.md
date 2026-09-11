# Narrative-only retrieval / full-source parents

Status: **historical A/B record**. The policy was later promoted: every build now
applies it through `scripts/build_parent_child_artifacts.py` (see
[PARENT_CHILD_BUILD_CONTRACT.md](PARENT_CHILD_BUILD_CONTRACT.md)). It differs from
an earlier, rejected experiment that embedded registry-rendered table text; that
experiment's scripts and write-up were removed and remain in git history.

## Contract

- Structured JSON remains unchanged and authoritative for structured lookup.
- Physical table regions that have been source-reviewed are removed from the
  text passed into the existing child chunker. No table-derived chunks or
  synthetic table-discovery descriptions are added to the embedding corpus.
- Full parent content preserves those tables as readable Markdown in their
  original locations, together with surrounding policy, exceptions and footnotes.
- Prose-derived structured records do not authorize removal of original prose.
  Original captions may remain; they are not new discovery/fallback chunks.
- Original and amended tables remain separate in the full source. The original
  K51 tables are source history, not replacements for current structured facts.
- No Planner, normalizer, structured resolver, Composer, retrieval algorithm,
  API or frontend behavior is modified.

## Implementation and scope

`scripts/build_parent_child_artifacts.py` consumes the original docstore,
unchanged structured registry and `data/curated/regulation_table_regions.json`.
The curated file records exact source spans, parent/cohort/document/page binding,
source-review dispositions and registry projections. Three historical table
representations are source-only transcriptions; they do not become lookup tables.

There is no query text, benchmark ID or routing condition in this build policy.
The annotations describe the source layout, including merged cells, not student
questions. Their review basis is the approved registry and the agent source
review documented in the earlier experiment; no independent human review is claimed.

The builder rejects stale parent/registry hashes, overlapping or mismatched
regions, wrong cohort/document/pages, unreviewed entries, invalid table shape,
duplicate parent IDs and physical-table dispositions without a representation.
It will not infer new deletion spans when a handbook changes. Review the new
source first, then update the annotation data.

Scope is the **35 registered regulation-table records across 16 parents**, not
an exhaustive detection of every possible table/image in the PDFs. Of these,
21 records bind physical tables (two duration records share one amendment table),
and 14 are prose-derived. Directory/catalog data is untouched.

| Build result | Value |
|---|---:|
| Parent documents retained | 462 |
| Reviewed physical table regions | 23 |
| Table rows preserved in parent Markdown | 150 |
| Generated duplicate table appendices removed | 12 |
| Baseline / candidate children | 3,125 / 3,121 |
| Baseline / candidate indexed content characters | 935,873 / 928,716 |
| Added table embedding chunks | 0 |

The 150 source-display rows include historical tables. They are not a replacement
count for the unchanged 171 registry rows: prose-derived records, projections
and historical tables have different accounting. No registry row was deleted.

The foreign-language appendix retains the blank TOEFL ITP level-4 cell. Runtime
fields such as `input_requirements` are not rendered as source cells. K51 retains
the original duration/grade tables, the amended tables, their effective-intake
notes, the bridging exception and the retake amendment.

## MongoDB verification

A **read-only** check of `parent_docs_v32` matched **16/16** in-scope live parents
against the original local snapshot: content, cohort, document ID and source pages.
This confirms that the cleanup targets correspond to live data. It does **not**
mean MongoDB already contains the cleaned parents: no live document was updated.

The candidate parent and child artifacts must be versioned together before any
future promotion. Do not build children directly from the full Markdown parents
using an older command that has not applied the reviewed-region separation.

## Validation (2026-09-05/06)

**88 tests passed**, covering the separation builder, source-drift rejection,
read-only Mongo verification, unchanged structured lookup, existing chunking,
local A/B harness, prompt building and amendment artifacts. Ruff passed.

Tests establish that source text outside the reviewed regions is retained, inputs
are not mutated, untouched parent content is unchanged, no source-table block
survives in the narrative view, table shape is preserved, and the actual JSON
resolver still returns **Tốt** for K50 conduct score **82** with grounded slots.
This resolver test does not claim the live Planner always selects those slots.

### Corpus A/B

Used the same isolated exact-cosine Qdrant/BM25/RRF diagnostic as the earlier
experiment: BGE-M3, no reranker, 24 children, top five primary parents, fixed
queries and gold cohorts. Candidate retrieval uses candidate full parents;
baseline uses original parents. Vectors for identical content were reused;
14 new unique narrative texts were encoded locally. No remote index writes.

On the frozen 155-question retrieval set (179 cohort execution units):

| Metric | Baseline | Separation candidate |
|---|---:|---:|
| Dense source Hit@5 | 164/179 | 164/179 |
| Dense macro required-source recall@5 | 89.11% | 89.11% |
| Dense MRR@5 | 0.7836 | 0.7836 |
| Dense binary nDCG@5 | 0.8023 | 0.8023 |
| RRF source Hit@5 | 179/179 | 179/179 |
| RRF macro required-source recall@5 | 98.60% | 98.60% |
| RRF MRR@5 | 0.9555 | 0.9555 |
| RRF binary nDCG@5 | 0.9553 | 0.9553 |
| Primary-source cohort leakage | 0 | 0 |

These are source metrics under fixed queries, not proof that focused evidence or
final answers are unchanged. Binary nDCG uses the existing grade >= 2 judgments;
it is not the official graded nDCG. This local corpus ablation does not replace
published end-to-end metrics or reproduce hosted approximate-search latency.

Targeted checks reveal the expected dependency on structured routing:

| Diagnostic group | Baseline RRF source hit | Candidate RRF source hit |
|---|---:|---:|
| Eight table/policy/compound questions | 8/8 | 7/8 |
| Four source-layout/amendment questions | 4/4 | 4/4 |

The loss is “K50 được 82 điểm rèn luyện thì xếp loại gì?” when **forced through
RAG**, where the conduct classification parent drops out of top five. Its dense
source hit remains, but fusion no longer preserves it in the selected parents.
The direct structured resolver still returns the correct JSON result. No routing
exception or top-k increase was added to recover the diagnostic.

All 24 production Composer preparations (12 paired questions) completed with
`ready_for_composer`; the compound question has two task units. The
`applicable_amendments` arrays are identical between arms for every pair. The
existing amendment-registry pathway is intentionally preserved: excluding table
rows from embeddings does not forbid separately authorized amendment evidence.

**No final-answer LLM A/B was run.** External Gemini payload permission was denied
in the earlier turn and has not been bypassed. Prepared packets are not graded
as correct answers, and this report makes no claim that Composer abstains reliably
when a misrouted table question lacks the necessary row evidence.

## Artifacts and reproduction

Current output: `work/table_separation_v1_verified/` (ignored experiment outputs).

- `all_docstore_items.json`: full readable candidate parents, for future Mongo import.
- `narrative_docstore_items.json`: build-only narrative view; not the Mongo source.
- `child_parent_chunks.json`: candidate embedding corpus.
- `audit.json`: source transformations, counts, input hashes and live-parent comparison.
- `hybrid_*.json`, `ab_retrieval_summary.json`: paired retrieval evidence/results.
- `answer_packets.jsonl`: prepared prompts/evidence only, no generated answers.

| Artifact | SHA-256 |
|---|---|
| Curated reviewed regions | `97d13b6bc0bb980048b67763b16aacb01a70a78b1371744de78e385a27f7390d` |
| Candidate full parents | `d3f051dd4c6ce22ceb67a0e7da4dd9b0b60d9e8ee5f3ba62ec16420197c42578` |
| Candidate children | `e93cb7dc36f3c89c86eb137058ef7b8e41d44d6cb6a6edeb076c0f1d6b3f6513` |

```powershell
# A new directory is mandatory. --verify-mongo only reads the live source.
.\.venv\Scripts\python.exe -X utf8 scripts/build_parent_child_artifacts.py --output-dir work/table_separation_next --verify-mongo
.\.venv\Scripts\python.exe -X utf8 scripts/ab_table_text_candidate.py --candidate-dir work/table_separation_next --stage retrieval
.\.venv\Scripts\python.exe -X utf8 scripts/ab_table_text_candidate.py --candidate-dir work/table_separation_next --stage packets
.\.venv\Scripts\python.exe -X utf8 scripts/summarize_table_text_ab.py --candidate-dir work/table_separation_next
```

Implementation and local data validation are complete for this scope. Promotion
is still separate: audit final answers/abstention with authorized API calls, then
version the approved parents, children and build identity together. Until then,
production artifacts, database contents, deployment and README metrics remain
unchanged. The known forced-RAG limitation is explicit, not scored away.

### Subsequent build integration

The hashes and A/B measurements above describe the historical candidate, before
source-page corrections and explicit corpus-role metadata. The official paired
builder, clean-build verification, and pre-upload contract are now documented in
[PARENT_CHILD_BUILD_CONTRACT.md](PARENT_CHILD_BUILD_CONTRACT.md). That integration
does not retroactively constitute final-answer A/B or production promotion.
