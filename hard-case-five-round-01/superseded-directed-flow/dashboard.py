"""Local read-only progress viewer; never starts an experiment or changes results."""
import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path


def status(root):
    def read(name, default):
        p = root / name
        return json.loads(p.read_text()) if p.exists() else default
    def lines(name):
        p = root / name
        if not p.exists():
            return []
        result = []
        for line in p.read_text().splitlines():
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:  # a concurrent writer may be mid-record
                pass
        return result
    plan = read('plan.json', {})
    slots, exams = lines('slots.jsonl'), lines('exams.jsonl')
    return {'collection': read('collection.json', {'status': 'running' if plan else 'not_started'}),
            'completed_practice_slots': len(slots), 'scheduled_practice_slots': len(plan.get('slots', [])),
            'completed_exams': len(exams), 'scheduled_exams': len(plan.get('exams', [])),
            'groups': {role: {'passed': sum(x['passed'] for x in exams if x['role'] == role),
                              'completed': sum(x['role'] == role for x in exams),
                              'categories': dict(Counter(x['category'] for x in exams if x['role'] == role))}
                       for role in ('static', 'evolved')},
            'report': read('report.json', None)}


HTML = '''<!doctype html><html lang="zh"><meta charset="utf-8"><title>固定困难题实验</title>
<style>body{background:#111827;color:#e5e7eb;font:16px system-ui;max-width:960px;margin:40px auto;padding:20px}td,th{padding:12px;text-align:left}table{width:100%;border-collapse:collapse}tr{border-bottom:1px solid #374151}pre{white-space:pre-wrap}</style>
<h1>固定困难题 · 五轮定向经验学习</h1><p>考试题固定；静态组无经验，对抗组使用五轮练习经验。目标差异由真实结果检验。</p>
<p id="state"></p><table><thead><tr><th>最终考试组</th><th>通过 / 已完成</th></tr></thead><tbody id="groups"></tbody></table>
<p>分数以冻结参考测试为准。两组最终考试使用同一批原缺陷题。</p><pre id="details"></pre>
<script>async function update(){try{const s=await(await fetch('/api/status')).json();document.getElementById('state').textContent=`${s.collection.fake ? "离线模拟（非模型成绩）；" : ""}状态：${s.collection.status}；练习 ${s.completed_practice_slots}/${s.scheduled_practice_slots}；考试 ${s.completed_exams}/${s.scheduled_exams}`;const body=document.getElementById('groups');body.replaceChildren();for(const [key,name] of [['static','静态 B₀（无经验）'],['evolved','对抗 B₅（五轮经验）']]){const tr=document.createElement('tr');for(const value of [name,`${s.groups[key].passed} / ${s.groups[key].completed}`]){const td=document.createElement('td');td.textContent=value;tr.append(td)}body.append(tr)}document.getElementById('details').textContent=s.report?JSON.stringify(s.report.per_case,null,2):'最终报告待实验完成后生成。'}catch(e){document.getElementById('state').textContent='读取失败：'+e.message}}update();setInterval(update,3000)</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8098)
    args = parser.parse_args()
    root = args.run_dir.resolve()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in {'/', '/api/status'}:
                self.send_error(404)
                return
            body = HTML.encode() if self.path == '/' else json.dumps(status(root), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if self.path == '/' else 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
    print(f'http://127.0.0.1:{args.port}/', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
