# Ingestion & Deployment Scripts

## Build multi-cohort artifacts

```bash
python scripts/build_multi_cohort.py
```

## Push local Chroma vectors to a new Qdrant collection

```bash
python scripts/migrate_to_qdrant.py --target-collection student_handbook_semantic_v4
```

## Deploy backend to Hugging Face Space

```bash
deploy_hf.bat
```
