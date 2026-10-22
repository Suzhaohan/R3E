import importlib.util
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pretest_experiment',HERE/'experiment-pretest-v1.py')
ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)

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


def run_batch(tmp_path,monkeypatch,passes,inconclusive=False,tamper=False,online_candidate=False):
    original=ex.runner;order=[]
    def runner(design):
        base=original(design)
        def smoke(out):
            _,loop,*_=base.modules()
            from r3e.loop.env import build_client
            from r3e.loop.budget import BudgetedClient
            from r3e.loop.fakes import _reply
            from r3e.loop.token_count import TokenCounter
            m=ex.material(design);clean=(Path(m['carriers'][0]['package'])/'src/rtl/sequence.sv').read_text()
            count=0
            def transport(**request):
                nonlocal count
                u=json.loads(request['messages'][-1]['content'])
                if 'carrier' in u:
                    order.append((design,'red'))
                    if online_candidate and design=='Prob001':
                        return _reply(dict(candidates=[dict(edits=[dict(find='a_tem[6:0]',replace='a_tem[5:0]')],
                            violated_requirement='offline public mutation witness',spec_basis='unchanged public specification')]),1)
                    return _reply({'abstain':'offline fixture'},1)
                count+=1;phase='pretest' if count<=2 else 'baseline' if count<=6 else 'B5'
                order.append((design,phase))
                content=clean if (count<=passes[design] or count>6) else u['files']['rtl/sequence.sv']['content']
                return _reply(dict(files=[dict(file='rtl/sequence.sv',content=content)],edit='offline fixture'),1)
            client=build_client({'DEEPSEEK_MODEL':'fake-local'},transport=transport,maximum_output_tokens=16000)
            counter=TokenCounter();plan=loop.make_plan(m['carriers'],m['anchors'],counter=counter,
                client_config=client.config.public_identity,rounds=5,slots_per_round=1,seed=700,carrier_mode='fixed',fixed_carrier_index=0,
                anchor_repeats=2,mechanism_focus=m['mechanism_focus'],red_output_tokens=16000,reserved_collision_retries=1)
            if inconclusive:
                original_trial=loop.measure.run_blue
                def invalid(*a,**kw):raise loop.measure.DirectContextLimit('offline fixture')
                monkeypatch.setattr(loop.measure,'run_blue',invalid)
            result=loop.collect(plan,out,client=BudgetedClient(client,max_calls=plan['max_calls']),counter=counter)
            if inconclusive:monkeypatch.setattr(loop.measure,'run_blue',original_trial)
            ex.save(out/'simulation_only.json',dict(fake=True,model_calls=0))
            if tamper:
                data=ex.read(out/'initial_exam.json');data['passed']=999;ex.save(out/'initial_exam.json',data)
            return result
        base.smoke=smoke
        return base
    monkeypatch.setattr(ex,'runner',runner)
    root=tmp_path/'batch'
    monkeypatch.setattr(sys,'argv',['experiment.py','smoke','--run-dir',str(root)])
    return root,order,ex.main


def test_full_pass_stops_entire_batch_without_training(tmp_path,monkeypatch):
    root,order,run=run_batch(tmp_path,monkeypatch,dict.fromkeys(ex.DESIGNS,2));run()
    gate=ex.read(root/'initial_exam_gate.json')
    assert gate['decision']=='stop_saturated' and gate['passed']==gate['samples']==6
    assert len(order)==6 and all(p=='pretest' for _,p in order)
    assert not (root/'training_barrier.json').exists()
    result=ex.read(root/'promotion_results.json')
    assert result['actual_requests']==6 and not result['comparison']['complete']
    for d in ex.DESIGNS:
        c=root/d/'collection'
        assert ex.read(c/'collection.json')['committed_rounds']==0
        assert not (c/'validation_baseline.json').exists()
        assert not (c/'rounds/1').exists()
        assert result['designs'][d]['final_exam'] is None


def test_partial_reuses_static_results_and_preserves_global_barriers(tmp_path,monkeypatch):
    root,order,run=run_batch(tmp_path,monkeypatch,dict(zip(ex.DESIGNS,[2,1,0])));run()
    assert ex.read(root/'initial_exam_gate.json')['decision']=='continue'
    assert all(p=='pretest' for _,p in order[:6])
    assert sum(p=='pretest' for _,p in order)==6
    last_red=max(i for i,(_,p) in enumerate(order) if p=='red')
    assert min(i for i,(_,p) in enumerate(order) if p=='B5')>last_red
    results=ex.read(root/'promotion_results.json')
    assert results['comparison']['complete']
    assert results['comparison']['static_passed_completed_designs']==3
    assert results['comparison']['promotion_passed_completed_designs']==6
    for d in ex.DESIGNS:
        c=root/d/'collection';initial=ex.read(c/'initial_exam.json')
        assert ex.read(c/'collection.json')['committed_rounds']==5
        rows=[json.loads(s) for s in (c/'probes.jsonl').read_text().splitlines()]
        assert [r for r in rows if r['snapshot']==0]==initial['probe_rows']
        for name,digest in initial['evidence_hashes'].items():assert ex.sha(c/name)==digest
        assert ex.sha(c/'initial_exam.json')==next(m['initial_exam_sha256'] for m in ex.read(root/'initial_exam_gate.json')['members'] if m['design']==d)
        assert len(rows)==4


def test_inconclusive_stops_without_claiming_difficulty(tmp_path,monkeypatch):
    root,order,run=run_batch(tmp_path,monkeypatch,dict.fromkeys(ex.DESIGNS,0),inconclusive=True)
    with pytest.raises(SystemExit) as error:run()
    assert error.value.code==2
    assert ex.read(root/'initial_exam_gate.json')['decision']=='stop_inconclusive'
    assert not order
    assert not (root/'training_barrier.json').exists()


def test_tampered_exam_rejected_before_training_calls(tmp_path,monkeypatch):
    root,order,run=run_batch(tmp_path,monkeypatch,dict.fromkeys(ex.DESIGNS,0),tamper=True)
    with pytest.raises(ValueError,match='initial static exam record changed'):run()
    assert len(order)==6 and all(p=='pretest' for _,p in order)


def test_training_promotion_still_works_after_pretest(tmp_path,monkeypatch):
    root,order,run=run_batch(tmp_path,monkeypatch,dict.fromkeys(ex.DESIGNS,0),online_candidate=True);run()
    result=ex.read(root/'promotion_results.json')
    first=result['designs']['Prob001']
    assert first['qualified_online_practices']>=1
    assert first['accepted_promotions']==1
    assert first['certified_validation']['initial_passed']==0
    assert first['certified_validation']['retained_passed']==4
    assert first['final_exam']=={'B_0':0,'B_5':2}
