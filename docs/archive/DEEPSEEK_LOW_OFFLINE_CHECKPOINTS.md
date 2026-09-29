# DeepSeek `low`: offline runtime/evaluator checkpoint (2026-09-26)

This is an implementation and verification record, **not** a new model score or
production approval. No inference API was called, and no deployment/production-configuration
change, commit, or push was made in this checkpoint. The dirty worktree present
before this work was preserved.

## Checkpoint 1 — observed behavior and desired contracts

The saved V9 DeepSeek-low run is
`data/eval/reports/official_v1_deterministic_20260926T072715Z/deterministic.json`
(SHA-256 `6515645c846f7c392c30de86c8255feecb27adc18463c63b792080847de8cd96`).
It has 135 executed cases, 123 passes, and 12 failures. In the saved execution,
`018` and `033` had structured evidence but no `resolved_result`. The current
desired contracts are separate from that historical observation:

| Case/shape | V9 observation | Desired/current offline behavior |
| --- | --- | --- |
| `018`, one pass/fail table + one score row | evidence only | `resolved_result` after scope/operand validation |
| `033`, TCF/DELF | evidence only | `resolved_result`: both names are in **one reviewed catalog row** |
| K51 `graded` without foundation/remaining | unresolved | per-table `resolved_rows`, evidence only; no fact lock |
| program → faculty contact | separate tasks or clarification | one program task can join one reviewed faculty profile, with two source citations |
| ambiguous directory source | no safe unique join | clarify before any join |

`tests/test_deepseek_offline_v10.py` now asserts those desired states as passing
tests, including evidence, citation and composer-input snapshots. No pending or
xfail marker remains. `resolved_rows` still means candidate rows within
alternative tables; it is not redefined as a final list answer.

## Checkpoint 2 — runtime changes

- A shared score parser retains both decimal value and declared scale. In a
  ten-point lookup, `3,6/10`, `3.6`, and `3,60` agree; `3,6/4` does not.
- `course_scope=graded` excludes pass/fail-ungraded tables. K51 still has two
  mutually exclusive grade tables; the runtime does not choose one without
  foundation/remaining scope. A fact lock requires one selected table, one
  resolved row and validated operation/slots/cohort.
- Catalog relations are declared in the lookup registry and traverse at most
  one hop. Source uniqueness is required first. Exact normalized keys are
  preferred; the only token-span fallback uses a **catalog-declared,
  multi-word, interior alias**, with cardinality checked after matching. It
  handles `Khoa Tâm lý học` → the reviewed `Tâm lý` alias of `Khoa Tâm lí học`
  without accent folding. It intentionally does **not** treat the prefix
  `Khoa Tiếng Trung` as a match for `Khoa Tiếng Trung Quốc`.
- The relation result keeps source and target in separate `sub_lookups`; the
  existing citation builder emits both. Missing targets retain source evidence
  and `target_unavailable`. One office can return multiple linked services;
  multiple source offices or multiple one-to-one targets request clarification.
- Planner diagnostics and whole-call planner latency survive downstream
  exceptions. The latency timer spans the planner call, including retries and
  key wait, not just one provider attempt. The evaluator reports planner,
  execution, and evaluator failures separately.

Catalog integrity checks covered **129 program records** and **239 service
records**. No relation had more than one matching target in its cohort.
All 239 services had a reviewed office target, and every office `service_id`
resolved back to a reviewed service in the same cohort. At the initial checkpoint,
two K51 programs—`Ngôn ngữ
Trung Quốc` (`K51_program_20`) and `Sư phạm tiếng Trung Quốc`
(`K51_program_35`)—name `Khoa Tiếng Trung Quốc`, while the reviewed profile is
`Khoa Tiếng Trung`. Initially there was no authorized alias, so these joins
returned unavailable rather than relying on generic prefix matching. This
gap is now resolved by the source-confirmed alias follow-up below. No program
record name was edited.

### Follow-up — source-confirmed Chinese faculty alias

The owner confirmed from the K51 source that these names designate the same
faculty. `configs/office_aliases.yaml` now declares
`Khoa Tiếng Trung: [Khoa Tiếng Trung Quốc]` under `unit_aliases`. The faculty
profile artifact was regenerated using the existing
`build_student_faculty_profiles` → `normalize_directory_catalog` → `save_json`
pipeline functions, not hand-edited. A pre-build comparison confirmed the
builder reproduced all 78 existing profiles; after this change the JSON diff
only adds the declared alias to the K50 and K51 `Khoa Tiếng Trung` profiles.
The program records, contact values, IDs, raw sources and gold are unchanged.

All **129/129 program records** now join exactly one faculty profile in their
own cohort; all **239/239 service records** still join exactly one office.
Tests check both K51 Chinese programs return
`khoatiengtrung@hcmue.edu.vn`, retain `Khoa Tiếng Trung Quốc` in the source
program record and `Khoa Tiếng Trung` in the target profile, and emit separate
program/faculty citations from the K51 handbook. The generic prefix block is
unchanged and has an explicit regression test. The pipeline output is also
checked for reproducibility. No new inference or gold change was performed.

## Checkpoint 3 — V10 contract and same-output regrade

The V9 compiled dataset and prior reports remain untouched. The V10 authoring
change adds exactly one accepted **one-task program→faculty** outcome each to
`114` and `119`. Every gold fact is identical to V9; all 133 other cases have
identical accepted outcomes. V10 additionally checks that the program and
faculty contact are both present in the same cohort with separate provenance.
`093/096` still fail when the plan chooses `office` instead of `student_service`.

The newly compiled dataset is
`data/eval/official_v1/deterministic_tool_cases_v10.json` (SHA-256
`99eb05c3a4ddc9d7059c9ecd6e676e7c7e859f77a7906b5141ad80a16002fd42`).
The V10 regrade of **the same saved outputs** is in
`data/eval/reports/official_v1_regraded_v10_20260926T124254Z/deterministic.json`.
It remains **123/135 = 91.1%**, with zero changed case pass/fail decisions.
Request success after retry is **131/135 = 97.0%**: one execution exception and
three planner request failures remain in the denominator. Among the 131
operationally successful requests, semantic pass rate is **123/131 = 93.9%**.
That latter number does not replace the overall score. Historical planner p95
cannot be reconstructed from this report because whole-call timings were not
saved in V9.

The 12 historical failures still break down as follows. Offline tests verify
the new runtime contracts, but they cannot retroactively change saved output:

| Cases | Saved failure / offline finding | Requires new inference? |
| --- | --- | --- |
| `013/014` | saved plans omit `graded`; both remain unlocked in saved output. New explicit-graded plans are validated offline. | Yes, to see whether planner emits scope. |
| `018/033` | saved output lacks lock; current single-table/combined-row resolver tests now produce one. | Yes, for measured end-to-end improvement. |
| `034` | downstream Qdrant exception; original report lacks planner diagnostics. Future failures retain the trace. | Yes, plus operational health check. |
| `035/047/122` | provider error or timeout, not semantic planner mistakes. | Yes. |
| `093/096` | wrong tool (`office` instead of `student_service`); V10 still fails both. | Yes; runtime join does not excuse routing error. |
| `114/119` | saved plan has program + clarification, not the one-task program/contact form. Synthetic one-task execution with two sources passes V10. | Yes, to see whether planner chooses it. |

All **1,057** repository tests pass after the alias follow-up (two dependency
deprecation warnings). The focused offline/contracts subset passed 288 tests
before the final added assertions. `git diff --check` found no whitespace
errors. No API, production, README or raw source/program records were changed;
the reviewed alias config and its derived faculty profile artifact were updated.

## Not yet approved for production

The saved 91.1% deterministic accuracy is below the ≥95% gate, and 97.0%
request success is below ≥99%. Relation coverage and planner p95 for a new
DeepSeek run are not measured yet. Before canary, obtain explicit cost approval,
then run the 12-case smoke, one full 135-case V10 run, 100-case staging run,
and a separately verified Qwen rollback configuration. Treat API/timeout cases
as operational failures, not removed samples. If a run stops early, report
requested/executed/not-run counts. Only then consider 10% canary, observing
at least 48 hours **and** 200 planner requests, with latency/error gates.

`v10` and `v9` scores must always be labeled separately. A future V10 run may
change because of runtime, planner behavior, provider availability and the
contract; the same-output regrade above isolates the contract change only.
