# Online answer-pipeline boundary fixes

Scope: four reproducible findings from the local online-pipeline audit. These
changes do not alter the planner prompt, planner JSON schema, gold datasets,
provider selection or deployment configuration. No inference is required for
the regression tests.

## Queue cleanup on stream close

`chat_stream.event_generator` now removes its queue ticket in an outer `finally`
covering both queued and active phases. Previously, closing at a `queued` yield
could leave an abandoned FIFO head even after active capacity became available.
Active-slot release retains its separate cleanup block.

Tests close the actual route generator while queued and while active, then
verify a following request can acquire capacity. This is a generator lifecycle
regression, not a live ASGI/proxy disconnect certification; that remains a staging
check.

## Empty generation and cache protection

Gemini streaming no longer records provider success when the stream ends without
non-whitespace text. Existing bounded retry rules and the prohibition on retrying
after emitted chunks remain unchanged. Sync generation also rejects whitespace.

Both answer paths check for empty public text after cleanup. Empty output is an
API-error/fallback outcome and is not written to the response cache. Empty cache
entries from an older runtime are treated as misses.

`PIPELINE_VERSION` advances to `v77-online-answer-boundaries`, so old formatted
answers (including nonempty answers cut by the former source-footer regex) are
not reused under the new runtime. Old cache entries are not deleted and expire
according to their existing TTL.

## Source-footer detection

Footer detection is anchored to the start of a line, with support for the
existing plain and Markdown-wrapped source headings. Inline source words,
table cells and quoted body content must not trigger truncation. Streaming
preserves whether its rolling buffer begins at a real line boundary; a buffer
cut must not turn an inline word into a heading. Final tail cleanup does not
repeat heading detection with a lost line boundary.

This remains a conservative formatting heuristic, not semantic source checking.

## Partial coverage across cohorts

The executor decides whether composition is possible using covered task/cohort
units as well as fully covered task summaries. A single task with evidence for
one cohort and missing evidence or clarification for another therefore reaches
the composer. The low-confidence guard accepts that executor decision only with
citations present.

Task-level coverage remains conservative and the existing API schema is
unchanged. The evidence packet still separates source permissions, coverage and
clarification by cohort. Tests verify both the packet and sync/stream execution;
they do not claim a live model will always verbalize the partial answer correctly.

## Regression suite

`tests/test_online_pipeline_regressions.py` contains fake-provider/offline cases
for all four boundaries, including negative formatting cases, empty answers
after cleanup, old empty cache entries, and a rolling-buffer boundary case.
Existing queue timeout, provider retry, stream failure, citation, evidence and
planner tests remain part of the full test suite.

Before production migration, separately check real client disconnects through
the deployment proxy and evaluate the selected DeepSeek reasoning configuration
with an approved inference budget. Passing these offline regressions is not an
accuracy, latency or load-test result for DeepSeek.
