# Failure Analysis

The assistant is designed to fail visibly and conservatively instead of guessing
when retrieval, ambiguity handling, backend access, or generation is uncertain.

## Ambiguity

When a query can refer to multiple handbook entities or departments, the system
returns a clarification-style response instead of silently selecting one
meaning.

Expected response style: ask the user to clarify the target subject, office,
faculty, form, or policy area.

## Out Of Domain

When the query is outside the student-handbook domain, the guardrail path avoids
pretending that the handbook contains an answer.

Expected response style: decline or redirect to questions about handbook rules,
forms, offices, procedures, scoring, or student services.

## Low Confidence

When retrieval returns weak or incomplete evidence, the system avoids a
definitive answer. If partial citations exist, the UI can still show them for
inspection.

Expected response style: say that there is not enough clear information in the
handbook and invite a more specific question.

## Context Contamination

In multi-turn chat, a new question can accidentally inherit the previous topic.
The context resolver handles this by asking a Groq/Llama model to classify the
current query as `standalone_new_topic`, `follow_up`, or `ambiguous`.

Expected behavior:

- Standalone new topics do not receive old chat history during rewrite.
- High-confidence follow-ups can be rewritten into a full standalone retrieval
  query.
- Ambiguous or low-confidence context decisions ask the user to clarify instead
  of guessing.

For accepted history-based rewrites, the answer pipeline runs dual retrieval on
both the original query and the rewritten query. If the two retrieval paths
conflict without a clear winner, the assistant asks for clarification.

Expected response style: ask whether the user wants to continue the previous
topic or switch to a new one.

## Semantic Drift

Query rewriting can accidentally add a new entity or change the user's intent.
The safe rewrite guard compares content tokens from the original query,
referenced history, and rewritten query before allowing the rewrite to reach
retrieval.

Expected behavior:

- Accent restoration and abbreviation expansion are allowed when meaning is
  preserved.
- New entities that are not grounded in the current query or referenced history
  are rejected.
- Unsafe history rewrites ask the user to restate the question more clearly.

Expected response style: avoid using the unsafe rewrite and ask for a clearer
standalone question.

## Backend Unavailable

The React frontend calls the FastAPI backend. If the backend is unreachable,
times out, returns invalid JSON, or returns an HTTP error, the UI shows a
friendly warning instead of a traceback.

Expected response style: tell the user that the API backend cannot be reached
and to try again later.

## Gemini/API Error

If the Gemini call fails after retrieval succeeds, the system should not discard
useful local evidence. When citations are available, the UI can show that
sources were found but answer generation is temporarily unavailable.

Expected response style: explain that relevant handbook information was found,
but Gemini could not be called to phrase the final answer.

## Retrieval Miss

When retrieval does not find a matching chunk for an in-domain question, the
assistant should avoid inventing policy details.

Expected response style: report that no sufficiently relevant handbook
information was found and suggest asking with a more specific keyword, office,
form name, or policy topic.

## Notes For Public Demo

- Offline CI covers import/compile health, unit/API tests, and router behavior.
- Golden retrieval and answer evaluations are regression sets, not production benchmarks.
- Raw data, processed artifacts, cache, and vectorstore policy should be reviewed before public release.
