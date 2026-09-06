"""Summarize saved corpus A/B runs without invoking models or remote services."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ab_table_text_candidate import ROOT, read, write  # noqa: E402


def source_metrics(expected, ranked):
    ranks = [rank for rank, pid in enumerate(ranked[:5], 1) if pid in expected]
    return {'hit': int(bool(ranks)), 'recall': len(ranks) / len(expected),
            'mrr': 1 / min(ranks) if ranks else 0,
            'binary_ndcg': sum(1 / math.log2(r + 1) for r in ranks) /
                sum(1 / math.log2(r + 1) for r in range(1, min(5, len(expected)) + 1))}


def summarize(report):
    from src.common.cohort import is_validated_source_applicable
    units = report['units']
    summary = {'execution_units': len(units), 'dense': {}, 'rrf': {}, 'changes': []}
    for method, field in [('dense', 'dense_parents'), ('rrf', 'parents')]:
        for arm in ['baseline', 'candidate']:
            measures = [source_metrics(u['expected'], u[arm][field]) for u in units]
            summary[method][arm] = {key: sum(m[key] for m in measures) / len(measures)
                                   for key in ['hit', 'recall', 'mrr', 'binary_ndcg']}
            summary[method][arm]['hit_count'] = sum(m['hit'] for m in measures)
        for unit in units:
            a, b = [source_metrics(unit['expected'], unit[arm][field]) for arm in ['baseline', 'candidate']]
            if a != b:
                summary['changes'].append({'id': unit['id'], 'cohort': unit['cohort'], 'method': method,
                    'baseline': a, 'candidate': b, 'expected': unit['expected'],
                    'baseline_parents': unit['baseline'][field], 'candidate_parents': unit['candidate'][field]})
    summary['cohort_leakage'] = {arm: sum(not is_validated_source_applicable(doc, u['cohort'])
        for u in units for doc in u[arm]['documents']) for arm in ['baseline', 'candidate']}
    summary['rrf_recall_losses'] = [c for c in summary['changes'] if c['method'] == 'rrf'
                                   and c['candidate']['recall'] < c['baseline']['recall']]
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-dir', type=Path, required=True)
    directory = parser.parse_args().candidate_dir.resolve()
    if not directory.is_relative_to((ROOT / 'work').resolve()):
        parser.error('Use candidate work directory')
    result = {p.stem: summarize(read(p)) for p in directory.glob('hybrid_*.json')}
    write(directory / 'ab_retrieval_summary.json', result)
    print(json.dumps({k: {a:b for a,b in v.items() if a != 'changes'} for k,v in result.items()}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
