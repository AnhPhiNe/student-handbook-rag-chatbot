# Luna medium — smoke V49, 2026-09-27

## Scope and configuration

User approved at most 26 cases, not the full benchmark. Completed exactly 18 contract/execution cases and 8 pre-authored contact-intent probes. No additional inference, composer evaluation, deployment, commit, or push followed these runs.

- OpenAI Responses API, `gpt-6-luna`, reasoning `medium`.
- Prompt `structured-regulation-v49-field-semantics`; deterministic contract v10.
- `json_object`, **not strict JSON Schema**.
- Explicit `max_output_tokens=8192`; timeout 20 seconds per attempt; maximum one transient-error retry. SDK automatic retries disabled.
- Router plan cache disabled. Provider cached input tokens are prompt-prefix caching, not reuse of a saved plan.
- Experiment configuration: `configs/experiments/ai_router_openai_luna_medium.yaml`. Production configuration was not changed.

## Artifacts and reproducibility

1. Contract/execution report: `data/eval/reports/deepseek_v48_smoke_deterministic_20260927T033418Z/deterministic.json`, with adjacent `run_snapshot.json` and `checkpoint.json`. The directory uses the existing **dataset bundle name**; its actual model is OpenAI Luna, not DeepSeek.
2. Contact probes: `data/eval/reports/luna_v49_medium_contact_20260927T033717Z/report.json`.
3. Both reports have `post_run_hashes_match=true`. Prompt/gold were not adjusted between the two runs.
4. Earlier startup attempt `deepseek_v48_smoke_deterministic_20260927T033341Z` stopped during blocked embedding-model initialization, before planner cases; it is not another inference trial.

Focused offline verification before the run: **88 tests passed** across `test_openai_planner.py`, `test_luna_contact_smoke.py`, and `test_ai_router_prompt.py`. This is not a claim that the entire repository suite was rerun in this turn.

## Results

| Measurement | Result |
| --- | --- |
| Contract/execution cases | **15/18 (83.3%)** |
| Historical failure subset | 9/12 |
| Additional scale/entity/cohort cases | **6/6** |
| Contact probes, original exact rubric | **5/8**; interpretation below |
| Successful planner requests | **26/26** |
| Request events / retries / repairs | 26 / 0 / 0 |
| API errors, timeout, truncation | 0 observed |
| Planner latency, all 26: p50 / p95 | **4.61 s / 8.79 s** |
| Planner latency, 18 contract cases: p95 | 11.66 s |
| Cross-cohort leakage, contract report | 0 observed |

Latency p50 is the median; p95 uses nearest rank. Planner latency is separate from executor latency. For example, case 122 took approximately 8.58 seconds in the planner but 29.17 seconds including execution; that is not a planner timeout.

Usage across all 26 requests: 110,634 input tokens (53,664 cached), 12,977 output tokens, including 8,093 reasoning tokens. All 26 finish reasons were `stop`; the largest output was 1,448 tokens. No exact billing claim is made.

These are development/regression samples, not an independent holdout. Do not combine the two suites into a single accuracy: they check different contracts. Successful requests do not imply semantically correct plans. A sample of 26 requests does not establish long-term 99% operational reliability.

## Contract failures

### 047 — unnecessary clarification in a whole-table comparison

Query: “Chính quy học mới, liên thông và văn bằng hai thì thời gian học khác nhau thế nào?”

Luna produced first-degree lookup, clarification asking whether the bridge program is from college or intermediate level, and second-degree lookup. The expected outcome is a whole-table comparison that includes both bridge options. This is not just malformed JSON: the planner unnecessarily interrupted a comparison that the available table can answer. The original failure is retained; no gold change was made.

### 093 and 096 — invalid field code

- 093: “Xin giấy chứng nhận điểm ở phòng nào?”
- 096: “Nhận bằng tốt nghiệp ở phòng nào?”

Both select `student_service`, but raw output uses `requested_field="địa chỉ"`. This is a Vietnamese field description, not an allowed field code. Normalization turns the task into clarification with `invalid_slot_value:requested_field`.

There are two distinct issues: enum adherence and the ambiguous boundary between responsible `unit` and physical `office`. A strict schema could prevent the illegal enum value **if that enum is encoded in the enforced schema**, but would not guarantee choosing `unit` rather than `office`. These runs did not invoke composer, so they do not establish final-answer accuracy.

## Contact-probe interpretation

Preserve the original **5/8** exact-rubric result:

- `service_responsible_unit` and `service_support_unit` fail only because they output `direct_value` instead of the rubric's `contact`. Their tool, requested `unit`, entity and cohort are correct. The registry permits both intents for `student_service`; these are overly narrow rubric expectations, not demonstrated field-routing errors. Any corrected grading should be a separately labeled offline report, not an overwrite.
- `service_physical_location` asks for the address of the library-borrowing support unit. The model requests `[unit, office]` instead of only `office`. It includes the requested address field but adds the responsible unit. This fails the exact field-set rubric; it is not evidence that the location was omitted or answered incorrectly.
- The remaining five probes pass their original rubric.

These probes check routing fields, not full entity resolution, evidence execution, or generated answers.

## Decision and next step

Do **not** select Luna for production yet. Operational behavior is promising in this small smoke, but the contract subset remains below the proposed 95% gate. Previous V48 runs and this V49 run are not a controlled model-only comparison.

The two invalid enums provide concrete motivation to investigate narrowly scoped strict structured output, with offline compatibility tests against the actual runtime contract. Also separate valid intent equivalence from semantic errors in the contact rubric. Neither requires a broad architecture refactor; neither guarantees improved semantic accuracy. Preserve these raw results, then seek approval before any further paid trial or full benchmark.
