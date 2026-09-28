# Official evaluation v3: planner hold-out

official_v3 measures the planner and structured execution on the kinds of question students ask: single requests, several requests at once, comparisons, follow-ups, boundary cases and one-hop relations. It is the hold-out for the planner rebuilt in 2026-09, from prompt v44 onward and the move to OpenAI Luna.

**Rule:** never use a v3 result to change the system. Prompts, rules, catalogs and code are tuned on official_v1, official_v2 and the smoke bundles only. v3 is run on the final system, and its result is reported as it comes out.

There is no manifest or freeze step: the rule above is what keeps the hold-out valid. The git history of this folder shows whether the questions or gold changed after a run.

Only the deterministic suite (planner plus structured execution) exists. Retrieval and answer suites can be derived later with `scripts/build_holdout_suites.py`, but they need their own review.

## Composition

| Family | Slice | Cases |
|---|---|---:|
| single | `single.structured` (scoring, conduct, foreign language, study duration, scholarship, formula, office, faculty, program, student service) | 17 |
| single | `single.regulation` | 17 |
| multi_intent | `struct_regu`: one table request plus one regulation request | 17 |
| multi_intent | `regu_regu`: two regulation requests | 17 |
| multi_intent | `struct_struct`: two table or directory requests | 17 |
| multi_intent | `three_plus`: three independent requests in one question | 6 |
| multi_intent | `over_limit`: four or five requests; the planner must ask the student to choose at most three | 4 |
| compare | `multi_cohort_structured` (7), `multi_cohort_regulation` (5), `same_table` (5) | 17 |
| memory | `cohort_switch`, `entity_switch`, `pronoun`, `topic_switch` (2 each); the earlier turns supply the missing cohort, entity or referent | 8 |
| boundary | `clarify` (2), `partial_clarify` (2), `out_of_domain` (1), `mixed_domain` (1) | 6 |
| relation | `program_faculty` (4): a faculty contact reached from a programme; `service_contact` (2): a contact field of the unit that offers a service | 6 |

The set has 132 cases. Cohorts are balanced at 44 each (K48-K49, K50, K51). Twenty-one cases are stress cases: dense requests (7), informal spelling (4), cohort differences (4), partial missing input (2), domain vocabulary (2), a boundary value (1), and a context trap (1), where a value from the previous turn must not be reused as the student's own.

The `single`, `multi_intent` (two requests) and `compare` families only combine **independent** requests. Dependent requests live in `relation`: v10 accepts either one program task that returns the faculty contact through the one-hop relation, or two tasks.

## Provenance

- **Authoring.** The AI assistant working on this project wrote the questions from the handbook content, in student phrasing: 102 on 2026-09-25 and 30 on 2026-09-27 (`three_plus`, `over_limit`, `memory`, `boundary`, `relation`). They were not collected from real students.
- **Gold.** Every gold value comes from catalog selectors, compiled by `scripts/build_official_deterministic.py --contract v10`. The sources are reviewed tables, directories and formula rules, plus a literal quote that the compiler checks is present in the named article of that cohort. No gold was taken from system output. Clarify, over-limit and out-of-domain gold follow the planner contract: at most three tasks, a missing required input means asking, and an out-of-scope part is dropped from a mixed request.
- **Independence from the new planner.** The sessions that built planner prompts v44–v49 did not read this bundle.
- **Overlap screening.** `python -m scripts.check_bundle_overlap --bundle official_v3 --reference official_v1|official_v2 --threshold 0.7` finds **no** question at 0.7 or above, and the bundle has no internal duplicates. Thirteen drafts that crossed the threshold were replaced with a *different fact*, not a rephrasing. A separate screen of the first 102 cases against the 18-case planner smoke bundle and the development rubrics also found nothing at 0.7 or above.

## Review (2026-09-27)

At the owner's request, the **same AI author** reviewed the bundle. This is not an independent second review. The review had three layers.

**1. Mechanical checks.** The compiler asserts that every quote exists in its article and that every selected row is unique. The bundle has contract v10 and 44 cases per cohort.

**2. Case-by-case reading** of all 132 questions against the source rows and articles. It led to three corrections in the first 102 cases:

- *#033, #058.* The 50% credit-transfer cap has an exception for teacher-training programmes. Most students here are in one, so the gold fact now states the exception.
- *#043.* "Làm thẻ bảo hiểm y tế ở đâu" could ask for the responsible unit or for its location. It now asks "liên hệ đơn vị nào", so the gold has a single reading.
- *#008, #050, #086 (K48-K49 part), #091 (K48-K49 part), #100.* These questions name no programme type (first degree, college or intermediate bridge, second degree). Their gold was changed from the first-degree row to the whole table. The runtime correctly returns every row when no programme type is given, and the planner contract forbids inferring a selector that the question does not state. K51 tables have one row and keep their fact lock.

For the 30 later cases, every assistant turn in a `memory` history was checked against the catalogs so that no history states a false fact. The foreign-language table is K50's; its `applicable_cohorts` validation lets K48-K49 and K51 questions use it.

**3. Reachability.** For each structured gold unit (119 in total, including the four program → faculty relations), a development check built the plan an ideal planner would emit, with literal spans from the question. Follow-ups used the earlier turns as the history. It ran that plan through the real normalizer and dispatcher, with the production embedding model for directory matching. 116 of the 119 units reach their gold. The other three are **known runtime gaps, kept on purpose**, because they are real student phrasings and changing them would fit the benchmark to the system:

| Case | Gap |
|---|---|
| #005 | The score parser does not read "57d" (57 điểm) |
| #016 | Service matching finds no unit for "mượn micro" (the catalog says "Cho mượn amply, micro lớp học") |
| #076 | Service matching asks for clarification on "đóng học phí", because two units mention học phí; the gold is the unit that collects tuition |

Regulation tasks are judged on mode and cohort only. Retrieval quality belongs to a retrieval suite.

## Protocol

1. Run it on the final planner configuration, with caches disabled:

   ```bash
   python -m scripts.run_official_deterministic --bundle official_v3 --contract v10 --current-worktree
   ```

   Only the v10 compile exists, so a run without `--contract v10` stops rather than grading against v9.

2. Report the overall rate and the rate per family with 95% intervals, including operational failures. The three known runtime gaps count as failures unless the runtime has been fixed for reasons found outside this bundle.

3. Do not change the system because of what the run shows. If a v3 failure is ever used to make a fix, later v3 numbers are post-fix regression measurements and must be labelled that way, as happened with official_v2.

4. Gold never changes because of a result.

## Limitations

- One AI author wrote and reviewed the questions and the gold; the owner has not reviewed them.
- The phrasing imitates students; it is not a sample of real traffic.
- Families have 6 to 17 cases, so intervals are wide: a family result shows direction, not a precise rate.

## Corrections

- **2026-09-28, catalog correction (not a result).** The directory catalogs were rebuilt without guessed keyword aliases and without two service records the catalog build had added: "Hỗ trợ kết nối mạng và wifi sinh viên", which no handbook lists, and "Hỗ trợ thủ tục vay vốn tín dụng dành cho sinh viên", which only the K48-K49 handbook mentions, inside Phòng CTCT's combined duty line. Case 132 (wifi, K50) now cites Phòng CNTT's handbook duty "Phụ trách kỹ thuật phòng máy chủ và hệ thống mạng trung tâm" and case 131 (student loans, K48-K49) cites the handbook's duty line; the expected unit, email and phone of both are unchanged. The bundle was recompiled; other cases changed only in their catalog record snapshots. No v3 run had used these catalogs.
