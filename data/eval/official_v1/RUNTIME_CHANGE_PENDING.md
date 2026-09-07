# Runtime snapshot refresh required before evaluation

The owner requested changing Composer `llm.request_timeout_seconds` from 60 to 20 seconds in `configs/answer_generation.yaml`. Retry policy and Planner timeout are unchanged. No live API test was requested or run for this change.

The existing `runtime_freeze.json` describes the previous configuration and is retained as historical identity, not overwritten. Before the next evaluation, record the updated runtime/configuration identity and hashes. Do not combine the interrupted five-case deterministic attempt with results under a changed snapshot. Dataset and official metrics remain unfrozen.
