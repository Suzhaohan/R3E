"""Prepare the agreed, explicit split without model calls."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main():
    rows = [json.loads(s) for s in (ROOT / 'datasets/low_pass_rate_rtl_cases/chipbench8.jsonl').read_text().splitlines()]
    splits = {k: [] for k in ('learning', 'qualification', 'holdout', 'guard')}
    for row in rows:
        role = ('learning' if 'Prob015' in row['case_id'] else
                'holdout' if any(n in row['case_id'] for n in ('Prob001', 'Prob002')) else 'qualification')
        if role == 'holdout':
            row['design'] = 'sequence_shift_family__' + row['case_id'].split(':')[-1]
        splits[role].append(row)
    for number, name in [('Prob003', 'non-overlapping_sequence_detect'), ('Prob015', 'vending_machine2')]:
        base = f'datasets/low_pass_rate_rtl_cases/reconstructed_red/{number}'
        splits['learning'].append(dict(
            case_id=f'reconstructed:{number}:documented_red',
            benchmark='documented_reconstruction_not_historical_artifact',
            design=f'chipbench_{number}_{name}__reconstructed',
            golden_rtl=base+'/golden.sv', buggy_rtl=base+'/buggy.sv', spec=base+'/spec.txt',
            tb_sources=[base+'/ref.sv', base+'/tb_visible.sv'], top_module='TopModule', eligible=True,
            provenance=base+'/reconstruction.json'))
    old = json.loads((ROOT / 'deepseek-run-06/source/competition/manifests/guard_regression.json').read_text())['rows']
    for row in old:
        if row['case_id'] == 'assignment4v:latch24_2':
            continue
        new = {k: row[k] for k in ('case_id', 'design', 'top_module', 'tb_sources', 'deps', 'sim_timeout') if k in row}
        new.update(golden_rtl=row['golden_rtl'], buggy_rtl=row['buggy_rtl'], benchmark='old_run06_guard')
        for key in ('golden_rtl', 'buggy_rtl'):
            new[key] = 'deepseek-run-06/source/' + new[key]
        for key in ('tb_sources', 'deps'):
            new[key] = ['deepseek-run-06/source/'+s for s in new.get(key, [])]
        splits['guard'].append(new)
    for name, rows in splits.items():
        path = HERE / 'manifests' / f'{name}.jsonl'
        value = ''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows)
        if path.exists() and path.read_text() != value:
            raise RuntimeError(f'refusing to overwrite changed manifest: {name}')
        path.write_text(value)
    print(json.dumps({k: len(v) for k, v in splits.items()}))


if __name__ == '__main__':
    main()
