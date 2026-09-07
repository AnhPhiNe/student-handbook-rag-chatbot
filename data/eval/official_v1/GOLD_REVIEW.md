# Deterministic gold review — in progress

Scope: system evaluation, not an independent research holdout. No historical
overlap screening and no model calls. All four suites must be authored and
frozen before official execution. Runtime remains unchanged.

## Completed checks

- Read the query and compiled source-backed fields for all 135 definitions.
- Checked the policy anchors in their surrounding parent text (including cohort
  differences: K48-K49 improvement uses the last attempt, not the K51 rule).
- Narrowed mandatory resolved outputs for duration and scholarship questions
  that only request a particular field. Full source records remain reviewable.
- Explicit scoring inputs now have slot assertions: a different score in the
  same classification interval must not pass merely because its label matches.
  Numeric strings with decimal commas or points are accepted equivalently.
- K51's unspecified course question permits clarification or conditional
  evidence from the applicable tables; it does not require a unique fact-lock.
- Self-tests use synthetic responses. They are not chatbot quality metrics.
- Compound self-tests accept task reordering and reject dropped tasks. Missing
  input tests reject both an empty plan and an ungrounded answered plan.
- Contact questions requesting two outputs accept a grouped lookup or separate
  grounded lookups. Neither decomposition is privileged in those cases.

## Remaining before freeze

- Finish cross-suite evaluator/source provenance checks. Freeze once, only after
  all four suites are complete; no individual-suite freeze gate.
- All four suites are now authored. Retrieval context/equivalent-source decisions are recorded in `RETRIEVAL_REVIEW.md`; final answer and Production review are recorded in `REVIEW_FOR_APPROVAL.md`. Owner approval and joint freeze remain pending.

This file records AI-assisted review, not independent human audit. The
deterministic suite is not frozen and no official evaluation has run.
