# Evaluation

Use these checks before changing README or publishing the portfolio version.

## Offline Checks

```bash
python -m compileall src app.py scripts
python -m unittest discover -s tests
```

These commands should not call Gemini.

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

## Optional Phase Scripts

These wrappers exist for local development and portfolio reproducibility:

```bash
python -m scripts.run_phase4
python -m scripts.run_phase5
python -m scripts.run_phase6
python -m scripts.run_phase7
python -m scripts.run_phase7_batch
python -m scripts.run_phase8
python -m scripts.run_phase8_batch --all
```

Phase 6 can rebuild vectorstore data. Phase 8 scripts may call Gemini depending
on the query and cache state.
