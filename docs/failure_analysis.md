# Failure Analysis

The assistant is designed to fail visibly and conservatively instead of guessing when retrieval, ambiguity handling, backend access, or generation is uncertain.

## Ambiguity

When a query can refer to multiple handbook entities or departments, the system returns a clarification-style response instead of selecting one meaning silently. The UI keeps the clarification context so the user's next message can resolve the intended entity.

Expected response style: ask the user to clarify the target subject, office, faculty, form, or policy area.

## Out Of Domain

When the query is outside the student-handbook domain, the guardrail path avoids pretending that the handbook contains an answer. The response should explain that the assistant is scoped to handbook information.

Expected response style: decline or redirect to questions about handbook rules, forms, offices, procedures, scoring, or student services.

## Low Confidence

When retrieval returns weak or incomplete evidence, the system avoids a definitive answer. If partial citations exist, the UI can still show them for inspection.

Expected response style: say that there is not enough clear information in the handbook and invite a more specific question.

## Backend Unavailable

In API mode, Streamlit calls the FastAPI backend. If the backend is unreachable, times out, returns invalid JSON, or returns an HTTP error, the UI shows a friendly warning instead of a traceback.

Expected response style: tell the user that the API backend cannot be reached and to try again later.

## Gemini/API Error

If the Gemini call fails after retrieval succeeds, the system should not discard useful local evidence. When citations are available, the UI can show that sources were found but answer generation is temporarily unavailable.

Expected response style: explain that relevant handbook information was found, but Gemini could not be called to phrase the final answer.

## Retrieval Miss

When retrieval does not find a matching chunk for an in-domain question, the assistant should avoid inventing policy details.

Expected response style: report that no sufficiently relevant handbook information was found and suggest asking with a more specific keyword, office, form name, or policy topic.

## Notes For Public Demo

- Offline CI covers import/compile health and unit tests, not Gemini quality.
- Golden retrieval evaluation is a small regression set, not a production benchmark.
- Raw data, processed artifacts, cache, and vectorstore policy should be reviewed before public release.
