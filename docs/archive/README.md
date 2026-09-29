# Archive

Dated records of experiments, audits and release checks. Each one describes the
system at the date and commit it names, not the current system. Components that
appear here and are no longer used include the Gemini composer, the Cohere
reranker, the local BGE-M3 model and the Qwen/Groq planners. For the current
system, read the [README](../../README.md) and the contracts in [docs/](..).

| Record | Topic |
|---|---|
| [PLANNER_CONTRACT_AUDIT](PLANNER_CONTRACT_AUDIT.md) | Audit of the planner JSON contract at v45 |
| [PLANNER_V44_DEVELOPMENT](PLANNER_V44_DEVELOPMENT.md) … [PLANNER_V49_OPENAI_OFFLINE](PLANNER_V49_OPENAI_OFFLINE.md) | Planner prompt versions v44–v49 |
| [PLANNER_PROMPT_OPENAI_READINESS_20260927](PLANNER_PROMPT_OPENAI_READINESS_20260927.md) | Move of the planner to OpenAI |
| [LUNA_STRICT_SCHEMA_OFFLINE_20260927](LUNA_STRICT_SCHEMA_OFFLINE_20260927.md), [LUNA_V49_MEDIUM_SMOKE_20260927](LUNA_V49_MEDIUM_SMOKE_20260927.md), [LUNA_V49_MEDIUM_STRICT_SMOKE_20260927](LUNA_V49_MEDIUM_STRICT_SMOKE_20260927.md) | gpt-6-luna planner smokes |
| [DEEPSEEK_LOW_OFFLINE_CHECKPOINTS](DEEPSEEK_LOW_OFFLINE_CHECKPOINTS.md), [DEEPSEEK_LOW_V10_SMOKE_20260926](DEEPSEEK_LOW_V10_SMOKE_20260926.md), [DEEPSEEK_V48_NONE_LOW_SMOKE_20260926](DEEPSEEK_V48_NONE_LOW_SMOKE_20260926.md) | DeepSeek as a planner, before the move to OpenAI |
| [COMPOSER_V323_RELEASE_SMOKE](COMPOSER_V323_RELEASE_SMOKE.md) | Composer prompt v3.23 release check |
| [COHERE_FAST_RERANK_EXPERIMENT](COHERE_FAST_RERANK_EXPERIMENT.md) | Why a reranker was added (Cohere, later replaced by Qwen3-Reranker-8B) |
| [ONLINE_PIPELINE_AUDIT_FIXES](ONLINE_PIPELINE_AUDIT_FIXES.md) | Fixes from the online answer-pipeline audit |
| [PARENT_CHILD_RELEASE_AB](PARENT_CHILD_RELEASE_AB.md), [TABLE_SEPARATION_CANDIDATE](TABLE_SEPARATION_CANDIDATE.md), [PARENT_TABLE_COVERAGE_AUDIT](PARENT_TABLE_COVERAGE_AUDIT.md) | Parent/child corpus and table handling |
| [V33_RELEASE_STATUS](V33_RELEASE_STATUS.md) | v33 data release record |
| [checkpoints/](checkpoints/) | Machine-readable checkpoint for the planner v49 record |
