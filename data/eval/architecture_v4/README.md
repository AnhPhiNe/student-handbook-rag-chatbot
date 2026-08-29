# Architecture v4 evaluation bundle

This is the frozen-candidate evaluation contract for the current QueryPlan/Composer
architecture. It evaluates four different layers separately so a high score in one
layer cannot hide a defect in another.

## Suite inventory

| Suite | Cases | What it isolates | Primary metrics |
|---|---:|---|---|
| Deterministic tools | 144 | Router, cohort resolution, structured lookup and execution contract | exact path/tool/source match, resolution accuracy |
| Retrieval | 180 | Evidence discovery before answer generation | Hit@1/3/5, MRR, nDCG, cohort leakage |
| Answer quality | 150 | Final answer behavior across all supported paths | correctness, completeness, faithfulness, citation correctness, path/handling accuracy |
| Production | 60 | Deployed API behavior and operational regressions | pass rate, TTFT, latency, stream/metadata contract, availability |

The 150 answer cases are distributed as follows:

- 72 regulation RAG cases: 18 each for K48-K49, K50, K51 and cohort-neutral questions.
- 30 structured cases: 10 lookup groups x 3 cohorts.
- 18 related mixed cases: 6 policy-plus-structured scenarios x 3 cohorts.
- 10 clarification cases with genuinely missing decision-critical information.
- 10 in-domain unanswerable cases whose requested personal/live data is absent.
- 10 clearly out-of-domain cases.

## Why the suites are not merged into one score

- Deterministic exactness answers whether the system selected and executed the right path.
- Retrieval metrics answer whether the needed evidence was found.
- Answer metrics answer whether Composer used that evidence correctly.
- Production metrics answer whether the deployed service still meets its API and latency contract.

Report each family separately. A weighted global score is allowed only as a secondary
dashboard value and must never replace the component metrics.

## Answer-quality protocol

Ground truth and required facts are derived from frozen parent sections or structured
records before any new model output is generated. Every answer case declares its
expected path, answerability, evidence identity and forbidden claims where applicable.

Recommended evaluation stages:

1. Generate exactly one fresh answer for all 150 cases with run metadata recorded.
2. Run the project judge over all 150 cases and keep raw per-case judgments.
3. Run RAGAS on a frozen 60-case answerable subset: 30 RAG, 15 structured and 15 mixed.
4. Human-review the stratified 30-case template; repeat 6 cases to estimate reviewer consistency.
5. Human-review every automatic failure before classifying it as a system defect,
   evaluation-case issue or acceptable minor limitation.

RAGAS faithfulness/relevancy is diagnostic for answerable cases only. Clarification,
abstention and OOD cases are evaluated with handling/path accuracy rather than being
forced into a faithfulness metric that does not fit their contract.

## Headline and diagnostic metrics

Suitable headline metrics:

- deterministic path-and-resolution exactness;
- retrieval Hit@5 and cohort leakage;
- human-reviewed answer correctness and faithfulness;
- production smoke pass rate and TTFT/latency percentiles.

Diagnostic metrics include Hit@1/3, MRR, nDCG, citation correctness, completeness,
RAGAS faithfulness/context precision/context recall/answer relevancy, per-path pass
rates and failure taxonomy. Always publish the denominator beside a percentage.

## Leakage and validity guards

- The bundle must be frozen before generation or judging.
- Source identity includes document, cohort and canonical parent section.
- Cross-cohort evidence is invalid unless explicit applicability metadata permits it.
- Mixed cases require both a structured source and regulation evidence.
- Duplicate normalized queries, missing ground truth and incomplete coverage fail the build.
- Model outputs are not used to author or repair reference answers after a run begins.

`coverage_report.json` records the static audit. `human_audit_template.json` defines
the stratified manual sample, and `ragas_subset.json` pins the 60-case diagnostic
subset before answers are generated. `manifest.json` pins dataset/config/docstore
hashes and states whether the bundle is frozen.
