# Data Policy

This project is a portfolio RAG system built around one HCMUE student handbook.
The code, configs, evaluation cases, and generated metadata are project assets.
The source PDF remains owned by its original publisher/source.

## Public Repository Guidance

- This portfolio repository intentionally includes the demo source PDF at
  `data/raw/so-tay-sinh-vien-khoa-48.pdf` for reproducibility.
- The repository does not relicense the source handbook. Ownership remains with
  the original publisher/source.
- The prebuilt ChromaDB vectorstore at `data/vectorstore/chroma` and generated
  processed artifacts may contain text or metadata derived from the source PDF.
- If you reuse the project with another document, review that document's rights
  before publishing the PDF or derived artifacts.

## Local Rebuild

After changing the source PDF, parser, chunking logic, embedding model, or
retrieval config, run:

```bash
python -m scripts.run_all_preprocessing
```

This regenerates extraction metadata, structured data, chunks, vectorstore
artifacts, and retrieval reports from the local source document.
