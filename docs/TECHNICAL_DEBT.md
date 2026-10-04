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
| Architecture diagrams | `docs/architecture/*.html` show the current components since 2026-09-29 (labels edited in place, since the archify generator is not installed here). Their code links are permalinks to commit `6eba6d4a` (2026-09-12), so they open that older code | After a push, point the links at the pushed commit and the current line of each named function; keep the file names, since GitHub Pages links to them |

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
