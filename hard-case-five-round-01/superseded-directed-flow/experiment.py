"""Fixed historical hard exams and five rounds of mechanism-directed practice."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# Read-only reuse of the full-file/format-correction generation. All imported
# source files are hashed in the new plan; old runs/plans are never modified.
SOURCE = ROOT / 'prob003-five-round-03/source'
sys.path.insert(0, str(SOURCE))
from r3e.loop.corpus import load_public_manifest
from r3e.loop.sim import Simulator
from r3e.loop.red_design import validate_design, _layout
from r3e.loop.blue_provider import apply_text_edits
from r3e.knowledge.verilog_utils import safe_tokenize
from r3e.protocol.hashing import hash_payload, atomic_write_json

SETTINGS = dict(rounds=5, repeats=2, red_output=32768, blue_output=65536,
                context_tokens=131072, collision_retries=3, format_corrections=1,
                seed=700, model='deepseek-v4-flash', thinking='low', temperature=0.2,
                timeout_seconds=1500, retrieval_entries=4, experience_tokens=8192)
RED_SYSTEM = """You are the practice-task author for a five-round directed repair curriculum.
The final exams are fixed historical hard defects, never replaced by your practice tasks.
Generate ONE NEW defective variant from the clean RTL. Teach transferable reasoning
for the supplied target mechanisms: boundary consumption, state transitions, bit order,
arithmetic and output timing as applicable. Use the incoming learner's actual practice
history and retrieved examples to choose a useful next exercise. Aim for progressive
coverage, not merely a failure or an obvious unrelated typo. Do not claim improvement
before final measurement. Preserve the specification, interfaces and comments.
If the learner fails a practice exercise, use a simpler related exercise next round
so it can obtain a successful repair example before increasing difficulty again.
Do not reproduce a final exam or prior practice task. Final exam RTL, answers and
exam scores are withheld. Return JSON {"edits":[{"find":"unique original text",
"replace":"mutated text"}],"learning_objective":"mechanism this exercise teaches"}.
You may return {"abstain":"reason"}. Your mutant must compile and fail the checks.
"""
BLUE_SYSTEM = """Repair the supplied RTL to satisfy its unchanged specification.
Use prior successful practice examples when applicable; they passed only the stated
public checks and are not correctness proofs. Return only JSON with exactly these keys:
{"files":[{"file":"rtl/design.sv","content":"complete repaired Verilog"}],
"edit":"brief description"}. Submit one complete file, never text-replacement edits.
Preserve the top-level interface. Do not modify or bypass the test infrastructure.
"""


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    atomic_write_json(Path(path), data)


def append(path, data):
    with Path(path).open('a') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalized(rtl):
    return hash_payload([t.value for t in safe_tokenize(rtl)])


def catalog():
    rows = [json.loads(l) for l in (HERE / 'cases.jsonl').read_text().splitlines() if l.strip()]
    _, challenges = load_public_manifest(HERE / 'cases.jsonl', ROOT)
    if len(challenges) != len(rows) or len({r['case_id'] for r in rows}) != len(rows):
        raise ValueError('incomplete or duplicate fixed hard-case catalog')
    for r in rows:
        h = r['historical']
        if h['runs'] < 1 or not 0 <= h['passed'] * 2 <= h['runs']:
            raise ValueError('case does not meet the frozen historical <=50% criterion')
    validate_selection(rows)
    return rows, dict(zip([r['case_id'] for r in rows], challenges))


def validate_selection(rows):
    evidence = read(HERE / 'selection.json')
    if [r['case_id'] for r in rows] != evidence['selected_case_ids']:
        raise ValueError('case catalog differs from the evidence-based selection')
    binding = evidence['binding']
    if sha(ROOT / binding['source']) != binding['sha256']:
        raise ValueError('selection binding changed')
    protocol_ref = evidence['protocol']
    if sha(ROOT / protocol_ref['source']) != protocol_ref['sha256']:
        raise ValueError('historical material manifest changed')
    protocol = read(ROOT / protocol_ref['source'])
    if (protocol['asset_hash'] != read(ROOT / binding['source'])['asset_hash']
            or hash_payload(protocol['assets']) != protocol['asset_hash']):
        raise ValueError('historical records are not bound to the source manifest')
    for row in rows:
        for path in [row[k] for k in ('buggy_rtl', 'golden_rtl', 'spec')] + row['tb_sources']:
            if sha(ROOT / path) != protocol['assets'].get(path):
                raise ValueError('exam differs from the historically measured material')
        records = [x for x in evidence['records'] if x['case_id'] == row['case_id']]
        if len(records) != 3 or len({x['source'] for x in records}) != 3:
            raise ValueError('three distinct local calibration records required')
        successes, failures = 0, 0
        for item in records:
            path = ROOT / item['source']
            if sha(path) != item['sha256']:
                raise ValueError('selection record changed')
            raw = read(path)
            result = raw['record']
            if (result['challenge_id'] != row['case_id'] or result['mode'] != 'none'
                    or raw['inconclusive'] or any(d.get('injected') for d in result['deliveries'])
                    or result['accounting']['memory_delivered']
                    or result['accounting']['provider_failures']
                    or any(a.get('memory_offered') for a in result['attempts'])
                    or raw['solved'] != item['solved']):
                raise ValueError('selection must use conclusive no-memory evidence')
            successes += bool(raw['solved'])
            failures += not raw['solved'] and result['attempts'][-1]['verdict_tier'] == 'visible_fail'
        if successes > 1 or failures < 2:
            raise ValueError('case does not meet stronger local functional-failure criterion')


def plan():
    rows, _ = catalog()
    families = sorted({r['family'] for r in rows})
    assets = {str(HERE.relative_to(ROOT) / 'cases.jsonl'): sha(HERE / 'cases.jsonl')}
    assets[str(HERE.relative_to(ROOT) / 'selection.json')] = sha(HERE / 'selection.json')
    evidence = read(HERE / 'selection.json')
    for item in [evidence['binding'], evidence['protocol'], *evidence['records']]:
        assets[item['source']] = sha(ROOT / item['source'])
    for r in rows:
        for n in [r[k] for k in ('golden_rtl', 'buggy_rtl', 'spec')] + r['tb_sources'] + ([r['provenance']] if r.get('provenance') else []):
            assets[n] = sha(ROOT / n)
    for p in [HERE / 'experiment.py', HERE / 'run.sh', HERE / 'dashboard.py', *sorted(SOURCE.rglob('*.py'))]:
        assets[str(p.relative_to(ROOT))] = sha(p)
    tokenizer = ROOT / 'prob003-five-round-03/handoff/tokenizer/tokenizer.json'
    assets[str(tokenizer.relative_to(ROOT))] = sha(tokenizer)
    slots = [{'round': i, 'family': f} for i in range(1, SETTINGS['rounds'] + 1) for f in families]
    # Static B0 and final B5 only; intermediate exams cannot influence training.
    exams = [{'role': role, 'case_id': r['case_id'], 'repeat': k}
             for r in rows for k in range(SETTINGS['repeats'])
             for role in (('static', 'evolved') if k % 2 == 0 else ('evolved', 'static'))]
    return dict(version='fixed_hard_exam_curriculum_v2', settings=SETTINGS,
                selection='three cases with newer local no-memory calibration <=1/3; selection frozen before new collection',
                families=families, cases=rows, slots=slots, exams=exams,
                max_calls=len(slots) * (1 + SETTINGS['collision_retries'] + 1 + SETTINGS['format_corrections'])
                          + len(exams) * (1 + SETTINGS['format_corrections']),
                assets=assets, selection_evidence_sha256=sha(ROOT / '09_Low_Pass_Rate_RTL_Cases.md'),
                runtime={'python': sys.version, 'executable': sys.executable,
                         'tools': {n: {'path': shutil.which(n), 'sha256': sha(shutil.which(n))}
                                   for n in ('iverilog', 'vvp')}},
                excluded=[{'case': 'Prob004 warm-slot-3', 'reason': 'original compound mutant unavailable; no repeated low-rate evidence'},
                          {'case': 'Ibex 907', 'reason': 'historical public pass 3/3; not a low-rate case'},
                          {'case': 'Ibex 2232', 'reason': 'historical public pass 2/3; above frozen <=50% criterion'},
                          *evidence['excluded']],
                limits=[*evidence['limitations'],
                        'Historical pass rates use different settings and do not guarantee a low current static rate.',
                        'Directed practice on known designs; not unseen-design generalization.',
                        'No exam outcomes select memories or tasks. No answer is sent to Blue.',
                        'Five rounds have one slot per design (two slots each round), not five total tasks.',
                        'No spending ceiling; finite request/token caps. Code preparation does not launch paid requests.'])


def load_plan(directory):
    frozen = read(directory / 'plan.json')
    if frozen != plan() or read(directory / 'plan_hash.json')['hash'] != hash_payload(frozen):
        raise ValueError('code/material/settings changed; freeze a new plan')
    return frozen


def verdict(sim, rtl, carrier):
    v = sim.verdict(rtl, carrier)
    # Simulation/compile errors must not masquerade as functional counterexamples.
    return {'category': v.tier, 'passed': v.visible_ok, 'feedback_hash': v.feedback.feedback_hash}


def preflight(directory):
    p = load_plan(directory)
    rows, cases = catalog()
    results = []
    with tempfile.TemporaryDirectory(prefix='hard-case-check-') as tmp:
        sim = Simulator(Path(tmp))
        for r in rows:
            c = cases[r['case_id']]
            good = verdict(sim, c.carrier.clean_rtl, c.carrier)
            bad = verdict(sim, c.buggy_rtl, c.carrier)
            item = dict(case_id=r['case_id'], golden=good, buggy=bad,
                        qualified=good['passed'] and not bad['passed'],
                        baseline_kind='functional' if bad['category'] == 'visible_fail' else 'compile_or_timeout_diagnostic')
            results.append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
    report = dict(ready=all(x['qualified'] for x in results), model_calls=0,
                  plan_hash=hash_payload(p), cases=results,
                  scoring='agreement with frozen reference tests; diagnostic failures kept separate')
    write(directory / 'preflight.json', report)
    if not report['ready']:
        raise ValueError('fixed cases did not qualify; none were silently removed')
    return report


def retrieve(entries, family, counter):
    selected = []
    for e in reversed(entries):
        if e['family'] != family:
            continue
        if len(selected) >= SETTINGS['retrieval_entries']:
            break
        if counter.count(json.dumps([*selected, e], ensure_ascii=False)) <= SETTINGS['experience_tokens']:
            selected.append(e)
    return selected


def blue_payload(spec, rtl, entries):
    # Exact allowlist: never include clean RTL, reference TB, final exam answers,
    # baseline mismatch windows or scores of any other exam attempt.
    return {'specification': spec, 'files': {'rtl/design.sv': {'content': rtl}},
            'repair_experience': entries}


def red_payload(row, carrier, entries, observations, round_index):
    return {'round': round_index, 'family': row['family'],
            'specification': carrier.spec, 'clean_rtl': carrier.clean_rtl,
            'target_mechanisms': sorted({r['mechanism'] for r in catalog()[0] if r['family'] == row['family']}),
            'prior_practice_observations': observations,
            'incoming_experience': entries}


def call(client, counter, directory, system, payload, seed, phase, cap):
    directory.mkdir(parents=True, exist_ok=False)
    messages = [{'role': 'system', 'content': system},
                {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
    size = counter.request(messages)
    write(directory / 'request.json', dict(messages=messages, request_hash=hash_payload(messages),
                                           input_tokens=size, output_limit=cap, seed=seed))
    if size + cap > SETTINGS['context_tokens']:
        return None, 'context_limit'
    try:
        with client.in_phase(phase):
            response = client.complete_json(messages=messages, seed=seed, maximum_output_tokens=cap)
        write(directory / 'response.json', response)
        if response.get('response_diagnostics', {}).get('finish_reason') == 'length':
            return None, 'output_limit'
        return response['result'], None
    except Exception as exc:
        from r3e.providers.openai_compatible import OpenAICompatibleProviderViolation
        if not isinstance(exc, OpenAICompatibleProviderViolation):
            raise
        diag = getattr(exc, 'diagnostics', {}) or {}
        write(directory / 'error.json', {'type': type(exc).__name__, 'diagnostics': diag})
        # Parse-format errors alone may receive a format correction; an empty
        # answer, transport failure or truncated generation never does.
        return None, 'provider_failure'


def parse_blue(raw):
    if (not isinstance(raw, dict) or set(raw) != {'files', 'edit'}
            or not isinstance(raw['edit'], str) or not isinstance(raw['files'], list)
            or len(raw['files']) != 1):
        raise ValueError('expected exactly files and edit, one complete file')
    f = raw['files'][0]
    if (not isinstance(f, dict) or set(f) != {'file', 'content'} or f['file'] != 'rtl/design.sv'
            or not isinstance(f['content'], str) or not f['content'].strip() or '```' in f['content']):
        raise ValueError('invalid file path or empty/non-code content')
    # Interface/syntax/functional issues are scored after format handling and
    # cannot trigger another functional repair attempt.
    return f['content']


def repair(client, counter, sim, directory, case, entries, seed, *, role):
    payload = blue_payload(case.carrier.spec, case.buggy_rtl, entries)
    write(directory / 'delivery.json', {'role': role, 'entries': [e['entry_hash'] for e in entries],
                                       'payload_hash': hash_payload(payload)})
    errors, candidate = [], None
    for i in range(SETTINGS['format_corrections'] + 1):
        raw, error = call(client, counter, directory / f'submission_{i}', BLUE_SYSTEM,
                          payload, seed + i, 'blue_inference', SETTINGS['blue_output'])
        if error:
            result = {'category': error, 'passed': False, 'format_corrections': i}
            break
        try:
            candidate = parse_blue(raw)
        except ValueError as exc:
            errors.append(str(exc))
            payload = {**blue_payload(case.carrier.spec, case.buggy_rtl, entries),
                       'format_correction': {'instruction': 'Keep the same repair intent; fix submission format only. No functional test has run.',
                                             'previous_answer': raw, 'error': str(exc)}}
            result = {'category': 'invalid_edit', 'passed': False, 'format_corrections': i}
            continue
        # Verify top-level ports without applying the Red edit-size constraint
        # to Blue's legitimate whole-file rewrites.
        try:
            if _layout(candidate, case.carrier.top_module)[2] != _layout(case.carrier.clean_rtl, case.carrier.top_module)[2]:
                raise ValueError('top interface changed')
            result = verdict(sim, candidate, case.carrier)
        except ValueError as exc:
            result = {'category': 'interface_violation', 'passed': False, 'reason': str(exc)}
        result['format_corrections'] = i
        break
    if candidate is not None:
        (directory / 'candidate.sv').write_text(candidate)
    result.update(role=role, errors=errors, delivered_entries=[e['entry_hash'] for e in entries])
    write(directory / 'result.json', result)
    return result, candidate


def make_entry(family, round_index, slot, buggy, candidate, result):
    if not result['passed'] or result['role'] != 'practice':
        raise ValueError('only public-passing practice repairs can teach')
    body = dict(family=family, created_round=round_index, source_slot=slot,
                validation='reference_test_pass_only',
                patch=''.join(difflib.unified_diff(buggy.splitlines(True), candidate.splitlines(True),
                                                 'a/rtl/design.sv', 'b/rtl/design.sv')),
                buggy_hash=hash_payload(buggy), candidate_hash=hash_payload(candidate))
    return {**body, 'entry_hash': hash_payload(body)}


def collect(p, out, client, counter, *, fake=False):
    if p != plan() or client.max_calls != p['max_calls'] or client.total_calls:
        raise ValueError('fresh exact frozen plan/client required')
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'plan.json', p)
    rows, cases = catalog()
    entries, observations, completed, exams = [], [], [], []
    family_rows = {f: next(r for r in rows if r['family'] == f) for f in p['families']}
    forbidden = {normalized(c.buggy_rtl) for c in cases.values()}
    seen = set()
    label = {}
    client.on_call = lambda x: append(out / 'calls.jsonl', {**x, **label})
    sim = Simulator(out / 'simulation')
    write(out / 'snapshots/B_0.json', {'entries': [], 'round': 0})
    status = 'aborted'
    try:
        for r in range(1, SETTINGS['rounds'] + 1):
            incoming = list(entries)
            pending, round_obs = [], []
            for family in p['families']:
                if p != plan():
                    raise ValueError('frozen code/material changed during collection')
                row = family_rows[family]
                base = cases[row['case_id']]
                slot = f'r{r}_{family}'
                directory = out / 'rounds' / str(r) / slot
                selected = retrieve(incoming, family, counter)
                payload = red_payload(row, base.carrier, selected,
                                      [x for x in observations if x['family'] == family], r)
                label.update(role='red', slot=slot)
                proposal = None
                for attempt in range(SETTINGS['collision_retries'] + 1):
                    raw, error = call(client, counter, directory / f'red_{attempt}', RED_SYSTEM, payload,
                                      SETTINGS['seed'] + len(completed) * 100 + attempt,
                                      'red', SETTINGS['red_output'])
                    reason = error
                    if not error:
                        try:
                            if set(raw) != {'edits', 'learning_objective'} or not isinstance(raw['learning_objective'], str):
                                raise ValueError('invalid Red schema or abstention')
                            mutant = apply_text_edits(base.carrier.clean_rtl, raw['edits'])
                            validate_design(base.carrier.clean_rtl, mutant, base.carrier.top_module)
                            ident = normalized(mutant)
                            if ident in forbidden or ident in seen:
                                reason = 'exam_collision' if ident in forbidden else 'practice_repeat'
                            else:
                                v = verdict(sim, mutant, base.carrier)
                                if v['category'] != 'visible_fail':
                                    reason = 'not_a_compiling_functional_defect'
                                else:
                                    proposal = (mutant, raw['learning_objective'], ident)
                        except (ValueError, TypeError, KeyError) as exc:
                            reason = str(exc)
                    write(directory / f'red_{attempt}/admission.json', {'admitted': proposal is not None, 'reason': reason})
                    if proposal or reason not in {'exam_collision', 'practice_repeat'}:
                        break
                    payload['excluded_proposals'] = [*payload.get('excluded_proposals', []), raw['edits']]
                record = dict(round=r, family=family, slot=slot, admitted=proposal is not None)
                if proposal:
                    mutant, objective, ident = proposal
                    (directory / 'practice.sv').write_text(mutant)
                    seen.add(ident)
                    practice = replace(base, challenge_id=slot, buggy_rtl=mutant, origin='red')
                    label.update(role='practice', slot=slot)
                    result, candidate = repair(client, counter, sim, directory / 'blue', practice, selected,
                                                SETTINGS['seed'] + len(completed) * 100 + 10, role='practice')
                    record.update(result=result, learning_objective=objective)
                    round_obs.append(dict(family=family, round=r, objective=objective,
                                          result=result['category'], mutant_hash=hash_payload(mutant),
                                          mutation_patch=''.join(difflib.unified_diff(
                                              base.carrier.clean_rtl.splitlines(True), mutant.splitlines(True))),
                                          attempted_repair_patch=''.join(difflib.unified_diff(
                                              mutant.splitlines(True), candidate.splitlines(True))) if candidate else ''))
                    if result['passed']:
                        pending.append(make_entry(family, r, slot, mutant, candidate, result))
                else:
                    record['reason'] = reason
                completed.append(record)
                append(out / 'slots.jsonl', record)
            # Whole round commits once. No within-round or final-exam learning.
            entries.extend(pending)
            observations.extend(round_obs)
            write(out / f'snapshots/B_{r}.json', {'entries': entries, 'round': r,
                                                 'entry_count': len(entries)})
        for i, exam in enumerate(p['exams']):
            if p != plan():
                raise ValueError('frozen code/material changed during final exams')
            row = next(r for r in rows if r['case_id'] == exam['case_id'])
            selected = [] if exam['role'] == 'static' else retrieve(entries, row['family'], counter)
            label.update(role=exam['role'], slot=f'exam_{i}')
            # Paired seed independent of role; requests remain separate.
            seed = SETTINGS['seed'] + 100000 + rows.index(row) * 100 + exam['repeat'] * 10
            result, _ = repair(client, counter, sim, out / 'exams' / str(i), cases[exam['case_id']],
                               selected, seed, role=exam['role'])
            result.update(case_id=exam['case_id'], repeat=exam['repeat'])
            exams.append(result)
            append(out / 'exams.jsonl', result)
        status = 'complete'
    finally:
        write(out / 'collection.json', dict(status=status, model_calls=0 if fake else client.total_calls,
                                            simulated_requests=client.total_calls if fake else 0,
                                            completed_slots=len(completed), scheduled_slots=len(p['slots']),
                                            completed_exams=len(exams), scheduled_exams=len(p['exams']),
                                            experience_entries=len(entries), plan_hash=hash_payload(p),
                                            fake=fake))
    return report(out)


def report(out):
    p = read(out / 'plan.json')
    summary = read(out / 'collection.json')
    exams = [json.loads(l) for l in (out / 'exams.jsonl').read_text().splitlines()] if (out / 'exams.jsonl').exists() else []
    groups = {}
    for role in ('static', 'evolved'):
        rs = [r for r in exams if r['role'] == role]
        groups[role] = dict(passed=sum(r['passed'] for r in rs), completed=len(rs),
                            scheduled=len(p['cases']) * p['settings']['repeats'],
                            categories=dict(Counter(r['category'] for r in rs)),
                            format_corrections=sum(r['format_corrections'] for r in rs))
    per_case = [{ 'case_id': c['case_id'], 'historical': c['historical'],
                  'selection_evidence': c['selection_evidence'], 'artifact': c['artifact'],
                  **{role: {'passed': sum(r['passed'] for r in exams if r['case_id'] == c['case_id'] and r['role'] == role),
                            'completed': sum(r['case_id'] == c['case_id'] and r['role'] == role for r in exams)}
                     for role in ('static', 'evolved')}} for c in p['cases']]
    # Count repeated repair locations explicitly: directed practice may teach
    # exactly the same line as a final defect, even if the mutants differ.
    rows, cases = catalog()
    final_entries = read(out / 'snapshots/B_5.json')['entries'] if (out / 'snapshots/B_5.json').exists() else []
    exposure = []
    for c in rows:
        task = cases[c['case_id']]
        def spans(a, b):
            return {i for tag, start, end, _, _ in difflib.SequenceMatcher(None, a.splitlines(), b.splitlines(), autojunk=False).get_opcodes()
                    if tag != 'equal' for i in range(start, max(start + 1, end))}
        exam_spans = spans(task.carrier.clean_rtl, task.buggy_rtl)
        overlapping = []
        for e in final_entries:
            if e['family'] != c['family']:
                continue
            practice = out / 'rounds' / str(e['created_round']) / e['source_slot'] / 'practice.sv'
            if practice.exists() and exam_spans & spans(task.carrier.clean_rtl, practice.read_text()):
                overlapping.append(e['entry_hash'])
        exposure.append({'case_id': c['case_id'], 'same_family_entries': sum(e['family'] == c['family'] for e in final_entries),
                         'practice_mutation_span_overlap': overlapping})
    result = dict(**summary, groups=groups, per_case=per_case, exposure=exposure,
                  static_low_evolved_high_is_a_hypothesis=True,
                  limits=p['limits'], scoring='frozen reference-test agreement; no proof of full correctness')
    write(out / 'report.json', result)
    return result


def counter():
    from r3e.loop.token_count import TokenCounter
    return TokenCounter(ROOT / 'prob003-five-round-03/handoff/tokenizer/tokenizer.json')


def smoke(p, out):
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.env import build_client
    from r3e.loop.fakes import _reply
    # Explicit synthetic transport; never counted as evidence of model ability.
    _, cases = catalog()
    clean_by_spec = {c.carrier.spec: c.carrier.clean_rtl for c in cases.values()}
    rounds = {f: 0 for f in p['families']}

    def transport(**request):
        u = json.loads(request['messages'][-1]['content'])
        if 'clean_rtl' in u:
            f = u['family']
            rounds[f] += 1
            clean = u['clean_rtl']
            # Deterministic synthetic exercise, useful only for plumbing tests.
            import re
            numbers = list(re.finditer(r"(?<![A-Za-z_0-9])(?:\d+'[bdh][0-9a-fA-F]+|\d+)(?![A-Za-z_0-9])", clean))
            eligible = []
            for m in numbers:
                replacement = "1'b1" if m.group() != "1'b1" else "1'b0"
                # Full-file exact find prevents ambiguous occurrences.
                mutant = clean[:m.start()] + replacement + clean[m.end():]
                try:
                    validate_design(clean, mutant, 'TopModule')
                except ValueError:
                    continue
                eligible.append(mutant)
            mutant = eligible[(rounds[f] - 1) % len(eligible)] if eligible else clean
            value = {'edits': [{'find': clean, 'replace': mutant}], 'learning_objective': 'offline fixture only'}
        else:
            value = {'files': [{'file': 'rtl/design.sv', 'content': clean_by_spec[u['specification']]}], 'edit': 'offline fixture only'}
        return _reply(value, 1)

    client = build_client({'DEEPSEEK_MODEL': 'fake-local'}, transport=transport, maximum_output_tokens=65536)
    return collect(p, out, BudgetedClient(client, max_calls=p['max_calls']), counter(), fake=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['freeze', 'check', 'smoke', 'collect', 'status', 'report'])
    parser.add_argument('--plan-dir', type=Path, default=HERE / 'plan-focused-v2')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    if args.action != 'collect':
        def offline(event, values):
            if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
                raise RuntimeError('offline command: network disabled')
        sys.addaudithook(offline)
    if args.action == 'freeze':
        p = plan()
        args.plan_dir.mkdir(parents=True, exist_ok=False)
        write(args.plan_dir / 'plan.json', p)
        write(args.plan_dir / 'plan_hash.json', {'hash': hash_payload(p)})
        print(json.dumps({'cases': len(p['cases']), 'practice_slots': len(p['slots']),
                          'exams': len(p['exams']), 'max_calls': p['max_calls'], 'model_calls': 0}))
        return
    if args.action in {'status', 'report'}:
        if args.run_dir is None:
            parser.error('--run-dir required')
        if args.action == 'status':
            from dashboard import status
            print(json.dumps(status(args.run_dir), ensure_ascii=False))
        else:
            print(json.dumps(report(args.run_dir), ensure_ascii=False))
        return
    p = load_plan(args.plan_dir)
    if args.action == 'check':
        preflight(args.plan_dir)
        return
    if args.run_dir is None:
        parser.error('fresh --run-dir required')
    if args.action == 'smoke':
        print(json.dumps(smoke(p, args.run_dir), ensure_ascii=False))
        return
    if args.env_file is None:
        parser.error('collect requires --env-file; this command starts paid requests')
    if args.run_dir.exists():
        raise ValueError('fresh run directory required; no resume')
    qualified = read(args.plan_dir / 'preflight.json')
    if not qualified['ready'] or qualified['plan_hash'] != hash_payload(p):
        raise ValueError('run offline check for this exact plan before paid collection')
    from r3e.loop.env import build_client, load_llm_env, ThinkingTransport
    from r3e.loop.budget import BudgetedClient
    from experiments.loop_probes.red907_launch import UsageGuard
    from decimal import Decimal
    env = load_llm_env(args.env_file, names=('DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL'))
    if env.get('DEEPSEEK_BASE_URL', '').rstrip('/') != 'https://api.deepseek.com':
        raise ValueError('expected frozen provider endpoint')
    tokens = counter()
    transport = ThinkingTransport(env, key_name='DEEPSEEK_API_KEY', url_name='DEEPSEEK_BASE_URL',
                                  thinking=SETTINGS['thinking'], timeout_seconds=SETTINGS['timeout_seconds'],
                                  failure_dir=args.run_dir / 'unparseable',
                                  error_log=args.run_dir / 'provider_errors.jsonl',
                                  response_log=args.run_dir / 'provider_responses.jsonl')
    guard = UsageGuard(transport, tokens, args.run_dir, envelope=Decimal('Infinity'),
                       direct_only=True, allowed_systems={RED_SYSTEM: SETTINGS['red_output'],
                                                         BLUE_SYSTEM: SETTINGS['blue_output']})
    client = build_client(env, model_override=SETTINGS['model'], maximum_output_tokens=65536,
                          thinking=SETTINGS['thinking'], timeout_seconds=SETTINGS['timeout_seconds'],
                          temperature=SETTINGS['temperature'], transport=guard)
    print(json.dumps(collect(p, args.run_dir, BudgetedClient(client, max_calls=p['max_calls']), tokens), ensure_ascii=False))


if __name__ == '__main__':
    main()
