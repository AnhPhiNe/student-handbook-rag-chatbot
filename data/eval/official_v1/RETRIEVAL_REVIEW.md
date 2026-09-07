# Retrieval relevance review

This is source review, not evaluation output. Runtime and corpus are unchanged.

## Reviewed multi-source corrections

- 045: Article 12 describes regular-study warnings, not registration permissions.
  Articles 9 and 13 are required for the comparison of registration across
  training modes. Article 12 is background (grade 1), not a third requirement.
  This revises the earlier draft that required all three articles.
- 090: The explicit exclusion of bridging students in Article 26 is sufficient
  to answer this particular question. Article 27 is relevant background (grade 1),
  not another mandatory source (grade 2). A fixture verifies that finding the
  exclusion alone yields full required-source recall.
- Multi-source does not automatically mean every listed article is required.
  Required-source recall and graded ranking metrics measure different things.

## Confirmed equivalent-source decisions

- 107, K50: training Article 16 and student affairs Article 30 both explicitly
  require faculty confirmation for temporary leave; either answers this narrow question.
- 113, K50: student affairs Articles 35 and 37 both identify the rector as the
  decision maker; the council proposes rather than issues the decision.
- 150, K51: conduct Article 14 and student affairs Article 31 both specify
  expulsion for the second occurrence of two consecutive weak/poor semesters
  for undergraduate students.
- 149 is NOT assigned that same equivalence: student affairs suspension wording
  does not state the minimum suspension duration given by conduct Article 14.

Equivalent articles form one requirement for required-source recall and one
relevance gain for nDCG. Repeated equivalent results retain their occupied ranks
but receive no duplicate gain. Missing unrelated mandatory articles still lowers
recall. Fixture tests cover either alternative, both alternatives and rank-six
preservation. This is not an exhaustive corpus-wide equivalence claim or freeze.

## Gold consistency checks

The offline builder validates all 155 cases: unique source judgments, matching
evidence records, declared cohort scope, valid relevance grades and at least one
required source. Equivalent groups must contain known required sources from one
cohort, with no overlapping groups. Negative fixtures reject missing source IDs,
cross-cohort equivalence, background-only equivalence and overlapping groups.

These checks establish structural consistency, not exhaustive semantic correctness.
The question/source-anchor pass now covers all 155 cases. Targeted full-parent
checks were used for the corrections and equivalences above, including K51's
amended grade-improvement rule. This is not a claim that every paragraph of every
parent or every possible equivalent article has been exhaustively reviewed.

## Context limitations and handoff to answer authoring

- `gold_evidence.context` is an anchor preview, not a complete reference answer.
  It may stop before an exception or match a title before the operative clause.
- K51 Article 10 contains both original wording and the amendment specifying the
  highest achieved score for improvement. Answer gold must use the amendment,
  not copy the truncated preview in cases 035/075.
- Retrieval source IDs target complete parents. A short preview does not change
  the indexed parent identity or justify changing runtime evidence handling.
- Generate + Judge gold must be authored against complete relevant clauses and
  catalog records, not mechanically copied from these previews.
- No model quality results, independent human audit or joint freeze is claimed.
