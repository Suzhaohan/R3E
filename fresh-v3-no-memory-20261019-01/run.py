"""One independent first answer per current 01 case, with no repair guidance."""
from pathlib import Path
import importlib.util
import json
import secrets
import re
import sys
from openai import OpenAI

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODEL = 'deepseek/deepseek-chat-v3-0324'
SYSTEM = ('You are an RTL repair engineer. Repair the supplied SystemVerilog implementation '
          'to satisfy its specification while preserving its interface. Return only JSON '
          '{"rtl":"complete replacement SystemVerilog source"}. Do not omit source or use placeholders.')

def save(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def decode(text):
    for match in re.finditer(r'\{',text):
        try:
            obj,_ = json.JSONDecoder().raw_decode(text[match.start():])
            if isinstance(obj,dict) and isinstance(obj.get('rtl'),str) and obj['rtl'].strip(): return obj['rtl']
        except ValueError: pass
    raise ValueError('Response has no valid JSON rtl string')

def main():
    spec=importlib.util.spec_from_file_location('current_exam',ROOT/'hard-case-five-round-01/experiment.py')
    ex=importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)
    ex.verify_questions()
    key=(ROOT/'remaining-static-20261019/.secrets/openrouter.key').read_text().strip()
    results=[]
    for design in ex.DESIGNS:
        folder=HERE/design
        folder.mkdir()  # Fail closed on repeat: never reuse an old answer.
        material=ex.material(design)
        taskdir=Path(material['anchors'][0]['task_dir'])
        public=taskdir/'public'
        messages=[{'role':'system','content':SYSTEM},
                  {'role':'user','content':json.dumps({'specification':(public/'spec.txt').read_text(),
                   'buggy_rtl':(public/'repo/rtl/sequence.sv').read_text()},ensure_ascii=False)}]
        request={'model':MODEL,'messages':messages,'max_tokens':16000,'temperature':0.2,'seed':secrets.randbits(30)}
        save(folder/'request.json',request)
        result={'design':design,'experience_entries':0,'messages_roles':['system','user'],
                'attempts':1,'previous_answers_supplied':False,'targeted_guidance_supplied':False,
                'test_sources_supplied':False,'pre_run_diagnostics_supplied':False}
        try:
            # New SDK client and one stateless Chat Completions call per case.
            with OpenAI(api_key=key,base_url='https://openrouter.ai/api/v1',max_retries=0,timeout=1500) as client:
                response=client.chat.completions.create(**request)
            save(folder/'response.json',response.model_dump(mode='json'))
            result.update(returned_model=response.model,provider_request_id=response.id,
                          finish_reason=response.choices[0].finish_reason)
            rtl=decode(response.choices[0].message.content or '')
            (folder/'answer.sv').write_text(rtl)
            _,loop,*_=ex.runner(design).modules()
            task=loop.rb.RepoTask.load(taskdir)
            overlay={'rtl/sequence.sv':rtl}
            visible=loop.rb.execute(task,overlay)
            carrier=material['carriers'][0]
            private=loop.measure._evaluate(task,overlay,ex.read(carrier['evaluator_freeze']),Path(carrier['evaluator_root'])/'evaluator')
            result.update(public_tier=visible.tier,public_evidence=visible.evidence,independent_evaluator=private,
                          passed=visible.tier=='visible_pass' and private['result']=='pass',status='graded')
        except Exception as error:
            result.update(status='error',error_type=type(error).__name__,error=str(error))
        save(folder/'result.json',result)
        results.append(result); save(HERE/'results.json',results)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    print('Finished: '+str(sum(r.get('passed',False) for r in results))+'/3',flush=True)

if __name__=='__main__': main()
