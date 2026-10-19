# scripts/

Entry points, run from the repository root as `python -m scripts.<name>`.
Library code lives in `src/`; a script only parses arguments and calls it.

## Build the corpus

The normal path is `build_multi_cohort`. It runs the per-cohort steps marked
"called by build_multi_cohort" in order, then the shared layers.

| Script | Does |
|---|---|
| `build_multi_cohort` | Full rebuild of `data/processed/` from the PDFs in `data/raw/`; with `PUSH_REMOTE=1` it also preflights, uploads and verifies |
| `extract_pdf_pages` | Page text from one handbook PDF (called by build_multi_cohort) |
| `parse_structure` | Documents, chapters, articles from the page text (called by build_multi_cohort) |
| `extract_structured_data` | Records for tables and directories (called by build_multi_cohort) |
| `build_chunks` | Per-cohort parent articles (called by build_multi_cohort) |
| `derive_foreign_language_policy` | Foreign-language policy records (imported by build_multi_cohort) |
| `build_structured_table_layer` | Reviewed tables, lookup registry, directory profiles, contact corrections |
| `build_parent_child_artifacts` | Readable parents and narrative-only children |
| `structure_chunking` | Replaces the children with one chunk per *khoản*, checks the invariants |
| `build_child_parent_index` | The child → parent index |
| `build_artifact_manifest` | Hashes, counts and target collections of a build |
| `build_table_search_candidate` | Table-description search handles, written to a separate candidate folder |
| `publish_table_search_candidate` | Embeds a frozen candidate into **new** Qdrant/Mongo collections; never activates production |
| `build_candidate_runtime_bundle` | Runtime overlay for a published candidate (used by `deploy_hf_backend.ps1 -CandidateArtifacts`) |
| `push_to_qdrant`, `push_to_mongo` | Uploads (called by build_multi_cohort with `PUSH_REMOTE=1`) |
| `verify_remote_build` | Checks the remote stores against the manifest |
| `reanchor_table_regions` | Re-anchors reviewed table regions after a parent's text changed; needed when adding a cohort |

## Check a build

| Script | Does |
|---|---|
| `check_chunk_invariants` | Fails on a lost line, a cut sentence, a heading-only chunk or a list cut from its lead-in |
| `check_deploy_artifacts` | Required runtime files and the build manifest |
| `audit_pdf_coverage` | Handbook text that reached no parent and no catalog |
| `audit_extraction` | Structured data against the handbook text, both ways |
| `audit_structured_lookups` | Every reference-table row is pinned by its lookup, and no other row is |
| `audit_table_quality` | Table quality report (called by build_multi_cohort) |
| `audit_tool_descriptions` | Every answerable field of a structured tool is known to the planner |

## Evaluate

| Script | Does |
|---|---|
| `run_official_deterministic` | Planner + structured execution suite, with a pre-run hash snapshot |
| `run_official_answers` | Retrieval, answers (generate + judge) or production suite; `--shared-plans` and `--answer-config` freeze or swap parts |
| `report_v4_run` | One official_v4 run against its pre-registered metrics; `--compare` for paired differences |
| `report_official_slices` | A suite report by slice, cohort and question style |
| `rerun_official_cases` | Rerun named cases of an answers run under its own snapshot |
| `rejudge_run` | Judge a finished answers run again without regenerating |
| `regrade_official_deterministic` | Rescore a saved deterministic run without model calls |
| `regrade_saved_deterministic_v10` | The same for runs saved with the V10 gold format |
| `judge_calibration` | A second rater against the judge |

## Compare components (ablations)

See [docs/EXPERIMENTS.md](../docs/EXPERIMENTS.md).

| Script | Compares |
|---|---|
| `replay_composer` | Composers or composer prompts on saved evidence packets |
| `compare_rerankers` | Rerankers on identical candidates (official_v1 retrieval) |
| `compare_plan_normalizers` | Two normalizer versions on the same planner replies |
| `eval_chunking_offline` | Chunkings with the production retriever, offline |
| `evaluate_table_search_lexical` | Table-search coverage under BM25, offline |
| `evaluate_table_search_live` | Fifteen live retrieval probes on a published candidate |
| `eval_directory_matching` | Directory matching on labelled cases |
| `eval_supplementary_questions`, `eval_retrieval_hardening` | Development questions with a known route, source and facts |
| `run_luna_contact_smoke` | Eight contact-intent planner probes |

## Author datasets

| Script | Does |
|---|---|
| `prepare_official_eval` | Runtime and source inventory before authoring official_v1 |
| `build_official_deterministic`, `build_official_retrieval`, `build_official_answers`, `build_official_production` | Compile hand-authored drafts into suite case files |
| `build_holdout_suites` | Retrieval and answer suites from a held-out deterministic authoring |
| `check_bundle_overlap` | Near-duplicates between a new bundle and an earlier one |
| `draw_v4_tickets`, `check_v4_authored`, `build_v4_cases` | The official_v4 authoring workflow and its K49 migration |

## Deploy

`deploy_hf_backend.ps1` packages the allowlisted runtime files and pushes them
to the Hugging Face Space. Use `-DryRun` first. Pass `-CandidateArtifacts`
with the published candidate folder, which sets the target collections from its
manifest. `deploy_hf.bat` at the repository root calls it.
