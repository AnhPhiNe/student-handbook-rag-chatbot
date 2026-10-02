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

## Stage 4 — approved full re-embedding and candidate publication

User explicitly approved re-embedding all 3,835 search records with parallel API
batches, then testing new MongoDB/Qdrant collections. This supersedes the earlier
35-only embedding limit, not production activation. Starting checkpoint is
`e5ca4706`. Keep v35, frozen source data/descriptions, README and gold unchanged.

`scripts.publish_table_search_candidate` validates the entire frozen corpus and
source hashes before paid work. Use batches of 64, 32 concurrent workers and at
most one retry per batch. EmbeddingClient defaults remain unchanged; only the
publisher sets the new optional document retry configuration. Save full vectors
locally before upload, refuse existing targets and never delete collections.
MongoDB stores unchanged full parents; embeddings belong in Qdrant only.

The publisher checks every remote payload/vector against the local artifact and
every remote parent against source data, then verifies baseline counts unchanged.
No old vectors need to be fetched or reused. Keep partial candidate resources and
saved vectors on failure, report the failed stage, and do not activate them.
The first live check is 15 frozen development retrieval probes using new stores,
actual embedding/RRF/reranking and source hydration. It is not a planner/composer
benchmark or proof of policy-complete final answers. No HF switch or push occurs.

Stage 4 result: full re-embedding completed with 32 workers, batch 64, 65 API
requests (60 batches plus retries) and 324,386 reported input tokens. Embedding
elapsed time was 13.59 seconds; upload and exhaustive read-back are additional
time, not included in that figure. Saved vectors have shape 3,835 × 1,024 and
SHA-256 `22fd8cf62ac03a531c40cf584c92d1e6d202905cf1004d6a8ed718fdcffbed2c`.
The new stores contain exactly 3,835 vectors and 541 unchanged parents. Every
vector/payload/parent matched the local artifacts; v35 counts stayed 3,800/541.
No source PDF rebuild, production environment change or baseline write occurred.

The live 15-case development run completed: parent Hit@5 15/15, expected table
family hydration 15/15, dense success 15/15, Voyage applied 15/15; no execution
errors, unauthorized cohort sources, incorrect parent provenance or raw tables
were observed. Retrieval p95 was 2.82 seconds (first query 3.94 seconds); it is not
planner or end-to-end latency and excludes initialization. All three foreign
language probes also retrieved an Article 4 policy parent alongside the appendix.

Family hydration is deliberately NOT exact query/scope correctness: duration
probes hydrated both training-mode tables, and the K51 grade probe hydrated both
course groups. Returned raw tables keep their applicability; composer behavior
and evidence budgeting across these sources still require end-to-end validation.
The fixture is known development data, not a new held-out score. No planner or
composer was called, so no final-answer accuracy or production readiness is claimed.

Offline verification: 1,451 backend tests passed (same two dependency warnings),
full CI-equivalent backend lint/artifact/diff checks passed. Standards: zero final
actionable findings after provider pinning, vector-index binding and live failure
handling corrections. Spec: zero final actionable findings after validating both
existing and added cohort/provenance fields and labeling family coverage accurately.

Runtime report paths are under the separate candidate output directory:
`publication_report.json`, `embeddings_full.npy` and `live_retrieval_report.json`.
The original candidate manifest stays frozen as a build record; publication status
is recorded separately, not by rewriting its historical `embedding_created=false`.
Live report SHA-256:
`c7d259e5d113dd82e1ab142781860ee07cdd0eb9860e7a507f22368d1c8169a7`.

## Stage 5 — task-local evidence fixes after the read-only audit

Approved implementation starts from `fd62acc8` and fixes two offline-reproduced
contracts only. Keep the planner/composer prompt text and versions, canonical
source data, gold, public response schema and production configuration unchanged.
No inference, re-embedding, remote write, push or deployment is part of this stage.

- Hydrated raw-table evidence stays task-local when items/citations share a
  canonical parent. The merge identity includes task support plus the hydrated
  representation; a table cannot replace a sibling table or a plain source for
  another task. Identical same-task duplicates still merge, ordinary parent
  fusion is unchanged, and public parent citations deduplicate after composition.
  The existing source-support diagnostic map unions task IDs instead of losing
  one when the parent has multiple internal representations.
- Amendment selection receives the unit's authorized parent IDs before registry
  selection, relevance ranking and item limits. Both registry records and parsed
  footnotes must amend an authorized primary parent. Related footnotes remain
  usable through their declared authoritative target; an unknown related target
  is not guessed from adjacency. Cohort/admission-year checks remain unchanged.

Regression fixtures cover both task orders, same-parent duration/grade tables,
plain RAG + table RAG, structured fact lock + table RAG, cross-cohort rejection,
low context budget, duplicate source behavior, source-support aggregation, real
K51 amendments across RAG/structured tasks, shared authorized parents, relevance
budget starvation, related targets, and wrong cohort/year. Fake composers verify
sync and SSE receive the corrected packet without calling a provider. No exact
question, program, certificate or benchmark ID is used as a runtime rule.

One old prompt-builder fixture was corrected to declare the related footnote's
authoritative target. Its previous expectation implicitly guessed that a note
in Article 11 amended Article 10, which the new authorization contract forbids.
This changes a synthetic unit fixture, not evaluation gold or source metadata.

The observed TOEIC warning and qualification issue is still a known composer
limitation. These runtime fixes do not claim to fix it. Candidate promotion,
portable registry paths, deploy/build identity, HF readiness and any live E2E
smoke remain subsequent release work; saved publication/retrieval reports stay
unchanged as historical measurements.

Review status: the two parallel reviewers supplied partial findings and offline
checks without identifying an introduced defect, but hit their usage limit before
their final reports. This is not recorded as a completed two-axis review. The main
agent completed the diff review and added a real pure-structured executor regression
alongside the synthetic task-isolation fixtures. That regression verifies the K51
canonical failing row remains fact-locked and its full source context reaches the
composer without RAG items or provider calls.

Known pre-existing limit: the amendment collector discovers primary parents from
`retrieved_items`, so a pure structured answer does not emit a separate registry
amendment list just from its citations. Canonical amended tables and the full
parent `source_context` are still supplied. This stage does not expand that
mechanism or claim all amendment paths have been redesigned.

Final offline verification: 1,473 backend tests passed with the same two dependency
warnings; 69 focused task-isolation/prompt-builder tests passed. CI-equivalent
backend lint, deploy-artifact/hash checks and diff whitespace checks passed.
AST source comparison confirms the composer prompt renderer is byte-for-byte
unchanged as normalized source; planner source, configurations, canonical data,
gold and README have no diff from the starting checkpoint. Main-agent review
completed after the partial reviewer reports. There were no inference calls or
remote writes, and the unrelated dirty primary checkout was preserved.

## Stage 6 — portable candidate runtime package, offline only

Approved scope: package the already-published reviewed candidate without changing
the canonical corpus, prompt, gold, public API or production environment. Starting
checkpoint is `3c259bbb`. This stage performs no inference, embedding, remote
verification, collection write, GitHub push or Hugging Face deployment.

`scripts.build_candidate_runtime_bundle` validates the frozen candidate, source
hashes, embedding configuration and completed publication verification before
writing a separate runtime overlay. It refuses protected/frozen destinations,
existing overlays, customized environment samples and conflicting source bytes.
The saved publication report is evidence from Stage 4, not a fresh remote check.

The runtime manifest keeps source build ID `build-0e6fa69b1de57a12dc1a`, matching
the unchanged source snapshot and tags on the published remote records. Its
canonical narrative artifact still contains 3,800 children; the original
table-separation audit is not rewritten. An explicit `indexed_artifacts` list
adds the 35 reviewed search descriptions, making the index count 3,835. The
manifest pins description/review/candidate/publication hashes separately.
`verify_remote_build` understands this declaration while retaining the 3,800
default for legacy manifests. No generated artifact is edited in place.

Only the packaged manifest/config/sample environment select the candidate stores:
`student_handbook_table_search_f3c77e0908bc` and
`parent_docs_table_search_f3c77e0908bc`. The table registry path becomes the
portable `data/processed/tables/structured_tables_registry.json`. The packaged
sample sets both Qdrant collection variables explicitly to prevent a stale hybrid
alias from silently selecting another collection. It contains no credentials;
the repository's sample environment, retrieval config and manifest are unchanged.

`deploy_hf_backend.ps1` accepts optional `-CandidateArtifacts` and
`-PythonExecutable`. Without the candidate option its v35 defaults remain intact.
A real deployment now requires a clean source worktree before any network step.
Explicit collection overrides must match the packaged manifest. Docker inclusion
and Git byte-preservation rules include the description artifact. The generated
HF metadata README exists only inside the package; the repository README is not
edited. A dry-run does not clone, commit or push an HF repository.

Offline checks cover immutable source bytes, portable table loading, publication
failure guards, destination guards, legacy/extended index counts, malformed
declarations and local readiness with mocked dependencies. Final backend suite:
1,486 tests passed, with the same two dependency deprecation warnings; 29 focused
packaging/configuration tests passed. Lint and diff whitespace checks passed.

The actual PowerShell dry-run completed and staged artifact/hash checks passed.
Importing the staged runtime loaded all 35 table descriptions and returned ready
with dummy credentials and mocked ready dependencies. That is a local packaging
check, NOT proof of live Qdrant/Mongo availability or HF readiness. The generated
runtime manifest SHA-256 is
`39a30516b865d2c35281be47ce99886ae56cce4fbcaa32b57d1147d89238934d`;
runtime retrieval-config SHA-256 is
`09174ad5da435529cb50a1bebdcb9439c1c7c15ac700cd6e2bb56cdcc19cd977`.
The package and bundle report remain untracked generated output.

Review: main-agent Spec review found no outstanding scope/contract defect in this
packaging diff; main-agent Standards review found no blocking readability or
speculative abstraction issue. These are not independent reviewer reports. The
parallel reviewers from Stage 5 did not finish because of their usage limit.

Next gate is a separately approved, bounded end-to-end development smoke against
this candidate with frozen prompts. Check final answers, evidence/citations,
cohort/scope and latency; include the known TOEIC qualification/noise concern.
Do not promote the candidate or claim production readiness from offline tests.

## Stage 7 — explicit conditional scoring evidence (2026-10-03)

The approved 12-case candidate smoke produced ten answers; the last two requests
received local HTTP 429 before planning. They have not been rerun. Its saved
`release_08` answer incorrectly opened with C for 5.2/10, then correctly described
D+ for both K51 course groups. The saved planner selected scoring/graded; the
resolver had already computed D+ with pass status in the foundation table and
fail status in the remaining-course table. The same contradiction was observed
in the user's website screenshot. These observations are not a new held-out score.

This correction preserves source facts and arithmetic.
`scoped_resolved_rows` recognizes complete conditional rows from trusted structured
citations, checking that each row belongs to its declared table. The packet
exposes these as explicit `resolved_rows` and focused content instead of requiring
another interval search inside the display table. Full parent text remains
in `source_context` for policy conditions. Full raw tables, public response fields
and source records remain unchanged for UI/audit. Incomplete groups, invalid or
wrong-scale inputs and ordinary RAG evidence keep their existing representation.

Conditional rows remain evidence-only: there is no new global fact lock and no
forced choice between mutually exclusive course scopes. Citation merging binds
them to their task and execution cohort, so two tasks with different operands
cannot share each other's computed rows even when they cite the same parent.
Same-task sibling tables still merge; existing unique `resolved_result` behavior
is unchanged. Budget truncation cannot retain an unbounded explicit row field.

No K51 ID, 5.2 threshold, D+ answer or particular question is introduced as a
runtime rule. The change uses the resolver's existing table identities and rows.
Planner/composer instruction text, prompt versions, production config, README,
canonical data and evaluation gold remain unchanged. Pipeline version is now
`v80-scoped-resolved-evidence` to identify the changed evidence presentation.

The first implementation only focused this evidence. The user approved six
DeepSeek composer replays (limit 18 requests including retries). All six completed
with one request each, no retry and no other provider calls. The ambiguous query
still produced C in two of three attempts; the explicit-scope, two-entity and /4
controls answered correctly. The historical reports remain saved separately.
Focusing evidence alone therefore was NOT accepted as a fix.

The final correction uses `build_scoped_score_answer` for a complete plan of pure
direct scoring lookups (`grade_10_to_letter` or `pass_threshold`) when every unit
has complete, source-bound conditional rows with scope labels. It presents each
verified row and its scope directly through the existing terminal-answer path,
with `status=answered` and `llm_called=false`. It never calculates another grade,
merges the scopes into a global fact or asks a composer to reinterpret intervals.
Known-scope fact locks, policy/list questions, mixed plans, explicit amendments
and incomplete evidence retain the existing composer path. This is a domain
presentation function, not a post-hoc regex replacement of model text.

Verification: 37 new offline tests cover eleven numeric values, range boundaries,
decimal spellings, unknown/known scope, wrong scale, two task orders, same-parent
input isolation, RAG/cohort isolation, malformed/partial groups, UI source-table
preservation, context budget, deterministic sync/SSE output and guards that keep
policy/mixed/incomplete plans outside the direct renderer. All 1,523 backend
tests passed, with the same two dependency
deprecation warnings. Lint and deployment source-artifact/hash checks passed.
Final local HTTP verification posted the original query to both `/chat` and
`/chat/stream` using the saved plan/evidence. Both returned HTTP 200, identical
D+ answers, separate pass/fail scopes, two public structured tables and
`llm_called=false`. No inference was needed for this final check. Offline executor
tests additionally exercise actual normalization/resolution/source binding, not
only the saved packet. This proves the direct-answer path for the covered contract;
it is not a new live planner/retrieval measurement or evidence of HF deployment.

Local output reports: `scoped_score_fix_replay_20261003` holds the six paid replays
of the rejected first implementation; `scoped_score_final_offline_20261003` holds
the final HTTP/SSE check. Original smoke reports, gold and source hashes remain
unchanged. The TOEIC warning concern and two rate-limited smoke cases remain
separate release items.
