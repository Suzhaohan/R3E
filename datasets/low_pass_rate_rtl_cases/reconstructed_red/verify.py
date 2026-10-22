"""Check golden passes and reconstructed mutant fails directed and visible tests."""
from pathlib import Path
import json
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
results = []
for name in ('Prob003', 'Prob015'):
    folder = ROOT / name
    for test in ('witness', 'visible'):
        for variant in ('golden', 'buggy'):
            with tempfile.TemporaryDirectory(prefix='r3e-red-reconstruction-') as work:
                output = Path(work) / 'sim.vvp'
                sources = [folder / f'{variant}.sv', folder / f'tb_{test}.sv']
                if test == 'visible':
                    sources.insert(1, folder / 'ref.sv')
                command = ['iverilog', '-g2012', '-s', 'tb_witness' if test == 'witness' else 'tb',
                           '-o', str(output), *map(str, sources)]
                compile_result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                if compile_result.returncode:
                    raise RuntimeError(compile_result.stderr)
                run = subprocess.run(['vvp', str(output)], cwd=work,
                                     capture_output=True, text=True, timeout=10)
                if test == 'witness':
                    passed = run.returncode == 0 and 'WITNESS_PASS' in run.stdout
                    target_failure = run.returncode != 0 and 'WITNESS_FAIL' in run.stdout
                else:
                    match = re.search(r'Mismatches: (\d+) in (\d+) samples', run.stdout)
                    if run.returncode != 0 or not match or int(match[2]) == 0:
                        raise RuntimeError(f'{name} {variant}: invalid visible test result: {run.stdout} {run.stderr}')
                    passed = int(match[1]) == 0
                    target_failure = int(match[1]) > 0
                assert passed if variant == 'golden' else target_failure, (name, test, variant, run.stdout)
                results.append({'design': name, 'test': test, 'variant': variant,
                                'passed': passed, 'returncode': run.returncode, 'stdout': run.stdout})
                print(f'{name} {test} {variant}: {"PASS" if passed else "EXPECTED FAILURE"}')
(ROOT / 'validation.json').write_text(json.dumps(results, indent=2) + '\n')
