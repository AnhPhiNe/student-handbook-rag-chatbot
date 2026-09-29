# Planner V47 — clarify contact-field intent

## Scope

This is a small, model-neutral instruction change after reviewing the V46
DeepSeek smoke case `096`. The observation was a mismatch with the gold's
intended field, not proof that the final composer answer was wrong or that
the cause was exclusively the model. No new inference was authorized for
this change.

The canonical instruction lives in
`configs/structured_lookup_registry.yaml`, under
`student_service.slot_schema.requested_field.description`.
`compact_registry_for_prompt` preserves this description, and
`AIRouter._build_plan_prompt` supplies it in `TOOLS` for both Qwen/Groq and
DeepSeek. There is no provider-specific wording or duplicated system-prompt
rule. The prompt version is now `structured-regulation-v47-contact-intent`;
the schema and normalizer versions are unchanged.

## Before and after

Before: define `unit` as the responsible unit, `office` as address/location,
and avoid selecting solely from the word `phòng`.

After: retain those definitions and clarify the decision by the requested
information:

- Who/which unit or department is responsible for or supports a service:
  `unit`.
- Physical working location, address, building, floor or room: `office`.
- A named unit followed by `ở đâu` also requests location; a floor/room number
  need not be explicitly mentioned.
- Both responsible unit and working location: `[unit, office]` or `all`.
- The existing shared rule still asks for clarification when intent is
  genuinely ambiguous; it is not duplicated in this slot description.

This does **not** impose a keyword/default rule that every `phòng nào`
question means `unit`, or every query without a floor/room number means
`unit`. It does not contain graduation, case IDs, named model exceptions,
or particular service-to-field mappings. The normalizer still preserves a
valid field selected by the planner; no post-hoc semantic correction was
added.

## Input-prompt size

The user explicitly approved exceeding the previous input-prompt test budget
when needed for clarity. The final description uses full decision sentences
rather than compressed cues. With the existing budget-test query, empty
history and unchanged schema:

| Prompt path | V46 total characters | V47 total characters |
| --- | --- | --- |
| Native JSON Schema | 14,150 | 14,368 |
| Embedded schema / JSON object | 14,062 | 14,280 |

The change adds 218 characters (about 1.5%), not an unbounded instruction
expansion. The test ceiling increases from 14,200 to 14,400 characters and
from 3,550 to 3,600 **character-based estimated** input tokens. These estimates
are not provider token counts, cost measurements or runtime truncation
settings. Output-token policy, timeout, retries and production configuration
remain unchanged.

## Offline checks

- Both provider prompt builders receive identical contact semantics for
  responsible-unit, plain-location and combined-field questions.
- Eight contrastive, hand-authored intent rubrics live in
  `data/eval/development/prompt_v47_contact_intent_cases.yaml`.
  They cover service-to-unit, service-to-location, named-unit location
  without physical keywords, a floor question, combined unit/location,
  combined unit/email, and overall contact information.
- The authored slots/spans pass the existing validator and full QueryPlan
  normalizer, including one-task multi-field plans.
- A deliberately supplied `office` field for a unit-intent question remains
  `office`; the normalizer does not introduce a keyword-based correction.
- Existing serialization/schema equivalence tests remain in the verification
  suite.

Verification completed: **156 focused tests passed** and the full offline
suite passed **1,063 tests**, with two dependency deprecation warnings.
`git diff --check` found no whitespace errors in the edited tracked files.
SHA-256 checks confirmed that the official V9/V10 compiled datasets and the
saved V46 smoke report are unchanged.

These checks establish that the instructions reach both providers and that
the authored plan shapes fit the runtime contract. They **do not** establish
that either live model will choose those intents, that the handbook contains
every hypothetical service/location detail, or that accuracy/latency improved.
The rubrics are development fixtures, not official gold or a new holdout.

## Unchanged measurements and remaining work

The V46 smoke remains **9/12** in its original report. Official V9/V10 gold,
compiled datasets and historical reports are not edited or regraded here.
The known `018` original-text versus retrieval-expansion grounding defect
and `122` scalar versus multi-field evaluator mismatch are not fixed in this
prompt-only change. They still require separate offline work before the next
paid benchmark. No production configuration, README, HTTP API or source data
is changed, and no commit/push is performed.

Any subsequent live comparison must explicitly record V47, keep both models'
task/schema semantics identical, disclose provider/reasoning/timeout/token
settings and operational errors, and obtain cost approval first. Do not claim
Qwen/DeepSeek parity from the offline fixtures or replace the saved V46 result.
