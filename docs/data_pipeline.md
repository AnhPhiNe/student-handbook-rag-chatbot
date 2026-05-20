# Data Pipeline

This project turns a raw student-handbook PDF into retrieval and answer-generation artifacts for the Streamlit and FastAPI apps.

## Flow

```text
data/raw/so-tay-sinh-vien-khoa-48.pdf
  -> PDF/text extraction
  -> structure parsing
  -> table, form, formula, procedure, and directory extraction
  -> semantic and structured chunking
  -> ChromaDB vectorstore embedding
  -> query routing, entity linking, retrieval, and reranking
  -> guarded answer generation or deterministic lookup response
```

## Main Inputs

- `data/raw/so-tay-sinh-vien-khoa-48.pdf`: source handbook PDF used for the portfolio demo.
- `configs/structure_parser.yaml`: structure parsing configuration.
- `configs/extraction.yaml`: extraction configuration.
- `configs/chunking.yaml`: chunking configuration.
- `configs/embedding.yaml`: embedding/vectorstore configuration.
- `configs/retrieval.yaml`: retrieval configuration.
- `configs/query_routing_rules.yaml`: query routing rules.

## Main Outputs

- `data/processed/metadata/pages.json`: extracted page text.
- `data/processed/metadata/structured_sections.json`: parsed handbook structure.
- `data/processed/tables/*.json`: extracted scoring, formula, and threshold tables.
- `data/processed/forms/form_templates.json`: form templates and related metadata.
- `data/processed/procedures/procedures.json`: procedure records.
- `data/processed/directories/*.json`: office, faculty, program, and reference directories.
- `data/processed/chunks/*.json`: semantic, lookup, table, form, procedure, directory, formula, and tool-rule chunks.
- `data/vectorstore/`: local ChromaDB vectorstore generated from the chunks.
- `data/processed/metadata/*_report.json`: pipeline reports and evaluation outputs.

## Rebuild Command

Run the full local preprocessing pipeline only when you intentionally want to regenerate PDF extraction, structure parsing, structured extraction, chunks, embeddings, and retrieval reports:

```bash
python -m scripts.run_all_preprocessing
```

This command runs the preprocessing, extraction, chunking, embedding, and
retrieval-report steps in order, rebuilds the local vectorstore, and can take
several minutes. It should not be part of the lightweight CI path.

Individual pipeline wrappers are also available:

```bash
python -m scripts.extract_pdf_pages
python -m scripts.parse_structure
python -m scripts.extract_structured_data
python -m scripts.build_chunks
python -m scripts.build_vectorstore
python -m scripts.evaluate_retrieval_batch
```

To capture the local package/config/file fingerprint used for a run:

```bash
python -m scripts.write_reproducibility_report
```

The report is written to:

```text
data/processed/metadata/reproducibility_report.json
```
