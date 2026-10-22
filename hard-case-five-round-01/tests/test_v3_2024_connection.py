"""Verify original V3 reaches the wire and cannot fall back to the 2025 release."""
import importlib.util
import json
from pathlib import Path
import sys
from decimal import Decimal
import pytest
HERE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
ex=module('v3_2024_experiment',HERE/'experiment.py')

@pytest.fixture(autouse=True)
def isolate():
    def owned(k):return k in ('r3e','experiments') or k.startswith(('r3e.','experiments.'))
    saved={k:v for k,v in sys.modules.items() if owned(k)};paths=list(sys.path)
    for k in saved:sys.modules.pop(k)
    sys.path.insert(0,str(ex.PROMOTION_SOURCE))
    yield
    for k in list(sys.modules):
        if owned(k):sys.modules.pop(k)
    sys.modules.update(saved);sys.path[:]=paths


def test_original_v3_client_and_pre_http_guard_ignore_stale_credential_model(tmp_path):
    launch,loop,shared,_,Counter=ex.runner('Prob003').modules()
    from r3e.loop.fakes import _reply
    sent=[]
    def transport(**request):sent.append(request);return _reply({'ok':True},1)
    guard=shared.UsageGuard(transport,Counter(),tmp_path,envelope=Decimal('Infinity'),direct_only=True,
        allowed_systems={loop.rb.SYSTEM_REPAIR:16000})
    messages=[{'role':'system','content':loop.rb.SYSTEM_REPAIR},{'role':'user','content':'Connection unit test; return JSON.'}]
    with pytest.raises(shared.UsageStop,match='unexpected model'):
        guard(model='deepseek/deepseek-chat-v3-0324',max_tokens=16000,messages=messages)
    assert not sent
    plan={'client_config':launch.client_identity(),'max_calls':1}
    client=shared.build_launch_client({'OPENROUTER_MODEL':'deepseek/deepseek-chat-v3-0324'},plan,guard)
    client.complete_json(messages=messages,seed=1)
    assert len(sent)==1 and sent[0]['model']=='deepseek/deepseek-chat'
    assert sent[0]['max_tokens']==16000
    assert client.config.model_id=='deepseek/deepseek-chat'


def test_no_experiment_mechanism_changed_during_model_migration():
    launch,loop,*_=ex.runner('Prob003').modules()
    assert launch.client_identity()['model_id']=='deepseek/deepseek-chat'
    assert ex.MODEL_RELEASE=='2024-12-26'
    old=HERE/'source-promotion-local-patch-v2'
    # No repair, selection, experience, scoring, validation or scheduling changes.
    expected_changes={'experiments/loop_probes/continuous_launch.py',
        'experiments/loop_probes/red907_launch.py','r3e/loop/env.py'}
    manifest=ex.read(HERE/'promotion_code_v3_2024_local_patch_v2.json')
    actual_changes={name for name in manifest if (old/name).read_bytes()!=(ex.PROMOTION_SOURCE/name).read_bytes()}
    assert actual_changes==expected_changes
    assert loop.CONFIG.budget_k==2 and loop.TRAINING_CONFIG.budget_k==4
    assert 'unchanged_final_policy' not in loop.INITIAL_EXAM_POLICY
    assert ex.DESIGNS==('Prob003','Prob023','Prob017')
    assert ex.verify_launch_guard('Prob003',(launch,loop,*ex.runner('Prob003').modules()[2:]))['model_calls']==0
