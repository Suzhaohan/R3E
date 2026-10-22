"""Exercise the real launcher and UsageGuard with a local transport; zero API calls."""
import importlib.util,json,sys,hashlib
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import pytest
HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('guard_fixed_experiment',HERE/'experiment-prob003-table-guard-v1.py');ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
MODEL='deepseek/deepseek-chat-v3-0324'

@pytest.fixture(autouse=True)
def isolate_core():
    def owned(k):return k in ('r3e','experiments') or k.startswith(('r3e.','experiments.'))
    saved={k:v for k,v in sys.modules.items() if owned(k)};paths=list(sys.path)
    for k in saved:sys.modules.pop(k)
    sys.path.insert(0,str(ex.PROMOTION_SOURCE))
    yield
    for k in list(sys.modules):
        if owned(k):sys.modules.pop(k)
    sys.modules.update(saved);sys.path[:]=paths


def test_failed_real_request_reproduces_old_block_and_passes_new_registration(tmp_path):
    _,loop,shared,_,counter=ex.runner('Prob003').modules()
    path=HERE/'prob003-table-20261018-235509/collection/rounds/1/r1_s0/online/blue/submissions/request_0001.json'
    messages=ex.read(path)['messages'];seen=[]
    original={loop.red.SYSTEM:16000,loop.rb.SYSTEM_REPAIR:16000}
    for label,systems in [('old',original),('new',ex.registered_systems('Prob003',loop,original))]:
        work=tmp_path/label;work.mkdir()
        guard=shared.UsageGuard(lambda **r:(seen.append(r) or dict(input_tokens=1,output_tokens=1)),counter(),work,envelope=Decimal('Infinity'),direct_only=True,allowed_systems=systems)
        request=dict(messages=messages,model=MODEL,max_tokens=16000)
        if label=='old':
            with pytest.raises(shared.UsageStop,match='before HTTP'):guard(**request)
            assert not seen and guard.calls==0
        else:
            guard(**request);assert len(seen)==1 and guard.calls==1


@pytest.mark.parametrize('design',['Prob001','Prob023','Prob003'])
def test_actual_paid_launch_path_registers_appropriate_systems_without_network(tmp_path,monkeypatch,design):
    base=ex.runner(design);_,loop,shared,_,counter=base.modules()
    from r3e.loop import env as env_module,transition_repair
    seen=[]
    class LocalTransport:
        def __init__(self,*args,**kwargs):pass
        def __call__(self,**request):
            seen.append(request)
            return dict(content='{"ok":true}',input_tokens=1,output_tokens=1,finish_reason='stop',provider_request_id='offline-launch-guard-check')
    monkeypatch.setattr(env_module,'ThinkingTransport',LocalTransport)
    credentials=tmp_path/'local.env';credentials.write_text('OPENROUTER_API_KEY=fake-offline-key\n')
    args=SimpleNamespace(run_dir=tmp_path/'run',env_file=credentials,plan_dir=ex.PLAN_ROOT/design)
    plan=ex.read(args.plan_dir/'plan.json');original={loop.red.SYSTEM:16000,loop.rb.SYSTEM_REPAIR:16000}
    systems=list(original)+([transition_repair.SYSTEM] if design=='Prob003' else [])
    def collect(plan,out,*,client,counter):
        for system in systems:
            client.complete_json(messages=[dict(role='system',content=system),dict(role='user',content='Local transport only')],seed=1)
        return dict(status='complete')
    # This enters the actual patched launch_collection wrapper, client and UsageGuard.
    base.launch_collection(args,plan,counter(),collect,shared,allowed_systems=original)
    assert len(seen)==len(systems) and all(r['model']==MODEL and r['max_tokens']==16000 for r in seen)
    identity=ex.read(args.run_dir/'launch_identity.json')
    assert len(identity['allowed_system_hashes'])==(3 if design=='Prob003' else 2)
    assert identity['allowed_system_hashes']=={hashlib.sha256(s.encode()).hexdigest():16000 for s in systems}


def test_unknown_system_wrong_model_and_wrong_output_cap_still_blocked(tmp_path):
    modules=ex.runner('Prob003').modules();_,loop,shared,_,counter=modules
    systems=ex.registered_systems('Prob003',loop,{loop.red.SYSTEM:16000,loop.rb.SYSTEM_REPAIR:16000});seen=[]
    for i,(system,model,limit) in enumerate([('unregistered',MODEL,16000),(loop.rb.SYSTEM_REPAIR,'wrong-model',16000),(loop.rb.SYSTEM_REPAIR,MODEL,16001)]):
        work=tmp_path/str(i);work.mkdir()
        guard=shared.UsageGuard(lambda **r:seen.append(r),counter(),work,envelope=Decimal('Infinity'),direct_only=True,allowed_systems=systems)
        with pytest.raises(shared.UsageStop):guard(messages=[dict(role='system',content=system),dict(role='user',content='no request')],model=model,max_tokens=limit)
        assert guard.calls==0
    assert not seen
    assert ex.verify_launch_guard('Prob003',modules)==dict(status='PASS',registered_systems=3,model_calls=0)
