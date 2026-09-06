# Registry-derived table text: candidate build

Status: candidate build and source/dense/RRF review completed locally; **do not
promote this candidate**. Final-answer API A/B is awaiting explicit permission.
Not deployed or included in published metrics.

The subsequent **narrative-only / full-parent** policy is implemented separately
in [TABLE_SEPARATION_CANDIDATE.md](TABLE_SEPARATION_CANDIDATE.md). Results below
describe only the earlier table-text embedding candidate, not its successor.

## Scope

The production index suppresses recognized Markdown table rows, but some source
paragraphs retain flattened values from the PDF. This experiment gives approved
regulation tables a consistent retrieval representation derived from the structured
registry. JSON remains the source used by structured lookup and fact locks.

The implementation is an opt-in build command. It imports the existing child
chunker; it does not change the default build, Planner, normalizer, Composer,
MongoDB parent documents, production collections, or directory matching.

## Rules

- Select only approved, runtime-enabled `regulation_table` records whose parent
  is indexable regulation prose. Validate parent, document, source cohort and pages.
- Identify a table by parent + cohort + table ID. An ID alone is not unique across
  cohorts. Conflicting entries for the same identity fail the build.
- Remove source text only when a complete header plus every row matches in order,
  with only whitespace and letter case ignored. Match Markdown and flattened
  layouts separately. Do not delete individual numbers or partially matched rows.
- Preserve text before and after each exact span. Record the removed text and
  offsets for inspection. Overlapping matches are retained for review.
- Render every approved regulation-table row from JSON, retaining all keys and
  value types. Repeat table name, column names, source cohort and applicability
  in each table chunk. Split between rows; fail if one row cannot fit the budget.
- Keep the runtime child schema and parent IDs. Add table provenance and row
  indices as metadata; do not mark this evidence as a resolved fact lock.
- Leave uncertain source text intact and flag it. No exact match does not prove
  that a paragraph is free of duplicated table content.

## Commands

Run from the repository root. Use a new output directory under `work/` for each build.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/build_table_text_candidate.py --output-dir work/table_text_experiment
.\.venv\Scripts\python.exe -X utf8 scripts/compare_table_text_candidate.py --candidate-dir work/table_text_experiment
.\.venv\Scripts\python.exe -X utf8 scripts/compare_table_text_candidate.py --candidate-dir work/table_text_experiment --cases tests/fixtures/table_text_candidate_queries.json
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_table_text_candidate.py tests/test_build_child_parent_index.py tests/test_bm25_retriever.py -q
```

The build refuses production output paths and an existing candidate directory.
Comparison reports also refuse overwriting a prior result. No command uploads
data or calls a language model.

## Local findings

Candidate artifacts: `work/table_text_candidate_final/` (ignored by Git).

| Check | Result |
|---|---:|
| Approved regulation tables rendered | 35 |
| JSON rows preserved | 171 |
| Registry-derived child chunks | 37 |
| Baseline / candidate child count | 3,125 / 3,163 |
| Unchanged chunk content | 3,105 |
| Removed or changed old chunk content | 20 |
| Added or changed chunk content | 58 |
| Complete flat-table spans removed | 13 |
| Complete Markdown-table spans removed | 22 |
| Parents with source-span removals | 12 |
| Tables without a proven complete flat span | 22 |
| Parents flagged for source review | 8 |
| Build and BM25 tests | 26 passed |
| Ruff | Passed |

The previously known K48–K49 and K50 study-duration duplicates are removed from
the candidate narrative and replaced by labeled JSON-derived table chunks. The
eight parents requiring review include 22 tables without an exact flat span;
this is an uncertainty count, not a count of confirmed duplicated tables.
K51 scholarship classification also has residual exact row sequences. These
remain intact rather than authorizing destructive paragraph cleanup.

Tests verify source binding, complete row coverage, preserved policy text, input
immutability, unchanged chunks outside table parents, budget failures, rejected
number/sign mismatches, and ID collisions across cohorts. This does not establish
visual coverage of tables stored as images in the source PDFs.

## Retrieval sensitivity check

The diagnostic uses the production BM25 tokenizer and scorer, known gold cohorts,
24 child candidates and the first five unique parent IDs. It bypasses Planner,
dense search, RRF and Composer. It must not replace published retrieval metrics.

| Query set | Units | Baseline source hit | Candidate source hit | Required-source recall decreases |
|---|---:|---:|---:|---:|
| Frozen V9.1 retrieval: 155 questions | 179 cohort units | 179 | 179 | 0 |
| Table/policy/compound diagnostics | 8 | 8 | 8 | 0 |

The diagnostic includes the exact `v9_det_105` question as a regression, not a new
holdout. Both target parent articles remain retrievable. Source presence alone
does not prove that a future Composer answer will select the right table row.
The final candidate bytes match the corpus used for these two comparisons; the
last build only refined the audit's review-required labels.

## Identity and promotion boundary

| Artifact | SHA-256 |
|---|---|
| Production parent docstore | `4d410553cfaddeaef51fc096ffd0025d52e585b4c5dfe7ee0807e73570648143` |
| Production registry | `865fe92aca6283147713f02b400734dac44dfc9a0f4d959095ce30978d8fb0fd` |
| Production child corpus | `acb78cd5a2f4db3d4ddc4d5c548ad9cc6823cebb4c20c67cecd8e5c1220ce26c` |
| Candidate child corpus | `76fccb9015c17cb29b6d4a9426c0e795b6fe70f47ee0256735a4aeb597c47b01` |

The production inputs retain their hashes. Candidate chunks are not stamped as
the production build and are not deploy-ready artifacts. Before promotion:

1. Review the eight flagged parents against the source layout and registry.
2. Compare the candidate and baseline using isolated dense indexes, production
   fusion and answer generation, with paired table, policy and compound queries.
3. Inspect all losses and scope changes. Keep the production corpus if the
   candidate reduces answer quality or adds retrieval noise.
4. Only after acceptance, integrate the policy into the official build and
   version the child index and build manifest consistently with deployment.

This experiment changes corpus representation, not source facts. Duplication
between structured and retrieval representations is not automatically research
data leakage; the representation policy should be declared and controlled in
ablation experiments.

## Source review and dense/RRF A/B (2026-09-05)

### Source review: all eight flagged parents inspected

The PDF pages below were rendered and visually inspected alongside the parent
text and approved registry. Page numbers are one-based PDF pages. This review
closes the uncertainty investigation; it does **not** certify complete removal
of duplicated text, or a new audit of every table in all three handbooks.

| Source parent | PDF pages | Finding and minimal disposition |
|---|---|---|
| K48–K49, Student Affairs, Article 28 | 52–53 | All four scholarship records derive from prose/formulae, not a literal four-table layout. Keep the prose and its conditions. Exact raw-table deletion is inapplicable. |
| K48–K49, Training, Article 10 | 18–21 | Grade scale has merged pass/fail cells; JSON repeats their labels. Ungraded pass/fail is a prose rule. Do not delete paragraph values by fuzzy number matching. |
| K50, Foreign-language outcomes, Article 8 + appendix | 112–116 | Actual table is the appendix on 114–115, with merged language cells and a blank TOEFL ITP level-4 cell. Registry also contains normalization/runtime fields absent from the printed table. Keep the blank value; the broad parent/page binding is not a precise table location. |
| K50, Student Affairs, Article 27 | 71–73 | Four normalized scholarship records derive from prose, including the final-year exception and formula. Source conditions must remain. |
| K50, Training, Article 10 | 16–19 | Grade scale uses merged cells; ungraded pass/fail is prose. Same structural reason as K48–K49, not missing rows. |
| K51, Student Affairs, Article 27 | 70–72 | Classification is a genuine merged-cell table on page 70. Six expanded JSON combinations agree with the visible rows. Five exact residual row sequences are explained by merged labels; duplicate flattened text remains in candidate v1. Other scholarship records derive from prose. |
| K51, Training, Article 10 | 16–19 | Page 18 contains the original scale plus amended foundation/remaining-course scales. D+/D are failing for the latter group. Registry matches these scopes; old and amended source text remain. Page 19 also includes the retake amendment. Do not erase amendment context with broad matching. |
| K51, Training, Article 3 | 9–11 | The source prints older duration tables and a page-10 amendment applying from the 2025 intake. Registry records the amended 4/6 and 5/7.5-year values plus the bridging exception. These JSON rows are not verbatim versions of the older tables. Retain the legal context; do not treat old and current tables as interchangeable duplicates. |

The 22 unmatched table records therefore mix prose-derived records, merged-cell
tables, an appendix and amendments. They are not 22 proven missing tables.
The candidate still fails the strict goal of one canonical table representation
per indexed content: some merged-cell raw tables coexist with canonical chunks.
Also, rendering every row key exposes `input_requirements` in the canonical
foreign-language text even though it is runtime metadata, not printed evidence.
These are candidate-build findings; no production artifact was edited to fix them.

Rendered pages, extracted parent/table comparisons and their index are retained
under `work/table_text_candidate_final/source_review/`.

### Controlled retrieval comparison

`scripts/ab_table_text_candidate.py` downloaded vectors read-only from
`student_handbook_semantic_v32`: all **3,125** baseline child IDs matched their
local content exactly. Three freshly encoded samples had cosine similarity
approximately **1.0** to the stored vectors. The 50 previously unseen unique
candidate texts were encoded with the same configured BGE-M3 model. Identical
content reuses its vector in both arms; no remote collection was created or written.

Both arms use Qdrant **in-memory exact cosine** indexes, the unchanged production
BM25/RRF (k=60), 24 child candidates, top five primary parents, and the existing
graph supplement code. Full parents are supplied from the same local docstore
snapshot instead of MongoDB. No reranker. Queries and gold cohorts are fixed;
Planner is bypassed. Thus this is a corpus ablation, not a reproduction of hosted
ANN/network latency or a replacement for published end-to-end metrics.

The 155 frozen retrieval questions produce 179 cohort execution units:

| Diagnostic | Baseline | Candidate |
|---|---:|---:|
| Dense source Hit@5 | 164/179 (91.62%) | 159/179 (88.83%) |
| Dense macro required-source recall@5 | 89.11% | 86.31% |
| Dense MRR@5 | 0.7836 | 0.7533 |
| Dense binary nDCG@5 | 0.8023 | 0.7726 |
| RRF source Hit@5 | 179/179 (100%) | 177/179 (98.88%) |
| RRF macro required-source recall@5 | 98.60% | 97.49% |
| RRF MRR@5 | 0.9555 | 0.9421 |
| RRF binary nDCG@5 | 0.9553 | 0.9422 |
| Primary-source cohort leakage | 0 | 0 |

Binary relevance here means the existing judgments with grade >= 2. It is
deliberately named **binary nDCG**, not the official graded nDCG. Hit means at
least one required source is present; it does not mean all required sources are
present. No thresholds, qrels or runtime behavior were changed after these results.

Eight targeted diagnostics and four source-review diagnostics retained all
required sources in both arms (12/12). On the eight-case group, RRF MRR increased
from 0.9167 to 1.0000, but this does not cancel losses on broader policy queries.
Across the 179 units, dense recall decreased on six units and increased on one;
RRF recall decreased on two and increased on none. RRF reciprocal rank decreased
on eight and increased on two.

The two RRF source losses were inspected:

- `v8_ret_111`, K48–K49: “O K48-K49, dieu khoan thi hanh duoc quy dinh the nao?”
  Gold Article 18 of the conduct regulation moves out of top five (previously
  rank three). New classification/duration table children occupy high ranks.
  The query does not name the regulation, and another “Điều khoản thi hành”
  source remains, so loss of this gold is **not proof of an incorrect answer**.
- `v8_ret_117`, K48–K49: “Sinh vien K48-K49 can hieu gi ve phan lop hoc phan?”
  Gold Article 26 of Student Affairs moves out of top five (previously rank five).
  Candidate top five instead contain conduct classification, grading,
  scholarship, academic classification and duration sources. This is clear
  off-topic source displacement under the fixed query.

The saved parent lists/matched chunks show corpus-induced ranking displacement,
not a Planner change. Repeated cohort/scope boilerplate in the new table text is
a plausible contributor, but its individual effect has **not** been isolated.
Do not add a query-specific exception or adjust top-k to conceal these losses.

### Composer boundary and outstanding API permission

Prepared **24 exact Composer packets** (12 questions x two arms) through the
production task execution, citation selection, evidence packet and prompt code.
The fixed plans use RAG deliberately to test retrieval evidence; this is not a
claim that the live Planner would route every table question through RAG.
The compound regression retains two distinct task units. All 24 packets reached
`ready_for_composer`; this is a preparation result, **not an answer-quality pass**.

The attempted Gemini answer-stage launch was rejected by the tool permission
reviewer before execution because it would send query/evidence payloads to an
external service. No final-answer A/B calls were made. The later `packets` stage
only prepared local prompts and did not call Gemini. The first packet run made
an unsuccessful Redis connection probe despite cache being disabled; the harness
now injects a disabled local cache directly, avoiding this irrelevant probe.

Before final-answer execution, the user must explicitly authorize sending the
12 diagnostic questions and their handbook evidence to the configured
`gemini-3.1-flash-lite` service for 24 paired calls. Temperature remains 0.0,
output budget 4,096; response caching is disabled. Successful answers must be
audited against the preserved packets and source scope, not only for fluency.

```powershell
# Retrieval (already run; outputs refuse overwrite)
.\.venv\Scripts\python.exe -X utf8 scripts/ab_table_text_candidate.py --candidate-dir work/table_text_candidate_final --stage retrieval
# Local preparation only (already run)
.\.venv\Scripts\python.exe -X utf8 scripts/ab_table_text_candidate.py --candidate-dir work/table_text_candidate_final --stage packets
# Only after explicit external-service permission
.\.venv\Scripts\python.exe -X utf8 scripts/ab_table_text_candidate.py --candidate-dir work/table_text_candidate_final --stage answers
.\.venv\Scripts\python.exe -X utf8 scripts/summarize_table_text_ab.py --candidate-dir work/table_text_candidate_final
```

Validation: **29 tests passed** (candidate build, existing chunker/BM25 and A/B
harness tests); Ruff passed. The original corpus/registry/docstore hashes remain
unchanged. Production code, prompts, deployment and published metrics are untouched.

**Decision: hold candidate v1, retain production corpus.** Retrieval losses and
remaining duplicate/source-metadata concerns already prevent recommending
promotion. The final-answer comparison remains unfinished, not silently marked
passed. Further build changes, if pursued, belong to a new candidate identity;
keep this run as the paired diagnostic of v1.
