# V33 release status

Updated 2026-09-09. This page retains the historical v64 upload-verified
candidate record. The current local v33 runtime uses pipeline `v73`; the three
official-v1 quality-suite results are recorded in [RESULTS_AND_LIMITATIONS.md](../data/eval/official_v1/RESULTS_AND_LIMITATIONS.md)
with hashes and run identity in [RESULTS_PROVENANCE.json](../data/eval/official_v1/RESULTS_PROVENANCE.json).
This is not a production certification or a claim that the public deployment
has been updated.

- Historical v64 candidate runtime: `90df81d5`; packaging fix: `0f3bc23a`.
- Historical candidate Composer: `gemini-3.1-flash-lite`; prompt v3.24: `cdf0c0e5`.
- Historical pipeline/cache version: `v64-preserve-group-fact-lock`.
- Historical v3.23 freeze manifest commit: `053e96e5`, against runtime/evaluator
  `1a71c971f1713d730baef4885cd92f9480bdd40b`. That manifest was not rewritten
  to claim evaluation of the current candidate.
- Build: `build-934f1caf384f99ad96e9`.
- Local tests: **698 passed**; targeted Ruff lint, artifact/hash checks and HF
  dry-run package checks passed. No Docker image build was performed.
- Post-fix live smoke: **4/4 answered**, using 3.1 with v33 stores, no response
  cache hit or Planner fallback. Both sync and streaming returned D+/not passed
  for K51 remaining-course score 5.2; GPA classification and both TOEIC columns
  matched the structured results. Every captured packet contained its fact lock.
- Historical Composer v3.23 diagnostics remain in `COMPOSER_V323_RELEASE_SMOKE.md`.
- Qdrant `student_handbook_semantic_v33`: 3,121 points uploaded.
- MongoDB `parent_docs_v33`: 462 parents uploaded.
- Both stores share the build ID and 462 linked parent IDs. Every remote parent
  and child payload equals its local frozen artifact. Embedding dimension is
  1,024; vectors were not downloaded for a numerical comparison.
- Full verification record: `data/eval/release_v33_smoke/remote_content_verification.json`.
- No v32 collection was changed or deleted.

## Current local status

- Runtime identity: Gemini 3.1 Flash-Lite, Composer prompt v3.24, pipeline `v73`, corpus build `build-934f1caf384f99ad96e9`.
- Deterministic: **124/135** contract pass; retrieval: **141/155** Hit@5, MRR **0.8333**.
- Generate + Judge: **150** rows; mean Judge correctness **0.9305**, a 0–1 rubric mean rather than exact-answer accuracy or a pass rate.
- Production60 was **not run** in the official-v1 scope; there is no current production metric, HF load/TTFT/SLA result, or verified public rollout here.

## Historical v64 review and model decision

The pre-fix full-pipeline comparison completed 20 requests per model (19 unique
questions), with identical paired plans/prompts. Median end-to-end latency was
7.77 seconds for 3.1 and 5.60 seconds for 3.5. It did not establish a quality
advantage for 3.5; the project keeps 3.1. This development diagnostic is not a
holdout or a new headline accuracy metric.

The concrete transport-of-evidence defect was an early return in citation
construction for `sub_lookups`: it dropped a fact lock owned by the group.
The fix preserves same-source group locks and prevents merging them with another
task/input's lock. Planner, resolver and model configuration were not changed.
Tests cover the tested task/cohort isolation paths, not all possible catalog
combinations. The separate TOEIC narrow-question clarification limitation seen
in the comparison was not changed by this fix.

Local diagnostic evidence (intentionally excluded from Git/runtime packaging):

- A/B: `work/composer_e2e_31_vs_35_v324_run3/answers.jsonl`, SHA-256
  `961cb2fa533f65e60f700c5150cf71593aee02e3d14a26a9b20fa61b574787cf`.
- Post-fix smoke: `work/group_fact_lock_v64_smoke_live/answers.jsonl`, SHA-256
  `b2fa727315bd490c0f22f990fe9687d4ba0cc06633e399cc5ef0e799beba5596`.

Cleanup removed only an unused placeholder class in the local A/B harness.
Historical evaluators, rejected corpus experiments and build inputs remain for
reproducibility, outside the deployed runtime image. No runtime module was
identified as safely removable in this scoped diff review. The Docker allowlist
now retains the manifest-declared table audit; staging verification confirmed its
hash matches the source artifact.

## Historical v64 release-gate record

The checklist below is retained as an audit trail for the v64 candidate. It is
not the current official-v1 status or a next-step requirement for the completed
three local quality suites; Production60 remains outside that scope.

1. Authenticate HF management access. API access returned 401; reusing a Git
   credential for the API was not approved. Do not switch only one storage
   variable or deploy a package with a mismatched collection pair.
2. Deploy the checked package with both v33 targets and verify health/readiness,
   runtime identity, sync and streaming. Preserve the v32 rollback configuration.
3. Run final suites sequentially, report and audit failures without tuning to
   results. The current corrected bundle contains 135 deterministic, 155
   retrieval, **141** answer and 60 production cases (not 150 answers).
   Confirmation of the answer-suite choice is pending.
4. Prepare a separate run manifest for v33 storage identity; the historical V9.1
   manifest requires v32 and must not be silently edited. Preserve case hashes
   and label this as a post-fix regression, not a fresh holdout.
5. Publish the separate metrics, update README and tag only after those gates.

The root README retains the previous V9.1 metrics as historical. Current
official-v1 metrics and their limitations are linked above; no current
Production60 metric is asserted.
