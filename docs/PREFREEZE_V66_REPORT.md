# v66 bounded fixes and verification

Date: 2026-09-06. Base reviewed: `62695429`. Supersedes the implementation status
in `PREFREEZE_V65_REPORT.md`, not its recorded smoke failures or diagnosis.

## Changes

1. Preserve already clear `qua môn` / `không qua môn` wording before Planner.
   Recognize other canonical pass/fail expressions produced by slang replacement
   through the existing registry. No whole-question branch was added.
2. Apply operation/scope selection from one registry entry to reference-table
   evidence and the scoring resolver catalog. The mapping lists catalog IDs,
   not questions or expected benchmark values. Explicit scope never falls
   through to another table; unknown scope remains unknown. Scoring arithmetic
   is unchanged. Existing prefixed catalog IDs remain accepted.
3. Compact only the Composer copy of a resolved payload: omit `display_rows`
   and duplicate `items` when an explicit `result` exists. Keep exact result,
   inputs and provenance. API/UI source data and full table evidence are intact.
4. Include the approved v65 fixes: row-defined component input guard and
   execution-cohort isolation for shared-source fact-locks.

Runtime/cache identity: `v66-scoring-selection-compact-facts`. Gemini remains
`gemini-3.1-flash-lite`; instruction prompt remains v3.24. This is a changed
runtime/evidence packet, not an unchanged measured system.

## Offline verification

- 766 tests passed. XML: `work/pytest_v66_final.xml`.
- Changed-file Ruff and whitespace checks passed.
- Artifact/manifest audit and explicit-v33 HF packaging dry-run passed.
- Regression covers both normalization stages, operation/scope candidate
  consistency, component inputs across cohorts, compact-packet immutability,
  and same-task multi-cohort locks through execution/merge/packet.
- The old V9 provenance test now compares reported drift with actual versus
  expected hashes instead of a hard-coded list of changed configs. No old
  dataset, manifest, output or metric was edited.

## Live smoke — one new run after the fixes

Explicit owner authorization covered eight requests through Groq Planner and
Gemini Composer with handbook evidence. No personal history was sent; stores
were read only. The first attempt was rejected by permission review before
execution; the run started only after explicit authorization for both providers.

All eight returned HTTP 200. Three streams each had exactly one answered terminal
event. Response-cache flags were false; the harness disabled router cache. After
component initialization, Qdrant and Mongo were both v33. No failed answer was
discarded or rerun to obtain a better result.

| Smoke | Observed final answer |
|---|---|
| K51 5.2 sync | D+/not passed, interpreting the course as remaining. |
| K51 5.2 stream | D+/not passed, same scope interpretation. |
| K50/K51 comparison | K50 D+/passed; K51 D+/not passed with remaining-course interpretation. |
| TOEIC one column | Speaking level 4: 160–179. |
| TOEIC two columns | All eight level-3/4 component ranges reproduced correctly. |
| TOEIC missing personal skills | No overall pass conclusion without the other three skills. |
| Scholarship exclusion | Bridging-program exclusion and credit exceptions included. |
| Compound | GPA 3.3 classified as Giỏi; highest achieved improvement score stated. |

The previous incorrect C values and contradictory answer did not recur in this
run. This is **not 8/8 official accuracy**: the course-scope inference below is
still unaudited, and the before/after pipeline changes do not isolate the causal
effect of compaction or establish a statistical hallucination-rate improvement.

Evidence: `work/prefreeze_v66_live/{answers.jsonl,summary.json,audit.json}`.
Answer SHA-256: `ea9d4e2d7780b338cf083c5651c1e414a7ddfdbf3b89cda1b3f9a7b10df70685`.
The audit file records runtime/config/manifest hashes. The old v65 output remains
available separately. These are AI-assisted development checks, not independent
human review or holdout results.

## Remaining limitations and release status

- Composer still interprets `môn chuyên ngành` as the remaining-course category.
  Runtime does not set that scope or create a unique K51 lock without grounding.
  The numeric row is now read consistently, but these runs do not independently
  validate that semantic mapping for every course. Treat unverified applicability
  as a limitation, not a proved universal rule.
- A correct fact-lock is an instruction/evidence constraint, not a guaranteed
  output validator. Compacting redundant fields cannot guarantee LLM obedience.
- The TOEIC missing-skills smoke still uses a table-first conditional answer when
  the Planner entity is `TOEIC Nói`, rather than a runtime clarification terminal.
  It does not assert that one speaking score proves the full standard.
- HF deployment, official evaluation, historical eval cleanup and final release
  freeze have not been performed by this verification.

## Standards

Review found no documented-standard violation or meaningful design smell
requiring a release change. Metadata selectors and packet compaction remain
within the existing architecture.

## Spec

Review found no implementation deviation from the approved bounded fixes.
Independent agent verification passed 69 targeted offline tests. This review
does not certify final answer correctness or remove the limitations above.

Summary: zero actionable findings on each review axis; answer-quality caveats
are recorded separately and must not be hidden by passing code tests.
