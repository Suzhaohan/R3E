"""One fresh exploratory transfer comparison; at most 14 paid calls, never final exams.

Two online-authored distinct practice defects, one learning repair, then one paired
comparison on the second defect. Report every outcome; do not retry a failed probe.
"""
import argparse
from dataclasses import replace
from datetime import datetime,timezone
from decimal import Decimal
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('transfer_probe_experiment',HERE/'experiment.py')
ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
MAX_CALLS=14


def execute(out,key_file):
    ex.verify_questions()
    ex.runner('Prob003').verify_import()
    if out.exists():raise ValueError('fresh probe directory required')
    out.mkdir(parents=True)
    _,loop,shared,_,counter_type=ex.runner('Prob003').modules()
    from r3e.loop.env import build_client,ThinkingTransport
    from r3e.loop.budget import BudgetedClient
    key=key_file.read_text().strip()
    if not key or any(c in key for c in ('\n','\r','\x00')):raise ValueError('invalid configured raw key file')
    env={'OPENROUTER_API_KEY':key,'OPENROUTER_BASE_URL':'https://openrouter.ai/api/v1','OPENROUTER_MODEL':'deepseek/deepseek-chat-v3-0324'};del key
    transport=ThinkingTransport(env,key_name='OPENROUTER_API_KEY',url_name='OPENROUTER_BASE_URL',thinking='default',timeout_seconds=300,
        failure_dir=out/'unparseable',error_log=out/'provider_errors.jsonl',response_log=out/'provider_responses.jsonl')
    counter=counter_type()
    guard=shared.UsageGuard(transport,counter,out,envelope=Decimal('Infinity'),direct_only=True,
        allowed_systems={loop.red.SYSTEM_TRANSITION:16000,loop.rb.SYSTEM_REPAIR:16000})
    client=BudgetedClient(build_client(env,prefix='OPENROUTER',maximum_output_tokens=16000,timeout_seconds=300,transport=guard),max_calls=MAX_CALLS)
    client.on_call=lambda row:loop.append(out/'calls.jsonl',row)
    material=ex.material('Prob003');carrier=material['carriers'][0]
    public=loop.red907.public_material(Path(carrier['package']),ex.read(carrier['suite_freeze']))
    # Probe deliberately uses the same 4 functional attempts for both paired arms;
    # no format retries and no provider retries. This is not a formal five-round score.
    cfg=replace(loop.TRAINING_CONFIG,format_corrections=0)
    identity={'runner':cfg.__dict__,'client':client.config.public_identity,'tokenizer':counter.identity,
        'runner_code':loop.code_identity()['r3e/loop/repo_blue.py']}
    b0=loop.state.snapshot(0,identity);incoming=loop.state.snapshot(1,identity,[],b0)
    excluded=set()
    for path in [material['anchors'][0]['task_dir'],*ex.read(ex.VALIDATION_ROOT/'Prob003/validation.json')['tasks']]:
        task=loop.rb.RepoTask.load(Path(path));excluded.add(loop.mutant_identity(public,(task.repo/'rtl/sequence.sv').read_text()))
    result={'status':'running','model':'deepseek/deepseek-chat-v3-0324','scope':'one exploratory practice-transfer pair; not final exams or proof of a stable advantage',
        'hard_max_calls':MAX_CALLS,'fresh_experience':True,'previous_run_memory_imported':False,'paired_attempt_limit':4,'format_corrections':0,
        'source_directory':str(ex.PROMOTION_SOURCE),'experiment_sha256':ex.sha(Path(ex.__file__)),
        'runner_sha256':identity['runner_code'],'created_at_utc':datetime.now(timezone.utc).isoformat()}
    def persist(status):
        result.update(status=status,actual_calls=client.total_calls)
        ex.save(out/'result.json',result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    def author(round_index,snapshot,observations,previous):
        target,omissions=loop.state.target_view(snapshot,public['specification'],identity,counter)
        batch=loop.red.propose(public,observations,round_index=round_index,snapshot_hash=loop.hash_payload(snapshot),red_state_hash=loop.hash_payload(observations),
            seed=7700+round_index,directory=out/f'red_{round_index}',client=client,counter=counter,target_blue=target,
            target_omissions=omissions,output_tokens=16000,mechanism_focus=None,rejected_edits=previous)
        if batch['status']!='candidate_batch':return None
        for index,proposal in enumerate(batch['candidates']):
            if proposal['status']!='proposal':continue
            if loop.mutant_identity(public,proposal['buggy_rtl']) in excluded:continue
            if loop.targeted_prompts.curriculum_violation(public,proposal,round_index,observations):continue
            directory=out/f'admission_{round_index}_{index}'
            admission=loop.red907.check_proposal(Path(carrier['package']),ex.read(carrier['suite_freeze']),proposal,directory,seen=set())
            if admission['status']=='admitted':return directory/'blue_task',proposal
        return None
    def trial(task_dir,snapshot,name):
        directory=out/name/'blue';directory.mkdir(parents=True)
        task=loop.rb.RepoTask.load(task_dir);setup=loop.rb.setup(task,counter,cfg)
        envelope=loop.state.delivery(snapshot,task,counter)
        runner=loop.rb.RepoBlueRunner(client=client,counter=counter,cfg=cfg,archive=directory/'archive')
        data=runner.run(task,setup,seed=77200,experience=envelope,experience_journal=directory/'experience.jsonl')
        loop.append(directory/'encounters.jsonl',{'encounter':0,'result':data})
        ex.save(directory/'delivery.json',envelope)
        endpoint=data['final_candidate_hash'];archive=None
        for p in (directory/'archive').glob('*.json'):
            row=ex.read(p)
            if row['candidate_hash']==endpoint:archive=row;break
        evaluator=loop.measure._evaluate(task,archive['files'],ex.read(carrier['evaluator_freeze']),Path(carrier['evaluator_root'])/'evaluator') if archive else {'result':'not_run_no_patch'}
        measured={'public_passed':data['outcome']=='fixed','independent_passed':evaluator['result']=='pass','passed':data['outcome']=='fixed' and evaluator['result']=='pass',
            'calls':data['calls'],'outcome':data['outcome'],'attempts':[a.get('tier') for a in data['attempts']]}
        ex.save(out/name/'measurement.json',measured)
        return data,measured
    persist('started')
    try:
        selected=author(2,incoming,[],[])
        if not selected:persist('stopped_first_author_no_qualified_task');return
        task_dir,proposal=selected
        data,measurement=trial(task_dir,incoming,'learning');result['learning']=measurement
        if data['outcome']!='fixed':persist('stopped_no_successful_learning_episode');return
        obs,entry,decision=loop.online_evidence(task_dir,out/'learning/blue',run=out,slot={'round':2,'slot_id':'probe_learning'},proposal=proposal,incoming=incoming,carrier_id=public['carrier_id'])
        if not entry:persist('stopped_no_authenticated_public_episode');return
        working,decisions=loop.state.update(incoming,[entry],identity,counter)
        ex.save(out/'fresh_training_snapshot.json',working)
        if not working['entries']:persist('stopped_no_deliverable_training_episode');return
        selected=author(3,working,[obs],[proposal['mutation_edits']])
        if not selected:persist('stopped_transfer_author_no_qualified_task');return
        transfer_task,transfer_proposal=selected
        result['paired_task_hash']=loop.rb.public_task_hash(loop.rb.RepoTask.load(transfer_task))
        result['pair_order']=['static','adaptive']
        _,static=trial(transfer_task,b0,'static')
        _,adaptive=trial(transfer_task,working,'adaptive')
        result.update(static=static,adaptive=adaptive,adaptive_minus_static=int(adaptive['passed'])-int(static['passed']))
        persist('complete')
    except Exception as exc:
        result['error_type']=type(exc).__name__;persist('stopped_error')
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',action='store_true');p.add_argument('--run-dir',type=Path)
    p.add_argument('--key-file',type=Path,default=HERE.parent/'remaining-static-20261019/.secrets/openrouter.key')
    args=p.parse_args();ex.verify_questions()
    if not args.run:
        print(json.dumps({'status':'PASS','model_calls':0,'probe_max_calls':MAX_CALLS}));return
    out=args.run_dir or HERE/('transfer-probe-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    execute(out.resolve(),args.key_file)

if __name__=='__main__':main()
