import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('data/processed/chunks/docstore_items.backup.json', 'r', encoding='utf-8') as f:
    old_docs = json.load(f)

with open('data/processed/chunks/all_docstore_items.json', 'r', encoding='utf-8') as f:
    new_docs = json.load(f)

old_data_map = {}
for d in old_docs:
    if d.get('tables') or d.get('highlights'):
        m = d.get('metadata', {})
        key = (m.get('cohort'), m.get('page_start'), m.get('article'))
        old_data_map[key] = {
            'tables': d.get('tables', []),
            'highlights': d.get('highlights', [])
        }

count = 0
for d in new_docs:
    m = d.get('metadata', {})
    key = (m.get('cohort'), m.get('page_start'), m.get('article'))
    if key in old_data_map:
        d['tables'] = old_data_map[key]['tables']
        d['highlights'] = old_data_map[key]['highlights']
        print(f"Restored table/highlight for {key}")
        count += 1

with open('data/processed/chunks/all_docstore_items.json', 'w', encoding='utf-8') as f:
    json.dump(new_docs, f, ensure_ascii=False, indent=2)

print(f"Total restored: {count}")
