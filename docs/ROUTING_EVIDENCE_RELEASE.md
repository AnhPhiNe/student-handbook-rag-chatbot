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

## Stage 8 — remove only the direct-score answer branch (2026-10-03)

User chose the existing composer pipeline and is testing reasoning `low` in the
primary checkout. Independent review of commit `45a44a8a` found a scope problem:
`direct_value` is a planner/normalizer label, not proof that the question asks
only for a table value. A valid scoring plan for a grade plus graduation/repeat
question could skip the composer and omit a condition already in source context.
Scoring also normalizes an unsupported `open_question` intent to `direct_value`,
so the former post-normalization intent guard test did not cover that behavior.

This stage deletes `build_scoped_score_answer`, its import and the early answered
return in `prepare_answer`. Complete scoring evidence once again reaches the
composer through the existing sync/SSE path. It removes no other Stage 7 change:
the explicit conditional rows, task/cohort binding, safe budget handling, full
source context and public UI source tables remain. No replacement template,
adapter, intent heuristic or case-specific rule is introduced.

Pipeline identity becomes `v81-composer-scoped-evidence`. Planner/composer prompt
instructions, gold, source data and model settings are unchanged by this commit.
The primary checkout's uncommitted `reasoning_effort: low` and its other local
changes are preserved; this worktree's model config is not silently synchronized
with it. This is a code-only removal, not a deployment or a new measured choice
of composer effort.

Tests now require an actual fake-composer invocation for the conditional score
path and final `llm_called=true` for sync/SSE. The graduation regression runs real
normalization/resolution with both raw intents and both scoring operations,
verifying the original question, resolved D+ rows and the repeat condition reach
the composer. Existing range, scale, multi-task/cohort and evidence-budget tests
remain. These tests verify routing/content delivery; they do not establish the
answer quality of DeepSeek `low`.

Historical Stage 7 reports describe the removed branch at its original commit.
They remain untouched; the old offline `llm_called=false` result is not presented
as a result of this restored composer pipeline. No inference, push, deployment
or worktree/branch deletion occurs in this stage.

Verification: 235 focused tests and all 1,524 backend tests passed, with the same
two dependency deprecation warnings. CI-equivalent lint, deploy-artifact/hash
checks and diff whitespace checks passed. The retained Stage 7 evidence/provenance
files have no diff in this removal. No executable source/test caller of the
deleted direct-answer helper remains.

## Stage 9 — approved low-reasoning composer probe (2026-10-03)

User explicitly authorized eight prepared outputs, sending handbook-derived
prompts/evidence to `https://api.deepseek.com/chat/completions`, capped at 24
requests including retries. The first execution was rejected before starting
because payload/destination approval needed to be explicit; it made zero calls.
After the user's explicit confirmation, the frozen run completed on `6487ca55`.

The separate test YAML changes only `llm.reasoning_effort` from none to low. Model,
prompt, evidence, 60-second attempt timeout, retry policy and omitted max_tokens
remain fixed. Three ambiguous-grade repetitions and two controls have identical
prompt hashes to historical none replays. Boundary/conditional-policy fixtures
use real offline normalization/resolution and canonical parents; other inputs
reuse saved evidence. This is composer validation, not fresh live planning/RAG.

All eight requests succeeded once, actually sent low and invoked the composer.
No retry, truncation, other provider or judge call occurred. The 5.2/10 ambiguous
query returned consistent D+ with separate foundation/remaining pass statuses in
3/3 attempts, versus 1/3 correct in the earlier identical-prompt none replay.
Both boundary values, two entity-score-scope pairs and the /4 operand were handled
correctly. The graduation answer retained the rule requiring repetition below C.

Required numeric/condition checks passed for 8/8 outputs. Strict source review
fully confirms 7/8: the graduation answer additionally asserts that graduation
courses belong to the remaining-course group, which is not directly established
by the supplied source. Its repeat conclusion is correct without that assertion.
This probe therefore does not claim 100% fully grounded answer accuracy.

Observed replay wall p50/p95 is 7.30/11.56 seconds, excluding live planner/retrieval.
Composer-only usage is 76,833 input and 12,735 output tokens; 11,029 reasoning
tokens are included in output, not additional. Historical router usage retained
in the saved result/tracker is excluded because the router was not called.
Omitting max_tokens retains the same application policy, but provider default
maxima differ (8K none / 64K thinking). This historical comparison is not a fully
isolated or randomized A/B, and eight outputs do not establish production reliability.

The candidate remains on the composer path. No canonical configuration, gold,
source data, prompt or production setting changed during this run. Low is a
candidate for the next existing answer-regression run; no default switch or
deployment is performed from this small probe alone. Source review and raw
outputs are under local `output/composer_low_probe_20261003/`; prior reports remain.

## Stage 10 — adopt low in the release candidate (2026-10-03)

User accepted the probe's eight required-answer outcomes and treats the extra
graduation-group explanation as a minor caveat. The original strict source-review
note remains in the historical report; no gold, answer or score is rewritten.

Candidate `configs/answer_generation.yaml` now sets composer reasoning to low.
This is the sole behavioral configuration change: model, input/output policy,
60-second timeout, retries and directory-selector settings remain unchanged and
match the probe's temporary profile. The primary checkout's user changes are
preserved. The direct-answer bypass remains removed.

An existing client-construction test now checks the intended default low rather
than the old none setting. Previous prompt-v3.30 comparisons and none-based
historical reports retain their original labels. Low is selected for the candidate,
not silently applied to HF; broad answer regression and deployment checks remain.

Preparation identified an important runner distinction: `run_official_answers
--suite answers` performs fresh planning/retrieval, generation and LLM judging;
it is not composer-only. The existing `replay_composer` reuses historical packets
and explicitly assumes an unchanged packet builder, which is not true across the
recent evidence fixes. A fresh regression must be labelled and budgeted accordingly;
do not pass an old packet replay off as validation of this release pipeline.

Verification: the candidate YAML is semantically identical to the low profile
used in the approved probe; comparison with the previous candidate confirms only
the composer effort changed. 90 focused configuration/client/packaging tests and
all 1,524 backend tests passed (the same two dependency warnings). Lint,
deploy-artifact/hash checks and diff whitespace checks passed. Broader API
regression has not started and its larger egress/request scope remains separate
from the completed eight-output approval.

## Stage 11 — approved 150-case current-pipeline regression (2026-10-03)

The user explicitly approved one fresh run over the existing 150 answer cases,
including OpenAI planning, DeepSeek composition/catalog selection, DeepInfra
query embedding, Voyage reranking and Groq judging. All payloads/destinations
and retry-inclusive caps were approved. The run used frozen `284d5a91`, Luna
medium, composer low and the reviewed table-search candidate collections. It
did not write either collection, export LangSmith traces or change production.

All 150 cases completed without a final pipeline exception: 146 answered,
two asked for missing information and two were out of domain. All 150 planner
requests succeeded with no fallback; 146 calls actually invoked composer low.
Provider request counts were OpenAI 150, DeepSeek 156 (146 composer and ten
selector calls), DeepInfra 86, Voyage 80 and Groq 156. Twelve embedding timeout
attempts across six cases fell back to BM25; six judge HTTP 401 attempts were
recovered through key rotation. These attempt failures remain in the report.

Raw judge scores were correctness 97.75/100, faithfulness 95.55/100 and citation
correctness 98.26/100. These are mean model scores, not verified percentages of
correct cases. Warm local pipeline p50/p95 was 13.17/24.99 seconds, excluding
judge and startup. This is neither an isolated reasoning A/B, a new hold-out,
nor validation of the deployed HF HTTP/SSE path.

Source review confirmed substantive routing/evidence errors in 029, 056 and
059: generic complaint-service records were supplied instead of the specific
graduation-review/training-conduct provisions. Raw unsupported flags were
18/150. Sixteen flags involved details present in the original composer packet
but lost by the judge's omission of `source_context` or later compaction; 056
was a real scope error and 125 was a questionable scoped-absence flag. No raw
score was rewritten and no corrected hallucination rate is claimed. Judge
packet repair/rejudging is a separate task, not included in Stage 12.

The raw run and manual review are preserved locally under
`output/answer_regression_low_20261003/`, including the frozen runtime, dataset,
provider attempts, full composer packets, raw judgments and `REVIEW.md`.

## Stage 12 — minimal directory task-context correction, offline (2026-10-03)

User approved fixing on the already-clean `codex/routing-evidence-coverage`
branch, testing offline and making a separate local commit. The primary
`eval/official-v4` checkout and its unrelated edits remain untouched. No new
branch or worktree was created.

Changes are limited to two concerns:

1. When the service selector needs an LLM, it now receives the full **task**
   question, the extracted service hint and scalar/list `requested_field`.
   The hint no longer replaces the question. Each hint is still selected
   independently; unrelated tasks and raw chat history are not supplied.
2. Selector instructions and the planner's registry tool-use text agree that
   a generic duty does not prove authority for every specialized situation.
   Equivalent wording is allowed; insufficient catalog support means `none`,
   not nearest-record guessing. Missing contact columns in the selector's
   compact list do not by themselves invalidate the identified unit.

No output schema, gold facts, source data, public HTTP shape, composer prompt,
model configuration or second-look/fallback policy changed. Exact name/alias
matching remains the identity fast path, and same-unit `ambiguous -> match`
grouping remains unchanged. Both are retained limitations: no independent
semantic verifier was added, and an erroneous match still bypasses second-look
and RAG. The existing verified-none path, cohort/catalog/input checks and
single RAG attempt are reused; API/JSON/ID failures still ask for clarification.

Selector prompt identity is `directory-selector-v3-task-context`; pipeline
trace identity is `v82-directory-task-context`. The planner system prompt and
schema remain v57; its existing registry digest distinguishes changed tool
instructions in plan-cache keys. A separate request snapshot
`luna_planner_request_v57_service_scope.json` changes exactly the three tool-use
occurrences in the captured request scenarios. The original v56/v57 snapshots
and historical reports remain unchanged.

Offline verification: 130 focused tests and all **1,544 backend tests** passed,
including 20 new task-context/outcome tests. Coverage includes normalization,
removed ungrounded slots, field arrays, missing contact targets, aliases,
multiple hints, task/history isolation, same-unit grouping, cross-cohort
filtering, valid-none fallback and fail-closed malformed/unknown/ambiguous
outputs. The three failed queries pass through real normalization/resolution/
execution with a **scripted none decision and fixture retrieval**; their correct
source/cohort/provenance reaches the composer packet. This proves plumbing,
not that live Luna/DeepSeek/retrieval will now answer the three cases correctly.

External socket connections were forbidden in the offline test process; local
loopback was allowed for Windows asyncio's internal socketpair. The first full
attempt blocked that internal loopback and failed API fixtures; after fixing
only the test harness and saving the revised request snapshot separately, the
full suite passed with the same two dependency deprecation warnings. Lint,
deploy-artifact/hash checks and whitespace checks passed. No inference API was
called, no model-accuracy/latency improvement was measured and nothing was
pushed or deployed. A bounded live smoke with normal service/alias controls
requires a separate approval before claiming semantic improvement.

## Stage 13 — approved twelve-case E2E selector-scope smoke (2026-10-03)

User approved one frozen run on `6f3a817c`: three original failures, three
development paraphrases and six existing controls, with explicit payload/API
destinations and retry-inclusive caps. All twelve answered and manual source
review confirmed the required answers. The six specialized queries took RAG
directly and received the correct same-cohort provisions, rather than generic
complaint-directory records. This does not isolate selector-prompt improvement
from registry routing instructions or model variation.

42 provider attempts all returned HTTP 200: OpenAI 12, DeepSeek 18 (12 composer
and six selector), DeepInfra six and Voyage six. The KTX selector fast pass
returned none; its existing low second-look correctly identified the service,
then the email came from the catalog. Composer had no retries. Warm pipeline
p50/p95 was 12.83/23.70 seconds; no judge, LangSmith, collection writes or
production deployment occurred.

The intended office control 109 actually routed to student_service, so no live
office-path coverage is claimed. Faculty 112 used exact matching; program 116
invoked the selector. No multi-entity live case was included. The 056 answers
correctly kept the distinction between seven days after council-approved
results and twenty days after provisional online results, supported by separate
provisions in the provided K50 packet. Results are under local
`output/selector_scope_smoke_6f3a817c/REVIEW.md`; source stayed clean at 6f3a817c.

## Stage 14 — source-faithful judge compaction, offline (2026-10-03)

User approved evaluator repair, offline tests and a separate local commit.
No new inference is authorized by this stage. Only evaluation code/tests and
this release log change; routing, composer prompt/model configuration, source
data, gold, deterministic contract, HTTP/SSE and README remain unchanged.

Judge extraction now retains each primary source's actual `source_context`,
including scope/conditions and table layout. Structured JSON and resolved_result
are kept intact instead of being split at address punctuation or truncated to
invalid JSON. The canonical composer packet is authoritative: execution JSON,
related references and public citations outside it cannot add evidence. An
empty authorized packet stays empty. Historical/legacy extraction remains as
fallback only when there is no recognized canonical packet.

Compaction preserves required source facts and anchors individual answer claims
to related **actual** source units with lexical overlap, then ranks remaining
evidence. This selects evidence, not entailment/correctness; neither answer nor
gold becomes retrieved evidence. The packer no longer cuts a unit halfway
through its qualification; oversized units are omitted whole, with omission
counts exposed. Source omissions are still possible under a finite budget.

Packet/report/checkpoint identity now carries `judge-packet-v2-source-context`.
Old-version checkpoints cannot silently resume into the new measurement.
Rubric, judge provider/model and request policies remain unchanged. Existing
budget settings are not increased; estimated full prompt plus output maximum
on the audited cases fits the existing 8K per-key token accounting. These are
character-based estimates, not provider usage or a guaranteed 5K prompt ceiling.

Offline reconstruction of all 150 saved answers restored complete source_context
for fourteen reviewed structured cases, the missing conditions of 039 and the
currency note of 142. The initial revision still lost 131's medical-certificate
condition; per-claim anchoring corrected it before commit. Checksums confirm
historical cases/answers/judgments/report are untouched, and wrong old answers
029/056/059 are not corrected or supplied gold evidence by the evaluator.

Eight lexical required-fact-coverage diagnostics decrease (041/049/112/114/121/
127/130/144). Manual review finds the real source facts still present, including
all units in the contact cases. Removing non-authorized execution fields and
differences between a semantic gold summary and source wording explain these
heuristic deltas; no threshold/alias/gold change is used to hide them. Coverage
is not a new accuracy score. No new judge scores or hallucination rate are
claimed before an approved API rejudging run.

Verification: all **1,561 backend tests** passed, with 17 new preservation,
authorization, provenance, atomic-packing, numeric negative-control and resume
identity tests. Lint, deploy-artifact/hash and whitespace checks passed; the
same two dependency deprecation warnings remain. External network was forbidden
in the test harness. The offline audit and 150 rebuilt packets are preserved
locally under `output/judge_packet_offline_20261003_verified/`.

Next, subject to separate payload/budget approval, judge-only remeasurement must
use a new report path for the old answers. It does not replace a fresh answer
benchmark of the fixed runtime and must not overwrite the historical report.
No API, push or deployment was performed in this stage.

## Stage 15 — approved judge-only remeasurement of saved answers (2026-10-03)

User agreed to rejudge all 150 historical answers with packet v2. One frozen
run used evaluator `4f87c395`, the same Groq `openai/gpt-oss-120b` judge/rubric
and existing request policy, capped at three attempts/case and 450 total.
150/150 judgments completed in 389.95 seconds; actual requests were 157
(150 HTTP 200, seven HTTP 401 recovered by key rotation/retry). No planner,
composer, embedding, reranker, source-store or telemetry calls occurred.

The answer runtime remains `284d5a91`; this remeasurement does not evaluate new
answers from the routing correction in 6f3a817c. All original dataset, answers,
judge scores and report hashes remain unchanged. New results are separate under
local `output/judge_remeasurement_4f87c395_20261003/`, with exact payload/prompt
hashes, per-attempt records and `comparison.json`.

Raw mean scores old -> new: correctness 97.75 -> 97.93/100, faithfulness
95.55 -> 98.74/100, citation correctness 98.26 -> 97.68/100. Unsupported flags
change from 18/150 to 4/150 (2.67%): all eighteen old flags disappear, and
029/033/059/129 are newly flagged. This reflects changed evidence presentation
plus stochastic judge variation, not changed runtime behavior. No numeric
correctness/pass-percentage claim is derived from these mean judge scores.

Correctness remains zero for wrong historical answers 029/056/059. 056's new
faithfulness is 1.0 and unsupported is false despite the wrong department:
following a provided generic catalog is not sufficient policy correctness.
Likewise critical_false_pass=0 does not mean there are no serious answer errors.
The successful twelve-case new-runtime smoke is reported separately in Stage 13.

Manual review confirms residual compaction omissions in two new flags: 033's
military-service exception exists in the original Article 16 composer evidence
but is absent from the compact judge packet; 129's Article 11 source_context
has exclusions from GPA that Composer stated, but that whole block is dropped
while less relevant scholarship evidence remains. Both have raw correctness
1.0, faithfulness 0.8. The rationale does not identify each exact clause, so
these omissions are evidence of measurement limitations, not a complete causal
account of judge scores. No packet or rubric was tuned during/after the run,
and no further API calls are made to remove the flags.

The 2.67% rate is therefore reported as a raw judge flag rate, not a fully
verified hallucination rate for the current chatbot. Future publication should
retain packet versions and qualify these limitations; a fresh runtime result
must not combine old answer scores with the separate routing smoke. Source
checks after completion were clean, and historical artifact hashes were verified.
Only this results note is committed afterward; no push or deployment occurs.

## Stage 16 — numbered source clauses in judge packets, offline (2026-10-03)

User approved the small evaluator correction for the remaining observed
omissions. Packet v3 (`judge-packet-v3-source-clauses`) splits authorized source
text at existing top-level numbered provision lines. Subpoints, qualifications
and tables within each provision stay together. An introduction before the
numbering is repeated verbatim for every provision so a shared scope restriction
cannot disappear when a later provision is selected. Unnumbered source_context
remains atomic; valid JSON records are untouched. No business-name/query rules,
new LLM verifier, schema layer or provider/token-setting change was introduced.

This addresses the measured granularity problem: 033's full leave-policy
provision now retains the military exception together with its other reasons,
and 129's relevant GPA exclusions fit separately from the rest of Article 11.
Task/cohort/source metadata remains attached. Required-fact/answer ranking,
rubric, gold and whole-unit packing are unchanged. The format-based splitter is
a bounded heuristic, not proof of all possible policy dependencies; unfamiliar
formatting, cross-provision dependencies or an oversized individual provision
can still need manual review.

Offline reconstruction of all 150 saved packets confirms all 19 reviewed
evidence checks (the previous 16, medical condition 131, and 033/129). Maximum
full prompt estimate is 5,880 tokens; no source/output ceiling was raised.
Lexical coverage decreases only at 147, an unanswerable personal scholarship
list query whose gold describes system access/abstention behavior. Handbook
policy text is not proof of personal-list access; its original abstention
answer and source evidence remain unchanged. The diagnostic delta is retained,
not hidden through gold/threshold edits.

Verification: **1,567 backend tests** pass, including six new clause/scope,
decimal/table, long-article and real saved-output regressions. The fixture copies
033/129 composer packets/answers and only citation fields actually used by the
compactor; case ids never enter implementation logic. Lint, deployment artifact
hashes and whitespace checks pass with the same two dependency warnings.
Historical source/case/answer/judge report hashes remain unchanged. Offline
results live under `output/judge_clause_packets_offline_20261003_final/`.

No API was called; scores from Stage 15 remain labelled packet v2. New v3
scores require a separate measured run/report; no correctness/hallucination
improvement is inferred from offline preservation checks. Runtime routing,
composer, HTTP/SSE, README and source data remain unchanged. This stage ends
with a separate local commit, without push or deployment.

## Stage 17 — approved eight-output judge v3 smoke (2026-10-03)

User requested step 1: judge-only smoke on 033/129, supported controls 039/142,
wrong historical-answer controls 029/056/059, and clarification control 145.
One frozen run used evaluator `cb4ad7c5`, packet v3, the same Groq
`openai/gpt-oss-120b` rubric/model/configuration, capped at three attempts/case
and 24 total requests. 8/8 judgments were valid in 23.03 seconds; actual API
requests were nine (eight HTTP 200, one HTTP 401 recovered by key rotation).

All intended smoke checks passed: 033/129 correctness and faithfulness are
1.0 with no unsupported flag (v2 had faithfulness 0.8 and flags); 039/142
remain supported; the missing-GPA clarification is accepted. Each of the three
wrong historical answers still has correctness 0.0. These negative controls
are not counted as correct chatbot answers merely because the smoke succeeds.

All three negative controls receive faithfulness/citation 1.0 and unsupported
false because they follow their generic catalog evidence, despite wrong
application to the query. Correctness is therefore essential alongside
faithfulness/unsupported diagnostics. Zero unsupported flags among these eight
does not establish a zero hallucination rate. This is a one-shot targeted
measurement on historical outputs, not a full benchmark of the fixed runtime.

Historical inputs/reports retain their checksums. No planner/composer,
embedding/reranking, source-store or telemetry call, prompt/gold edit, extra
rerun, push or deployment occurred. Exact inputs, raw judgments and provider
attempts are under local `output/judge_v3_smoke_cb4ad7c5_20261003/REVIEW.md`.
Only this results note is committed afterward on the existing candidate branch.

## Stage 18 — catalog record identity through evidence fusion, offline (2026-10-03)

The pre-push audit reproduced a pre-existing loss of independently selected
records in multi-task questions. Office summaries omitted `office_profile_id`
from their generic `record_id`; program summaries dropped their existing
`record_id`. Two different records in the same cohort/catalog therefore had
the same fusion key. The second record disappeared while task support and
source pages were combined. Independent lookup was correct; downstream evidence
fusion was not. Synthetic tests supplying IDs had missed the formatting step.

The user approved a general correction. Both summaries now preserve existing
catalog identities. The shared identity helper lives in the existing
`source_identity` module and is used by executor item/citation fusion and final
citation deduplication. The latter had also collapsed distinct faculty/service
records after their executor evidence had already been kept separate.

A complete record-ID list can still share evidence across tasks that request
the same records. A missing, blank or partial ID list instead retains task-local
evidence and its payload, without deriving an ID from a name or guessing
equivalence. Cohort/catalog provenance remains part of the surrounding identity.
Ordinary RAG parent fusion and task-bound raw tables/fact locks are unchanged;
even JSON-list regulation text is not classified as directory evidence.
Program IDs remain internal rather than becoming UI table columns.

Runtime identity advances to `v83-directory-evidence-identity`. No prompt, model
setting, schema, HTTP/SSE field, gold fact or source artifact changes. No new
resolver layer, LLM verifier, database build or API call is introduced.

Verification uses real catalogs across all three cohorts: all 64 office, 69
faculty, 232 service and 129 program records retain their original IDs and
pages, with unique IDs within cohort. New regressions cover distinct records,
reversed task order, legitimate repeated records, missing/partial identities,
cross-cohort identity, final citations, display safety and the sync/stream
composer interfaces. Forty-five initial tests reproduced 38 failures before
the fix and all passed afterward; one additional RAG-JSON negative control
brings the new suite to 46 tests. The targeted suite has 170 passing tests.
All **1,613 backend tests** pass on the final implementation; lint, deployment
artifact validation and whitespace checks pass. The two existing dependency
deprecation warnings remain; no new warnings are introduced.

Offline paired-task probes for all nine lookup branches (office, faculty,
service, program, scoring, formula, duration, scholarship and foreign language)
retain both expected records/values in composer evidence after the correction.
These are evidence-preservation checks, not new model-answer accuracy scores.

The Git ownership exception needed by snapshot tests is scoped to subprocesses
in the offline harness; global Git settings are untouched. Source data, README,
historical reports and the user's separate dirty primary checkout are preserved.
This correction is committed locally on the existing candidate branch; no push
or deployment occurs.

## Stage 19 — signed numeric inputs and completed fact locks, offline (2026-10-03)

The user approved four small hardening stages after the two-branch audit.
This stage addresses numeric parsing and fact-lock completion only. Task/input
binding, per-task target roles and program-existence evidence are later stages,
not silently included here. The starting candidate is `d2f11305`.

The existing `parse_score` now supplies scalar inputs to GPA/conduct, foreign
language and scholarship resolvers. The old input regexes that erased minus
signs were removed. Scoring operations validate their declared 10/4/100 scales
and bounds, including direct legacy calls. Distinct positive/negative list
values no longer collapse through text normalization into conditional rows.
Foreign-language lists also retain their original cardinality: discarding an
invalid member cannot turn a multi-input request into one scalar equivalency.
Source interval extraction remains unchanged, including compact range hyphens,
decimal commas and inclusive/exclusive bounds. No new certificate-scale limits
are invented where the source does not declare them; foreign/scholarship input
fractions are not silently reduced to a scalar with an assumed scale.

A unique certificate row alone no longer creates a fact lock for an unfinished
personal equivalency. Unknown codes, unmatched scalar scores and complete TOEIC
components without a computed level retain the reference table as evidence-only.
No new four-component evaluator was added. Completed numeric/textual levels
still lock; explicit validated reference-column requests (including both bậc 3
and bậc 4) can still lock the verified source row without claiming a personal
level. Full display/reference tables and provenance remain available.

The existing longer-code tests previously expected `resolved_result` containing
`matched_level=None`. They now require evidence-only and preserved reference
columns; the positive-code tests still require the same completed level. This
is a documented contract correction, not an edit to benchmark gold or historical
results. Pipeline identity advances to `v84-numeric-resolution-safety`.

The first 51 new tests reproduced 19 failures before implementation and passed
afterward. Reference-column, source-range, direct-leaf and opposite-sign-list
controls, including five mixed-list review regressions, bring the new suite
to 66 tests. All **1,679 backend tests** pass; lint, deployment artifact and
whitespace checks pass, with the same two dependency deprecation warnings.
Standards review found no actionable issue. Spec review caught the mixed-list
scalarization gap; the final guard and controls resolve it, leaving no
actionable stage-one finding. Tests cross the real normalizer, canonical
resolver, executor and composer sync/stream interfaces with external
network disabled. Fake composer checks establish evidence preservation, not new
LLM answer-quality or latency metrics. No model-specific prompt, case-name
patch, architecture/schema/HTTP field change, provider-setting change or data
rebuild was introduced. README, gold, source artifacts, previous reports and
the user's dirty primary checkout are preserved. The stage ends in a local
commit only, with no inference API, push or deployment.

## Stage 20 — task/cohort and grounded-input consistency, offline (2026-10-03)

The user requested continuation of stage two from clean commit `e88c409a`.
Validation still grounds supplied inputs in the original query and only its
referenced visible history. A new bounded check runs after each task's contract
validation but before compatible/cohort-variant merging. Explicit task-cohort
contradictions and incomplete explicit comparisons become task-local
clarifications; executable siblings are retained. The existing unambiguous
single-task/single-cohort override is preserved. A single follow-up uses its
validated standalone question for consistency, not just the current short turn.
The check never reassigns a student's score or a task's cohort.

Numeric consistency uses the existing signed, scale-preserving grounded parser
and registry input roles. A supplied value is not rejected merely because a
paraphrase omits it. A different grounded sibling operand in the same slot may
prove a conflict only when the task question anchors to the original user text;
explicit denominator contradictions are also checked. Document locators, cohort
identifiers and credit quantities are not personal score operands. No semantic
selector meaning is reinterpreted and no semantic repair/model call is added.

Spec review caught two overblocking cases in the first implementation: three
course credits coinciding with a sibling GPA of 3.0, and a K51 request quoting
a table explicitly printed in the K50 handbook. The final implementation masks
credit quantities, requires user-clause anchoring for sibling-input conflicts,
and excludes explicit printed-source locators from execution-cohort checks.
Plain handbook requests and handbook comparisons still retain their scopes.
Regression controls cover both reviewed cases and the opposite valid cases.

This is not proof of semantic ownership or complete question decomposition.
Paraphrased clauses not anchored to user text, semantic negation or conditions,
and a conflicting number not supplied by any sibling may remain outside the
detector. Explicit scale contradictions still inspect task prose: a planner
inventing a new condition with the same value on another scale may be asked to
clarify; this does not authorize trusting that invented condition. Printed-book
and non-score quantity recognition is a small syntax heuristic, not a general
Vietnamese parsing engine. Further changes require evidence rather than an
expanding keyword policy list.

The first 28 tests reproduced 15 failures on the previous normalizer. Review
counterexamples and controls bring the new suite to 37 tests, spanning RAG and
structured tasks, comparison completeness, three cohort defaults, scope versus
source edition, signed values/scales, reversed order, referenced history,
non-mutating validation, preserved siblings and composer sync/stream packets.
Offline re-normalization of 150 saved answer-run plans and 12 saved routing
smoke plans adds no binding diagnostics; historical plans/answers/reports are
unchanged. This is a compatibility check, not a new runtime accuracy score.
All **1,716 backend tests** pass on the final implementation, with the same two
dependency deprecation warnings. Lint, deployment-artifact and whitespace checks
pass. Spec review confirms the reported overblocking cases are corrected; the
remaining scale-condition ambiguity above is retained as a detector limitation.

Normalizer identity advances to `v32-task-binding-safety` to keep old cached
decisions from bypassing the new checks; pipeline identity is
`v85-task-binding-safety`. Prompt, strict schema, resolver interfaces, HTTP/SSE
fields, provider settings, gold, source data and README remain unchanged. No
source-store rebuild, remote/API request, push or deployment is performed.
Stage three (task-local target roles) and stage four (existence evidence) are
not included in this commit. The user's separate dirty checkout is preserved.

## Stage 21 — task-local evidence targets, offline (2026-10-03)

The user requested stage three from `5917633c`. The existing role assignment
used both task and whole-request article references. A sibling naming Article 16
could promote that candidate in a GPA task; two named tasks could also lose their
own target because the whole query named both Article 11 and Article 16. The
mistake affected prompt metadata and context-budget priority, not retrieval IDs.

Target assignment now reads the task's own question first. Original-query
fallback is allowed only for one logical task (including multiple cohort units)
or an unplanned retrieval, and only when local text names no article. Sibling
and clarification-task references cannot supply a target. A request naming
multiple articles does not get a unique target merely because retrieval found
one of them. A requested article still needs one unique authorized source
identity; different documents or applicable source editions stay candidates.
Multiple representations of the same canonical article can share target role.

Review found that a singleton missing identity could otherwise become a target
through a positional/display ID. Normalization now records privately whether
source identity exists before assigning a `source-N` display fallback. The role
gate checks that distinction, and the private flag is stripped before the
composer packet. Missing/blank identity keeps evidence but not target priority.
One old direct-helper fixture was given explicit source IDs for its valid-target
control; separate tests cover absent identity without relaxing the gate.

The allocator, source applicability checks, citation fusion, fact locks,
amendment authorization and sync/SSE paths are unchanged. A fused parent may
be target for one task and candidate for another. A structured task keeps its
verified row and source context while a RAG sibling keeps full regulation text;
neither representation nor result scope is borrowed from the other.

The first 21 tests reproduced 15 failures on the prior implementation. Final
identity/provenance, fallback, ambiguity and mixed-path controls bring the new
suite to 29 tests; 221 focused tests pass. Fixtures include real K50/K51 parents,
the real normalizer and executor, low-budget target-tail preservation and fake
sync/stream composers. They verify packet metadata/preservation, not live answer
accuracy or latency. Standards and Spec reviews have no remaining actionable
stage-three finding after the missing-identity correction.
All **1,745 backend tests** pass on the final implementation, with the same two
dependency deprecation warnings; lint, deployment-artifact and whitespace checks
pass. Two stalled sandbox full-suite processes were stopped rather than counted
as results. The completed full run used the same network-blocking harness with
scoped filesystem permission, without changing global Git configuration.
Role-only inspection of 146 saved answer-run packets and 12 saved smoke packets
finds no role changes and preserves all non-role fields; four terminal cases
have no composer packet. This is saved-output compatibility, not new inference
or answer-quality measurement; historical artifacts remain unchanged.

The composer instruction template and its v3.34 identifier remain unchanged;
the evidence roles received by it intentionally change. Pipeline identity is
`v86-task-local-evidence-targets`. No new model call, task graph, semantic document
matcher, HTTP field or data build is introduced. Unfamiliar article wording,
missing task-local references in multi-task plans and ambiguous documents can
remain candidate-only; target means priority among authorized sources, not proof
that the source completely answers the question.

Prompt/gold/source-data/provider configurations, README and historical reports
are preserved. Stage four (program-existence evidence) remains separate. This
stage is committed locally only, without inference API, push or deployment.

## Stage 22 — per-program existence evidence, offline (2026-10-04)

The user approved the fourth hardening stage from clean `1a833f90`. Previously
program existence stored `exists`/`not_found_note` outside the real-record result
list, while citations serialized that list alone. A scalar NONE became `[]` in
the composer packet; a mixed name list kept only matches and used any match as
the whole-request boolean. The UI also had no row for a missing program.

The program lookup now retains one outcome per queried name: match or not_found,
the scoped boolean, actual matching program summaries and cohort/catalog scope.
The existing real-record `result`, program count and faculty counts stay intact
for callers/evaluators/joins. Scalar `exists` is compatible; list `exists` is
true only when all requested names matched, not merely any one. Composer and UI
use the per-name outcomes. No fake program or record ID is created for a missing
name. Catalog document identity and pages survive even when no record matches.
Empty input/missing catalog does not prove absence. Selector ambiguity, malformed
JSON, unknown IDs or pure API failure keep the existing whole-lookup clarification
path; a previously valid NONE followed by a failed optional second look retains
the existing selector policy, rather than inventing a new success/failure rule.

Only `program_exists` citations consume the new outcome payload. The existing
generic display-row projection shows positives and negatives without a frontend
or top-level HTTP schema change. Other program actions retain their original
record citation shape. Internal selector replies are not copied into outcomes.
Two tasks or two cohort executions keep their respective names/results through
source fusion and composition; negative proof never becomes a global fact lock.

Spec review caught default-budget loss on a supported 45-name/three-cohort
comparison: embedding full career paragraphs in existence outcomes produced
truncated JSON at the ordinary 160,000-character context budget. Pure existence
citations now compact matches to canonical record identity, names and provenance;
the original lookup records stay full. Mixed existence/career requests retain
their career detail through the existing requested_field signal. The budget
engine and limits are unchanged. The real 45-name comparison now retains all
135 outcomes as complete JSON; its query fits the existing 2,000-character input
limit. Requests that genuinely exceed context capacity still have the existing
truncation limitations; no unbounded coverage is claimed.

The first 24 tests reproduced 18 failures on the old implementation. Alias,
fusion, non-mutation and budget/detail controls bring the new suite to 31 tests;
161 focused tests pass. All 129 actual program records produce identity-bound
positive outcomes. Fixtures test scalar/mixed/reversed match/NONE, all three
cohorts, failed/ambiguous selectors, missing inputs/catalogs, full source
provenance, generic UI rows, independent tasks and fake sync/stream composers.
Scripted valid NONE replies test evidence preservation, not the semantic accuracy
of the real selector or composer; no new answer-quality score is claimed.
All **1,776 backend tests** pass on the final implementation, with the same two
dependency deprecation warnings. Lint, deployment-artifact and whitespace checks
pass. Standards review has no actionable finding; Spec review's budget-loss
finding is corrected, with no remaining stage-four blocker.

Pipeline identity is `v87-program-existence-evidence`. Prompt instructions,
models, strict schema, resolver interfaces, gold, source artifacts, README,
historical reports and the user's dirty primary checkout remain unchanged.
No new agent/graph/lookup engine, source-store build, inference API, push or
deployment is introduced. This completes the four approved offline stages;
live smoke and deployment require separate authorization and measurements.

## Stage 23 — answer-kind routing clarification, offline (2026-10-04)

The user approved a minimal, general clarification after the v53/v57 comparison
and saved-plan answer replays. Those measurements do not isolate a single prompt
line: they support testing a narrower directory/policy distinction, not a claim
that the whole v57 prompt is worse. In particular, a RAG plan bypasses the
directory selector; the selector's specialized-authority guard alone cannot
correct that route or prevent a composer from overgeneralizing generic evidence.

The first draft enumerated verbs taken from the observed failures. At the user's
review, that list and the analogous verb sequence in student_service.use were
removed. The final change replaces only the existing student_service bullet:
asking for a service's unit/contact is a directory lookup, not automatically a
request for statutory authority. Choose by the question's purpose and the
lookup's scope, not an individual word; retain the kind of service and entity
asked for in task.question. The tool description assigns catalog fit to the
existing selector, while preserving the prohibition on inferring specialized
authority from a general duty and the existing policy/procedure exclusions.
The general RAG/structured rules, other tool descriptions, contact-field
semantics, task splitting/limits, schema, normalization, resolver, composer and
provider settings are not changed. No query-specific correction or department
mapping is added. Format/scale/entity examples elsewhere describe actual
runtime contracts and are not answers to particular benchmark questions.

Prompt identity is v58-answer-kind-routing, so planner cache entries from v57
are not reused. Historical v56/v57 request snapshots and evaluation outputs stay
unchanged. A small v58 instruction snapshot reuses the v57 request baseline:
the captured request must differ only in its system instructions and service
tool-use line. Schema, other tools, scenarios and transport settings remain
pinned. No extra runtime representation, parser or adapter is introduced.

All **1,788 backend tests pass**, including 12 additional instruction/snapshot,
authored-plan and real-catalog contract checks. The 215 focused API/routing/
selector tests also pass with external socket connections blocked (local
loopback remains available for Windows asyncio/TestClient). An initial overly
broad test-only socket guard blocked asyncio's self-pipe and produced transport
failures; correcting that guard, not application code, resolves them. Lint,
deployment-artifact and whitespace checks pass. Existing prompt budget limits
remain unchanged. Scripted plans/clients establish plumbing and preservation,
not that Luna will follow the new instructions or that final answers improve.

This change is local and uncommitted in codex/routing-evidence-coverage. The
user's dirty eval/official-v4 checkout, gold, source corpus, database collections,
README and production are unchanged. No inference API, push or deployment runs.
Live targeted planner and final-answer evaluation needs separate approval; the
old 132/135 measurement is still a v57 result, not a score for these instructions.
