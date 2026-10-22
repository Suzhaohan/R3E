"""Independent development validation variants; preserve the three final exams."""
import json
import shutil
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'source-promotion'))
from experiments.loop_probes import witness_matrix as wm, carrier_task
from r3e.protocol.hashing import hash_payload


def save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2))


def prepare():
 root=HERE/'validation-promotion-v1'
 if root.exists(): raise FileExistsError(root)
 for design in ('Mux','Counter','Prob015'):
  old=HERE/'materials-selected-v2'/design
  package=root/design/'package'
  shutil.copytree(old/'package',package)
  freeze=json.loads((old/'suite_freeze.json').read_text())
  man=wm.load(package)
  clean=(package/'src/rtl/sequence.sv').read_text()
  fixtures=json.loads((old/'practice_fixtures.json').read_text())
  tasks=[]
  for i,index in enumerate((1,2)):
   name=f'validation_{i}'
   edit=fixtures[index][0];mutant=clean.replace(edit['find'],edit['replace'])
   man['variants'][name]={'role':'defect'}
   p=package/'variants'/name/'rtl/sequence.sv';p.parent.mkdir(parents=True);p.write_text(mutant)
  save(package/'carrier.json',man)
  q=wm.qualify(package,freeze);save(root/design/'qualification.json',q)
  if not q['qualified']: raise ValueError(q['problems'])
  for i in range(2):
   task=carrier_task.export(package,f'validation_{i}',root/design/f'task_{i}',freeze)
   tasks.append(str(task.resolve()))
  pairs={'Mux':[('out <= b;','out <= a;'),('out <= d;','out <= b;')],
         'Counter':[("counter_out == 4'b1111","counter_out == 4'b1100"),("counter_out == 4'b1111","counter_out == 4'b1001")],
         'Prob015':[('d2? S2:', 'd2? S0_5:'),("S2_5        : {out1, out2, out3} = ~sel? 3'b101: 3'b010;", "S2_5        : {out1, out2, out3} = ~sel? 3'b000: 3'b010;")]}[design]
  training=[fixtures[i] for i in (0,3,4)] + [[{'find':a,'replace':b}] for a,b in pairs]
  for edits in training:
   assert clean.count(edits[0]['find'])==1
  save(root/design/'training_fixtures.json',training)
  save(root/design/'validation.json',{'tasks':tasks,'repeats':2,'exam_used_for_selection':False,
      'task_bytes':{t:hash_payload((Path(t)/'public/repo/rtl/sequence.sv').read_text()) for t in tasks}})

if __name__=='__main__': prepare()
