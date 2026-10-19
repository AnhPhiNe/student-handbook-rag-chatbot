# docs/

| Read this | When you want to know |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | How a question flows through planner, normalizer, lookups, retrieval and composer, plus the code map: which function to open first |
| [EXPERIMENTS.md](EXPERIMENTS.md) | The current version of every component, how to switch or swap it, which ablations still need code, and the runs to compare against |
| [EVALUATION.md](EVALUATION.md) | The datasets and suites, how to run them, and the 2026-09-12 hold-out result |
| [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) | Why each component is what it is, with the measurements: one section per component, newest decisions at the end of each |
| [ROUTING_EVIDENCE_RELEASE.md](ROUTING_EVIDENCE_RELEASE.md) | The stage-by-stage log of planner, normalizer and directory changes |
| [STRUCTURED_EXECUTION_CONTRACT.md](STRUCTURED_EXECUTION_CONTRACT.md) | Fact locks and what a structured lookup may and may not state |
| [PARENT_CHILD_BUILD_CONTRACT.md](PARENT_CHILD_BUILD_CONTRACT.md) | How parents, children and reviewed tables are built, validated and published |
| [TECHNICAL_DEBT.md](TECHNICAL_DEBT.md) | Known debt, and code that looks unused but is called dynamically |
| [architecture/](architecture/index.html) | Generated HTML diagrams (2026-09-29; their code links point to an older commit) |

Per-dataset notes live next to the data: `data/eval/<bundle>/README.md`, and
for official_v4 also `SPEC.md` (pre-registrations) and `RESULTS.md`.
Script and config indexes: [scripts/README.md](../scripts/README.md),
[configs/README.md](../configs/README.md).

Dated experiment logs from before 2026-10-19 (`docs/archive/`) were removed
from the tree; they are in git history at commit `635c0e7c`.
