# Structured execution contract

This contract separates interpretation from execution in the existing modules.
It does not add a planner, resolver framework, or fallback orchestration layer.

## Responsibilities

- **Planner** owns task decomposition, lookup intent, semantic selectors and
  extraction of input values with their source spans.
- **Normalizer** validates schema, source spans and factual correspondence. It
  does not invent missing slot values from query aliases or replace supplied
  values/spans with a different interpretation. An absent span may be recovered
  by exact matching for the same supplied value.
- **Dispatcher** selects applicable source tables, retains complete evidence,
  and checks eligibility before exposing a unique lookup as a fact lock.
- **Resolver** uses supplied slots for reference-table/formula execution. An
  explicit empty slot mapping is not permission to extract missing inputs from
  the query. Row/range matching and directory catalog matching remain necessary
  execution work.
- **Composer** receives evidence and any eligible fact lock; it is not a tool
  for calculating or inventing missing lookup inputs.

## Grounding is not a second semantic classifier

Reading-intent fields are validated against their declared schema. Canonical
string result selectors (such as course scope or program type) require valid
schema values and source spans, but not an exhaustive literal alias match.
Their semantic interpretation therefore depends on the Planner. A real span
does **not** prove that the Planner chose the correct category; this remains a
quality risk to evaluate, not a guarantee provided by validation.

Numeric values, free-form factual labels and catalog entities retain their
value-to-span checks. Cohort/source applicability and task isolation remain
required. Alias metadata is still useful for representation and catalog identity;
it is not used to fill missing semantic selectors.

## Missing and multiple inputs

Missing optional selectors preserve applicable table evidence. Missing required
inputs use the existing clarification policy. Ambiguous/multiple result inputs
must not be collapsed into a single fact lock. No response-quality improvement
is implied merely by having a cleaner execution contract.

Legacy direct lookup callers may explicitly omit `slots` (`None`) to retain
query-based compatibility. The dispatcher supplies a mapping on the runtime
reference/formula path. Directory lookups retain task-local catalog search;
they are not required to become numeric-style slot-only resolvers.

## Verification

Unit expectations that formerly required alias-based inference are updated to
the new contract, without modifying evaluation gold or model prompts. Regression
coverage includes missing inputs, factual hallucinations, explicit semantic
paraphrases, multiple selections, and task/cohort-specific fact locks through
source merging and Composer evidence-packet construction. Offline tests do not
replace a later live quality evaluation.
