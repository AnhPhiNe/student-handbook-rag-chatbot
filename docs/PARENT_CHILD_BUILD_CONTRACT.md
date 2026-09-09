# Parent/child build and publish contract

## Scope

The official builder separates the two representations of supported handbook
articles. It does not expand ingestion to every appendix, notice, or form.

| Consumer | Artifact | Content |
|---|---|---|
| MongoDB / full-article display | `all_docstore_items.json` | Article prose plus readable, reviewed tables |
| Qdrant embedding | `child_parent_chunks.json` | Narrative children, with reviewed physical table regions removed |
| Structured lookup | `structured_tables_registry.json` | Approved JSON tables; unchanged by separation |
| Build only | `narrative_docstore_items.json` | Intermediate narrative view; never the MongoDB upload input |

Numbers in ordinary policy prose remain. Prose-derived structured records do not
authorize removing their source paragraphs. Directory catalogs stay on their
existing structured path. No table-summary fallback chunks are added.

## Official build order

`scripts.build_multi_cohort` runs:

1. PDF extraction, curated article selection, chunk construction, and cohort merge.
2. Structured table/catalog construction.
3. `scripts.build_parent_child_artifacts --publish-artifacts`: finalize local
   full parents and narrative children together. This flag does **not** upload.
4. Reference graph construction from full parents.
5. Build identity/manifest, table quality audit, and deploy-artifact checks.
6. Remote publication only when `PUSH_REMOTE=1`.

Run from the repository root (this rebuilds local processed artifacts):

```powershell
$env:PUSH_REMOTE = '0'
.\.venv\Scripts\python.exe -X utf8 -m scripts.build_multi_cohort `
  --qdrant-collection student_handbook_semantic_v33_candidate `
  --mongo-collection parent_docs_v33_candidate
```

Collection names above are candidate targets, not evidence of a live deployment.
For isolated source-to-artifact verification, copy scripts, source, configuration,
raw inputs, curated review metadata, `constraints-runtime.txt`, and the independent
amendment registry into a fresh workspace; do not seed parent/child outputs.

The legacy child-only CLI refuses separated input. Rebuilding only children from
full parents would reintroduce display tables and invalidate the audited pair.
Re-run the complete source build instead. The historical candidate command remains
a thin forwarding entry point for existing experiment instructions.

## Review and failure behavior

`data/curated/regulation_table_regions.json` binds every supported registry parent
to a reviewed source hash, exact non-overlapping spans, cohort, document, pages,
and table projection. Changed source text or registry data stops the build and
requires source review; the builder does not guess new boundaries.

Two content-hash-bound page corrections narrow article metadata to its actual
source page (K50 support-funding Article 15: page 152; K51 talent-policy Article
15: page 155). They do not delete content or introduce query-specific routing.

The separation audit binds the complete parent and child content, including
metadata. The manifest incorporates policy/review identity into `build_id` and
records artifact file hashes. Both upload validators verify the complete pair,
registry, and audit before uploading either side. Missing/stale files, mixed
views, wrong source identity, or a missing separation-aware manifest fail closed.
Historical unmarked manifests remain verifiable.

Uploads are not a cross-database transaction. Existing non-overwrite protections
remain: use new versioned collections, verify both stores, then switch runtime
configuration together. If either upload fails, do not promote the partial pair.

## Local verification — 2026-09-06

- A source-to-artifact build in `work/parent_child_clean_build` succeeded without
  seeding existing parent, child, or table artifacts.
- Its build ID matches the separately produced local candidate:
  `build-934f1caf384f99ad96e9`.
- 462 parents, 3,121 children, 35 structured tables, 78 reference edges.
- 23 reviewed physical table regions, 150 display rows, and 12 duplicate generated
  table appendices removed. Two parent page ranges corrected.
- Structured registry and reference graph byte hashes match the current originals.
- Table-quality audit: no boundary, missing-source, invalid-table, or invalid-
  directory errors. Deploy-artifact checks passed.
- Both MongoDB and Qdrant **local pre-upload validators** accepted the clean build.
- Final unit/regression run: **676 passed**. Targeted lint and `git diff --check`
  passed (Git emitted only line-ending conversion warnings).
- Regression tests use a frozen 18-parent source fixture (16 registry parents
  plus two page-correction parents), so rebuilding processed outputs does not
  accidentally turn already-separated data into test inputs.
- A clean-build ordering defect was fixed: the foreign-language artifact is now
  validated after its producing structured-layer step, not before it exists.

No production artifacts or live stores were replaced during this verification.
No Planner, Composer, runtime retrieval, frontend, or published metric was changed.
The earlier retrieval A/B remains documented in `TABLE_SEPARATION_CANDIDATE.md`.
The subsequently authorized final-answer A/B is now complete; results and the
remaining completeness regression are in `PARENT_CHILD_RELEASE_AB.md`. Production
promotion remains a separate decision.

## Final release preparation — 2026-09-06

The repository was rebuilt from source for `student_handbook_semantic_v33` and
`parent_docs_v33`, retaining build ID `build-934f1caf384f99ad96e9` and the same
parent/child/registry hashes as the isolated build. This is a local artifact
state, not a claim that either collection has been uploaded or deployed.

A full rebuild exposed a pre-existing namespace omission: formula references
for K48–K49 lacked the prefix applied by `merge_docstore`. The structured merge
now applies that same idempotent prefix, covered by a synthetic regression test.
The rebuild also emits cohort-qualified program IDs/provenance; all 129
cohort/program identities and their substantive content remain unchanged.

The release-time local test run recorded **683 passed**. The V5/V7 bundle tests
used for that historical check have since been removed from the current branch;
their datasets and results remain recoverable from Git history. Production pair
validation replaces the legacy row-matcher test when the manifest declares
reviewed table separation.

HF packaging accepts explicit expected collection names, defaults to the current
v33 pair, checks both against the packaged manifest, and includes the
manifest-declared table audit. Dry-run package artifact/hash validation passed.
HF environment variables still have to be switched to the verified new pair;
these parameters alone do not change the running Space.

Composer v3.23 smoke results, including the remaining exclusion omission, are
recorded in `COMPOSER_V323_RELEASE_SMOKE.md`.
