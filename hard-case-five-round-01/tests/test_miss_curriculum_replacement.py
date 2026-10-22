import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import pytest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('miss_curriculum_experiment',HERE/'experiment-miss-curriculum-v1.py')
ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)

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


def core():
    _,loop,*_=ex.runner('Prob003').modules();m=ex.material('Prob003');c=m['carriers'][0]
    p=loop.red907.public_material(Path(c['package']),ex.read(c['suite_freeze']))
    return loop,m,p


def observation():
    return [{'round':1,'label':'public_pass_single_sample_hidden_unknown','source_hash':'current-run-public-success'}]


def test_exact_miss_archive_variant_and_seed_removed():
    rows=ex.verify_questions();m=ex.material('Prob003');r=rows[0]
    assert r['case_id']=='handoff:Prob003:eval_miss_branch'
    assert len(rows)==3 and ex.DESIGNS==('Prob003','Prob023','Prob017')
    previous=[json.loads(l) for l in (HERE/'cases-prob003-match-branch-v1.jsonl').read_text().splitlines()]
    assert rows[1:]==previous[1:]
    assert m['mechanism_focus'] is None
    with tarfile.open(ex.ROOT/r['source_archive']) as archive:
        raw=archive.extractfile(r['archive_member']).read()
    task=Path(m['anchors'][0]['task_dir'])
    assert raw==(ex.ROOT/r['buggy_rtl']).read_bytes()==(task/'public/repo/rtl/sequence.sv').read_bytes()
    clean=(Path(m['carriers'][0]['package'])/'src/rtl/sequence.sv').read_text()
    assert raw.decode()==clean.replace('        sf6:\n\t\t\tnstate=data?sf1:s1;','        sf6:\n\t\t\tnstate=data?s1:sf1;')
    assert ex.read(ex.PLAN_ROOT/'Prob003/plan.json')['mechanism_focus'] is None
    for d in ['Prob023','Prob017']:
        assert ex.material(d)==ex.read(HERE/'materials-prob003-match-branch-v1'/d/'materials.json')
    assert ex.VALIDATION_ROOT==HERE/'validation-handoff-prob003-red-only-v1'


def test_golden_passes_and_miss_defect_fails_both_evaluations():
    loop,m,p=core();c=m['carriers'][0];task=loop.rb.RepoTask.load(Path(m['anchors'][0]['task_dir']))
    for rtl,expected,hidden in [(p['clean_rtl'],'visible_pass','pass'),((task.repo/'rtl/sequence.sv').read_text(),'visible_fail','fail')]:
        result=loop.rb.execute(task,{'rtl/sequence.sv':rtl})
        assert result.tier==expected and result.evidence['suites']['W_preserve']['result']=='visible_pass'
        assert loop.measure._evaluate(task,{'rtl/sequence.sv':rtl},ex.read(c['evaluator_freeze']),Path(c['evaluator_root'])/'evaluator')['result']==hidden
    exam=loop.mutant_identity(p,(task.repo/'rtl/sequence.sv').read_text())
    for v in ex.read(ex.VALIDATION_ROOT/'Prob003/validation.json')['tasks']:
        vt=loop.rb.RepoTask.load(Path(v))
        assert exam!=loop.mutant_identity(p,(vt.repo/'rtl/sequence.sv').read_text())
    assert ex.read(ex.PLAN_ROOT/'Prob003/plan.json')['anchors'][0]['mutant_identity']==exam


def test_public_success_gates_boundaries_but_never_compound_faults():
    loop,m,p=core();g=loop.targeted_prompts
    assert g.curriculum_stage(p['carrier_id'],1,[])['preferred_states'][0]=='s5'
    assert g.curriculum_stage(p['carrier_id'],2,[])['preferred_states'][0]=='sf5'
    assert g.curriculum_stage(p['carrier_id'],3,[])['preferred_states'][0]=='sf4'
    assert not g.curriculum_stage(p['carrier_id'],5,[])['allow_group_boundary_changes']
    boundary=p['clean_rtl'].replace('        s6:\n            nstate=data?sf1:s1;','        s6:\n            nstate=data?s1:sf1;')
    proposal={'status':'proposal','buggy_rtl':boundary}
    assert g.curriculum_violation(p,proposal,3,observation())
    assert g.curriculum_violation(p,proposal,4,observation()) is None
    assert g.curriculum_stage(p['carrier_id'],5,observation())['maximum_next_state_expressions']==1
    double=boundary.replace('nstate=sf5;','nstate=sf4;')
    assert g.curriculum_violation(p,{'status':'proposal','buggy_rtl':double},5,observation())
    for round_index in range(1,6):
        inv=g.transition_inventory(p,round_index,observation() if round_index>1 else [])
        assert all(s['state'] not in {'idle','default'} for s in inv['sites'])
    assert g.transition_inventory(p,1,[])['sites'][0]['state']=='s5'
    # Other designs retain the original two-success/latest-pass gate.
    assert not g.curriculum_stage('chipbench_Prob023',5,observation())['allow_group_boundary_changes']
    assert not g.curriculum_stage('chipbench_Prob017',5,observation())['allow_group_boundary_changes']


def test_author_request_has_public_lesson_but_no_exam_seed(tmp_path):
    loop,m,p=core()
    from r3e.loop.token_count import TokenCounter
    from r3e.loop.env import build_client
    from r3e.loop.budget import BudgetedClient
    from r3e.loop.fakes import _reply
    requests=[]
    def transport(**request):
        requests.append(json.loads(request['messages'][-1]['content']))
        return _reply({'abstain':'offline fixture only'},1)
    client=BudgetedClient(build_client({'DEEPSEEK_MODEL':'fake-local'},transport=transport,maximum_output_tokens=16000),max_calls=2)
    counter=TokenCounter();plan=ex.read(ex.PLAN_ROOT/'Prob003/plan.json');identity=loop.blue_identity(plan)
    incoming=loop.state.snapshot(0,identity);target,omissions=loop.state.target_view(incoming,p['specification'],identity,counter)
    loop.red.propose(p,[],round_index=1,snapshot_hash=loop.hash_payload(incoming),red_state_hash='offline',seed=700,
        directory=tmp_path/'red',client=client,counter=counter,output_tokens=16000,target_blue=target,
        target_omissions=omissions,mechanism_focus=m['mechanism_focus'])
    request=requests[0]
    assert 'mechanism_focus' not in request
    assert 'last-bit decision' in request['round_curriculum']['focus']
    assert request['eligible_transition_sites']['sites'][0]['state']=='s5'
    assert 'eval_miss_branch' not in json.dumps(request)
    assert request['target_blue']['spec_selected_experience']['entries']==[]


def test_other_two_designs_author_guidance_and_blue_code_are_unchanged():
    loop,m,p=core();g=loop.targeted_prompts
    path=HERE/'source-promotion-feedback-training-v1/r3e/loop/targeted_prompts.py'
    spec=importlib.util.spec_from_file_location('r3e.loop.previous_targeted_prompts',path)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    two=[{'round':1,'label':'public_pass_single_sample_hidden_unknown','source_hash':'a'},
         {'round':2,'label':'public_pass_single_sample_hidden_unknown','source_hash':'b'}]
    for design in ['chipbench_Prob023','chipbench_Prob017']:
        for round_index in range(1,6):
            observations=[r for r in two if r['round']<round_index]
            assert g.curriculum_stage(design,round_index,observations)==old.curriculum_stage(design,round_index,observations)
            assert g.red_guidance(design,round_index,observations)==old.red_guidance(design,round_index,observations)
    for relative in ['r3e/loop/repo_blue.py','r3e/loop/continuous_state.py','r3e/loop/repair_diagnostics.py']:
        assert (ex.PROMOTION_SOURCE/relative).read_bytes()==(HERE/'source-promotion-feedback-training-v1'/relative).read_bytes()
