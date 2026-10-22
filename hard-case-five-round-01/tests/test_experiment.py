import importlib.util
import json
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('question_only_experiment', HERE / 'experiment-medium-high-v2.py')
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)


def test_three_original_questions_and_evidence_are_preserved():
    rows = ex.verify_questions()
    assert len(rows) == 3
    assert {r['family'] for r in rows} == {'Arbiter', 'VendingTiming', 'VendingState'}
    for design in ex.DESIGNS:
        m = ex.material(design)
        names = [Path(a['task_dir']).name for a in m['anchors']]
        for row, name in zip([r for r in rows if r['family'] == design], names):
            actual = Path(m['anchors'][names.index(name)]['task_dir']) / 'public/repo/rtl/sequence.sv'
            assert actual.read_bytes() == (ex.ROOT / row['buggy_rtl']).read_bytes()


def test_changed_historical_evidence_is_rejected(monkeypatch):
    original = ex.sha
    evidence = ex.read(ex.SELECTION)
    target = (ex.ROOT / next(iter(evidence['evidence']))).resolve()
    monkeypatch.setattr(ex, 'sha', lambda path: 'changed' if Path(path).resolve() == target else original(path))
    with pytest.raises(ValueError, match='historical evidence'):
        ex.verify_questions()


def test_uses_identical_completed_core_and_policies():
    baseline = ex.read(ex.BASE / 'real-v1/collection/plan.json')
    for design in ex.DESIGNS:
        base = ex.runner(design)
        launch, loop, shared, curriculum, counter = base.modules()
        m = ex.material(design)
        p = loop.make_plan(m['carriers'], m['anchors'], counter=counter(),
            client_config=launch.client_identity(), rounds=5, slots_per_round=1,
            seed=700, carrier_mode='fixed', fixed_carrier_index=0, anchor_repeats=2,
            mechanism_focus=m['mechanism_focus'], red_output_tokens=ex.RED_OUTPUT, reserved_collision_retries=3)
        assert p['code'] == ex.read(HERE / 'promotion_code.json')
        assert all(p[k] == baseline[k] for k in ex.FLOW_FIELDS if k not in ('blue_config','client_config','red_output_tokens'))
        assert p['blue_config']['output_reserve'] == p['client_config']['maximum_output_tokens'] == 16000
        assert p['blue_config']['context_tokens'] == 128000
        assert len(p['validation_tasks']) == 2
        assert not p['promotion']['final_exam_for_selection']
        assert p['retrieval']['max_entries'] == 2
        assert p['retrieval']['wrapper_tokens'] == 4096
        assert p['learning'] == baseline['learning']
        assert len(p['slots']) == 5
        assert {x['snapshot'] for x in p['anchor_probes']} == set(range(6))
        assert len(p['anchor_probes']) == len(m['anchors']) * 2 * 6


def test_derived_caps_and_same_role_reservations():
    assert all(ex.cap(d) == 112 for d in ex.DESIGNS)
    assert sum(ex.cap(d) for d in ex.DESIGNS) == 336
    for design in ex.DESIGNS:
        base = ex.runner(design)
        launch, *_ = base.modules()
        budget = base.budget(launch)
        calls = {r['role']: r['calls'] for r in budget['rows']}
        assert calls['red'] == 20
        assert calls['online'] == calls['reference'] == 10
        assert calls['promotion'] == 48
        assert budget['max_calls'] == ex.cap(design)


def test_qualification_and_no_answer_in_public_test_material():
    for design in ex.DESIGNS:
        root = ex.MATERIAL_ROOT / design
        q = ex.read(root / 'qualification.json')
        assert q['qualified']
        assert {x['tier'] for key, x in q['matrix'].items() if key.startswith('exam_') and key.endswith('/W_bug')} == {'fail'}
        assert {x['tier'] for key, x in q['matrix'].items() if key.startswith('exam_') and key.endswith('/W_preserve')} == {'pass'}
        for path in (root / 'package/suites').rglob('*.sv'):
            assert 'module RefModule' not in path.read_text()


def test_flow_guard_rejects_previous_unsolicited_retrieval_change():
    base = ex.runner('VendingTiming')
    launch, loop, shared, curriculum, counter = base.modules()
    p = ex.read(ex.BASE / 'real-v1/collection/plan.json')
    p['retrieval']['max_entries'] = 4
    with pytest.raises(ValueError, match='workflow mechanism'):
        base.check_scope(p, launch)


def test_training_material_passes_the_unchanged_structural_gate():
    base = ex.runner('VendingTiming')
    _, loop, *_ = base.modules()
    for design in ex.DESIGNS:
        package = Path(ex.material(design)['carriers'][0]['package'])
        result = loop.red907._loop_check(package, loop.wm.load(package), 'clean')
        assert result['status'] == 'ok'


def test_previous_false_public_passes_fail_new_original_sample_checks():
    spec = importlib.util.spec_from_file_location('selected_material_builder', HERE / 'prepare_selected.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    old = ex.ROOT / 'hard-case-five-round-01/real-all-20261015-034425/Prob015/collection/anchors'
    tb = (ex.MATERIAL_ROOT / 'VendingTiming/package/suites/W_bug/tb.sv').read_text()
    for repeat in (0, 1):
        archive = next((old / f'b0_a0_repeat{repeat}/blue/archive').glob('*.json'))
        candidate = ex.read(archive)['files']['rtl/sequence.sv']
        output = builder.simulate({'dut.sv': candidate, 'tb.sv': tb})
        assert 'CHECK_FAIL original samples' in output


def test_practice_examples_are_distinct_from_exams_and_seed():
    for design in ex.DESIGNS:
        m = ex.material(design)
        clean = (Path(m['carriers'][0]['package']) / 'src/rtl/sequence.sv').read_text()
        exam = (Path(m['anchors'][0]['task_dir']) / 'public/repo/rtl/sequence.sv').read_text()
        fixtures = ex.read(ex.MATERIAL_ROOT / design / 'practice_fixtures.json')
        mutants = [clean.replace(f[0]['find'], f[0]['replace']) for f in fixtures]
        assert len(set(mutants)) == 5
        assert all(mutant != exam and mutant != clean for mutant in mutants)
        assert 'Across five rounds build transferable repair experience' in m['mechanism_focus']['mechanism']


def test_promotion_requires_gain_without_losing_any_certified_sample():
    _,loop,*_ = ex.runner('Arbiter').modules()
    judge=loop.promotion_decision
    assert judge({'a':True,'b':False}, {'a':True,'b':True}, {'a'})['accepted']
    assert not judge({'a':True,'b':False}, {'a':False,'b':True}, {'a'})['accepted']
    assert judge({'a':True}, {'a':True}, {'a'})['reason']=='no_strict_gain'
    # A past certificate remains protected even if the incumbent fluctuates now.
    assert judge({'a':False,'b':False},{'a':False,'b':True},{'a'})['reason']=='regression'
    with pytest.raises(ValueError,match='certificates missing'):
        judge({'a':True},{'a':True},{'missing'})


def test_validation_defects_are_not_final_exams_or_development_seed():
    for design in ex.DESIGNS:
        _,loop,*_ = ex.runner(design).modules()
        material=ex.material(design)
        package=Path(material['carriers'][0]['package'])
        public=loop.red907.public_material(package,ex.read(material['carriers'][0]['suite_freeze']))
        clean=public['clean_rtl']
        edit=material['mechanism_focus']['seed_edits'][0]
        seed=clean.replace(edit['find'],edit['replace'])
        forbidden={loop.mutant_identity(public,seed),ex.read(ex.PLAN_ROOT/design/'plan.json')['anchors'][0]['mutant_identity']}
        for task in loop.PROMOTION_VALIDATION:
            code=(Path(task)/'public/repo/rtl/sequence.sv').read_text()
            assert loop.mutant_identity(public,code) not in forbidden


def test_promotion_reservation_counts_every_pair_and_format_correction():
    _,loop,*_=ex.runner('Arbiter').modules()
    assert loop.promotion_max_calls(5,1,2)==48
    assert loop.promotion_max_calls(5,1,2,start_round=5)==8
    suite=ex.read(ex.PLAN_ROOT/'suite.json')
    assert suite['normal_max_calls']==153
    assert suite['hard_max_calls']==336


def test_retains_accepted_state_and_rolls_back_bad_candidate(tmp_path, monkeypatch):
    base=ex.runner('Arbiter')
    _,loop,*_=base.modules()
    def score(trial, task, carrier):
        directory=Path(trial['directory'])
        if 'validation_baseline' in directory.parts:
            return False
        round_index=int(directory.parents[2].name)
        # Artificial gate outcomes exercise control flow, not model performance.
        if round_index==1:
            return directory.name=='candidate'
        if round_index==3 and directory.name=='candidate':
            return False
        return True
    monkeypatch.setattr(loop,'promotion_pass',score)
    base.smoke(tmp_path/'collection')
    logs=[json.loads(l) for l in (tmp_path/'collection/promotions.jsonl').read_text().splitlines()]
    assert logs[0]['accepted']
    assert logs[2]['reason']=='regression'
    assert not any(g['accepted'] for g in logs[1:])
    final=ex.read(tmp_path/'collection/rounds/5/commit.json')['blue']
    assert len(final['entries'])==1 and final['entries'][0]['body']['created_round']==1
    assert all(g['retained_state_hash']==logs[0]['retained_state_hash'] for g in logs)
    assert (tmp_path/'collection/audits/exposure_audit.json').exists()
    baseline=ex.read(tmp_path/'collection/validation_baseline.json')
    assert len(baseline['trials'])==4 and not any(baseline['scores'].values())
    assert all(len(g['trials'])==4 for g in logs)
    assert all(t['role']=='candidate' for g in logs for t in g['trials'])
    assert [g['retained_validation_passed'] for g in logs]==[4]*5
    for g in logs:
        assert ex.read(g['retained_cache_path'])['state_hash']==g['retained_state_hash']
    # Cached baseline receipts cannot be silently edited after collection.
    baseline['scores'][next(iter(baseline['scores']))]=True
    ex.save(tmp_path/'collection/validation_baseline.json',baseline)
    from experiments.loop_probes.continuous_audit import exposure_audit
    with pytest.raises(loop.measure.MeasurementRefused,match='incumbent validation cache changed'):
        exposure_audit(tmp_path/'collection')


def test_v3_client_and_guard_use_original_model_and_compatible_limits(tmp_path):
    from decimal import Decimal
    base=ex.runner('Arbiter')
    launch,loop,shared,_,counter_type=base.modules()
    response={'input_tokens':1,'output_tokens':16000,'finish_reason':'stop'}
    guard=shared.UsageGuard(lambda **request:dict(response),counter_type(),tmp_path,
        envelope=Decimal('Infinity'),direct_only=True,allowed_systems={loop.rb.SYSTEM_REPAIR:16000})
    request={'model':'deepseek/deepseek-chat','max_tokens':16000,
             'messages':[{'role':'system','content':loop.rb.SYSTEM_REPAIR},{'role':'user','content':'local check'}]}
    assert guard(**request)['output_tokens']==16000
    with pytest.raises(shared.UsageStop,match='unexpected model'):
        guard(**dict(request,model='deepseek-v4-flash'))
    response['output_tokens']=16001
    with pytest.raises(shared.UsageStop,match='provider_output_exceeds_requested_limit'):
        guard(**request)
    client=shared.build_launch_client({}, {'client_config':launch.client_identity(),'max_calls':112}, guard)
    assert client.config.maximum_output_tokens==16000
    assert client.config.api_key_env=='OPENROUTER_API_KEY'
    assert client.config.base_url_env=='OPENROUTER_BASE_URL'
    assert client.config.model_id=='deepseek/deepseek-chat'


def test_initial_validation_baseline_is_reserved_once():
    _,loop,*_=ex.runner('Arbiter').modules()
    # 4 B0 requests + 20 candidate requests, each allowing one format correction.
    assert loop.promotion_max_calls(5,1,2)==48
    assert loop.promotion_max_calls(5,1,2,start_round=1)==40
    assert loop.promotion_max_calls(5,1,2,start_round=5)==8


def test_original_v3_sends_no_v4_thinking_parameters(monkeypatch):
    from types import SimpleNamespace
    import openai
    ex.runner('Arbiter').modules()
    from r3e.loop.env import ThinkingTransport
    captured={}
    def create(**request):
        captured.update(request)
        return SimpleNamespace(id='offline-test',choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"answer":"local"}',refusal=None),finish_reason='stop')],
            usage=SimpleNamespace(prompt_tokens=10,completion_tokens=1))
    def client(**options):
        assert options['base_url']=='https://openrouter.ai/api/v1'
        assert options['api_key']=='test-key-not-a-secret'
        assert options['max_retries']==0
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(openai,'OpenAI',client)
    transport=ThinkingTransport({'OPENROUTER_API_KEY':'test-key-not-a-secret',
        'OPENROUTER_BASE_URL':'https://openrouter.ai/api/v1'},key_name='OPENROUTER_API_KEY',
        url_name='OPENROUTER_BASE_URL',thinking='default',timeout_seconds=1500)
    result=transport(model='deepseek/deepseek-chat',max_tokens=16000,messages=[{'role':'user','content':'local'}])
    assert result['content']=='{"answer":"local"}'
    assert 'thinking' not in captured and 'reasoning_effort' not in captured and 'extra_body' not in captured


def test_only_question_materials_differ_from_previous_v3_plan():
    mapping={'Arbiter':'Mux','VendingTiming':'Prob015','VendingState':'Counter'}
    for design in ex.DESIGNS:
        old=ex.read(HERE/'plan-v3-original-v1'/mapping[design]/'plan.json')
        new=ex.read(ex.PLAN_ROOT/design/'plan.json')
        for key in ('code','blue_config','client_config','promotion','learning','retrieval','slots','anchor_probes',
                    'rounds','slots_per_round','seed','anchor_repeats','reserved_collision_retries','max_calls','tokenizer'):
            assert new[key]==old[key],key
        assert len(new['anchors'])==len(old['anchors'])==1
        assert len(new['validation_tasks'])==len(old['validation_tasks'])==2


def test_v3_launch_uses_openrouter_credentials_without_deepseek_balance(tmp_path, monkeypatch):
    from types import SimpleNamespace
    base=ex.runner('Arbiter')
    _,_,shared,_,counter_type=base.modules()
    from r3e.loop import env as client_env
    seen={}
    class LocalTransport:
        def __init__(self, env, **settings):
            seen.update(settings)
            assert env['OPENROUTER_BASE_URL']=='https://openrouter.ai/api/v1'
            assert env['OPENROUTER_API_KEY']=='local-only-key'
    monkeypatch.setattr(client_env,'ThinkingTransport',LocalTransport)
    monkeypatch.setattr(client_env,'deepseek_balance',lambda *a,**k: (_ for _ in ()).throw(AssertionError('wrong balance endpoint')))
    credentials=tmp_path/'openrouter.env'
    credentials.write_text('OPENROUTER_API_KEY=local-only-key\n')
    args=SimpleNamespace(run_dir=tmp_path/'run',env_file=credentials,plan_dir=ex.PLAN_ROOT/'Arbiter')
    plan=ex.read(args.plan_dir/'plan.json')
    def collect(plan,out,*,client,counter):
        assert client.config.model_id=='deepseek/deepseek-chat'
        assert client.config.provider_id=='openrouter'
        return {'status':'complete'}
    base.launch_collection(args,plan,counter_type(),collect,shared,allowed_systems={})
    assert seen['thinking']=='default'
    assert seen['key_name']=='OPENROUTER_API_KEY'
    assert seen['url_name']=='OPENROUTER_BASE_URL'
    assert ex.read(args.run_dir/'launch_identity.json')['balance_precheck']['checked'] is False


def test_selected_historical_state_defect_has_real_empty_memory_failure():
    row=next(r for r in ex.verify_questions() if r['family']=='VendingState')
    task=ex.ROOT/row['buggy_rtl']
    slot=next(p for p in task.parents if p.name=='r4_s0')
    delivery=ex.read(slot/'reference/delivery.json')
    encounter=json.loads((slot/'reference/blue/encounters.jsonl').read_text().splitlines()[0])['result']
    assert delivery['payload']['entries']==[]
    assert encounter['attempts'][-1]['tier']=='visible_fail'


def test_fsm_functional_success_is_not_mislabeled_zero_pass():
    replay=ex.read(ex.ROOT/'analysis/medium-high-selection-20261016/selected_originals/fsm_full_3/replay.json')
    candidates=[v for v in replay['variants'] if v.get('source')]
    assert len(candidates)==9
    assert sum(v['passed'] for v in candidates)==1


def test_arbiter_oracle_unknown_warmup_bits_are_not_artificial_failures():
    spec=importlib.util.spec_from_file_location('medium_high_builder',HERE/'prepare_medium_high.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    package=ex.MATERIAL_ROOT/'Arbiter/package'
    clean=(package/'src/rtl/sequence.sv').read_text()
    initialized=clean.replace('endmodule',"initial begin gnt_0=0;gnt_1=0;gnt_2=0;gnt_3=0;end\nendmodule")
    out=builder.simulate({'dut.sv':initialized,'tb.sv':(package/'suites/W_bug/tb.sv').read_text()})
    assert 'TESTBENCH PASS' in out and 'CHECK_FAIL' not in out
