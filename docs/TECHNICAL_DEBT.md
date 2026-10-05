# Technical Debt and Maintenance Boundary

This document records known maintenance debt in the current runtime. It also
prevents future cleanup from mistaking dynamically invoked code or build inputs
for dead production code.

## Release boundary

- Runtime readiness requires the structured catalogs, parent and child
  artifacts, graph edges, build manifest, environment keys and live storage
  targets listed in `src/common/runtime_artifacts.py`. The deploy allowlist and
  `.dockerignore` are tested against that list.
- `office_directory.json`, `faculty_directory.json`, `scoring_tables.json`,
  `foreign_language_equivalency_table.json` and the cohort-prefixed files under
  `data/processed/` are build inputs, not runtime inputs. Production lookup uses
  the structured registry and the student office, faculty and service profiles.
- `configs/retrieval.yaml` is a runtime dependency: it defines the embedding and
  build contract loaded by `src/retrieval/runtime_config.py`.
- FastAPI route handlers and dependencies, and executor callbacks used by
  LangSmith telemetry, may have no ordinary static caller. The framework calls
  them, so call-graph in-degree alone never justifies removing them.

## Known debt

| Area | Current state | Safe way to change it |
|---|---|---|
| Scoring result schema | `scoring_lookup_from_reference` renames columns to an English schema read by the evaluator and `StructuredResults.tsx`. `resolved_result` is a verified result for one applicable scope; `resolved_rows` can retain scope-specific candidates without a fact lock. They are not interchangeable meanings | Any future migration must preserve operation, grounded value/scale, cohort and scope validation. Never derive fact lock only from list length or treat all candidate rows as the answer. Migrate runtime, frontend and evaluator together; leave the existing schema unchanged before release |
| Directory matching | Office, service and faculty matching are kept as they are | Refactor only with tests covering exact aliases, ambiguity, cohort applicability and cross-entity isolation |
| Structured span grounding | Planner slots are grounded by matching the same value in the question | Change only with tests for schema values, negation and literal grounding |
| Sync and streaming answer paths | `AnswerPipeline.answer` and `answer_stream` share preparation, citation selection and usage recording but differ for real reasons (a dict against progress/metadata/token/done events; `generate` against `generate_stream`; partial token emission). Runtime v79 has no answer cache; the stream guardrail is `StreamAnswerCleaner` with its own tests | Do NOT merge them into one method with a streaming flag: that trades duplication for a larger branching method. Verify any change with a fake-LLM replay over saved plans comparing both paths before and after |
| BM25 tokens | `BM25Retriever._tokenize` adds underthesea words and syllable bigrams, so a two-syllable word such as `học_bổng` is counted twice, and every accented token also gets an unaccented twin, so `bạn`, `bán` and `ban` share one token. Both are deliberate (segmentation fallback, unaccented questions) and every reported retrieval and answer run measured them | Change only with a retrieval run on `official_v1` and `official_v2` against the current numbers, and an unaccented slice; a change here invalidates the comparison with every earlier run |
| Architecture diagrams | `docs/architecture/*.html` show the current components since 2026-09-29 (labels edited in place, since the archify generator is not installed here). Their code links are permalinks to commit `6eba6d4a` (2026-09-12), so they open that older code | After a push, point the links at the pushed commit and the current line of each named function; keep the file names, since GitHub Pages links to them |

## Layers that never fire (measured 2026-10-05)

Counted over the 984 answer cases of the four saved `official_v4` runs, and over
the committed artifacts. They are inert rather than wrong: none costs latency or
changes an answer, and each is sized for data that may change, so they are
recorded here instead of removed. Removing any of them is a behaviour claim that
needs the equivalence evidence named in the rule below.

| Layer | Measured | Why it is kept |
|---|---|---|
| Context trimming in `prompt_builder` (`_allocate_source_content_budgets`, `_fair_allocations`, `limit_context`, about 110 lines) | 0 of 984 answers were trimmed; the five longest parents total 54,427 characters against a 120,000 usable budget, so it cannot fire on this corpus | A larger corpus, a fourth cohort or a higher `default_top_k` would reach it |
| `_is_supplemental_regulation_metadata` in `hybrid_pipeline` | Matches 0 of 2,646 children and 0 of 541 parents | It filters retired or supplemental regulations, which this build happens not to contain |
| `safe_rag_fallback_plan` | 0 of 984 | It is the planner-outage net; an outage is exactly when nothing else helps |
| `retrieval_mode` ablation switches (`no_graph`, `vector_only`, 42 lines in the runtime path) | Used only by the evaluation runner | The graph and BM25 ablations are still owed for the paper |

Not measured: the reranker and embedding fallbacks. The saved answer runs do not
carry retrieval telemetry, so nothing here says whether those ever ran.

## Dead-code removal rule

A symbol or file is removable only when all of the following are true:

1. Static call and import search finds no production, build, test or
   evaluation caller.
2. It is not registered dynamically as a FastAPI route or dependency, a
   callback, a plugin, a serializer hook or a command entry point.
3. Deployment and artifact-build scripts do not copy, generate or validate it.
4. Removing it passes lint, the full test suite, deploy-artifact validation and
   an equivalence check suited to the code: a byte-for-byte rebuild for build
   code, an offline regrade of saved runs for evaluators, or a fake-provider
   comparison for provider clients.

The September 2026 cleanup (`chore/p2-cleanup`) applied this rule across the
backend, the offline build and the evaluation code. Each removal is recorded
in its commit message together with the check that verified it.
