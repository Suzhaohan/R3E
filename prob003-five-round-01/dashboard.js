(() => {
  const element = id => document.getElementById(id);
  const labels = {
    fixed: '公开修复通过', failed: '公开修复未通过', admitted: '准入', rejected: '拒绝',
    provider_failure: '供应商接口失败，未出题', public_pass_hidden_pass: '公开及补充均通过',
    public_pass_hidden_fail: '公开通过 / 补充失败', public_fail: '公开失败', inconclusive: '无法判定',
    red: 'Red 出题', online: '当前经验组', reference: '无经验 B₀', anchor: '最终考核',
    public_pass_single_sample_hidden_unknown: '单次公开通过，补充检查未知（provisional）',
    waiting: '尚未启动', running: '记录收集中', aborted: '中断 / 非完成', complete: '收集完成'
  };
  const label = value => value == null ? '未运行 / 无记录' : (labels[value] || String(value));
  const text = (tag, value, parent, className) => {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    parent.append(node);
    return node;
  };
  const card = (parent, className = '') => {
    const node = document.createElement('article');
    node.className = 'card '+className;
    parent.append(node);
    return node;
  };
  let data = null;
  let cursor = 0;
  let follow = true;
  let replay = null;

  function stopReplay() {
    clearInterval(replay);
    replay = null;
    element('arena-replay').textContent = '播放已记录轮次';
  }

  function renderRounds() {
    const target = element('arena-rounds');
    target.replaceChildren();
    const recorded = data.rounds.filter(row => row.committed || row.admission);
    if (follow) cursor = recorded.length;
    cursor = Math.min(cursor, recorded.length);
    for (const row of recorded.slice(0, cursor)) {
      const node = card(target, 'arena-round');
      text('strong', `第 ${row.round} 轮 · ${row.snapshot || '未提交状态'}`, node);
      text('p', '新缺陷：'+label(row.admission), node, row.admission === 'provider_failure' ? 'fail' : '');
      text('p', '当前经验组：'+label(row.online), node);
      text('p', '无经验 B₀：'+label(row.reference), node);
      text('p', `累计经验条目：${row.entries ?? '未提交'}`, node);
      text('small', row.committed ? '槽位记录已提交，不等于有效修复成功。' : '该槽位未提交完成。', node);
      if (row.state_hash) text('small', ' 状态 '+row.state_hash, node);
    }
    if (!recorded.length) text('p', '尚无已记录轮次。', target, 'muted');
    element('arena-position').textContent = `${cursor} / ${recorded.length} 个已记录槽位（计划 5 轮）`;
    element('arena-step').disabled = cursor >= recorded.length;
    element('arena-replay').disabled = recorded.length === 0;
  }

  function finalResults(target) {
    target.replaceChildren();
    if (!data.report_available) {
      text('p', data.status === 'aborted' ? '实验已中断，没有最终考核成绩；不能比较两组优劣。' : '尚无最终离线报告，不能提前判断哪组更好。', target, 'notice');
      return;
    }
    const container = document.createElement('div');
    container.className = 'scroll';
    const table = document.createElement('table');
    const header = document.createElement('tr');
    for (const value of ['经验状态', '公开及补充检查均通过', '其他结果']) text('th', value, header);
    table.append(header);
    for (const row of data.final) {
      const line = document.createElement('tr');
      text('td', row.snapshot, line);
      text('td', `${row.categories.public_pass_hidden_pass || 0} / ${row.scheduled}`, line);
      text('td', Object.entries(row.categories).filter(([key]) => key !== 'public_pass_hidden_pass').map(([key, count]) => `${label(key)}：${count}`).join('；') || '无', line);
      table.append(line);
    }
    container.append(table);
    target.append(container);
    text('p', '每个状态：两个保留变体 × 两次重复。样本量很小，不保证经验组胜出，也不证明跨设计泛化。', target, 'muted');
    text('p', data.audits_available ? '两项离线审计已生成。' : '离线审计尚未齐全。', target);
  }

  function render() {
    element('health').textContent = label(data.status);
    element('arena-status').textContent = data.phase;
    element('arena-status').className = data.status === 'aborted' ? 'fail' : '';
    element('run-warning').textContent = data.mock ? '离线模拟数据，非 DeepSeek 真实结果。' : '';
    element('arena-provenance').textContent = `${data.run_dir} · ${data.model || '模型未加载'} · 仅本次运行`;
    const machines = element('arena-machines');
    machines.replaceChildren();
    for (const [role, title, style] of [['reference', 'Machine A · 静态修复', 'static'], ['online', 'Machine B · 对抗演化', 'adversarial']]) {
      const node = card(machines, 'machine-'+style);
      text('h3', title, node);
      text('p', role === 'reference' ? '固定 B₀ · 不读取经验 · 每道准入新缺陷一次修复' : '逐轮更新 B₁～B₅ · 只使用此前在线公开记录', node);
      const attempts = data.rounds.filter(row => row[role]);
      const hits = attempts.filter(row => row[role] === 'fixed').length;
      text('strong', `在线公开修复通过 ${hits} / ${attempts.length} 次已记录尝试`, node);
      text('p', attempts.length ? '公开通过不等于补充检查通过。' : '尚未进行有效 Blue 修复，不能算成功或失败。', node, 'muted');
    }
    const metrics = element('run-metrics');
    metrics.replaceChildren();
    for (const [title, value] of [
      ['已发出请求 / 上限', `${data.calls} / 39`],
      ['有效新挑战 / 已提交槽位', `${data.admitted_challenges} / ${data.completed_rounds}`],
      ['最终考核已记录', `${data.probes_completed} / 24`],
      ['已返回输入 / 输出 tokens', `${data.input_tokens.toLocaleString()} / ${data.output_tokens.toLocaleString()}`],
      ['未返回用量的失败请求', `${data.unknown_usage_requests} 次（账单未知）`],
      ['有效模型返回', `${data.successful_responses} 次`]
    ]) {
      const node = card(metrics);
      text('small', title, node);
      text('div', value, node, 'metric');
    }
    if (data.unknown_usage_requests) text('p', '上方 token 只统计已返回的有效用量，不是零消费保证；接口失败部分计费未知。', metrics, 'notice');
    element('diagnosis').textContent = data.phase+'\n'+JSON.stringify(data.provider_error, null, 2);
    const trace = element('trace');
    trace.replaceChildren();
    for (const row of data.trace) {
      const node = card(trace);
      text('strong', `${row.slot_id || '保留题'} · ${label(row.role)} · ${row.snapshot_id}`, node);
      text('p', row.ok ? '模型已返回；公开修复结果另看轮次记录。' : `接口/模型返回失败：${row.error || '未知原因'}`, node, row.ok ? '' : 'fail');
    }
    if (!data.trace.length) text('p', '尚无调用记录。', trace);
    const evolution = element('evolution-data');
    evolution.replaceChildren();
    for (const row of data.rounds.filter(row => row.committed)) {
      const node = card(evolution);
      text('strong', `第 ${row.round} 轮 → ${row.snapshot}`, node);
      text('p', `出题状态：${label(row.admission)}；经验条目 ${row.entries}`, node);
      text('small', row.state_hash, node);
    }
    if (!evolution.childNodes.length) text('p', '尚无已提交状态。', evolution);
    const memory = element('memory-data');
    memory.replaceChildren();
    for (const entry of data.memory) {
      const node = card(memory);
      text('strong', `来自第 ${entry.created_round} 轮`, node);
      text('p', label(entry.validation), node);
      const details = document.createElement('details');
      text('summary', '查看公开经验中的代码差异', details);
      text('pre', entry.applied_patch || '无代码差异', details, 'diff');
      node.append(details);
    }
    if (!data.memory.length) text('p', '当前已提交状态中没有经验条目。', memory);
    renderRounds();
    finalResults(element('arena-metrics'));
    finalResults(element('benchmark-data'));
    element('updated').textContent = '最近刷新：'+new Date().toLocaleString();
  }

  document.querySelectorAll('.tabs button').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('.tabs button,.page').forEach(node => node.classList.remove('active'));
    button.classList.add('active');
    element(button.dataset.page).classList.add('active');
  }));
  element('arena-reset').addEventListener('click', () => { stopReplay(); follow = false; cursor = 0; if (data) renderRounds(); });
  element('arena-live').addEventListener('click', () => { stopReplay(); follow = true; if (data) renderRounds(); });
  element('arena-step').addEventListener('click', () => { stopReplay(); follow = false; cursor += 1; if (data) renderRounds(); });
  element('arena-replay').addEventListener('click', () => {
    if (!data) return;
    if (replay) { stopReplay(); return; }
    follow = false;
    cursor = 0;
    renderRounds();
    element('arena-replay').textContent = '暂停回放';
    replay = setInterval(() => {
      cursor += 1;
      renderRounds();
      if (cursor >= data.rounds.filter(row => row.committed || row.admission).length) stopReplay();
    }, 1000);
  });
  async function refresh() {
    try {
      const response = await fetch('/api/status', {cache: 'no-store'});
      if (!response.ok) throw Error('HTTP '+response.status);
      const next = await response.json();
      if (next.schema_version !== 2) throw Error('此端口仍是旧版服务。请用 view --port 8094 启动新版后打开新地址。');
      data = next;
      render();
    } catch (error) {
      element('arena-status').textContent = '读取失败：'+error.message;
      element('arena-status').className = 'fail';
    }
    setTimeout(refresh, 3000);
  }
  refresh();
})();
