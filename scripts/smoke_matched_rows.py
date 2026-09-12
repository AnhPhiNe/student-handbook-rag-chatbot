"""Small live scoring smoke; saves actual prepared evidence for manual review."""
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.common.env_loader import load_project_env


def main():
    load_project_env()
    os.environ['STUDENT_RAG_QUALITY_EVAL'] = '1'
    os.environ['STUDENT_RAG_DISABLE_ROUTER_CACHE'] = '1'
    os.environ.pop('STUDENT_RAG_OFFLINE_EVAL', None)
    os.environ['HF_HUB_OFFLINE'] = '1'
    logging.disable(logging.CRITICAL)
    from src.generation.answer_pipeline import AnswerPipeline

    class ObservedPipeline(AnswerPipeline):
        def prepare_answer(self, *args, **kwargs):
            prepared = super().prepare_answer(*args, **kwargs)
            self.observed = {
                'context_used': prepared.context_used,
                'query_plan': prepared.retrieval_result.get('query_plan'),
                'terminal_status': prepared.terminal_status,
            }
            return prepared

    cases = [
        ('K51', 'Em được 5,1 điểm học phần thì đạt hay không đạt?'),
        ('K51', 'Học phần chuyên ngành của em được 5,1 điểm thì có qua môn không?'),
        ('K51', 'Học phần nền tảng của em được 5,1 điểm thì có qua môn không?'),
        ('K50', 'Em được 5,1 điểm học phần thì quy đổi điểm chữ và đạt hay không đạt thế nào?'),
    ]
    output = Path('data/eval/reports') / ('matched_rows_smoke_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(parents=True, exist_ok=False)
    report = {'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(), 'cases': []}
    print(f'Output: {output}', flush=True)
    print('Loading cached embedding model...', flush=True)
    pipeline = ObservedPipeline()
    for index, (cohort, query) in enumerate(cases, 1):
        print(f'[{index-1}/{len(cases)}] Running: {query}', flush=True)
        try:
            result = pipeline.answer(query, cohort=cohort)
            row = {'query': query, 'cohort': cohort, **pipeline.observed,
                   'status': result.get('status'), 'answer': result.get('answer'),
                   'usage': result.get('usage')}
        except Exception as exc:
            row = {'query': query, 'cohort': cohort, 'status': 'exception', 'error_type': type(exc).__name__}
        report['cases'].append(row)
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print(f'[{index}/{len(cases)}] {row["status"]}; matched_rows in context: {"matched_rows" in row.get("context_used", "")}', flush=True)
        print(row.get('answer') or row.get('error_type'), flush=True)


if __name__ == '__main__':
    main()
