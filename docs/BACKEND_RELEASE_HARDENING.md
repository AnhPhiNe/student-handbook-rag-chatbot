# Backend release hardening — offline candidate

Base: GitHub main `1507d524`. Branch: `codex/backend-release-hardening`.
This is the PR draft and handoff for the offline changes; it is not a deployment
record or a new model accuracy measurement.

## Suggested PR title

Fix backend packaging, incomplete answers, reference thresholds and Voyage validation

## Problem and resulting behavior

- The HF package omitted `handbook_currency.yaml`, although every composer
  prompt reads it. Reuse the packaging fix of `53a76d2a` and include the file in
  the shared artifact/readiness inventory. Missing notes now fail readiness.
- DeepSeek sync/stream output ending with `length` or another non-success
  terminal reason was accepted as a complete answer. Only `stop` is successful;
  incomplete output is not retried. SSE keeps cleaned partial text, emits
  `api_error` with a classified `error_type`, and the UI shows one incomplete
  answer notice with low confidence. Provider usage is retained where supplied.
  Transport EOF without a terminal event and reader errors use the same partial
  preservation path and stop the typing/progress indicators.
- A foreign-language reference-level query mentioning some personal scores
  incorrectly demanded the scores being asked for. Reference levels can now
  expose their thresholds without all component inputs. Partial personal
  scores never create a fact lock. Personal equivalency requests without a
  reference level still require the components declared by the table.
  Grouped certificates are matched independently, and every shared selector
  must be recognized by every selected certificate, preventing a JLPT code
  from exempting TOEIC component requirements.
- Voyage responses must cover unique integer indices `0..n-1`; invalid mappings
  retain RRF. Rerank telemetry and LangSmith tracing identify the actual provider.
- Summary documentation now names v56/v3.33 and distinguishes historical
  hold-out results from post-fix measurements and deployment checks.

The HTTP fields and SSE event names are unchanged. The interface uses the
existing `api_error` status and free-form `error_type` field. Planner schema,
prompts, models, configuration, gold and corpus v35 are unchanged.

## Validation

- Backend: **1,339 tests passed**, with two dependency deprecation warnings.
- Frontend: **16 tests passed**; ESLint, TypeScript and Vite production build
  passed. The existing bundle-size warning remains. Cached dependencies match
  the lockfile (Vite 8.1.0, TypeScript 6.0.3).
- Backend Ruff E/F checks and `git diff --check`: passed.
- Runtime artifact/hash audit: passed, including the newly required currency
  config. Corpus, gold and provider config diffs against main are empty.
- HF deploy dry run: passed. Inside the resulting package all 17 declared
  runtime files exist, a fixture composer prompt includes handbook labels and
  currency notes, and the scoped foreign-language resolver is exercised offline.
- Reference-row audit: 120 probes, 115 unique and 5 ambiguous, zero findings.
  Extraction/tool-description audits retain the 7/4 flags discussed below.
- Two-axis review completed; follow-up SSE EOF and grouped-certificate findings
  were fixed and rechecked before the final suite.

Tests use fake providers and scripted plans. No model request, Docker image
build, new quality benchmark or HF deployment was performed in this delivery.

## Retained data limitations

- Two advising-regulation parents (K50 Article 4 and K51 Article 4) end with a
  dangling QR cross-reference. The rule about Appendix 1 remains complete.
  Keep this low-priority cleaning debt for a future corpus update; no rebuild
  or reindex for these two fragments.
- Extraction audit compares extracted text by sets of numbers/words. Its seven
  scholarship-eligibility flags are review candidates, not seven proven errors;
  it cannot prove all cell meanings, exceptions or PDF page metadata correct.
- Four tool-description flags concern scholarship eligibility/formula fields.
  No explicit `aspect` selects those two tables, but the no-aspect lookup
  returns all four scholarship tables; rule/formula paths also exist. Do not
  extend the schema merely to eliminate lexical audit flags.
- Catalog integrity gives one same-cohort target for each of 129 programs and
  232 service records. It does not independently verify every association
  against the PDFs. The scope remains the three handbooks and main campus.

## Release after review

1. Review the diff and validation, then authorize commit/push and PR creation.
2. Merge after CI passes. Use a clean checkout of the merged main for deployment.
3. Verify HF keys for OpenAI, DeepSeek, DeepInfra and Voyage; the Voyage key must
   match the configured MongoDB Atlas endpoint. Verify v35 store targets,
   including the higher-precedence Qdrant compatibility alias, CORS and stale
   environment overrides. Never put key values in this document or the PR.
4. Prepare a rollback snapshot of the current HF commit and non-secret settings.
   Run the deploy dry run and inspect the package, then deploy with approval.
5. After inference scope/budget approval, smoke lookup/RAG/follow-up/cohort/SSE
   on HF using production timeouts. Verify the applied reranker from traces,
   record errors and latency including retries, and label these operational
   observations separately from v4 quality scores. No production certification
   follows merely from a few successful smoke requests.

No commit, push, PR creation, store upload, model call or HF deployment is part
of this offline delivery.
