# Evaluation Suite V8

V8 is the frozen, CV-grade benchmark for the current production architecture.
Legacy evaluation files remain development/regression sets and must not be used
as headline results.

## Frozen datasets

- `deterministic_tool_cases.json`: 120 structured/router cases.
- `retrieval_cases.json`: 180 source-selection cases.
- `generated_answer_cases.json`: 100 generation/Judge cases.
- `production_cases.json`: 60 latency and concurrency requests.
- `human_audit_template.json`: 20 manual audits, including 5 repeated scores.
- `manifest.json`: dataset, config, docstore, Git and model provenance.

Do not edit a frozen case after using its failure to tune the system. Create a
new holdout version instead.

## Run order

```powershell
# 1. Local validation and fault tests
.\.venv\Scripts\python.exe scripts\evaluate_system_v8.py --suite validate --profile full
.\.venv\Scripts\python.exe scripts\evaluate_system_v8.py --suite faults --profile full

# 2. Deterministic full suite (no external LLM call)
.\.venv\Scripts\python.exe scripts\evaluate_system_v8.py --suite deterministic --profile full

# 3. Qdrant + Mongo headline retrieval and ablations
.\.venv\Scripts\python.exe scripts\evaluate_system_v8.py --suite retrieval --profile full --backend qdrant --ablation all --resume

# 4. Generate once with Gemini, then Judge from the checkpoint
.\.venv\Scripts\python.exe scripts\evaluate_system_v8.py --suite generate --profile full --resume
.\.venv\Scripts\python.exe scripts\evaluate_system_v8.py --suite judge --profile full --resume

# 5. Start FastAPI with evaluation telemetry and benchmark it
$env:STUDENT_RAG_EVAL_TELEMETRY="1"
$env:STUDENT_RAG_SHOW_DEBUG="1"
.\.venv\Scripts\python.exe scripts\evaluate_system_v8.py --suite production --profile full --base-url http://127.0.0.1:8000
```

Required production credentials are `QDRANT_URL`, `MONGODB_URL`,
`GEMINI_API_KEYS` (or `GEMINI_API_KEY`) and `GROQ_API_KEYS` (or
`GROQ_API_KEY`). The Judge is pinned to `openai/gpt-oss-120b` and never falls
back to another model.

Smoke reports and incomplete human audits are marked `partial_not_for_headline`
or `human_audit_pending`. Only a complete report whose gates pass may be copied
to the main README or a CV.
