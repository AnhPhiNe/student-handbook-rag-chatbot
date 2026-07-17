# Evaluation Suite V8.3 Holdout

V8.3 is the full-system holdout benchmark for the current production architecture.
It separates realistic student questions from stress/adversarial questions and must
not be edited after failures are used to tune the system.

## Counts

- deterministic_tool_cases.json: 120 cases.
- retrieval_cases.json: 180 regulation RAG cases.
- generated_answer_cases.json: 100 answer cases.
- production_cases.json: 60 latency/robustness requests.

## Policy

Use V8.3 once for headline metrics. If failures are used for fixes, create a new
holdout version before publishing new headline numbers.
