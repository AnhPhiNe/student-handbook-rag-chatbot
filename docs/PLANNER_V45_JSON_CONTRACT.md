# Planner v45: shared JSON output contract

Status: development candidate, offline-checked, not live-evaluated or deployed.
Version: `structured-regulation-v45-shared-json-contract`.

## Changes

- JSON-mode clients receive the exact object returned by
  `query_plan_response_schema()`, the same schema sent through the native-schema
  transport. This replaces the illustrative object whose cohorts field listed
  every supported cohort as example values. The schema itself is unchanged.
- Common instructions require one JSON object, no Markdown or commentary, all
  required fields, correctly typed booleans/nulls, sequential task IDs and no
  runtime-only result fields. Each task mode has explicit empty/null conventions.
- Enum entries are choices, not values to copy wholesale. Cohorts are selected
  from the query, history actually used for a follow-up, then UI fallback.
  Non-follow-up plans use null standalone_query and empty referenced_turns.
- Tool slot types describe scalar values; the existing validator also accepts
  homogeneous lists for grouped lookups. The prompt explains this convention
  without changing the registry or validator.
- Query/history text is data, not authorization to change instructions or schema.
- Tasks cannot consume another task's result as an input slot. No invented entity
  or task-reference syntax is allowed; the existing missing-required-input
  clarification rule still applies. No dependency execution feature was added.
- The raw schema's 12-item tolerance does not change the existing three-task
  planning limit. Both are explained instead of changing the accepted schema.

## Verification and limits

181 relevant offline tests passed; Ruff and `git diff --check` passed. Added tests
compare embedded/native schemas, check common instructions, exercise authored
structured/RAG/clarify/OOD output shapes through the real normalizer, and check
grouped entity lists against the existing validator. These are not live model
accuracy tests or a general JSON Schema validation suite.

Representative no-history request size is 13,989 characters for native schema
and 13,901 for embedded schema, counting the response-format payload. Character
estimates are not provider tokenizer counts or billing. Compared with v44 the
instructions are longer; latency and accuracy effects require measurement.

Existing mixed in-domain/out-of-domain, explicit request-count repair and >3-task
rules were not changed. Their precedence in mixed enumerated queries remains an
edge case to test separately; this formatting change does not claim to resolve
all routing semantics. No changes to normalizer, executor, gold datasets, API
schema, production config or README were made in this v45 change.

The previous 5/5 DeepSeek provider-default-limit probe belongs to v44, not v45.
Preserve those reports. A future approved comparison must pin the runtime, shared
prompt/registry, schema transport and output-token policy for each variant.
