"""Local files the API reads at runtime.

Shared by the /health/artifacts endpoint and scripts/check_deploy_artifacts.py so
the two checks cannot drift apart. The retrieval config is not listed because its
path can be overridden with STUDENT_RAG_RETRIEVAL_CONFIG; callers add it.
"""

RUNTIME_FILES = (
    "configs/ai_router.yaml",
    "configs/answer_generation.yaml",
    "configs/hcmue_slang_dictionary.yaml",
    "configs/structured_lookup_registry.yaml",
    "configs/office_aliases.yaml",
    "data/processed/tables/formula_rules.json",
    "data/processed/tables/structured_tables_registry.json",
    "data/processed/directories/student_service_directory.json",
    "data/processed/directories/student_office_profiles.json",
    "data/processed/directories/student_faculty_profiles.json",
    "data/processed/directories/program_directory.json",
    "data/processed/graphs/document_edges.json",
    "data/processed/amendments/amendments.json",
    "data/processed/chunks/all_docstore_items.json",
    "data/processed/chunks/child_parent_chunks.json",
    "data/processed/metadata/build_manifest.json",
)
