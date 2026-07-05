# Testing Guide

## Run offline evaluations

```bash
python scripts/evaluate_answers.py
python scripts/evaluate_retrieval.py
python scripts/evaluate_router_behavior.py
```

## Production Smoke Test Checklist

Before public beta, test these flows on the deployed UI:

- Switch between K48-K49 and K50-K51.
- Ask school-wide and faculty-specific program questions.
- Ask pass/fail threshold questions, especially D and D+ for K50-K51.
- Ask about grade appeal, dormitory, temporary leave, scholarship, and re-study.
- Ask office contact questions such as tuition, training, and student affairs.
- Expand citations and verify source metadata.
- Try ambiguous and out-of-domain questions.
