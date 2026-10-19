# Experiments and ablations

A starting point for comparing components, for example in a paper. This page
covers four things:

- what each pipeline component is today and where it is configured;
- which components can already be switched or swapped for a comparison, and
  which cannot yet;
- the measured runs to compare against;
- how to run a comparison without changing production.

The decisions that led to the current choices, with their measurements, are in
[DESIGN_DECISIONS.md](DESIGN_DECISIONS.md). The pre-registered runs are in
[official_v4/SPEC.md](../data/eval/official_v4/SPEC.md).

## Pipeline components

The state of production on 2026-10-19 (Hugging Face Space commit `1d7aa77`,
main `635c0e7c`).

| # | Component | Current choice | Where it is set | Switch for an ablation |
|---|---|---|---|---|
| 1 | Slang and abbreviation expansion | Dictionary rewrite of retrieval queries | `configs/hcmue_slang_dictionary.yaml` | — none |
| 2 | Planner | OpenAI `gpt-6-luna`, reasoning `medium`, prompt `structured-regulation-v63d-social-handbook-scope` | `configs/ai_router.yaml`; `ROUTER_PROMPT_VERSION` in `src/retrieval/core/ai_router.py` | Reasoning: `STUDENT_RAG_ROUTER_REASONING_EFFORT`. Plans can be frozen with `--shared-plans`. No "planner off" mode |
| 3 | Plan normalizer | `v36-social`, grounding by value kind | `QUERY_PLAN_NORMALIZER_VERSION` in `src/retrieval/core/query_plan.py`; value kinds in `configs/structured_lookup_registry.yaml` | Offline only: `scripts/compare_plan_normalizers.py`. No "off" mode |
| 4 | Structured lookups | 9 capabilities over reviewed JSON tables and directories | `configs/structured_lookup_registry.yaml`, `data/processed/tables`, `data/processed/directories` | — none (a "RAG only" baseline needs one) |
| 5 | Directory selector | DeepSeek-V4.1-Flash on DeepInfra, reasoning `none`, retried with `low`; prompt `directory-selector-v3-task-context` | `directory_selector` in `configs/answer_generation.yaml` | Offline: `scripts/eval_directory_matching.py` |
| 6 | Dense retrieval | `BAAI/bge-m3` over DeepInfra, Qdrant, 24 children | `configs/retrieval.yaml` (`embedding`, `candidate_children`) | `vector_only` = dense alone |
| 7 | Lexical retrieval | In-process BM25 (underthesea tokens plus unaccented twins), 24 children | `src/retrieval/core/bm25_retriever.py` | Removed by `vector_only`; no BM25-only mode |
| 8 | Fusion | Reciprocal rank fusion, k = 60 | `RRF_K` in `src/retrieval/core/hybrid_pipeline.py` | — constant |
| 9 | Reranker | Voyage `rerank-3` over all 24 children; fails open to the RRF order | `reranker` in `configs/retrieval.yaml` | `STUDENT_RAG_RERANKER_ENABLED=false`; Qwen3-Reranker-4B in `configs/retrieval_reranker_4b.yaml`; offline: `scripts/compare_rerankers.py` |
| 10 | Parents handed to the composer | Fixed k = 5 full parent articles from MongoDB | `default_top_k` in `configs/retrieval.yaml` | Change k in a config copy. No dynamic k (score threshold or a selector model) |
| 11 | Cross-reference graph | Related-article links for the UI, never evidence | `src/ingestion/graph_extractor.py` | `no_graph` |
| 12 | Table search | One description per reviewed table (32), `table-description-v1`, wording v4 | `configs/table_search_descriptions.yaml` | Offline: `scripts/evaluate_table_search_lexical.py` |
| 13 | Chunking | One chunk per *khoản*, never split; out-of-scope clauses not indexed | `configs/structure_chunking.yaml`, `configs/layout_fixes.yaml`, `configs/corpus_scope.yaml` | Offline: `scripts/eval_chunking_offline.py`; another chunking needs another build and collection |
| 14 | Composer | DeepSeek-V4.1-Flash on DeepInfra, reasoning `none`, prompt `student-handbook-answer-v3.44-catalog-referral` | `llm` in `configs/answer_generation.yaml`; `ANSWER_PROMPT_VERSION` in `src/generation/prompt_builder.py` | `--answer-config <yaml>` on the answers suite; `scripts/replay_composer.py` reuses saved evidence packets |
| 15 | Catalog referral and template | A referral for a task the composer marks as unsupported; a fixed template when every task is marked and matched | `src/generation/catalog_referral.py` | — none |
| 16 | Social and out-of-domain replies | Planner field `social`; fixed replies | `configs/social_replies.yaml` | — none |
| 17 | Judge (evaluation only) | `openai/gpt-oss-120b`, pinned | `src/evaluation/judge.py` | `scripts/judge_calibration.py` compares a second rater |

Retrieval modes are set with `STUDENT_RAG_RETRIEVAL_MODE`
(`vector_primary_graph_supplement`, `no_graph`, `vector_only`). A non-default
mode also needs `STUDENT_RAG_ALLOW_RETRIEVAL_ABLATION=1`
(`src/retrieval/core/retrieval_mode.py`).

## Missing switches for a paper

These comparisons cannot be run today without code changes:

| Comparison | What is missing |
|---|---|
| Typed plan vs plain RAG | A mode that skips the planner and the structured lookups and sends the question straight to hybrid retrieval and the composer (rows 2–4) |
| With and without the normalizer | A mode that executes the planner's plan unchecked (row 3) |
| With and without structured lookups | A mode that sends every structured task to RAG (row 4) |
| BM25 only | A lexical-only retrieval mode (row 7) |
| Fixed k vs dynamic k | A selection step after reranking: a Voyage score threshold baseline, then any model-based selector (row 10) |
| Referral and template on and off | A flag on the catalog referral path (row 15) |
| Long-context baseline | A path that gives the composer the whole cohort handbook instead of retrieved parents |

Each needs a flag defaulting to the production behaviour, a test that the
default is unchanged, and a pre-registered rule before its run.

## Runs to compare against

All runs are on `official_v4`'s 228 in-scope cases, scored by the pinned judge.
The reports are under `data/eval/reports/`, which git ignores. Keep a copy:
the per-case records of run N were lost this way.

| Run | Date | What it measured | `answer_correctness` |
|---|---|---|---:|
| K49 | 2026-10-18 | K49 replaces K48-K49; composer v3.36; planner v61 plans shared | K49 0.960; K50+K51 0.975 |
| Q | 2026-10-19 | Composer v3.43 on DeepInfra, K49's plans | 0.964 |
| S | 2026-10-19 | Composer v3.44 plus catalog referral, K49's plans | 0.972 |

What is **not** measured: the deployed combination of planner v63d,
normalizer v36, composer v3.44, the referral template and the social replies
has had no end-to-end `official_v4` run. The owner deferred that run on
2026-10-19. The template and the social replies are validated on development
sets and probes only.

## Running a comparison

1. **Freeze what is not compared.** For a composer comparison, pass
   `--shared-plans data/eval/reports/official_v4_k49_plans.json` so every run
   reads the same plans. For a retrieval comparison, use the retrieval suite,
   which calls neither the planner nor the composer.
2. **Point at the right data.** Set `QDRANT_COLLECTION_NAME`,
   `STUDENT_RAG_HYBRID_COLLECTION` and `MONGODB_PARENT_COLLECTION` to the
   collections of the build being measured. Production uses
   `…table_search_3bbd93e9f05a`.
3. **Pre-register.** Before the run, write the change, the baseline run and the
   acceptance rule into `data/eval/official_v4/SPEC.md`.
4. **Run and report.** `python -m scripts.run_official_answers --bundle official_v4 --suite answers [--answer-config …] [--shared-plans …]`,
   then `python -m scripts.report_v4_run --run <run_dir> --compare <baseline_dir>`
   for the case-by-case comparison with cluster-bootstrap intervals.
5. **Re-run noisy cases** with `scripts/rerun_official_cases.py`, and re-judge a
   saved run with `scripts/rejudge_run.py`; do not rerun the whole suite.

Reported noise: the planner varies by about ±2–3 cases on official_v1/v2
between identical runs. The judge has moved a case between 0 and 0.6 on an
identical answer (V4-172), so read every new zero.
