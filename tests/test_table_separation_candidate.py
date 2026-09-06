import copy
import json
import re
from pathlib import Path

import pytest

from scripts.build_table_separation_candidate import POLICY, digest, separate_tables, text_hash, verify_mongo_parents
from tests.test_table_text_candidate import fixtures


def fixture():
    parent, table, raw = fixtures()
    a = parent['content'].index(raw)
    review = {'policy': POLICY, 'registry_sha256': digest([table]), 'parents': [{
        'parent_id': 'p1', 'content_sha256': text_hash(parent['content']), 'review_status': 'source_checked',
        'cohort': 'K51', 'document_id': 'handbook', 'registry_dispositions': {'duration': 'physical_source_table'},
        'regions': [{'start': a, 'end': a+len(raw), 'source_text': raw, 'kind': 'physical_table', 'source_pages': [3],
                     'table': {'columns':table['columns'], 'keys':table['columns'], 'registry_ids':['duration']}}]}]}
    return [parent], [table], review, raw


def test_full_parent_keeps_table_children_do_not_and_inputs_immutable():
    parents, tables, review, raw = fixture()
    before = copy.deepcopy((parents, tables, review))
    full, narrative, children, audit = separate_tables(parents, tables, review)
    assert (parents, tables, review) == before
    assert '| Liên thông | 2 năm | 4 năm |' in full[0]['content']
    assert raw not in full[0]['content']
    assert 'Liên thông' not in narrative[0]['content']
    assert not any('Liên thông' in c['content'] for c in children)
    assert all('registry_table' != c['metadata'].get('block_type') for c in children)
    for text in (full[0]['content'], narrative[0]['content']):
        assert 'Chỉ áp dụng chính quy' in text
        assert 'Sinh viên nộp đơn theo quy định' in text
    assert audit['parent_table_rows'] == 2


@pytest.mark.parametrize('mutation', ['parent', 'registry', 'cohort', 'pages', 'overlap', 'span', 'review', 'disposition'])
def test_stale_or_unsafe_source_edits_fail_closed(mutation):
    parents, tables, review, _ = fixture()
    entry = review['parents'][0]
    if mutation == 'parent':
        parents[0]['content'] += ' policy edit'
    elif mutation == 'registry':
        tables[0]['rows'][0]['Chuẩn'] = '5 năm'
    elif mutation == 'cohort':
        entry['cohort'] = 'K50'
    elif mutation == 'pages':
        entry['regions'][0]['source_pages'] = [999]
    elif mutation == 'overlap':
        entry['regions'].append(copy.deepcopy(entry['regions'][0]))
    elif mutation == 'span':
        entry['regions'][0]['source_text'] += ' different'
    elif mutation == 'review':
        entry['review_status'] = 'pending'
    elif mutation == 'disposition':
        entry['regions'] = []
    with pytest.raises(ValueError):
        separate_tables(parents, tables, review)


def test_prose_derived_record_does_not_authorize_deleting_policy_numbers():
    parents, tables, review, _ = fixture()
    parents[0]['content'] = 'Điều 3. Chính sách\n1. Sinh viên phải tích lũy 15 tín chỉ.'
    entry = review['parents'][0]
    entry.update(content_sha256=text_hash(parents[0]['content']), regions=[],
                 registry_dispositions={'duration': 'prose_derived_keep_original_policy'})
    full, narrative, children, _ = separate_tables(parents, tables, review)
    assert full[0]['content'] == narrative[0]['content'] == parents[0]['content']
    assert any('15 tín chỉ' in c['content'] for c in children)


def test_mongo_verification_reads_only_and_reports_missing_parent(monkeypatch):
    from types import SimpleNamespace
    from src.retrieval.vectorstore import mongo_store
    parents, _, review, _ = fixture()
    calls = []
    store = SimpleNamespace(collection=SimpleNamespace(name='test_parents'),
                            client=SimpleNamespace(close=lambda: calls.append('close')),
                            get_document_by_id=lambda pid: calls.append(pid))
    monkeypatch.setattr(mongo_store, 'get_mongo_store', lambda: store)
    audit = verify_mongo_parents(parents, review)
    assert calls == ['p1', 'close']
    assert audit['matched'] == 0
    assert audit['checked'] == 1
    assert audit['read_only']


def test_numeric_conduct_lookup_still_uses_unchanged_structured_json():
    from src.retrieval.core.structured_dispatcher import resolve_structured_decision
    def read(path):
        return json.loads(Path(path).read_text(encoding='utf-8'))
    result = resolve_structured_decision(
        {'lookup_type':'scoring', 'intent':'direct_value',
         'slots':{'operation':'conduct_classification', 'score_or_grade':'82'},
         'slot_spans':{'score_or_grade':'82'}},
        query='K50 được 82 điểm rèn luyện thì xếp loại gì?', cohort='K50',
        scoring_tables=read('data/processed/tables/scoring_tables.json'), formula_rules=[],
        office_directory=[], student_service_directory=[], student_faculty_profiles=[],
        foreign_language_tables=[], program_directory=[],
        structured_tables_registry=read('data/processed/tables/structured_tables_registry.json'))
    assert result is not None
    resolved = result.result['resolved_result']
    assert resolved['input_value'] == 82
    assert 'Tốt' in json.dumps(resolved, ensure_ascii=False)


def test_reviewed_source_snapshot_preserves_gaps_and_binds_all_tables():
    def read(path):
        return json.loads(Path(path).read_text(encoding='utf-8'))
    parents = read('tests/fixtures/reviewed_parent_source_snapshot.json')
    tables = read('data/processed/tables/structured_tables_registry.json')
    review = read('data/curated/regulation_table_regions.json')
    full, narrative, children, audit = separate_tables(parents, tables, review)
    full_map, narrative_map = ({p['_id']:p for p in values} for values in (full,narrative))
    original = {p['_id']:p for p in parents}
    assert audit['physical_tables'] == 23
    assert audit['parent_table_rows'] == 150
    assert audit['table_embedding_chunks_added'] == 0
    assert len(full) == len(parents)
    for entry in review['parents']:
        pid = entry['parent_id']
        source = original[pid]['content']
        cursor = 0
        for region in entry['regions']:
            gap = source[cursor:region['start']]
            assert gap in full_map[pid]['content']
            assert gap in narrative_map[pid]['content']
            if region['kind'] == 'physical_table':
                assert re.sub(r'\s+', '', region['source_text']) not in re.sub(r'\s+', '', narrative_map[pid]['content'])
            cursor = region['end']
        assert source[cursor:] in full_map[pid]['content']
        assert source[cursor:] in narrative_map[pid]['content']
    touched = {e['parent_id'] for e in review['parents']}
    for parent in parents:
        if parent['_id'] not in touched:
            assert full_map[parent['_id']]['content'] == parent['content']
    k51 = 'K51_QuyCheDaoTao_Chuong1_Dieu3'
    assert '| Chính quy | 04 năm học | 06 năm học |' in full_map[k51]['content']
    assert '| Đào tạo đại học cấp bằng thứ nhất | 04 năm học | 08 năm học |' in full_map[k51]['content']
    assert 'áp dụng từ khoá tuyển sinh năm 2025' in narrative_map[k51]['content']
    assert 'khối lượng được miễn trừ' in re.sub(r'\s+', ' ', narrative_map[k51]['content'])
    foreign = 'K50_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu8'
    assert '| Tiếng Anh | TOEFL ITP | 450 - 499 |  |' in full_map[foreign]['content']
    assert 'input_requirements' not in full_map[foreign]['content']
    assert 'Ghi chú: Đối với một số chứng chỉ' in narrative_map[foreign]['content']
