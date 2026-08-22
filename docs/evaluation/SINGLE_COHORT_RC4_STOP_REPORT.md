# Single-Cohort RC4 Stop Report

## Decision

RC4 stops at the development Planner gate. Executor/retrieval, answer/judge,
human audit, production smoke, freeze, and hidden evaluation were not run.
This follows the pre-registered stop condition: no RC5 and no case-specific
remediation after the single bounded RC4 remediation.

## Evaluated candidate

- Branch: `codex/single-cohort-rc4`
- Runtime commit: `4f1e397ba3f923ebdb97262435fd5969a4666847`
- Base commit: `1283ec86a8f9fd0e7cabe59888146dd33923943a`
- Planner: `qwen/qwen3.6-27b`
- Planner contract: `single-cohort-planner-v2.5`
- Planner prompt: `single-cohort-planner-v2.12`
- Validator: `single-cohort-validator-v2.9`
- Evaluation protocol: `single-cohort-release-v6-rc4`
- Composite planner registry digest:
  `061cfa23481965b59ae296b3804411a411c460f5909668aad2e1146ecb77568d`
- Implementation tree:
  `6c3bcc06f8355c1a2e12748d2590f6874c1dcd20f7a1ab7a5720fb1f1588d1aa`

## Deterministic verification

- Pytest: `479 passed`, two expected legacy migration warnings.
- Ruff: all checks passed.
- The runtime diff contains no verifier, reranker, classifier, new Planner
  retry, keyword routing, or case-ID branch.
- The two RC3 regression cases passed `2/2`, exact/semantic/execution eligible,
  with zero provider failures.
- The bounded robustness rerun passed its pre-gate: semantic plan `13/14`
  (`92.86%`), execution eligible `14/14`, provider failures `0`.

## Full development Planner result

The denominator is exactly 148 live Planner cases. The two deterministic
fault-injection cases are excluded and reported separately.

| Metric | Result | Gate | Status |
|---|---:|---:|---|
| Semantic plan accuracy | 138/148 (`93.24%`) | `>=95%` | Fail |
| Execution eligible rate | 143/148 (`96.62%`) | `>=95%` | Pass |
| Follow-up semantic plan | 15/15 (`100%`) | `>=90%` | Pass |
| Robustness semantic plan | 12/14 (`85.71%`) | `>=90%` | Fail |
| Cohort resolution | `100%` | `100%` | Pass |
| Safety/failure isolation | `100%` | `100%` | Pass |
| Multi-cohort rejection | `100%` | `100%` | Pass |
| Provider failures | `0` | `0` | Pass |

There were ten semantic-plan mismatches. Five remained execution eligible and
were representation differences. Five were execution-ineligible Planner gaps:

- `dev-single_rag-05`: clarify instead of one RAG request.
- `dev-single_rag-06`: clarify instead of one RAG request.
- `dev-single_rag-10`: omitted an atomic request.
- `dev-two_regulations-13`: omitted an atomic request.
- `dev-three_to_six_requests-05`: wrong decomposition/tool for one request.

One transport timeout triggered the pre-existing provider key failover and then
produced a valid model output. It is recorded as an operational incident, not a
failed case; RC4 added no Planner retry behavior.

## Single bounded remediation

The robustness pre-gate initially scored `12/14`. Both misses shared one
registry-boundary cause: accent folding let ordinary words inside purpose text
collide with short entity aliases. The remediation accepts single-token hints
only when the token is an acronym declared by a loaded registry artifact or is
an uppercase acronym span. This preserved `BHYT`/`PĐT`-style aliases without a
keyword list and removed low-information hint collisions. No second
remediation is allowed.

## Artifact bindings

- Planner checkpoint SHA-256:
  `0e823ed4aa6c6cd7f80f1c0c0c8fe682373467e0c378ab404bce67dcaace30eb`
- Development Planner report SHA-256:
  `6b91195c4e334fdba9a95043b440c761ee21f027a717b20b7bb262fe3c25334c`
- Robustness report SHA-256:
  `b55df2fafa63dadab2adf8accd873c4a44368e50ce9caa77a4011089e28637b5`

Local reports are stored under
`data/eval/reports/single_cohort_v2/` and remain excluded from Git to avoid
self-referential commit provenance.

## Limitation and next decision

The RC4 architecture and safety boundaries pass deterministic tests, and the
Planner is execution eligible for `96.62%` of live development cases. However,
the pre-registered semantic-plan and robustness gates did not pass. Therefore
this candidate must not be tagged as `single-cohort-technical-baseline`, must
not open the hidden set, and must not be represented as a frozen release.

Any future work is a separately approved research/product phase, not RC5. It
must start from this limitation report and use a new pre-registered protocol
rather than tuning against the failed development rows.
