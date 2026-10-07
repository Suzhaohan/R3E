"""Persistent observations and local improvements, independent of active memory."""
import json
from pathlib import Path
from competition.arena.evidence import read, signed, verify_signed
from competition.services.experience_memory import collect, initial_bank, family
from r3e.protocol.hashing import atomic_write_json


def archive(root, state):
    root, state = Path(root), Path(state)
    destination = state/'experience/library.json'
    prior = verify_signed(read(destination)) if destination.exists() else {'entries': [], 'local_improvements': []}
    historical = verify_signed(read(root/'competition/manifests/history_archive.json'))['entries']
    entries = {e['receipt_hash']:e for e in [*historical, *initial_bank(root)['entries'], *prior['entries']]}
    paths = [p for folder in ('replays','eval') for p in (state/folder).rglob('receipt.json')]
    # Preserve all observations. Eligibility for later prompts is separate.
    extra, rejected = collect(paths)
    entries.update({e['receipt_hash']:e for e in extra})
    final_families = {family(r['design']) for name in ('demo32_heldout', 'demo32_strider')
                      for r in read(root/f'competition/manifests/{name}.json')['rows']}
    improvements = {r['key']:r for r in prior['local_improvements']}
    paths = [*sorted((state/'rounds').glob('R*/screening_results.jsonl')),
             *sorted((state/'rounds').glob('R*/target_prechecks.jsonl'))]
    for path in paths:
        for text in path.read_text().splitlines():
            row = json.loads(text)
            for pair in row.get('pairs', []):
                before, after = (pair['before'], pair['after']) if isinstance(pair,dict) else pair
                if not before['oracle_ok'] and after['oracle_ok']:
                    key = after['receipt_hash']
                    improvements[key] = {'key': key, 'round_id': path.parent.name,
                        'policy_id': row['policy_id'], 'case_id': after['case_id'],
                        'seed': after['seed'], 'before_receipt': before['receipt_hash'],
                        'after_receipt': key, 'status': 'local_evidence_only',
                        'message': '此题观察到改善；保留方法，未经单独验证不自动用于其他题。'}
    value = signed({'schema_version': 'r3e-retained-experience-v1', 'entries': list(entries.values()),
        'local_improvements': list(improvements.values()), 'rejected_receipts': rejected,
        'eligible_receipts': sorted(k for k,v in entries.items() if v['family'] not in final_families),
        'activation': 'archive_only; active memory remains frozen', 'deleted_entries': 0})
    atomic_write_json(destination, value)
    return value
