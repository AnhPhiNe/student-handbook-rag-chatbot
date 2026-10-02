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

## Stage 3 — directly authored and source-reviewed search text

User requested Codex itself write and review the descriptions, without calling a
separate generation model. Scope: all 35 tables, offline only; preserve metadata
v1 as the comparison baseline, canonical facts, source files, gold and production.
Starting checkpoint is `7217745e`. No new routing rule or runtime LLM is added.

`configs/table_search_descriptions.yaml` freezes 35 Vietnamese descriptions
(`table-description-reviewed-v2`), each two to four sentences. These are reviewed
against the canonical table rows, applicability and their full source parents.
The foreign-language scope also uses the parent containing Article 1. This is
Codex's source review, not an independent human review or a new policy authority.
No benchmark questions or gold were used to author the text. Numeric thresholds,
money amounts and actual formulas remain in raw evidence, not the search text;
scale identifiers and source-scope years are included where needed.

The v1 review identified three pairs of identical duration descriptions inside
the same cohort/parent, 12 tables whose applicability was absent from search text,
and 13 descriptions exposing technical English column names. Reviewed text names
training mode, relevant course scope, scales and supported outputs in Vietnamese.
Duration descriptions describe only their own training mode rather than inserting
the other mode's search keywords as a negation. K51 scholarship classification
describes combinations of academic/conduct classifications, unlike K48-K49/K50's
numeric-range tables. Formula descriptions distinguish scholarship points from
money and include input scales. Foreign-language text identifies the appendix,
certificates and separate TOEIC components, without making TOEIC compulsory.
Classification tables do not promise policy eligibility or override exceptions.

The review file can supply only an exact composite key and text for each approved
table. It pins the registry and full-parent artifact hashes. Missing, duplicate,
unknown or stale entries and metadata overrides fail before building. Generated
metadata, identities, source hashes, source pages and applicability are unchanged
except for the description-version marker. Only search text is replaced.

Build with `python -m scripts.build_table_search_candidate --descriptions
configs/table_search_descriptions.yaml --output <new-separate-output>`. Omitting
`--descriptions` still produces metadata v1. The reviewed candidate namespace also
includes the review file's SHA-256, so changing text cannot reuse the old namespace
silently. Preserve the existing v1 artifacts; do not regenerate over them.
The builder refuses any destination containing one of its generated filenames,
including a partially populated candidate directory; use a new output directory.

The lexical measurement command accepts the same optional `--descriptions` and
records text version/hash. Run it only after freezing text; do not tune the text
against the frozen development fixture. Training-mode unit probes also check the
exact matched table inside a common parent, which parent Hit@5 alone cannot test.
These checks cannot prove live dense/rerank or final-answer improvements.

No embedding, remote collection write, API inference, push or HF deployment is
part of this step. The previously approved 35-description embedding publication
is paused pending this review and a working read-only vector preflight. No remote
candidate collection has been created. Default retrieval configuration is unchanged.

Stage 3 verification: 1,423 backend tests passed (the same two dependency warnings),
including 42 focused candidate/text tests. Full CI-equivalent backend lint,
deploy-artifact checks and diff whitespace checks passed. Final Standards review:
zero actionable findings after correcting output overwrite protection. Final Spec
review: zero actionable findings; all 35 descriptions checked against sources.
Canonical source data, README, production configuration and gold were not edited.

Frozen review-file SHA-256:
`73ebe0333f53941ada328dcd5445b0dd47f3bf114594fee320f2d2e9cc4538d7`.
Generated reviewed-text SHA-256:
`838acdb45041fdae1dfef6ab96121d42b31270c216e248b71499b63bb6471d73`.
Proposed reviewed namespaces: `student_handbook_table_search_f3c77e0908bc` /
`parent_docs_table_search_f3c77e0908bc`. Neither was created remotely. Existing
metadata-v1 output hash remains
`546ef1cfb66d9db6c1268817c3ab59bb32d779715d2b6f2bfb0210238d8e3b17`.

After freezing text, the unchanged 15-case development fixture measured BM25
parent Hit@5 at 12/15 without handles and 15/15 with reviewed handles. Metadata v1
also measured 15/15, so this is not a measured improvement over v1. Six separate
description-corpus probes distinguish training-mode tables within each cohort's
shared parent. They establish that the earlier text collision is removed, not
end-to-end answer accuracy or live retrieval quality. The frozen text was not
revised in response to development benchmark results.
