# Official evaluation v3: planner hold-out

official_v3 measures the planner and structured execution on six kinds of question students ask. It is the hold-out for the planner rebuilt in 2026-09, from prompt v44 onward and the move to OpenAI Luna.

**Status:** frozen on 2026-09-27, by the commit that adds `deterministic_manifest.json`. It has not been run. Run it once, on the final system, then report.

Only the deterministic suite (planner plus structured execution) exists. Retrieval and answer suites can be derived later with `scripts/build_holdout_suites.py`, but they need their own review and freeze.

## Composition

| Family | Slice | Cases |
|---|---|---:|
| single | `single.structured` (scoring, conduct, foreign language, study duration, scholarship, formula, office, faculty, program, student service) | 17 |
| single | `single.regulation` | 17 |
| multi_intent | `struct_regu`: one table request plus one regulation request | 17 |
| multi_intent | `regu_regu`: two regulation requests | 17 |
| multi_intent | `struct_struct`: two table or directory requests | 17 |
| compare | `multi_cohort_structured` (7), `multi_cohort_regulation` (5), `same_table` (5) | 17 |

The set has 102 cases. Cohorts are balanced at 34 each (K48-K49, K50, K51). Eight cases are stress cases: informal spelling, a dense request, a boundary value, or a cohort difference.

Multi-request questions only combine **independent** requests. A request that needs another request's answer ("email của khoa đó") is out of scope: official_v1 covers it, together with the v10 program → faculty relation.

## Provenance

- **Authoring.** The questions were written on 2026-09-25 from the handbook content, in student phrasing, by the AI assistant working on this project. They were not collected from real students.
- **Gold.** Every gold value comes from catalog selectors, compiled by `scripts/build_official_deterministic.py --contract v10`: reviewed tables, directories, formula rules, and a literal quote that the compiler checks is present in the named article of that cohort. No gold was taken from system output.
- **Independence from the new planner.** The sessions that built planner prompts v44–v49 did not read this bundle.
- **Overlap screening.** `python -m scripts.check_bundle_overlap --bundle official_v3 --reference official_v1|official_v2 --threshold 0.7` finds **no** question at 0.7 or above. Twelve drafts that crossed the threshold were replaced with a *different fact*, not a rephrasing. A separate screen against the 18-case planner smoke bundle and the development rubrics found nothing at 0.7 or above; the closest pair, IELTS vs Linguaskill "bậc 4", scored 0.67.

## Review (2026-09-27)

At the owner's request, the **same AI author** reviewed the bundle. This is not an independent second review. The review had three layers.

**1. Mechanical checks.** The compiler asserts that every quote exists in its article and that every selected row is unique. The bundle has contract v10 and 34 cases per cohort.

**2. Case-by-case reading** of all 102 questions against the source rows and articles. It led to three corrections:

- *#033, #058.* The 50% credit-transfer cap has an exception for teacher-training programmes. Most students here are in one, so the gold fact now states the exception.
- *#043.* "Làm thẻ bảo hiểm y tế ở đâu" could ask for the responsible unit or for its location. It now asks "liên hệ đơn vị nào", so the gold has a single reading.
- *#008, #050, #086 (K48-K49 part), #091 (K48-K49 part), #100.* These questions name no programme type (first degree, college or intermediate bridge, second degree). Their gold was changed from the first-degree row to the whole table. The runtime correctly returns every row when no programme type is given, and the planner contract forbids inferring a selector that the question does not state. K51 tables have one row and keep their fact lock.

**3. Reachability.** For each structured gold unit (92 in total), a development check built the plan an ideal planner would emit, with literal spans from the question. It ran that plan through the real normalizer and dispatcher, with the production embedding model for directory matching. 89 of the 92 units reach their gold. The other three are **known runtime gaps, kept on purpose**, because they are real student phrasings and changing them would fit the benchmark to the system:

| Case | Gap |
|---|---|
| #005 | The score parser does not read "57d" (57 điểm) |
| #016 | Service matching finds no unit for "mượn micro" (the catalog says "Cho mượn amply, micro lớp học") |
| #076 | Service matching asks for clarification on "đóng học phí", because two units mention học phí; the gold is the unit that collects tuition |

Regulation tasks are judged on mode and cohort only. Retrieval quality belongs to a retrieval suite.

## Protocol

1. Check that nothing in this folder changed since the freeze. No output means it is unchanged:

   ```bash
   git diff --stat $(git log -1 --format=%H -- data/eval/official_v3/deterministic_manifest.json) -- data/eval/official_v3 ':!data/eval/official_v3/RESULTS.md'
   ```

2. Run it once on the final planner configuration, with caches disabled:

   ```bash
   python -m scripts.run_official_deterministic --bundle official_v3 --contract v10 --current-worktree
   ```

   Only the v10 compile exists, so a run without `--contract v10` stops rather than grading against v9.

3. Report the overall rate and the rate per slice family with 95% intervals, including operational failures. The three known runtime gaps count as failures unless the runtime has been fixed. A fix derived from *reading this bundle* spends the hold-out, and later runs must then be labelled post-fix regression measurements, as happened with official_v2.

4. Gold never changes because of a result.

## Limitations

- One AI author wrote and reviewed the questions and the gold; the owner has not reviewed them.
- The phrasing imitates students; it is not a sample of real traffic.
- 17 cases per family give wide intervals: a family result shows direction, not a precise rate.
