from types import SimpleNamespace

import numpy as np
import pytest

from scripts.ab_table_text_candidate import check_stage_outputs, make_index
from scripts.summarize_table_text_ab import source_metrics


def test_source_metrics_measure_all_required_parents():
    measured = source_metrics(['a', 'b'], ['x', 'a', 'y'])
    assert measured['hit'] == 1
    assert measured['recall'] == 0.5
    assert measured['mrr'] == 0.5
    assert 0 < measured['binary_ndcg'] < 1
    assert source_metrics(['a'], ['x']) == {'hit': 0, 'recall': 0, 'mrr': 0, 'binary_ndcg': 0}


def test_local_index_runs_production_fusion_without_crossing_cohorts(monkeypatch):
    import hashlib
    from qdrant_client import QdrantClient
    from src.retrieval.core.bm25_retriever import BM25Retriever

    original = QdrantClient.__init__
    def local_only(self, location=None, **kwargs):
        assert location == ':memory:'
        original(self, location, **kwargs)
    monkeypatch.setattr(QdrantClient, '__init__', local_only)
    monkeypatch.setenv('STUDENT_RAG_RETRIEVAL_MODE', 'vector_primary_graph_supplement')
    monkeypatch.setenv('STUDENT_RAG_EVAL_RETRIEVAL_MODE', 'vector_primary_graph_supplement')
    monkeypatch.setattr(BM25Retriever, 'build_bm25_index', lambda *args: None)
    monkeypatch.setattr(BM25Retriever, 'sparse_search', lambda *args, **kwargs: [])
    v = np.zeros(1024, dtype=np.float32)
    v[0] = 1
    corpus = [{'chunk_id': c, 'content': c, 'metadata': {
        'parent_section_id': c, 'cohort': c, 'chunk_type': 'regulation', 'content_type': 'regulation_text'}}
        for c in ['K50', 'K51']]
    parents = {c['chunk_id']: {'_id':c['chunk_id'], 'content': 'full parent', 'metadata':c['metadata']} for c in corpus}
    index = make_index(corpus, {hashlib.sha256(c['content'].encode()).hexdigest():v for c in corpus},
                       SimpleNamespace(encode=lambda *a, **kw:v), parents, {})
    try:
        result = index.retrieve('test', cohort='K51', graph_depth=0)
        assert [d['chunk_id'] for d in result] == ['K51']
        assert result[0]['content'] == 'K51'
        assert result[0]['document'] == 'full parent'
        assert result[0]['metadata']['retrieval_telemetry']['ranking_method'] == 'rrf'
        assert not result[0]['metadata']['retrieval_telemetry']['phoranker_used']
    finally:
        index.qdrant_client.close()


def test_empty_ranked_result_has_no_credit():
    assert source_metrics(['required'], [])['recall'] == pytest.approx(0)


@pytest.mark.parametrize('stage,result', [('answers','answers.jsonl'), ('packets','answer_packets.jsonl'), ('retrieval','hybrid_v9_1.json')])
def test_rejected_rerun_preserves_provenance(tmp_path, stage, result):
    identity = tmp_path / f'ab_identity_{stage}.json'
    identity.write_bytes(b'{"original": true}')
    (tmp_path / result).write_bytes(b'original result')
    before = {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError, match='Refusing to overwrite'):
        check_stage_outputs(tmp_path, stage)
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()} == before
