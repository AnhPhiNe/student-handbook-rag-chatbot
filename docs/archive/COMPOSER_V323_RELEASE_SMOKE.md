# Composer v3.23 release smoke

Date: 2026-09-06. This is a six-case diagnostic, not a new benchmark or a
replacement for the final evaluation suites. Expectations and evidence packets
were prepared before generation. Each case ran once, without response cache.

- Prompt: `v3.23-material-exceptions`.
- Model: `gemini-3.1-flash-lite`, configured generation settings.
- Fixed RAG task and supplied candidate-parent evidence: no Planner or retrieval
  calls, no writes to remote stores, no sync/stream transport measurement.
- Prepared packets SHA-256:
  `e7ce13da87122026878b3c7f1cd9d1a61f4fa5be11ca166a71ec121edc4de8fe`.
- Answers SHA-256:
  `909f4ff3782cd9b81e60f373aaea0cdca24dc7d0c525268df7c1f03875a95ca0`.
- Archived under `data/eval/release_v33_smoke/` (no API keys or chat history).

## Agent review (not independent human review)

| Case | Finding |
|---|---|
| Scholarship conditions, K51 | Incomplete: omits exclusion of bridging students, explicitly present in supplied Article 26. Other main conditions and credit exceptions retained. |
| Personal leave conditions, K51 | Main eligibility, expulsion/discipline exclusion, procedure and deadline retained. |
| Conduct score 82 with current reprimand, K50 | Correctly applies Khá cap despite normal Tốt score band. |
| Highest versus latest retake score, K51 | Correct K51 highest-score rule; also states earlier-cohort rule, more scope than needed. No conversion-table dump. |
| TOEIC four-skills level-4 speaking, K50 | Correct narrow range 160–179; no unrelated certificate inventory. |
| Personal leave application deadline, K51 | Correct two-week deadline with relevant late-submission consequence. |

All six API calls succeeded. Five cases satisfy their main requested answer
criterion; one remains incomplete. This small smoke does **not** establish an
accuracy estimate or prove the exception-coverage issue fixed. The prompt was not
changed and these cases were not rerun after observing the result.

The known omission is carried forward for final evaluation and release reporting,
not patched with a scholarship-specific rule. Production promotion and full
evaluation results must be reported separately.
