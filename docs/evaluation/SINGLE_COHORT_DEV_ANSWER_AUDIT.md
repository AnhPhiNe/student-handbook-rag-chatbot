# Single-cohort dev answer audit

This audit is performed before changing composer evidence selection or the judge
packet. It uses only the frozen development run; hidden cases remain unopened.

## Files to review

All run-specific files are under:

`data/eval/reports/single_cohort_v2/<commit-prefix>/`

Use these files:

1. `dev_answer_human_audit_queue.json` — the complete evidence packet for 20
   judge-flagged answers and 10 stratified negative controls.
2. `dev_answer_human_audit_decisions.json` — the only file the human reviewer
   edits. Do not edit the queue, gold dataset, answer report, or judge report.
3. `dev_rank5_technical_audit.md` — compact overview of the six RAG requests
   whose first gold source is at rank 5.
4. `dev_rank5_technical_audit.json` — full rank-5 candidate content and
   provenance used for technical decisions.
5. `dev_answer_human_audit_manifest.json` — commit and SHA-256 bindings for the
   frozen queue.

## Review procedure for the 30 answer cases

Review one row at a time without looking at whether it is a flagged case or a
control until after judging the answer.

1. Read `query`, `selected_cohort`, `chat_history`, and `expected_requests` in
   the queue row.
2. Split the answer into factual claims. A claim includes every number,
   condition, exception, responsible unit, deadline, entitlement, prohibition,
   and recommendation stated as fact.
3. For each claim, search only the request-scoped citations with the same
   `request_id`. Do not use general knowledge and do not let evidence from `r1`
   support a claim belonging to `r2`.
4. Compare the answer with the user's requested scope. A true but unsolicited
   detail is scope expansion; record whether it is harmless or could change a
   student's decision.
5. Compare the full runtime citations with `judge.citations_in_packet` and
   `judge.omitted_citations`. If a claim is supported only by an omitted runtime
   citation, record it in `supported_but_omitted_claims`.
6. Fill the matching row in `dev_answer_human_audit_decisions.json`. Do not set
   the top-level status to approved until all 30 rows are complete.

Use exactly one label:

- `judge_false_positive`: every material claim is supported and in scope; the
  judge missed or misread available evidence.
- `minor_unsupported`: an unsupported or out-of-scope detail exists but does
  not alter the requested answer or a reasonable student decision.
- `material_hallucination`: an unsupported detail can alter the answer,
  eligibility, required action, deadline, amount, or interpretation.
- `critical_false_pass`: wrong cohort/entity/number/prohibition/source binding,
  fabricated policy, or an unsafe confident answer where the system should
  abstain.
- `clean_control`: a negative-control answer is fully supported and in scope.
- `judge_false_negative`: a negative control contains an unsupported claim the
  judge did not flag.
- `incorrect_abstention`: a verified, source-bound result exists but the public
  answer incorrectly says that no answer or source was found.

Severity must be `none`, `minor`, `material`, or `critical`. Set
`answers_user_need` to a boolean independently of correctness: an answer can
address the user's need yet still contain a material unsupported claim.

Recommended layers are: `none`, `judge_packet`, `composer_context`,
`composer_prompt`, `retrieval`, `structured_guardrail`, or `gold_annotation`.
Do not recommend a keyword rule, case-ID rule, or hidden-label change.

## Review procedure for six rank-5 RAG requests

For each request in `dev_rank5_technical_audit.json`:

1. Confirm that the rank-5 gold source directly answers the `query_span` for the
   effective cohort.
2. Inspect ranks 1–4 and mark whether each directly answers the same request or
   merely shares vocabulary.
3. Decide whether the rank-5 source was necessary for the generated answer.
4. Decide whether any rank 1–4 candidate could be excluded from composer input
   using existing request scope, source provenance, and retrieval scores.
5. Record a general evidence-policy signal, never a phrase-specific mapping.

The retrieval pool stays at Hit@5 during this audit. These six cases determine
whether composer evidence can be filtered without losing recall; they do not
authorize a fixed top-N cut or a reranker.

## Completion and approval

The reviewer completes all 30 decision rows, sets `reviewer` and `reviewed_at`,
then asks the project owner to approve the decision file. Automation may verify
completeness and hashes, but must never mark human approval by itself.

Only after approval may engineering decide whether to change composer evidence
selection or increase the judge packet cap. Any such policy must be registered
and tested on development data before the hidden run.
