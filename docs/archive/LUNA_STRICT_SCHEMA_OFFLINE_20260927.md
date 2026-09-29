# Luna medium: strict schema and contact rubric, offline checkpoint

Completed 2026-09-27. This checkpoint adds an opt-in strict-schema configuration
and regrades saved contact probes. It made **zero inference calls**.

## Strict transport contract

`query_plan_strict_response_schema()` in `src/retrieval/core/query_plan.py`
derives eight structured task branches directly from the current lookup registry,
plus RAG and clarification branches. Each structured branch fixes its lookup and
supported intents, declares only that tool's slots, and enforces its enums.
String/number slots also accept homogeneous lists, matching the runtime validator.
Mixed string/number lists are not accepted. Cohort enums and plan fields retain
the shared contract.

OpenAI Responses receives:

```json
{"text":{"format":{"type":"json_schema","name":"query_plan","strict":true,"schema":"<generated schema object>"}}}
```

The actual `schema` value is an object, not the placeholder string above.
The schema uses nested `anyOf`, closes every object with
`additionalProperties=false`, and declares every property as required.
These constraints follow the [official OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

All slot/span keys for the selected tool must be serialized. An unknown optional
slot uses `null`; the native-output prompt explains this convention. The existing
normalizer removes null values only for declared slots before handing them to
the resolver. It retains unknown slot keys so they still trigger validation.
Missing required inputs still result in clarification, and score grounding still
rejects lost scales. No outcome type or downstream adapter was added.

Normalizer identity is now `v31-null-slot-omission`; strict schema identity is v1.
The router cache identity includes the strict schema version. Explicit
`json_object` remains supported for historical configurations. Existing Groq and
DeepSeek response-format payloads retain their provider conventions.

## Opt-in configuration

Use `configs/experiments/ai_router_openai_luna_medium_strict.yaml` for a future
approved trial:

- OpenAI `gpt-6-luna`, reasoning `medium`.
- Strict JSON Schema, explicit output budget 8,192 tokens.
- Timeout 20 seconds per attempt, at most one transient-error retry.
- Router cache disabled; separate key-state/cache paths for this experiment.

Existing Luna JSON-mode configurations, production config, README, official gold
and source catalogs were not modified in this checkpoint. No commit/push occurred.
OpenAI `response_format=auto` now selects strict schema when explicitly using
the OpenAI provider; it does not switch the configured provider to OpenAI.

## Offline verification

- **198 focused tests passed**: provider serialization, incomplete/refused
  responses, schema, contact rubric, planner contract and normalizer behavior.
- **1,191 tests passed** in the full suite; two existing dependency deprecation
  warnings from FastAPI/Starlette.
- The installed OpenAI SDK was exercised through `httpx.MockTransport` for both
  JSON mode and strict schema; no network was used for these request tests.
- Schema tests check closed objects, required properties, supported composition,
  nesting/property/enum limits, every registry slot, arrays, invalid enum values,
  illegal tool/slot combinations, nullable omissions, grounding, and missing inputs.
- A read-only scan of captured raw diagnostic slot/intent projections covered
  **29 structured tasks across the previous 26 cases**. After supplying null
  placeholders for omitted keys, only 093/096 fail the new slot schema because
  `requested_field="địa chỉ"` is invalid. This is a projection compatibility
  check, not replay of full provider responses or execution of old plans.
- Generated compact schema size: **16,061 characters**. This describes the new
  request shape, not measured provider input tokens or latency.

Offline checks do not prove that the live API accepts the schema. A new strict
request can have different input cost and latency. Strict output prevents an
illegal enum when enforced by the provider, but `unit` and `office` are both
legal values; intent interpretation still needs evaluation. Runtime grounding,
cohort checks, resolver/fact-lock checks and incomplete-response handling remain.

## Contact rubric v2: unchanged saved plans

The development authoring file now declares both `contact` and `direct_value`
as accepted intents for `student_service` probes. They are supported by the
registry, share required inputs and use the same lookup dispatch. The grader
checks that declared alternatives have that input contract. Other tools, fields
and cohorts remain constrained. Official benchmark gold is unchanged.

Regrading command, already completed offline:

```powershell
& .\.venv\Scripts\python.exe -X utf8 -m scripts.run_luna_contact_smoke --regrade data/eval/reports/luna_v49_medium_contact_20260927T033717Z/report.json --output data/eval/reports/luna_v49_medium_contact_rubric_v2_offline_20260927
```

The output directory must be new; the script refuses to overwrite an existing
directory. Regrading never initializes a planner.

| Saved probe | Original rubric | Rubric v2 |
| --- | --- | --- |
| service_responsible_unit | fail: intent | pass |
| service_support_unit | fail: intent | pass |
| service_physical_location | fail: extra requested field | fail |
| Remaining five probes | pass | pass |
| Total | **5/8** | **7/8** |

The remaining failure requests `[unit, office]` when only `office` was expected.
No field expectation was widened to make it pass. This rubric grades routing,
not entity resolution, evidence execution or final answers.

New report:
`data/eval/reports/luna_v49_medium_contact_rubric_v2_offline_20260927/report.json`.
It retains original judgments, records source report SHA-256
`44d1909fde79f18a9aceed639f3dffb5da396ef1f0d9f802e3d76594f2f7a247`,
new evaluation hashes and `inference_calls=0`. The original report is unchanged.

The previous 18-case live result remains a historical **15/18** result. No new
strict-schema accuracy, latency or production-readiness result exists yet.

## Next measurable step

Freeze this configuration and evaluate the same 18 execution cases plus eight
contact probes in a separately approved smoke. Use rubric v2 for contact results
and retain the v10 execution contract, so comparisons distinguish the rubric
correction from newly generated plans. Keep the already observed 047 failure and
the remaining field-set failure visible. A full benchmark or production change
is outside this offline checkpoint.
