# Smoke 15 root-cause audit — `4ce48aaa`

## Scope

This audit is based on the frozen 15-case request-scoped-composer smoke report at
`data/eval/reports/single_cohort_v2/4ce48aaa/smoke15/request_scoped.json`.
It does not use the hidden dataset and does not make live provider calls.

## Source-binding audit

- 18 RAG atomic requests produced answers.
- 16/18 cited at least one currently annotated gold parent section.
- All 18 kept request and cohort isolation.
- The two source-contract failures used directly relevant, request-scoped K51
  sources that are not represented as acceptable alternatives in the current
  gold annotation.

| Case/request | Current gold | Sources used | Retrieval ranks | Finding |
|---|---|---|---|---|
| `dev-single_rag-09/r1` | `K51_QuyCheDaoTao_Chuong4_Dieu16` | `K51_QuyCheCongTacSinhVien_Chuong5_Dieu31`, `K51_QuyCheCongTacSinhVien_Chuong6_Dieu34` | 1, 5 | Điều 31 directly covers voluntary and forced withdrawal; Điều 34 directly covers disciplinary forced withdrawal. The broad query does not uniquely identify Điều 16. |
| `dev-two_regulations-01/r2` | `K51_QuyCheDaoTao_Chuong3_Dieu10` | `K51_QuyCheDaoTao_Chuong2_Dieu9` | 1 | Điều 9 directly specifies registration for already-passed courses to improve grades. Điều 10 specifies grade-result handling. Both are valid aspects of the broad request. |

The failures are therefore classified as **gold source-coverage gaps**, not
retrieval misses, cross-request leakage, or malformed citations. The dev gold
should only be expanded after reviewer approval. No runtime keyword, case ID,
reranker, or source-specific prompt rule is justified by this evidence.

## Latency audit

- Safe TTFT range: about 3.30–25.02 seconds.
- The 25.02-second outlier is `dev-two_regulations-15/r2` (`khiếu nại điểm`).
- Its sibling request completed in about 2.83 seconds; the outlier request took
  about 24.98 seconds and returned six claims.
- No provider failure is recorded, but the old artifact discards per-request
  attempts, key fingerprint, prompt size, and usage.
- Concurrent Gemini calls also wrote usage through one shared `_last_usage`
  field, so aggregate token attribution could race even though answers and
  request-local clients remained isolated.

The old artifact cannot distinguish provider tail latency from a retry, key-pool
wait, or prompt/output-size effect. The follow-up change records non-secret
per-request provider provenance and makes usage request-local without changing
retrieval, prompts, source selection, or answer behavior. Official latency gates
remain the responsibility of the 60-case production/load suite; a 15-case p95 is
only an outlier detector.
