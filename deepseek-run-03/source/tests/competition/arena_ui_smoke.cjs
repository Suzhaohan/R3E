// Dependency-free interaction smoke test; does not replace visual browser QA.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

class Element {
  constructor() { this.children = []; this.textContent = ''; this.disabled = false; this.hidden = false; }
  append(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  setAttribute() {}
}

async function check(payload) {
  const elements = new Map();
  const el = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  let tick = null;
  const context = {
    document: {getElementById: el, createElement: () => new Element(), addEventListener() {}},
    fetch: async () => ({ok: true, json: async () => payload}),
    setInterval: callback => { tick = callback; return 1; },
    clearInterval: () => { tick = null; },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../competition/app/frontend/arena.js'), 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  return {el, tick: () => tick};
}

(async () => {
  const unavailable = await check({available: false, message: '证据不可用'});
  assert.equal(unavailable.el('arena-status').textContent, '证据不可用');
  const data = {available: true, mode: 'offline_protocol_demo', message: '离线工程演示',
    model: 'fixture', candidate_budget: 3, baseline_hash: 'hash', machines: {
      static: {promotion_count: 0, policy_hash: 'A'}, adversarial: {promotion_count: 1, policy_hash: 'B'}},
    design_count: 10,
    rounds: [0, 1, 2, 3, 4].map(i => ({round_id: `R00${i}`, parent_policy_id: 'B0', active_policy_id: 'B1',
      designs: ['assignment4v:fa_behavioral'], families: ['combinational.expression_operator'],
      proposed_count: 4, valid_count: 4, repaired_count: 2, promoted: i === 1, audit_record_hash: 'audit', stages: ['RED_GENERATE', 'PAIRED_REPLAY']})),
    case_results: {regression: [{case_id: 'fixture-case', seed: 1, static: {oracle_ok: false, status: 'evaluated'}, adversarial: {oracle_ok: true, status: 'evaluated'}}]},
    metrics: {regression: {static_repaired: 0, adversarial_repaired: 6, denominator: 6,
      static_rate: 0, adversarial_rate: 1, delta: 1}}};
  data.rounds[0].cases = [{case_id: 'fixture-case', design: 'fixture-design', operator: 'replace_comparator',
    valid: true, challenged_policy_id: 'B0', mutation: {old_text: '<', new_text: '<=', clean_start: 5},
    poison_id: 'P1', poison_hash: 'hash', seeds: [{seed: 1, oracle_ok: false,
      candidates: [{candidate_id: 'C1', parse_ok: true, compile_ok: true, scope_ok: true, oracle_ok: false}]}]}];
  const ui = await check(data);
  assert.equal(ui.el('arena-machines').children.length, 2);
  assert.equal(ui.el('arena-rounds').children.length, 5);
  assert.equal(ui.el('arena-result-title').textContent, '工程回归检查（非能力评测）');
  assert.match(ui.el('arena-provenance').textContent, /5 回合实际覆盖 10 个设计/);
  assert.ok(ui.el('arena-rounds').children[0].children.some(c => c.textContent.includes('assignment4v:fa_behavioral')));
  function allText(node) { return node.textContent + node.children.map(allText).join(' '); }
  assert.match(allText(ui.el('arena-rounds')), /fixture-case/);
  assert.match(allText(ui.el('arena-rounds')), /C1：解析 通过/);
  assert.match(allText(ui.el('arena-metrics')), /fixture-case/);
  const live = await check({...data, mode: 'live_local_progress', message: '真实实验进度',
    sampling_note: 'seed 仅用于本地调度，不保证生成可复现',
    machines: {adversarial: data.machines.adversarial}, metrics: {}});
  assert.equal(live.el('arena-machines').children.length, 1);
  assert.equal(live.el('arena-status').textContent, '真实实验进度');
  assert.match(live.el('arena-provenance').textContent, /seed 仅用于本地调度/);
  ui.el('arena-reset').onclick();
  assert.equal(ui.el('arena-rounds').children.length, 0);
  assert.equal(ui.el('arena-result').hidden, true);
  ui.el('arena-step').onclick();
  assert.equal(ui.el('arena-rounds').children.length, 1);
  ui.el('arena-replay').onclick();
  ui.tick()();
  assert.equal(ui.el('arena-rounds').children.length, 2);
  ui.el('arena-replay').onclick(); // pause
  assert.equal(ui.tick(), null);
  ui.el('arena-replay').onclick(); // resume, not restart
  ui.tick()();
  assert.equal(ui.el('arena-rounds').children.length, 3);
  assert.equal(ui.el('arena-result').hidden, true);
  ui.tick()(); ui.tick()();
  assert.equal(ui.el('arena-rounds').children.length, 5);
  assert.equal(ui.el('arena-result').hidden, false);
  assert.equal(ui.el('arena-step').disabled, true);
  assert.equal(ui.tick(), null);
  console.log('Arena UI: unavailable, render, reset, step, pause/resume, completion passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
