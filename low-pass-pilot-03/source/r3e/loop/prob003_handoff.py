"""Runner-side integration of the delivered Prob003 materials."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

from r3e.knowledge.verilog_utils import safe_tokenize
from r3e.protocol.hashing import hash_payload

from .red import RedAgent
from .sim import Simulator


BENCHMARK = 'prob003_handoff_20261013'
SEED_ID = 'handoff:Prob003:historical_seed'
EVAL_IDS = frozenset({'handoff:Prob003:eval_match_branch', 'handoff:Prob003:eval_miss_branch'})


def normalized_rtl(rtl):
    return tuple(token.value for token in safe_tokenize(rtl))


def verify_materials(root, manifest):
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in {'handoff_manifest.json', 'tb_visible.sv'}:
            continue
        expected = manifest['files_sha256'].get(relative)
        data = path.read_bytes()
        digests = {hashlib.sha256(data).hexdigest()}
        if data.endswith(b'\n'):
            digests.add(hashlib.sha256(data[:-1]).hexdigest())
        if expected is None or expected not in digests:
            raise ValueError(f'Prob003 handoff material changed: {relative}')


def run_suite(rtl, suite, workspace):
    workspace.mkdir(parents=True, exist_ok=True)
    dut = workspace / 'dut.sv'
    dut.write_text(rtl)
    binary = workspace / 'suite.out'
    try:
        compiled = subprocess.run(['iverilog', '-g2012', '-s',
            'evaluate_sequence' if suite.parent.name == 'evaluator' else 'tb',
            '-o', str(binary), str(dut), str(suite)], capture_output=True, text=True, timeout=30)
        if compiled.returncode:
            return {'result': 'error', 'log': (compiled.stderr or compiled.stdout)[-2000:]}
        result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {'result': 'error', 'log': 'suite timeout'}
    log = result.stdout + result.stderr
    passed = result.returncode == 0 and 'TESTBENCH PASS' in log and 'CHECK_FAIL' not in log
    return {'result': 'pass' if passed else 'fail', 'log': log[-2000:]}


def qualification(root, workspace):
    package = root / 'materials/package'
    suites = {'W_bug': package/'suites/W_bug/tb.sv',
              'W_preserve': package/'suites/W_preserve/tb.sv',
              'evaluator': root/'materials/evaluator/tb.sv'}
    variants = {'clean': package/'src/rtl/sequence.sv'}
    variants.update({name: package/f'variants/{name}/rtl/sequence.sv'
                     for name in ('defect', 'eval_match_branch', 'eval_miss_branch', 'reset_control')})
    matrix = {name: {suite: run_suite(path.read_text(), testbench, workspace/name/suite)
                    for suite, testbench in suites.items()} for name, path in variants.items()}
    ready = all(result['result'] == 'pass' for result in matrix['clean'].values())
    for name in ('defect', 'eval_match_branch', 'eval_miss_branch'):
        ready &= matrix[name]['W_bug']['result'] == 'fail'
        ready &= matrix[name]['W_preserve']['result'] == 'pass'
    ready &= matrix['reset_control']['W_bug']['result'] == 'pass'
    ready &= matrix['reset_control']['W_preserve']['result'] == 'fail'
    return {'ready': bool(ready), 'matrix': matrix, 'model_calls': 0}


class Prob003Simulator(Simulator):
    def verdict(self, rtl, carrier, *, registers=False):
        if carrier.source.get('benchmark') == BENCHMARK:
            artifact = self.workspace.parent/'prob003-artifacts'/f'{hash_payload(rtl)[7:]}.sv'
            artifact.parent.mkdir(parents=True, exist_ok=True)
            if not artifact.exists():
                artifact.write_text(rtl)
        return super().verdict(rtl, carrier, registers=registers)


class ReservedRedAgent(RedAgent):
    def __init__(self, *, reserved, **kwargs):
        super().__init__(**kwargs)
        self.reserved = {normalized_rtl(ch.buggy_rtl) for ch in reserved}

    def _admit(self, carrier, mutant):
        if carrier.source.get('benchmark') == BENCHMARK and normalized_rtl(mutant) in self.reserved:
            return 'reserved_evaluation_duplicate', None
        return super()._admit(carrier, mutant)
