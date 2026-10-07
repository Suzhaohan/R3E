(() => {
  let data = null, timer = null;
  const el = id => document.getElementById(id);
  const text = (tag, value, parent) => { const node = document.createElement(tag); node.textContent = value; parent.append(node); return node; };
  function rounds(count) {
    const target = el('arena-rounds'); target.replaceChildren();
    for (const row of data.rounds.slice(0, count)) {
      const card = document.createElement('article'); card.className = 'card';
      text('strong', `${row.round_id}: ${row.parent_policy_id} → ${row.active_policy_id}`, card);
      text('p', row.promoted ? '策略升级通过' : '未晋升，保留原策略', card);
      text('small', `审计 ${row.audit_record_hash}`, card); target.append(card);
    }
  }
  async function load() {
    try {
      const response = await fetch('/api/arena/status');
      if (!response.ok) throw new Error('读取证据失败');
      data = await response.json();
      if (!data.available) { el('arena-status').textContent = data.message; return; }
      el('arena-status').textContent = `VERIFIED EVOLUTION REPLAY · ${data.model} · 候选预算 ${data.candidate_budget} · Baseline ${data.baseline_hash}`;
      for (const [arm, label] of [['static', 'Machine A · 静态修复'], ['adversarial', 'Machine B · 对抗演化']]) {
        const card = document.createElement('article'); card.className = 'card';
        text('h3', label, card); text('p', `晋升次数 ${data.machines[arm].promotion_count}`, card);
        text('small', data.machines[arm].policy_hash, card); el('arena-machines').append(card);
      }
      for (const [name, metric] of Object.entries(data.metrics)) {
        const card = document.createElement('article'); card.className = 'card'; text('h4', name, card);
        for (const [arm, label] of [['static', '静态'], ['adversarial', '对抗']]) {
          text('p', `${label}: ${metric[arm + '_repaired']}/${metric.denominator} (${(metric[arm + '_rate'] * 100).toFixed(1)}%)`, card);
          const bar = document.createElement('progress'); bar.max = 1; bar.value = metric[arm + '_rate']; bar.setAttribute('aria-label', `${name} ${label}修复率`); card.append(bar);
        }
        text('p', `变化 ${(metric.delta * 100).toFixed(1)} 个百分点`, card); el('arena-metrics').append(card);
      }
      rounds(data.rounds.length);
      el('arena-replay').disabled = !data.rounds.length;
      el('arena-replay').onclick = () => {
        if (timer) { clearInterval(timer); timer = null; el('arena-replay').textContent = '播放已验证轮次'; return; }
        let count = 0; rounds(count); el('arena-replay').textContent = '暂停回放';
        timer = setInterval(() => { rounds(++count); if (count >= data.rounds.length) { clearInterval(timer); timer = null; el('arena-replay').textContent = '重新回放'; } }, 5000);
      };
    } catch (error) { el('arena-status').textContent = `证据不可用：${error.message}`; }
  }
  load();
})();
