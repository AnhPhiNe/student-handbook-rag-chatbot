# official_v4: an independently authored hold-out

official_v4 measures the whole system, from the student's message to the final
answer, on questions the system was never tuned on and that neither the system's
author nor its models wrote.

## Why a new set

- `official_v3` is no longer a clean hold-out: prompt v53 was written after its
  run. Its 87.1% (2026-09-27) stays the pre-fix planner result.
- `official_v1`, `official_v2` and `official_v3` were all written by Claude, and
  the planner prompt was tuned on v1 and v2. A new set from the same author would
  share their phrasing, so v4 is written by a model from another vendor.
- v3 has only a planner suite; v4 has answer gold from the start.

## Rules

1. **No result from v4 may change the system.** Prompts, catalogs and code are
   tuned on v1, v2 and the development sets only. Any later v4 run after a fix
   is a post-fix measurement and is labelled so.
2. **The draw is frozen before any question exists.** `scripts/draw_v4_tickets.py`
   (seed 20260930) writes `tickets.json`; it refuses to overwrite it without
   `--force`, which is allowed only before authoring starts.
3. **The author does not see the system.** It gets `GEMINI_PROMPT.md`, one batch
   of tickets and the public handbook excerpts in that batch. Never the code,
   prompts, catalog internals, design notes or known failures.
4. **Questions are not edited after authoring.** A case is dropped only for a
   stated reason (a false fact in the draft gold, a ticket marked
   `khong_phu_hop`, a near-duplicate of v1–v3), logged before any run.
5. **Run once**, end to end, on the frozen final system.

## Allocation (246 base tickets + 36 variants)

| Family | Cells | Tickets |
|---|---|---:|
| A. Single request | 9 table or directory lookups × 6 (grade scales, foreign language, study duration, scholarship, formulas, offices, faculties, programmes, student services); regulations: policy 10, procedure 10, consequence or exception 10, open 6 | 90 |
| B. Several requests | table + regulation 18, regulation + regulation 18, table + table 18, three requests 6, four or five requests 6 | 66 |
| C. Comparison | two cohorts on a table 9, two cohorts on a regulation 9, two rows of one table 6 | 24 |
| D. Relation | programme → faculty contact 6, service → unit contact 6 | 12 |
| E. Conversation (two turns, the second is scored) | cohort switch, entity switch, pronoun, topic switch, 6 each | 24 |
| F. Boundary | missing information 6, partly answerable 6, in domain but not in the handbook 8, out of domain 6, mixed 4 | 30 |
| G. Variants | 36 A/B tickets written naturally get one rewrite each: informal, no diacritics or typos, long context (12 each) | 36 |

- **Size.** About 280 cases give an overall 95% interval of about ±4 points
  (v3: ±6 with 132). Families of 24 or more are reported on their own (about
  ±12 points); cells of 6 are descriptive only.
- **Cohorts.** Tickets rotate K48-K49, K50 and K51 within each cell. The six
  foreign-language table tickets are all K50, because only the K50 handbook has
  the certificate equivalence table; a ticket always takes its source's cohort.
- **Styles** over the base tickets, assigned at random: natural 50%, informal
  20%, no diacritics or typos 15%, long context 15%.
- **Variants** are scored with their base case as one cluster, so a pair does not
  count as two independent observations.
- **Over-limit tickets** (four or five requests) accept either answering them or
  asking the student to choose at most three.

## What the draw samples

- **Tables:** a random row of a reviewed table (grade scales, classifications,
  scholarship, study duration, the language table) or a formula; the excerpt is
  the handbook article that prints the table.
- **Directories:** a random office, faculty, programme or student-service record,
  with its contact lines only.
- **Regulations:** a random handbook article, excluding articles that print a
  lookup table, articles under 300 characters, and administrative articles no
  student asks about (scope, entry into force, duties of ministries or units,
  budgeting), matched on the article title.
- **Main campus only:** records and articles naming the branch campus
  (Phân hiệu Long An) are left out.
- **Free tickets:** out-of-domain and not-in-handbook tickets (F) have no source;
  the author invents them.

## Workflow and status

| Step | Who | Status |
|---|---|---|
| Draw tickets and batches | `scripts/draw_v4_tickets.py` | done (246 tickets, 13 batches) |
| Pilot: batch 00 (15 tickets, every family) | external author (Gemini) | pending |
| Check the pilot: facts, style, naturalness | this repo's maintainer | pending |
| Batches 01–12 | external author | pending |
| Variants (G): rewrite 36 authored questions | external author | pending (needs the authored base) |
| Planner gold labels; fact check against the data; overlap check with v1–v3 | maintainer, scripts | pending |
| Owner review of a random sample of about 30 cases | owner | pending |
| Freeze and run once, end to end | | pending |

## Limitations to report

- The author is a language model, not students; the questions are still
  synthetic. A set of real questions collected after the deploy remains the
  test of realism.
- The ticket draw and the planner gold labels are made by the system's
  maintainer. The draw is random with a fixed seed; the labels are checked by
  the owner on a sample.
- The judge (`openai/gpt-oss-120b`) has not been compared with a human rater.
