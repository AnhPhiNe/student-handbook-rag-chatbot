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
