import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

HERE = Path(__file__).resolve().parents[1]
MODEL = 'deepseek/deepseek-chat-v3-0324'
spec = importlib.util.spec_from_file_location('v3_0324_experiment',HERE/'experiment-v3-0324-listed-v1.py')
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)


@pytest.fixture(scope='module',autouse=True)
def isolate_core():
    def owned(name):
        return name in ('r3e','experiments') or name.startswith(('r3e.','experiments.'))
    saved={k:v for k,v in sys.modules.items() if owned(k)}
    paths=list(sys.path)
    for k in list(saved):sys.modules.pop(k)
    sys.path.insert(0,str(ex.PROMOTION_SOURCE))
    yield
    for k in list(sys.modules):
        if owned(k):sys.modules.pop(k)
    sys.modules.update(saved)
    sys.path[:]=paths


def test_new_model_is_frozen_and_experiment_unchanged():
    for design in ex.DESIGNS:
        plan=ex.read(ex.PLAN_ROOT/design/'plan.json')
        old=ex.read(HERE/'plan-v3-listed-v1'/design/'plan.json')
        assert plan['client_config']['model_id']==MODEL
        assert plan['client_config']['maximum_output_tokens']==16000
        assert plan['blue_config']['context_tokens']==128000
        for key in ('blue_config','promotion','learning','retrieval','carriers','anchors','validation_tasks',
                    'rounds','slots_per_round','anchor_repeats','red_output_tokens','max_calls'):
            assert plan[key]==old[key],key
    before=ex.read(HERE/'promotion_code_batch_v1.json')
    after=ex.read(HERE/'promotion_code_v3_0324_v1.json')
    assert {p for p in before if before[p]!=after[p]}=={
        'experiments/loop_probes/continuous_launch.py','experiments/loop_probes/red907_launch.py'}


def test_launch_passes_0324_to_red_and_blue_transport(tmp_path,monkeypatch):
    base=ex.runner('Prob001')
    launch,loop,shared,_,counter=base.modules()
    from r3e.loop import env as env_module
    requests=[]
    settings={}
    class LocalTransport:
        def __init__(self,env,**options):
            settings.update(options)
            assert env['OPENROUTER_API_KEY']=='test-only-not-a-real-key'
            assert env['OPENROUTER_BASE_URL']=='https://openrouter.ai/api/v1'
        def __call__(self,**request):
            requests.append(request)
            return dict(content='{"ok":true}',input_tokens=1,output_tokens=1,finish_reason='stop',
                        provider_request_id='local-mock-response')
    monkeypatch.setattr(env_module,'ThinkingTransport',LocalTransport)
    credentials=tmp_path/'test.env'
    credentials.write_text('OPENROUTER_API_KEY=test-only-not-a-real-key\nOPENROUTER_MODEL='+MODEL+'\n')
    args=SimpleNamespace(run_dir=tmp_path/'run',env_file=credentials,plan_dir=ex.PLAN_ROOT/'Prob001')
    plan=ex.read(args.plan_dir/'plan.json')
    def collect(plan,out,*,client,counter):
        for phase,system in [('red',loop.red.SYSTEM),('blue_inference',loop.rb.SYSTEM_REPAIR)]:
            with client.in_phase(phase):
                response=client.complete_json(messages=[dict(role='system',content=system),
                    dict(role='user',content='Return JSON for a local transport check.')],seed=1)
                assert response['result']=={'ok':True}
        return {'status':'complete'}
    base.launch_collection(args,plan,counter(),collect,shared,
        allowed_systems={loop.red.SYSTEM:16000,loop.rb.SYSTEM_REPAIR:16000})
    assert len(requests)==2 and all(r['model']==MODEL for r in requests)
    assert all(r['max_tokens']==16000 and r['response_format']=={'type':'json_object'} for r in requests)
    assert all('extra_body' not in r and 'thinking' not in r for r in requests)
    assert settings['thinking']=='default'
    assert settings['key_name']=='OPENROUTER_API_KEY'
    assert ex.read(args.run_dir/'launch_identity.json')['client']['model_id']==MODEL


def test_guard_rejects_old_model_before_transport(tmp_path):
    from decimal import Decimal
    _,loop,shared,_,counter=ex.runner('Prob001').modules()
    seen=[]
    guard=shared.UsageGuard(lambda **r:seen.append(r),counter(),tmp_path,
        envelope=Decimal('Infinity'),direct_only=True,allowed_systems={loop.rb.SYSTEM_REPAIR:16000})
    request=dict(model='deepseek/deepseek-chat',max_tokens=16000,
                 messages=[dict(role='system',content=loop.rb.SYSTEM_REPAIR),dict(role='user',content='JSON check')])
    with pytest.raises(shared.UsageStop,match='unexpected model'):
        guard(**request)
    assert not seen and guard.calls==0


def test_old_model_override_in_credentials_is_rejected(tmp_path):
    base=ex.runner('Prob001')
    _,loop,shared,_,counter=base.modules()
    credentials=tmp_path/'test.env'
    credentials.write_text('OPENROUTER_API_KEY=test-only-not-a-real-key\nOPENROUTER_MODEL=deepseek/deepseek-chat\n')
    args=SimpleNamespace(run_dir=tmp_path/'run',env_file=credentials,plan_dir=ex.PLAN_ROOT/'Prob001')
    with pytest.raises(ValueError,match='fixed to DeepSeek V3-0324'):
        base.launch_collection(args,ex.read(args.plan_dir/'plan.json'),counter(),lambda *a,**kw:None,
                               shared,allowed_systems={loop.rb.SYSTEM_REPAIR:16000})
    assert not args.run_dir.exists()
