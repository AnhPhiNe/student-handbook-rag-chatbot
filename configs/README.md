# configs/

## Runtime (packaged into the Space)

| File | Controls |
|---|---|
| `ai_router.yaml` | Planner model, reasoning effort, output budget, key pool, plan cache |
| `answer_generation.yaml` | Composer (`llm`) and directory selector (`directory_selector`): model, provider, reasoning, key pool |
| `retrieval.yaml` | Embedding model, candidate depth (24), parents handed to the composer (5), reranker |
| `structured_lookup_registry.yaml` | Lookup capabilities, slots, value kinds and aliases shown to the planner and checked by the normalizer |
| `hcmue_slang_dictionary.yaml` | Student slang and abbreviation expansion |
| `office_aliases.yaml` | Unit aliases and reviewed contact corrections |
| `handbook_currency.yaml` | Handbook years and notes on replaced regulations |
| `social_replies.yaml` | Fixed replies for greetings, thanks, questions about the assistant and out-of-domain questions |

## Corpus build

| File | Controls |
|---|---|
| `document_sections_k49.yaml`, `_k50`, `_k51` | Section layout of each cohort's handbook (found by name, see `sections_config_path`) |
| `structure_parser.yaml`, `extraction.yaml`, `chunking.yaml`, `structure_chunking.yaml` | Parsing, extraction and chunking settings |
| `layout_fixes.yaml` | Reviewed line groupings the PDF layout breaks |
| `corpus_scope.yaml` | Clauses kept out of the search index (part-time study, college programme, staff only) |
| `program_overrides.yaml` | Reviewed programme lists and programme-to-faculty corrections per cohort |
| `supplementary_documents.yaml`, `image_text.yaml` | Documents and image text added to the corpus by hand |
| `table_search_descriptions.yaml` | Reviewed wording of the table-description search handles |

## Evaluation only

| File | Used for |
|---|---|
| `ai_router_eval_patient.yaml`, `answer_generation_eval_patient.yaml`, `retrieval_eval_patient.yaml` | The same models with longer timeouts and waits, so a suite run is not cut short by rate limits |
| `retrieval_eval_patient_k49.yaml` | The K49 candidate collections (run K49 and later runs) |
| `retrieval_eval_patient_table_search.yaml` | The table-search candidate (run B of table search, 2026-10-04) |
| `retrieval_reranker_4b.yaml` | Qwen3-Reranker-4B instead of Voyage (official_v4 ablation, 2026-09-30) |
| `experiments/answer_deepseek_low.yaml` | Composer with reasoning `low` (composer replay experiments) |

Runs record the configs they used in their `run_snapshot.json`; see
[docs/EXPERIMENTS.md](../docs/EXPERIMENTS.md).
