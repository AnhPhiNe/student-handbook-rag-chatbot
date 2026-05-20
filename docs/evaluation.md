# Evaluation

Use these checks before changing README or publishing the portfolio version.

## Offline Checks

```bash
python -m compileall src app.py scripts
python -m unittest discover -s tests
```

These commands should not call Gemini.

The same offline checks run in GitHub Actions. They intentionally avoid the
full vectorstore and Gemini path so pull requests can be validated without
secrets or heavyweight generated artifacts.

## Golden Retrieval Evaluation

Golden cases live in:

```bash
data/eval/golden_queries.json
```

Run the retrieval evaluator after the ChromaDB vectorstore has been built:

```bash
python -m scripts.evaluate_retrieval
```

The evaluator writes:

```bash
data/processed/metadata/golden_retrieval_eval_report.json
```

Tracked metrics:

| Metric | Meaning |
|---|---|
| `intent_accuracy` | Router predicts the expected query intent. |
| `strategy_accuracy` | Router selects the expected retrieval strategy. |
| `hit_at_1` / `hit_at_3` / `hit_at_5` | Expected source chunk appears in top K retrieved items. |
| `mrr` | Expected source appears near the top of the ranked list. |
| `lookup_accuracy` | Structured lookup queries hit the expected lookup type. |
| `tool_accuracy` | Calculator-style queries use the expected deterministic tool. |

Use `--fail-under-hit3` when you want the command to fail below a minimum
retrieval threshold:

```bash
python -m scripts.evaluate_retrieval --fail-under-hit3 0.75
```

## Router Behavior Evaluation

Router behavior cases live in:

```bash
data/eval/router_behavior_queries.json
```

This is a larger 100+ query behavioral set covering paraphrases, typo/no-accent
queries, ambiguity probes, out-of-domain probes, multi-hop routing, and negative
regression cases. It is intentionally separate from the smaller source-level
golden retrieval benchmark so source labels do not become self-generated.

```bash
python -m scripts.evaluate_router_behavior --fail-under-intent 0.95 --fail-under-strategy 0.95
```

The evaluator writes:

```bash
data/processed/metadata/router_behavior_eval_report.json
```

## Offline Answer Evaluation

Answer evaluation cases live in:

```bash
data/eval/answer_eval_cases.json
```

This check uses the real retrieval, guardrail, deterministic lookup, and citation
selection code, but injects an offline mock LLM so it does not call Gemini.

```bash
python -m scripts.evaluate_answers --fail-under-pass-rate 1.0
```

The evaluator writes:

```bash
data/processed/metadata/answer_eval_report.json
```

Tracked answer checks include deterministic exactness, expected guardrail
status, citation presence, citation chunk type, citation page, and source-section
formatting.

## Local App Smoke Test

Terminal 1:

```bash
python -m uvicorn src.api.main:app --reload
```

Terminal 2:

```bash
python -m streamlit run app.py --server.fileWatcherType none
```

In Streamlit, verify both Local and API modes with a deterministic lookup style
question before testing Gemini-backed answer generation.

## Optional Pipeline Scripts

These pipeline wrappers exist for local development and portfolio reproducibility:

```bash
python -m scripts.extract_pdf_pages
python -m scripts.parse_structure
python -m scripts.extract_structured_data
python -m scripts.build_chunks
python -m scripts.build_vectorstore
python -m scripts.run_retrieval
python -m scripts.evaluate_retrieval_batch
python -m scripts.run_answer_generation
python -m scripts.evaluate_answer_batch --all
```

Equivalent direct module entrypoints:

```bash
python -m src.ingestion.pdf_loader
python -m src.preprocessing.structure_parser
python -m src.extraction.runner
python -m src.chunking.runner
python -m src.retrieval.vectorstore.runner
python -m src.retrieval.core.runner
python -m src.retrieval.core.retrieval_batch_eval
python -m src.generation.runner
python -m src.generation.answer_batch_eval
```

The preprocessing and retrieval wrappers can rebuild local data and vectorstore
artifacts. Answer-generation wrappers may call Gemini depending on the query and
cache state.
