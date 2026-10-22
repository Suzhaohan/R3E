"""Offline checks of feedback delivery and memory promotion boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import run

class WorkflowTests(unittest.TestCase):
    def test_parse_wrapped_response_and_unique_edits(self):
        self.assertEqual(run.decode('Explanation\n```json\n{"paths":["rtl/a.sv"]}\n```')['paths'],['rtl/a.sv'])
        with self.assertRaises(ValueError):
            run.checked_edits({'a':'same same'},[{'file':'a','find':'same','replace':'other'}])
        with self.assertRaises(ValueError):
            run.checked_edits({'a':'one'},[{'file':'oracle/clean','find':'one','replace':'two'}])

    def test_actual_compile_feedback_reaches_second_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            task=Path(tmp); (task/'public').mkdir(); (task/'public/spec.txt').write_text('public spec')
            class Client:
                calls=[]
                def call(self,label,messages,limit=16000):
                    self.calls.append(json.loads(json.dumps(messages)))
                    return json.dumps({'files':{'buggy.sv':'first' if len(self.calls)==1 else 'second'},'transfer_summary':'Check reset polarity against the specification.'})
            client=Client()
            with patch.object(run,'grade',side_effect=[{'status':'compile_error'},{'status':'pass'}]), patch.object(run,'feedback',return_value={'diagnostics':'actual syntax error at line 7'}):
                result=run.repair({'id':'chipbench:test'},task,client,'repair',{'buggy.sv':'source'},[],True)
            self.assertTrue(result['passed'])
            self.assertEqual(len(result['attempts']),2)
            self.assertIn('actual syntax error at line 7',client.calls[1][-1]['content'])
            self.assertEqual(json.loads(client.calls[0][1]['content'])['experience'],[])

    def test_no_validation_gain_keeps_experience_empty_and_runs_five_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); case={'id':'chipbench:test','slug':'test'}; task=root/'work/test'; task.mkdir(parents=True)
            v=[{'files':{'buggy.sv':'one'},'source_hash':'v1'},{'files':{'buggy.sv':'two'},'source_hash':'v2'}]
            def generate(case,task,client,contexts,label,wanted,seen):
                return v if wanted==2 else [{'files':{'buggy.sv':label},'source_hash':label}]
            with patch.object(run.s,'ROOT',root),patch.object(run.s,'preflight',return_value={'status':'ready'}),patch.object(run,'Client'),patch.object(run,'source_context',return_value={}),patch.object(run,'generate',side_effect=generate),patch.object(run,'repair',return_value={'passed':True,'transfer_summary':'A reusable lesson.'}),patch.object(run,'validation_scores',return_value={'0_0':True,'0_1':True,'1_0':True,'1_1':True}):
                result=run.train(case,'fake-not-used')
            self.assertEqual(len(result['rounds']),5)
            self.assertEqual(result['frozen_experience'],[])
            self.assertTrue(all(r['reason']=='no_strict_gain' for r in result['rounds']))

if __name__=='__main__': unittest.main()
