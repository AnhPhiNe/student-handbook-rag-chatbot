# Technical Debt and Maintenance Boundary

This document records intentional maintenance debt in the current runtime. It
prevents future cleanup work from mistaking dynamically invoked code, build
inputs, or evaluation-only capabilities for dead production code.

## Verified release boundary

- Runtime readiness requires only the current structured catalogs, parent/chunk
  artifacts, graph edges, build manifest, environment keys, and live storage
  targets.
- `office_directory.json`, `faculty_directory.json`, and their cohort-specific
  variants are build inputs. Production lookup uses
  `student_office_profiles.json`, `student_faculty_profiles.json`, and
  `student_service_directory.json`; the raw directory inputs are not packaged
  by the Hugging Face deployment allowlist.
- `configs/retrieval.yaml` is an active runtime dependency. It defines the
  embedding/build contract loaded by `src/retrieval/runtime_config.py` and must
  remain in readiness and deployment packaging.
- `LocalReranker` is not dead code. Production mode keeps it disabled, while
  explicit evaluation ablations can still call it.
- FastAPI route handlers and dependencies, plus executor callbacks used by
  LangSmith telemetry, may have no ordinary static caller. Framework or
  callback registration invokes them at runtime, so they must not be removed
  based only on call-graph in-degree.

## Intentionally deferred

| Area | Current decision | Safe condition for later work |
|---|---|---|
| Directory matching | Keep the existing office/service/faculty matcher | Refactor only with characterization tests covering exact aliases, ambiguity, cohort applicability, and cross-entity isolation |
| Structured slot repair | Keep grounded, domain-specific repairs | Move a repair to registry metadata only after equivalent behavior is tested; remove it only with activation/error evidence |
| Text normalization | Keep domain-local implementations | Consolidate only after tests lock Unicode, punctuation, numeric range, acronym, and identifier behavior for every caller |
| Evaluation compatibility | Keep explicit compatibility aliases and historical evaluators outside the deployed image | Remove only when no maintained evaluation bundle or script depends on them |
| Cache compatibility | Keep legacy-entry readers | Remove after the supported cache migration window is explicitly closed |

## Dead-code removal rule

A symbol or file is removable only when all of the following are true:

1. Static call/import search finds no production, build, test, or evaluation
   caller.
2. It is not registered dynamically as a FastAPI route/dependency, callback,
   plugin, serializer hook, or command entry point.
3. Deployment and artifact-build scripts do not copy, generate, or validate it.
4. Removing it passes lint, the full test suite, deploy-artifact validation,
   readiness checks, and sync/stream smoke tests.

The current audit found no additional runtime symbol that satisfies all four
conditions. Future cleanup should therefore begin with evidence from a caller
trace or failing maintenance boundary, not with line-count reduction.
