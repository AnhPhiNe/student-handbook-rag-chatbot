# DeepSeek low — V10 live smoke, 26 September 2026

## Scope and run identity

This is the first new model/runtime measurement after the offline V10 and
Chinese-faculty alias changes. It is **not** the evaluator-only regrade of the
old 135 outputs described in `DEEPSEEK_LOW_OFFLINE_CHECKPOINTS.md`.

The user approved only the 12 historical failures, with the existing retry
policy. No full 135-case run, composer evaluation, staging, deployment, commit
or push was performed. This deliberately difficult, selected subset must not
be interpreted as an estimate of full-benchmark accuracy.

- Report: `data/eval/reports/official_v1_deterministic_20260926T132645Z/deterministic.json`.
- Snapshot: the same directory's `run_snapshot.json`.
- Dataset: `official_v1`, contract `query-plan-grounded-outcome-v10`.
- Model: `deepseek-flash`, provider `deepseek`, reasoning `low`.
- Prompt: `structured-regulation-v46-contract-boundaries`.
- Normalizer: `v29-planner-contract-boundaries`.
- Timeout: 20 seconds per attempt; maximum one retry.
- Output policy: provider default; `max_tokens` was not sent.
- Router cache disabled; all 12 diagnostics have `cache_hit=false`.
- Response cache is not used by deterministic retrieval-only execution.
- Snapshot file hashes still matched at the end of the run.

Reasoning was overridden only in the running process. Production and the
experiment YAML were not changed to select `low` for this smoke.

The runner now supports explicit `--case-ids`, rejects empty, duplicate and
unknown IDs, and preserves dataset order. The snapshot records all selected
IDs, the original dataset size, and derived directory artifact hashes.

## Measured results — unchanged report

| Measurement | Result |
| --- | --- |
| Requested / executed / not run | 12 / 12 / 0 |
| Contract passes | **9/12 (75.0%)** |
| Final planner or execution errors | 0 |
| Request success after retry | **12/12 (100%)** |
| Recorded transient planner request failures | 1 timeout, recovered by retry |
| Cross-cohort leak | 0 |
| Planner median | 8.22 seconds |
| Planner p95, whole call including retry/key wait | **39.84 seconds** |
| Reported input / output / total tokens | 59,224 / 24,393 / 83,617 |

Token totals are the usage captured in successful responses. They are not a
guaranteed billing total for a timed-out request. No dollar cost is inferred.

The recorded p95 uses the evaluator's nearest-rank method. With only 12 cases,
it is the slowest observation, not a stable production latency estimate.
Case `047` timed out on its first attempt, then succeeded; its whole planner
call took 39.84 seconds. Case `122` took 20.40 seconds without a recorded retry;
the per-attempt SDK timeout must not be interpreted as a strict whole-call
20-second deadline.

Passes: `013`, `014`, `033`, `034`, `035`, `047`, `093`, `114`, `119`.
Failures: `018`, `096`, `122`.

Both `114` and `119` matched `one-hop-program-faculty-contact`, including the
V10 same-cohort source/target provenance checks. This covers two measured
relation cases, not all possible production relation questions.

The 12 selected cases all failed in the old saved report. Nine now pass, but
the new measurement combines current runtime, new model outputs, provider
availability and the V10 contract; it is not an isolated runtime A/B test.

## Failure diagnosis — offline, no additional API calls

### 018 — runtime grounding text is changed after planning

Question: `Môn không tính GPA, chỉ xét đạt hay trượt, 4,9 có qua không?`

The new plan correctly selects `scoring`, `pass_threshold`, score `4.9`,
scope `pass_fail_ungraded`, and cohort `K51`. The returned evidence uses the
correct pass/fail table, but lacks `resolved_result`.

`PlanExecutor._execute_planned_structured_task` passes
`SlangNormalizer.normalize_for_retrieval(task.question)` to the dispatcher.
That expands `GPA` into:

`GPA điểm trung bình học kỳ hoặc điểm trung bình tích lũy`

The literal planner span `không tính GPA, chỉ xét đạt hay trượt` then no
longer occurs in the execution query. Offline replay of the **same saved
task** confirmed:

| Text supplied to grounding | Validation errors | Resolution |
| --- | --- | --- |
| Original task question | `[]` | `resolved` |
| Retrieval-expanded question | `ungrounded_slot:course_scope` | `evidence_only` |

The existing offline `018` test called the dispatcher with the original
question, so it missed this executor-boundary defect. The correct next fix
is to preserve the original grounding source while keeping any retrieval
expansion separate, and test through the executor. It is not a reason to
remove fact-lock grounding checks or blame DeepSeek for this case.

### 096 — planner selects the wrong requested field

Question: `Nhận bằng tốt nghiệp ở phòng nào?`

The new plan now correctly chooses `student_service`, but emits
`requested_field="office"`. The registry defines `office` as a physical
address/location and `unit` as the responsible unit name. Gold requires
`unit` or `all` and the K51 `Phòng Đào tạo` evidence.

The execution finds the correct service/unit record, but the selected field
does not express the question's intended answer. An in-memory diagnostic
changing only the requested field to `unit`, with the same evidence, passes.
This was not applied to the saved output or counted in the reported score.

The registry already documents this distinction. One observation supports
a field-selection error, not a conclusion that the shared prompt must be
rewritten or that DeepSeek always fails this category. Preserve this negative
case when addressing the evaluator issue below.

### 122 — evaluator rejects a valid multi-field representation

Question asks who issues a grade certificate and their email, cohort K50.

The plan chooses one `student_service` task with
`requested_field=["unit", "email"]`. Normalization reports no validation
errors; the current slot validator accepts string arrays. The execution
returns the correct `Phòng Khảo thí và Đảm bảo chất lượng` record, K50
provenance, and `phongkhaothi@hcmue.edu.vn` in `emails`.

`_task_matches` compares the entire normalized slot value against the scalar
accepted alternatives `email` / `all`. It therefore rejects the two-field
array before binding execution evidence to the required task. This also
causes the reported row/evidence check to fail despite the correct selected
record.

An in-memory regrade changing only the plan's requested-field representation
to scalar `email`, without changing execution evidence, passes. This confirms
a representation mismatch in the evaluator, not missing email data.

A future correction should handle requested-field coverage generically,
retain task/source/cohort/provenance binding, and continue rejecting `office`
as a substitute for `unit`. Do not add this particular output to gold or
accept a fact merely because it occurs somewhere in a table. Record any
measurement change explicitly and regrade saved outputs into a **new** report;
the current 9/12 report remains untouched.

## Verification and next gate

After the runner-selection change, the full offline suite passed:
**1,058 tests**, with two dependency deprecation warnings.
`git diff --check` found no whitespace errors. Passing those tests does not
negate the executor coverage gap discovered by this smoke.

The 100% request-success observation is based on only 12 requests and does
not establish long-term >=99% availability. The measured planner p95 fails
the <=20-second gate. The selected 75% contract score cannot establish the
>=95% full-benchmark gate.

Do not proceed automatically to production or another paid benchmark. First
address the proven `018` runtime and `122` evaluator issues offline, retain
`096` as a semantic field-selection failure, and explicitly decide whether
latency policy/model settings need a separate experiment. Obtain approval
before any subsequent smoke/full run; verify staging and Qwen rollback before
canary.

