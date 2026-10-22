"""Reconstruct only the two mutations explicitly specified in document 09.

The included golden.sv files are local ChipBench baselines, not recovered
historical Red artifacts. Re-running this script refreshes buggy.sv and diffs.
"""
from pathlib import Path
import difflib
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
RULES = {
    'Prob003': [
        (r'(\bs6:\s*)nstate=data\?sf1:s1;', r'\1nstate=idle;'),
        (r'(\bsf6:\s*)nstate=data\?sf1:s1;', r'\1nstate=idle;'),
    ],
    'Prob015': [
        (r'(\bS0_5\s*:\s*nstate\s*=\s*d1\?\s*S1:\s*d2\?\s*)S1_5:', r'\1S1:'),
        (r'(\bS1_5\s*:\s*nstate\s*=\s*~sel\?\s*S0:\s*d1\?\s*S2:\s*d2\?\s*)S2_5:', r'\1S2:'),
    ],
}

for name, rules in RULES.items():
    folder = ROOT / name
    baseline = (folder / 'golden.sv').read_text()
    mutant = baseline
    for pattern, replacement in rules:
        mutant, count = re.subn(pattern, replacement, mutant)
        if count != 1:
            raise ValueError(f'{name}: expected exactly one occurrence of {pattern}, got {count}')
    (folder / 'buggy.sv').write_text(mutant)
    (folder / 'mutation.diff').write_text(''.join(difflib.unified_diff(
        baseline.splitlines(True), mutant.splitlines(True),
        fromfile='golden.sv', tofile='buggy.sv')))
    (folder / 'reconstruction.json').write_text(json.dumps({
        'status': 'reconstructed_from_description_not_original_artifact',
        'description_source': '09_Low_Pass_Rate_RTL_Cases.md section 1',
        'historical_challenge_id': {'Prob003': 'RC_406d811b4d61a2', 'Prob015': 'RC_02caa510ba2821'}[name],
        'baseline': 'local converted ChipBench golden.sv; historical context not verified',
        'replacement_count': 2,
        'baseline_sha256': hashlib.sha256(baseline.encode()).hexdigest(),
        'buggy_sha256': hashlib.sha256(mutant.encode()).hexdigest(),
        'historical_success_rate_reproduced': False,
    }, indent=2) + '\n')
    print(f'{name}: reconstructed two documented state transitions')
