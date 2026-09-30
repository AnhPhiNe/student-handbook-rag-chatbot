# Authoring log

Every decision about an authored case, made before any system run (SPEC.md,
rule 4). Questions are never edited; a case is dropped or reclassified here,
with its reason.

| Case | Batch | Decision | Reason |
|---|---|---|---|
| V4-166 | 00 | Reclassified from `C.cohorts_regulation` to `B.cross_cohort` (kept) | The K51 excerpt had no procedure, so the author asked a different question for each cohort; the case is a valid two-request question but not a comparison. From batch 01 the prompt says both requests of a comparison change together |
| Batch 01 | 01 | Kept as saved; the checker drops the `[cite: 2]` marks | Gemini adds these marks when the batch is attached as a file; they are not part of the text |
| V4-078, V4-079 | 01, 02 | Kept; scored as one cluster | The same article (Quy chế công tác sinh viên, Điều 32) in two cohorts' handbooks gave the same question twice |
| V4-086, V4-087 | 02 | Kept; scored as one cluster | The same article (Quy định ngoại trú, Điều 10) in two cohorts' handbooks gave the same question twice |
| V4-104, V4-200 | 07, 10 | Kept | They ask about K51 faculty records of the Gia Lai branch, which the branch filter missed (it matched "phân hiệu" and "Long An"). The K51 handbook lists these units with the main-campus faculties, the system's directory holds them, and the gold follows the handbook |
| V4-142 | 08 | Kept; expected behaviour taken as answer plus refusal | It asks for the phone of "Tổ Khoa học cơ bản", a Long An branch unit the filter missed (email longan.khcb@…); the record has no phone, so the author answered the other request and said the handbook gives none, which is the right behaviour |
| V4-154 | 04 | Kept; reported with the API limit | At 1,616 characters it is over the 1,000-character question limit, so the deployed API would refuse it; the evaluation runs the pipeline directly and scores it, and the report says so |
| V4-104 | 07 | Kept; gold widened (`gold_adjustments.yaml`) | K51 lists two branch faculties with nearly the same name, Long An "Khoa Khoa học – Tự nhiên" and Gia Lai "Khoa Khoa học Tự nhiên"; the question names neither, so the Long An address, both, or asking which branch also count |
| V4-172 | 09 | Kept; gold widened | The gold gives the staff dress rule (Điều 4, viên chức, người lao động) as the students' rule; the students' rule is Điều 12 of the same document. Either article counts for the dress part; the no-smoking rule stays required |
| V4-211 | 11 | Kept; required facts narrowed | The question asks only about using public property for private work; the other two parts of the clause are no longer required |
| V4-229 to V4-236 | 00, 12 | Kept; scoring rule added | The suggested channel in a refusal may be any relevant official one, not only the gold's |
| All 246 | all | Gold review done 2026-09-30 | Read by the system author with Claude against each case's excerpts and, where needed, the whole handbook: cohort values (K51 durations after amendment 4743, K51 grade scales), same-or-different claims in the 24 cohort cases, computed values, and the refusal cases' claim that the handbook lacks the information. Not an independent human review |
