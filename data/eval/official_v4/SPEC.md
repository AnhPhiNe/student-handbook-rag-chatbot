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

## Allocation (246 tickets)

| Family | Cells | Tickets |
|---|---|---:|
| A. Single request | 9 table or directory lookups × 6 (grade scales, foreign language, study duration, scholarship, formulas, offices, faculties, programmes, student services); regulations: policy 10, procedure 10, consequence or exception 10, open 6 | 90 |
| B. Several requests | table + regulation 18, regulation + regulation 18, table + table 18, three requests 6, four or five requests 6 | 66 |
| C. Comparison | two cohorts on a table 9, two cohorts on a regulation 9, two rows of one table 6 | 24 |
| D. Relation | programme → faculty contact 6, service → unit contact 6 | 12 |
| E. Conversation (two turns, the second is scored) | cohort switch, entity switch, pronoun, topic switch, 6 each | 24 |
| F. Boundary | missing information 6, partly answerable 6, in domain but not in the handbook 8, out of domain 6, mixed 4 | 30 |

- **Size.** 246 cases give an overall 95% interval of about ±4 points at 90%
  (v3: ±6 with 132); clustering widens it a little. Families of 24 or more are reported on their own (about
  ±12 points); cells of 6 are descriptive only.
- **Cohorts.** Tickets rotate K48-K49, K50 and K51 within each cell. The six
  foreign-language table tickets are all K50, because only the K50 handbook has
  the certificate equivalence table; a ticket always takes its source's cohort.
- **Styles** over the base tickets, assigned at random: natural 50%, informal
  20%, no diacritics or typos 15%, long context 15%.
- **Repeated content.** The three cohorts' handbooks share many articles and the
  two formulas, so some tickets ask the same thing. Cases whose required facts
  overlap by 80% or more (word 3-grams) are scored as one cluster, decided from the
  authored gold before any run. This only widens the intervals.
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
  budgeting), matched on the article title. Procedure tickets draw only from
  articles that mention a file, a procedure or a submission; consequence tickets
  only from articles that mention a sanction, a prohibition or an exception.
  When an article still cannot carry the ticket's question kind, the author asks
  something else the article states and records the kind in `ghi_chu`.
- **Main campus only:** records and articles naming the branch campus
  (Phân hiệu Long An) are left out.
- **Free tickets:** out-of-domain and not-in-handbook tickets (F) have no source;
  the author invents them.

## Workflow and status

| Step | Who | Status |
|---|---|---|
| Draw tickets and batches | `scripts/draw_v4_tickets.py` | done (246 tickets, 13 batches) |
| Pilot 1 (15 tickets) | Gemini 3.8 Flash | done, questions discarded (below) |
| Batch 00 (pilot 2, 15 tickets) | Gemini 3.8 Flash | done: 15 of 15 written, all facts found in their excerpts, 1 reclassified (AUTHORING_LOG.md) |
| Check each batch | `scripts/check_v4_authored.py N` | done for 00–06 |
| Batch 01 (30 tickets) | Gemini 3.8 Flash | done: 30 of 30 written, all facts found in their excerpts; 3 consequence tickets asked another kind, as allowed |
| Batch 02 (25 tickets) | Gemini 3.8 Flash | done: 25 of 25 written, all facts found in their excerpts; 5 of 10 procedure tickets asked another kind |
| Batch 03 (28 tickets) | Gemini 3.8 Flash | done: 28 of 28 written; facts in their excerpts, and the three computed scholarship scores recomputed correct |
| Batch 04 (8 tickets) | Gemini 3.8 Flash | done: 8 of 8 written; the computed scores (3,40, 3,60) recomputed correct; the 6- and 8-year maximum durations are the K51 and K50 handbooks' own values |
| Batch 05 (14 tickets) | Gemini 3.8 Flash | done: 14 of 14 written; all facts in their excerpts |
| Batch 06 (14 tickets) | Gemini 3.8 Flash | done: 14 of 14 written; facts in their excerpts, the computed score (3,40) recomputed correct |
| Batches 07–12 | external author | pending |
| Fact check against the data; overlap check with v1–v3; clusters | scripts | pending |
| Owner review of a random sample of about 30 cases | owner | pending |
| Freeze and run once, end to end | | pending |

## Pilot 1 (2026-09-30)

The first draw was tried on 15 tickets. The output is kept in
`pilot/batch_00_gemini_flash.yaml`; its questions are not part of v4, and the
tickets were redrawn with the same seed after the fixes below. No system was run.

- 10 of 15 tickets were written; the author marked 5 as not writable, each with
  a correct reason. 4 asked for a question kind the drawn article could not
  carry (a procedure from an article on using conduct results, a consequence
  from an article on advisers' rights); 1 drew a programme whose record has no
  faculty. Fixes: procedure and consequence tickets draw from matching
  articles, the author may change the question kind and record it, and
  programmes without a faculty are left out.
- The author invented nothing: missing content was reported, not filled in.
- The informal style was followed in 4 of 4 tickets. One table question copied
  the row's whole range ("từ 5,5 đến 6,2"); table tickets now ask for one value
  inside a range.

## Limitations to report

- The author is a language model, not students; the questions are still
  synthetic. A set of real questions collected after the deploy remains the
  test of realism.
- The ticket draw is made by the system's maintainer, at random with a fixed
  seed.
- v4 measures the final answer, not the planner on its own: planner labels
  were dropped to keep the set small (2026-09-30). Failed cases are traced to
  the planner, retrieval or the composer after the run. The planner's own
  hold-out figure remains v3's 87.1% before the fix.
- Robustness to rewording is seen only through the mix of writing styles; the
  36 paired variants in the first design were dropped with the planner labels.
  The `variant_style` field in `tickets.json` is left from the draw and unused.
- Some drawn articles give questions few students would ask (staff conduct, a
  unit's internal duties, the legal basis of a notice); they stay in the set,
  and the owner's review can mark them.
- Procedure and consequence tickets often fell back to another question kind
  when the article had none; results are reported by the kind actually asked.
- The judge (`openai/gpt-oss-120b`) has not been compared with a human rater.
