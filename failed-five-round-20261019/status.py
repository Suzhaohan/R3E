"""Read-only progress monitor. Does not import the runner or call any model."""
import argparse
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent

def load(path):
    return json.loads(path.read_text())

def status():
    cases = load(ROOT/'catalog.json')
    complete = 0
    errors = []
    lines = []
    for case in cases:
        task = ROOT/'work'/case['slug']
        rounds = len(list((task/'rounds').glob('*.json')))
        exam = task/'exam.json'
        error = task/'error.json'
        if exam.exists() and load(exam).get('status') == 'complete':
            result = load(exam)
            complete += 1
            text = f"考试完成：静态 {result['static_passed']}/2，对抗 {result['adaptive_passed']}/2"
        elif error.exists():
            details = load(error)
            errors.append(case['id'])
            text = '异常：'+details.get('error','查看 error.json')
        elif (task/'trained.json').exists():
            text = '训练完成，等待统一冻结或考试'
        else:
            text = '尚未完成训练'
        lines.append(f"{case['id']}：{rounds}/5 轮；{text}")
    finished = complete == len(cases)
    if finished:
        heading = f'整批已完成：{complete}/{len(cases)} 题均已完成五轮训练及最终双组考试。'
    elif errors:
        heading = f'尚未完成：已完成考试 {complete}/{len(cases)} 题；有 {len(errors)} 题出现异常。'
    else:
        heading = f'尚未完成：已完成考试 {complete}/{len(cases)} 题。'
    return '\n'.join([heading,*lines]), finished, bool(errors)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait',action='store_true',help='每十秒检查，完成或发现异常时退出')
    args = parser.parse_args()
    previous = None
    while True:
        text,finished,errors = status()
        if text != previous:
            print(text,flush=True)
            previous = text
        if finished:
            print('完整结果：'+str(ROOT/'RESULTS.md'),flush=True)
            return
        if errors:
            print('存在异常，不能将本批视为运行完成。请检查 run.log 和对应 error.json。',flush=True)
            raise SystemExit(1)
        if not args.wait:
            return
        time.sleep(10)

if __name__=='__main__': main()
