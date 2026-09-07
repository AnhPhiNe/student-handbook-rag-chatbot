# Coverage review

Both suites remain drafts. No inference, runtime change or freeze performed.
Counts stay at Deterministic 135 and Retrieval 155 by replacing redundant
single-operation questions, not increasing the suite sizes.

## Added deterministic coverage

- 017: two different faculties, same lookup type.
- 039: improvement policy for K50 and K51.
- 048: temporary leave and transfer-policy requests.
- 112: classification, formula reference and improvement policy (three requests).
- 113: scholarship classification for K50 and K51 with distinct source rows.
- 115: three contact requests across offices and a faculty.

The existing structured/structured, structured/regulation and two-output contact
cases remain. These identifiers list additions, not the complete category counts.
Task-specific cohort overrides are dataset metadata; production is unchanged.

## Added retrieval coverage

Eleven replacements require multiple primary sources: 005, 020, 035, 045, 055,
065, 075, 090, 100, 120, 140. They include two cross-cohort comparisons, two
three-request questions, two cross-article exceptions and a comparison of
training modes. Grade 2 means each declared source is required, not interchangeable.

Actual request cohorts: K48-K49 52, K50 51, K51 50, general/multi-cohort 2.
The original allocation remains 52/52/51; it must not be reported as actual
single-cohort request counts after these replacements.

Self-tests verify partial required-source recall when a necessary article or
cohort is missing. These tests are not retrieval results.

## Latest fixture audit

- Partial clarification: case 124 requires both the known faculty contact lookup
  and a clarification for the missing GPA. Dropping the lookup is rejected.
- Case 039 accepts either separate cohort policy tasks or one grouped policy task.
- A swapped-evidence fixture initially passed incorrectly. Official deterministic
  contracts now opt into plan/task-ID binding; the two-faculty case includes
  entity slots so one faculty's evidence cannot satisfy the other task.
- This is an evaluator-only correction. No runtime or inference changed.

## Limits to resolve before the joint freeze

- Equivalent-source decisions are now recorded in `RETRIEVAL_REVIEW.md`. Related graph nodes are not automatically required evidence.
- Grouped structured case 113 now has per-cohort execution assertions and an
  accepted grouped-plan alternative. Fixtures accept complete K50/K51 results,
  reject swapped fact-locks, and reject missing K51 execution even when the K50
  envelope advertises shared document applicability. Schema validation rejects
  missing cohort units. This validates the evaluator, not the live pipeline.
- Extend semantic selectors where same-type tasks remain indistinguishable by
  declared slots. Task-ID binding alone cannot disambiguate underspecified gold.
- Do not claim exhaustive coverage of all combinations or final-answer quality.
  Generated-answer 150 and Production 60 are now authored; see `REVIEW_FOR_APPROVAL.md` for the joint handoff.
