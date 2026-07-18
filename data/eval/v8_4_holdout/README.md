# Evaluation Suite V8.4 Holdout

V8.4 is a cleaned holdout derived after auditing V8.3 retrieval failures.
It does not mutate V8.3. Cases that were not valid pure regulation retrieval
targets were replaced with source-anchored production-valid regulation cases.

## Counts

- deterministic_tool_cases.json: 120 cases.
- retrieval_cases.json: 180 regulation RAG cases.
- generated_answer_cases.json: 100 answer cases:
  66 retrieval-linked regulation, 20 independent regulation, 4 structured/mixed,
  and 10 unanswerable.
- production_cases.json: 60 latency/robustness requests.

## Policy

Use V8.4 for the next headline run. Retrieval and deterministic sets are kept
fixed after passing gates. The answer set mixes retrieval-linked and independent
cases before any full judge run. If V8.4 failures are used to tune the system,
create V8.5 before publishing new headline numbers.
