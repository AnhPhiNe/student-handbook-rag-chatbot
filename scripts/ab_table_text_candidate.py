"""Isolated corpus A/B: local Qdrant, production RRF/parent grouping and Composer.

Only the baseline vector download reads the remote Qdrant collection. All index
writes are to Qdrant :memory:. Planner is fixed to RAG for this corpus ablation.
Results are diagnostics, not a new end-to-end benchmark or deployment command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_index(corpus, vectors, model, parents, config):
    from qdrant_client import QdrantClient, models
    from src.retrieval.core.bm25_retriever import BM25Retriever
    from src.retrieval.core.graph_traverser import NetworkXGraphTraverser
    from src.retrieval.core.hybrid_pipeline import ChildParentHybridRetriever

    client = QdrantClient(":memory:")
    client.create_collection("ab_local", vectors_config=models.VectorParams(size=1024, distance=models.Distance.COSINE))
    for start in range(0, len(corpus), 128):
        client.upsert("ab_local", points=[models.PointStruct(
            id=i, vector=vectors[hashlib.sha256(c["content"].encode()).hexdigest()].tolist(),
            payload={**c["metadata"], "chunk_id": c["chunk_id"], "content": c["content"]},
        ) for i, c in enumerate(corpus[start:start + 128], start)])
    # Bypass only network/bootstrap. Every retrieval algorithm method is unmodified.
    retriever = ChildParentHybridRetriever.__new__(ChildParentHybridRetriever)
    retriever.qdrant_client, retriever.collection_name = client, "ab_local"
    retriever.runtime_config, retriever.embed_model = config, model
    retriever.normalize_embeddings, retriever.reranker = True, None
    retriever.graph = NetworkXGraphTraverser()
    retriever.parent_cache, retriever.parent_cache_max_entries = OrderedDict(), 2048
    retriever.mongo_store = SimpleNamespace(get_document_by_id=lambda key: parents.get(key))
    retriever.ab_parent_snapshot = parents
    retriever.bm25 = BM25Retriever()
    retriever.bm25.build_bm25_index(corpus)
    return retriever


def prepare_vectors(directory, corpora, model):
    import numpy as np
    from qdrant_client import QdrantClient
    from src.common.storage_config import require_qdrant_collection_name

    cache = directory / "vectors.npz"
    if cache.exists():
        with np.load(cache) as stored:
            vectors = {key: stored[key] for key in stored.files}
    else:
        vectors = {}
        remote = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ.get("QDRANT_API_KEY"), timeout=60)
        expected = {c["chunk_id"]: c["content"] for c in corpora[0]}
        offset = None
        verified = 0
        while True:
            points, offset = remote.scroll(require_qdrant_collection_name(), limit=256,
                                           offset=offset, with_payload=True, with_vectors=True)
            for point in points:
                payload = point.payload or {}
                content = payload.get("content")
                if expected.get(payload.get("chunk_id")) != content or content is None:
                    continue
                vector = np.asarray(point.vector, dtype=np.float32)
                if vector.shape != (1024,):
                    raise ValueError("Remote embedding dimension mismatch")
                vectors[hashlib.sha256(content.encode()).hexdigest()] = vector
                verified += 1
            if offset is None:
                break
        remote.close()
        if verified != len(expected):
            raise ValueError(f"Live corpus differs from baseline: {verified}/{len(expected)} exact content matches")
        # Confirm local model agrees with downloaded vectors before mixing them.
        sample = corpora[0][:3]
        checks = model.encode([c["content"] for c in sample], normalize_embeddings=True)
        similarities = [float(np.dot(v, vectors[hashlib.sha256(c['content'].encode()).hexdigest()]))
                        for c, v in zip(sample, checks)]
        if min(similarities) < 0.999:
            raise ValueError(f"Embedding identity check failed: {similarities}")
        write(directory / "vector_identity.json", {"exact_live_matches": verified, "sample_cosines": similarities,
              "collection": require_qdrant_collection_name(), "sample_chunk_ids": [c['chunk_id'] for c in sample]})
    missing = {hashlib.sha256(c['content'].encode()).hexdigest(): c['content']
               for corpus in corpora for c in corpus if hashlib.sha256(c['content'].encode()).hexdigest() not in vectors}
    print(f"Embedding {len(missing)} new contents; reusing {len(vectors)} exact-content vectors", flush=True)
    for key, content in missing.items():
        vectors[key] = model.encode(content, normalize_embeddings=True)
    np.savez_compressed(cache, **vectors)
    return vectors


def retrieval(directory, indexes, cases, name):
    from src.retrieval.core.hybrid_pipeline import _regulation_query_filter
    output = directory / f"hybrid_{name}.json"
    if output.exists():
        raise ValueError(f"Do not overwrite {output}")
    units = []
    for case in cases:
        targets = [t for t in case["relevance_judgments"] if t.get("grade", 0) >= 2]
        for cohort in sorted({t['cohort'] for t in targets}):
            unit = {"id": case["id"], "query": case["query"], "cohort": cohort,
                    "expected": [t['parent_section_id'] for t in targets if t['cohort'] == cohort]}
            for label, index in zip(("baseline", "candidate"), indexes):
                docs = index.retrieve(case['query'], cohort=cohort)
                dense = index.qdrant_client.query_points("ab_local", query=index.embed_model.encode(case['query'], normalize_embeddings=True).tolist(),
                    query_filter=_regulation_query_filter(cohort), limit=24).points
                unit[label] = {"parents": [d['chunk_id'] for d in docs], "documents": docs,
                    "dense_parents": list(dict.fromkeys(p.payload['parent_section_id'] for p in dense))[:5]}
            units.append(unit)
        print(f"{name}: {len(units)} units", flush=True)
    write(output, {"method": "Local exact cosine Qdrant + unmodified production RRF/grouping/graph; original query, gold cohort; no Planner/reranker", "units": units})


def answers(directory, indexes, cases, *, generate=True):
    import copy
    from src.generation.answer_pipeline import AnswerPipeline
    from src.retrieval.core import hybrid_pipeline
    from src.generation import answer_pipeline
    from src.common.usage_tracker import UsageTracker
    from src.generation.response_cache import ResponseCache
    from datetime import datetime, timezone

    output = directory / ("answers.jsonl" if generate else "answer_packets.jsonl")
    if output.exists():
        raise ValueError("Answer output exists; do not rerun for a better score")
    # No Redis probe or local production-cache access is needed in this ablation.
    disabled_cache = ResponseCache(enabled=False)
    with patch.object(answer_pipeline, 'get_response_cache', return_value=disabled_cache):
        pipeline = AnswerPipeline()
    pipeline.llm_config.setdefault('key_pool', {})['state_path'] = str(directory / 'gemini_key_state.json')
    for case_index, case in enumerate(cases):
        cohort = case['relevance_judgments'][0]['cohort']
        questions = case['query'].split('Thứ hai:')
        plan = {"schema_version": "1.0", "context_mode": "standalone", "normalized_query": case['query'],
                "standalone_query": case['query'], "referenced_turns": [], "out_of_domain": False,
                "tasks": [{"id": f"t{i+1}", "question": q.strip(), "mode": "rag", "cohorts": [cohort], "intent": "open_question"}
                          for i, q in enumerate(questions)]}
        # Alternate arm order to avoid a systematic provider/time ordering effect.
        for arm in ([0, 1] if case_index % 2 == 0 else [1, 0]):
            label = ('baseline', 'candidate')[arm]
            pipeline.parent_sources_by_id = indexes[arm].ab_parent_snapshot
            router = SimpleNamespace(plan=lambda *a, **kw: copy.deepcopy(plan))
            with patch.object(pipeline, '_get_router', return_value=router), \
                 patch.object(hybrid_pipeline, 'initialize_hybrid_retriever', return_value=indexes[arm]), \
                 patch.object(answer_pipeline, 'run_hybrid_retrieval_pipeline', hybrid_pipeline.run_hybrid_retrieval_pipeline):
                pipeline.router = router
                if generate:
                    result = pipeline.answer(case['query'], cohort=cohort)
                else:
                    prepared = pipeline.prepare_answer(case['query'], cohort=cohort, chat_history=None,
                        tracker=UsageTracker(), router_started_at=datetime.now(timezone.utc).isoformat())
                    result = {"status": prepared.terminal_status or "ready_for_composer",
                              "prompt": prepared.prompt, "context_used": prepared.context_used,
                              "citations": prepared.selected_citations, "terminal_answer": prepared.terminal_answer}
            with output.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({"id": case['id'], "arm": label, "fixed_plan": plan, "result": result}, ensure_ascii=False, default=str) + '\n')
            print(f"answer {case['id']} {label}: {result.get('status')}", flush=True)


def check_stage_outputs(directory, stage):
    """Refuse reruns before changing provenance or any cached run artifacts."""
    names = [f'ab_identity_{stage}.json']
    if stage == 'retrieval':
        names += ['hybrid_diagnostics.json', 'hybrid_v9_1.json']
    else:
        names += ['answers.jsonl' if stage == 'answers' else 'answer_packets.jsonl']
    existing = [name for name in names if (directory / name).exists()]
    if existing:
        raise ValueError(f'Refusing to overwrite existing stage artifacts: {existing}')


def main():
    import numpy as np
    from src.common.env_loader import load_project_env
    from src.retrieval.runtime_config import load_retrieval_runtime_config, load_retrieval_build_contract
    from src.retrieval.core.vector_retriever import load_embedding_model
    load_project_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-dir', type=Path, required=True)
    parser.add_argument('--stage', choices=['retrieval', 'answers', 'packets'], required=True)
    args = parser.parse_args()
    directory = args.candidate_dir.resolve()
    if not directory.is_relative_to((ROOT / 'work').resolve()) or not (directory / 'audit.json').is_file():
        parser.error('Use an existing isolated candidate build under work/')
    check_stage_outputs(directory, args.stage)
    os.environ['STUDENT_RAG_RETRIEVAL_MODE'] = 'vector_primary_graph_supplement'
    os.environ['STUDENT_RAG_EVAL_RETRIEVAL_MODE'] = 'vector_primary_graph_supplement'
    os.environ['STUDENT_RAG_OFFLINE_EVAL'] = '1'
    config = load_retrieval_runtime_config()
    contract = load_retrieval_build_contract()
    paths = [ROOT / 'data/processed/chunks/child_parent_chunks.json', directory / 'child_parent_chunks.json']
    corpora = [read(p) for p in paths]
    parent_paths = [ROOT / 'data/processed/chunks/all_docstore_items.json']
    candidate_parents = directory / 'all_docstore_items.json'
    parent_paths.append(candidate_parents if candidate_parents.exists() else parent_paths[0])
    parent_maps = [{p['_id']: p for p in read(path)} for path in parent_paths]
    model = load_embedding_model(config['embedding']['model_name'])
    vectors = prepare_vectors(directory, corpora, model)
    class QueryCache:
        def __init__(self):
            self.cache = {}
        def encode(self, query, **kwargs):
            if query not in self.cache:
                self.cache[query] = np.asarray(model.encode(query, **kwargs))
            return self.cache[query]
    query_cache = QueryCache()
    indexes = [make_index(c, vectors, query_cache, parents, config) for c, parents in zip(corpora, parent_maps)]
    identity = {"runtime_contract": contract, "corpus_hashes": [sha(p) for p in paths],
                "candidate_only": True, "production_writes": False,
                "parent_hashes": [sha(p) for p in parent_paths],
                "harness_sha256": sha(__file__),
                "runtime_sha256": {str(p): sha(ROOT / p) for p in [
                    'src/retrieval/core/hybrid_pipeline.py', 'src/generation/answer_pipeline.py',
                    'src/generation/prompt_builder.py', 'configs/answer_generation.yaml']},
                "case_sha256": {str(p): sha(ROOT / p) for p in [
                    'data/eval/official_v1/retrieval_cases.json',
                    'tests/fixtures/table_text_candidate_queries.json',
                    'tests/fixtures/table_text_source_review_queries.json']}}
    write(directory / f'ab_identity_{args.stage}.json', identity)
    diagnostics = read(ROOT / 'tests/fixtures/table_text_candidate_queries.json')
    if args.stage == 'retrieval':
        retrieval(directory, indexes, diagnostics, 'diagnostics')
        retrieval(directory, indexes, read(ROOT / 'data/eval/official_v1/retrieval_cases.json'), 'official_v1')
    else:
        review_cases = read(ROOT / 'tests/fixtures/table_text_source_review_queries.json')
        if not (directory / 'hybrid_source_review.json').exists():
            retrieval(directory, indexes, review_cases, 'source_review')
        answers(directory, indexes, diagnostics + review_cases, generate=args.stage == 'answers')
    for index in indexes:
        index.qdrant_client.close()


if __name__ == '__main__':
    main()
