# Data Policy

This project is a portfolio RAG system built around one HCMUE student handbook.
The code, configs, evaluation cases, and generated metadata are project assets.
The source PDF remains owned by its original publisher/source.

## Public Repository Guidance

- Do not publish raw PDFs unless redistribution rights are clear.
- Keep `data/raw/README.md` in the repository so users know where to place the
  handbook locally.
- If the PDF cannot be redistributed, remove it from Git tracking before making
  the repository public and document where an authorized user can obtain it.
- Generated processed artifacts may contain extracted text from the source PDF.
  Review them under the same copyright policy before publishing.

## Local Rebuild

After placing the authorized PDF at `data/raw/so-tay-sinh-vien-khoa-48.pdf`, run:

```bash
python -m scripts.run_all_preprocessing
```

This regenerates extraction metadata, structured data, chunks, vectorstore
artifacts, and retrieval reports from the local source document.
