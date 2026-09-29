# Shared planner prompt v44 — development candidate, not validated for release

Baseline: commit `a8db95be58fb2c748bbcf016f0ac426ce8e900c1`, prompt
`structured-regulation-v43-no-catalog-hint`. Git preserves the original prompt
and registry; do not overwrite or relabel existing evaluation reports.

## Hypothesis and boundaries

v44 clarifies explicit optional selectors, contact lookup by service, scholarship
money versus score, and unit name versus office location. The same system prompt
and tool descriptions serve Qwen and DeepSeek. Their existing schema transports
remain different (native JSON Schema versus embedded schema/JSON mode).

No new routing heuristic, slot, tool, source fact, resolver behavior or gold change
is introduced. Optional selectors remain optional in the schema. In particular,
this does not resolve task dependencies or the shared scoring/foreign-language
fact-lock failures. Case 096's ambiguous field contract is not silently changed.

The new `data/eval/development/prompt_v44_cases.yaml` contains 10 contrastive intent
rubrics. It is development material, not a hold-out, not answer gold, and not an
input compatible with the official V9 runner. The examples are NOT inserted into
the model prompt. Offline tests validate plumbing and authored slot compatibility;
they do not show that either model follows the new instructions.

## Before any paid experiment

- Owner approves the request budget and latency/quality criteria in advance.
- Compare Qwen low and DeepSeek low with v43 and v44, restoring only the prompt
  and registry between variants on the same runtime. Do not compare whole old
  checkouts with changed runtime behavior. Use an isolated checkout for trials.
- Use identical v1/v2 case versions, cache settings and explicit timeout/token
  limits within each model's before/after comparison. Record effective settings
  after environment overrides, provider/model, prompt/registry hashes and schema
  transport. Disable response and planner caches for quality comparisons.
- Capture pre/post-normalization decisions, retry/repair counts, planner timing
  and retrieval/execution timing separately on these synthetic cases. Do not log
  secrets or turn on unrestricted user-conversation logging.
- Run all cases, not just known failures. Report paired wins/losses, contract
  accuracy, schema/repair/fallback rates, p50/p95 with the percentile convention,
  and token/cost assumptions. Treat repeated runs as repeats, not new independent
  questions. The 15 `compound` cases must use their actual IDs and pass counts.
- v1/v2 and the new rubrics are development/regression material. Leave v3 alone:
  it is not eligible as a clean hold-out until its separate provenance/gold audit
  is resolved. Do not tune against a final hold-out result and keep that label.

The initial prompt change involved no inference or deployment and made no
model-quality claim. Subsequent authorized diagnostic runs are recorded below.
If v44 does not improve the agreed trade-off, retaining v43 is acceptable.

## Offline verification

The targeted prompt, normalizer, resolver, deterministic-evaluation, diagnostics,
and evaluation-contract suites passed all 134 tests after installing
`openai==2.54.0` (with `jiter==0.17.0`) in the local Python 3.12 environment.
The SDK is now declared directly in requirements.txt. Previously, two request
construction tests failed because this dependency was missing. These tests mock
the client; they do not verify acceptance by the live DeepSeek API.

`pip check` reports no broken requirements. The existing Python 3.11 runtime
constraints were not regenerated; a clean target-runtime dependency resolution
and deployment check remain necessary before production release.

`git diff --check` passed. No existing official datasets or reports were edited.

## Operational hardening and limited live probe — 2026-09-26

After the failed 20260925T151028Z run, offline reproductions established that
JSON error offsets such as `char 429` could be misclassified as HTTP status
codes, and one configured key prevented transient retries despite max_retries=1.
The old run does not retain enough error detail to establish the original cause
of every fallback or prove whether its rate-limit label came from HTTP 429.

Implemented and checked offline:

- JSON errors are classified before HTTP errors; status codes come from exception
  metadata rather than arbitrary digits in messages.
- Transient retry and key-rotation allowances are separately bounded. Authentication
  failures are not retried; rate-limited keys retain their cooldown.
- Diagnostic schema v2 records failure stage, safe exception metadata, JSON offset,
  finish reason and token usage when available. It does not store raw response
  text, reasoning, provider error bodies or credentials. Key-acquisition errors
  preserve prior diagnostic attempts. Follow-up history capture remains disabled.
- The official runner defaults to stopping after three consecutive operational
  failures, saves partial results, marks unrun cases and exits with code 2.
  Ordinary gold mismatches do not trigger this stop. `--limit` supports smoke runs.
- Evaluation reports distinguish runtime exceptions from planner fallbacks. These
  summary semantics differ from historical reports; old reports remain untouched.

Validation: 171 targeted tests passed; Ruff and `git diff --check` passed.

Authorized live probe: `official_v1_deterministic_20260926T012751Z`, first five v1
cases, DeepSeek low, prompt v44, 20-second timeout, 768 base output tokens and
2048 hard cap (the latter does not automatically allocate 2048 to single tasks).
Both caches relevant to planner/answer evaluation were disabled or unused.
The five cases completed: 002 and 005 passed; 001, 003 and 004 failed parsing.
All three failures returned `finish_reason=length` with exactly 768 output tokens;
their content lengths were respectively 247, 0 and 0 characters. No HTTP/key-pool
failure occurred in this probe. Pre/post source hashes matched.

The provider reported 20,148 input and 3,694 output tokens across these requests;
this is usage, not a verified billed cost. No Qwen or answer-judge run was launched.
This probe establishes truncation in these three new failures, not retrospective
proof about all 39 historical fallbacks, nor an accuracy estimate for the model.
Next experiment should change only DeepSeek's output-token budget on this small
probe before any full-suite rerun; prompt and gold should stay unchanged.

## Provider-default output limit probe — 2026-09-26

With owner approval, added `omit_max_tokens` (default false, DeepSeek only) and
enabled it in the DeepSeek experiment YAML. The client omits the API parameter
instead of sending null or a large numeric value. The provider still has an output
limit. Qwen's request construction and production YAML remain unchanged. Cache
identity now distinguishes explicit and provider-default output policies; the
run snapshot records `output_token_policy` and `max_tokens_sent` explicitly.
The numeric output settings in this experiment are local reservation estimates,
not transmitted limits, when omission is enabled. Offline checks: 174 tests passed,
including request-shape tests for thinking/non-thinking and both limit policies;
Ruff and diff whitespace checks passed.

Live run `official_v1_deterministic_20260926T014549Z` used the same first five v1
cases, prompt v44, registry, DeepSeek low, timeout 20 seconds and cache policy as
the preceding capped probe. All five passed; no fallback or runtime error occurred.
Output tokens per case 001–005 were 1288, 1337, 1307, 948 and 1333, respectively.
Reported usage totaled 20,148 input and 6,213 output tokens (not verified billing).
Median retrieval/execution case time was 6.43 seconds versus 6.04 seconds in the
preceding capped probe; neither is planner-only or final-answer latency.
Pre/post source hashes matched. No Qwen, answer-judge or full 135-case run was made.

This removes the observed truncation failures on this small development probe.
It does not establish full-set accuracy, production reliability, prompt superiority,
or the exact token settings used in the historical 128/135 run. The next validation
is a separately approved full v1 run with this policy; any v43/v44 comparison must
use the same token policy on both sides.
