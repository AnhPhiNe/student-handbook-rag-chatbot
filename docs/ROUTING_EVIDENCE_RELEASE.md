# Routing/evidence work — offline, staged delivery

Approved scope starts from deployed main `e88bca6c`. Each stage is tested and
reviewed before a separate local commit; no push, inference, remote indexing or
deployment is authorized by this offline work.

## Stage 1 contract

- Keep existing QueryPlan v1, independent tasks and the three-task cap. No
  answer_groups, DAG, new planner mode or provider/config change.
- Fix operation/scope compatibility through registry metadata, not query words:
  course scope selects course-grade/pass tables, not letter-to-4/GPA/conduct.
- Describe actual table/catalog capabilities and policy exclusions. No
  certificate-specific mandatory threshold or benchmark-case rule is added.
- Reference-table/formula evidence can include its own parent as source_context;
  directories cannot. It shares the existing context budget, task/cohort and
  provenance. A fact lock is a table result, not a final policy entitlement.
- Unknown resolver None and exceptions never authorize fallback. A classified,
  validated missing source permits one RAG retrieval per task/cohort; ambiguity,
  missing input, selector conflicts, valid negative results and missing fields do
  not. Empty/malformed catalogs remain unclassified rather than proving absence.
- Keep the original planner decision in diagnostics. Record executed mode and
  fallback/failure reasons per cohort. A successful fallback is not a correct
  planner decision or a new accuracy score.
- Only notes of sources actually used belong in the answer. Prompt clarification
  and fixture checks are not proof of live composer compliance.
- Freeze a new v57 offline provider-request fixture and preserve historical v56.
  Gold facts and all historical evaluation reports remain unchanged.

## Stage 2 contract

Generate deterministic retrieval descriptions for every reviewed structured table
(currently 35), using existing metadata/columns/entity labels. Identity is source
cohort + parent ID + table ID, not table ID alone. Descriptions are search handles,
never numeric evidence. Retrieve raw table/parent with applicability/provenance;
keep structured execution and the existing hybrid/parent-child pipeline.

Candidate artifacts, manifest and storage targets must be separate from v35. Do
not rebuild PDFs, modify canonical source data, upload points or call embeddings
in this offline stage. Validate with fake stores/embeddings; live quality/latency
and any paid index build remain a separately approved experiment.

## Acceptance

Tests cover normalization, operation/scope selection, bounded fallback and blocked
fallback causes, source-context budget, task/cohort isolation, policy+table data,
and final sync/SSE composition with fake providers. Existing full backend tests
must pass before each commit. Test expectations/snapshots are changed only for
documented new behavior, not to change evaluation facts. No claim of exhaustive
handbook search, zero hallucination or improved production performance is made.

Stage 1 verification: 1,381 backend tests passed (two existing dependency
deprecation warnings); CI-equivalent Ruff E/F, artifact/hash audit and diff
whitespace check passed. Review findings on malformed catalogs, mixed-operation
scope selection, original grounding and unknown diagnostics were corrected and
covered by regressions before commit. v57 is an unmeasured candidate: a changed
request snapshot is not a new quality result. No production/source data changed.

## Stage 2 candidate use and limits

Use `python -m scripts.build_table_search_candidate --output <separate-output>`.
The generator produces 35 stable table handles and 3,835 combined search records,
plus an experiment manifest and an opt-in retrieval configuration. It never
embeds, uploads, rebuilds PDFs or changes the canonical build manifest. Unreviewed
tables are excluded; duplicate composite keys or invalid parent identity fail.
The manifest uses a separate experiment schema and must not replace the default
runtime build manifest or be fed blindly to the v35 publisher.

For this source the proposed namespaces are
`student_handbook_table_search_fd6ed6b33c44` and
`parent_docs_table_search_fd6ed6b33c44`; neither was created remotely. The opt-in
configuration refuses the baseline collection and pins registry bytes. The Mongo
target must be supplied separately when a later approved experiment publishes
copies of the unchanged parent artifacts. Candidate publication and readiness
verification are a later step, not a claim made by this offline package.

The existing dense/BM25/RRF/rerank path is reused. Trusted handles are grouped to
their exact full parent and materialize the matched raw table, not a summary.
The raw table is prioritized within the same context budget; if it cannot fit,
its absence is explicit rather than passing a cut JSON table as complete data.
This internal table context is removed from public citations. No lookup slots or
fact locks are inferred, and default retrieval.yaml remains unchanged.

`python -m scripts.evaluate_table_search_lexical --output <report.json>` compares
baseline/candidate BM25 on the frozen 15-case development fixture. Observed parent
Hit@5 is 12/15 baseline and 15/15 candidate. This is BM25-only source coverage, not
held-out quality, exact-row correctness, dense/rerank performance or production
latency. Do not place it on the CV as an answer accuracy improvement.

Tests additionally use fake embeddings, Qdrant, Mongo parents and reranking to
check hydration/provenance, disabled operation, stale hashes, wrong parents,
budget exhaustion, all five table types and newly reviewed tables. Real composer
behavior, policy+table retrieval completeness and operational latency still need
separately approved API experiments; no automatic production activation occurs.

Stage 2 verification: 1,406 backend tests passed with the same two dependency
warnings; lint/artifact/hash/diff checks passed. Spec and Standards reviews have
no remaining actionable findings after fixes for canonical-table applicability,
unsupported cohorts, zero-budget diagnostics, protected report destinations and
public/internal payload separation. No case-specific routing rule was introduced.
All generated candidate files remain outside canonical data and are not committed
as a replacement corpus. Commit stages were kept separate as requested.
