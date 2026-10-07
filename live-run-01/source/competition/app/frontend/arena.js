(() => {
  let data = null, timer = null, cursor = 0;
  const el = id => document.getElementById(id);
  const text = (tag, value, parent) => { const node = document.createElement(tag); node.textContent = value; parent.append(node); return node; };
  const stageLabels = {
    INIT: '初始化', LOAD_ACTIVE_POLICY: '加载当前策略', RED_GENERATE: 'Red 发现新缺陷',
    VALIDITY_GATE: 'EDA 缺陷有效性检查', BLUE_CHALLENGE: 'Blue 尝试修复', ARCHIVE_UPDATE: '归档未解决问题',
    FREEZE_RESIDUAL_MANIFEST: '冻结残余缺陷', SPLIT_ADAPT_TARGET: '划分适配与目标集',
    PROPOSE_CHILDREN: '搜索候选策略', SCREEN_CHILDREN: '筛选候选策略',
    FREEZE_PROMOTION_MANIFEST: '冻结晋升验证集', PAIRED_REPLAY: '目标重放与非目标回归',
    DECIDE: '正确性门控决策', ATOMIC_COMMIT: '原子更新策略', RENEWED_CHALLENGE: '针对新策略继续挑战', COMPLETE: '完成审计'
  };
  function stop() {
    clearInterval(timer); timer = null;
    el('arena-replay').textContent = cursor >= (data?.rounds.length || 0) ? '重新回放' : '继续播放';
  }
  function rounds(count) {
    cursor = count;
    const target = el('arena-rounds'); target.replaceChildren();
    for (const row of data.rounds.slice(0, count)) {
      const card = document.createElement('article'); card.className = 'card arena-round';
      text('strong', `${row.round_id}: ${row.parent_policy_id} → ${row.active_policy_id}`, card);
      text('p', row.promoted ? '策略升级通过' : '未晋升，保留原策略', card);
      const reasons = {insufficient_residual_designs: '未解决缺陷覆盖的设计不足，未进入策略搜索；这不是策略搜索失败。'};
      if (row.defer_reason) text('p', `原因：${reasons[row.defer_reason] || row.defer_reason}`, card);
      if (row.child_count !== undefined) text('p', `本轮产生 ${row.child_count} 个候选策略。上述升级决定针对整套修复策略，不是给每个案例升级一次。`, card);
      if (row.designs) {
        text('p', `本轮设计：${row.designs.join('、')}`, card);
        text('p', `缺陷类型：${row.families.join('、')}`, card);
        text('p', `生成 ${row.proposed_count} · 验证有效 ${row.valid_count} · 全部种子修复通过 ${row.repaired_count}`, card);
      }
      if (row.stages?.length) {
        const details = document.createElement('details');
        text('summary', `查看 ${row.stages.length} 个已完成阶段`, details);
        const list = document.createElement('ol');
        row.stages.forEach(stage => text('li', stageLabels[stage] || stage, list));
        details.append(list); card.append(details);
      }
      if (row.cases?.length) {
        const details = document.createElement('details');
        text('summary', `逐案例与候选结果（${row.cases.length} 个缺陷）`, details);
        text('p', '以下是本轮开始时的策略接受挑战的结果；轮末策略是否晋升是后续独立决策。修复通过指至少一个候选通过验证。', details);
        for (const item of row.cases) {
          const c = document.createElement('article'); c.className = 'card';
          text('strong', `${item.case_id} · ${item.design}`, c);
          text('p', `${item.operator} · EDA 缺陷有效性 ${item.valid ? '通过' : '未通过'} · 挑战策略 ${item.challenged_policy_id}`, c);
          if (item.mutation?.old_text !== undefined) text('pre', `变异位置 ${item.mutation.clean_start}: ${item.mutation.old_text} → ${item.mutation.new_text}`, c);
          if (item.first_mismatch?.first_divergence_signal) text('p', `实际首个分歧：${item.first_mismatch.first_divergence_signal}，采样周期 ${item.first_mismatch.first_divergence_cycle}，${item.first_mismatch.mismatch_pattern}`, c);
          if (!item.seeds.length) text('p', '未进入 Blue 修复，不计为修复成功。', c);
          for (const seed of item.seeds) {
            text('p', `种子 ${seed.seed}：${seed.oracle_ok ? '修复通过' : '未修复'}`, c);
            const list = document.createElement('ul');
            for (const candidate of seed.candidates) {
              const li = text('li', `${candidate.candidate_id}：解析 ${candidate.parse_ok ? '通过' : '失败'}，编译 ${candidate.compile_ok ? '通过' : '失败'}，范围 ${candidate.scope_ok ? '通过' : '失败'}，功能 ${candidate.oracle_ok ? '通过' : '失败'}`, list);
              if (candidate.diff !== undefined) {
                const patch = document.createElement('details'); text('summary', '本机候选代码差异', patch);
                text('pre', candidate.diff || '候选未改变缺陷代码。', patch); li.append(patch);
              }
            }
            c.append(list);
          }
          text('small', `缺陷 ${item.poison_id} · ${item.poison_hash}`, c); details.append(c);
        }
        card.append(details);
      }
      if (row.promotion_gates?.length) {
        const details = document.createElement('details'); text('summary', '晋升门控与目标/回归得分', details);
        for (const gate of row.promotion_gates) {
          text('strong', `${gate.candidate_policy_id} · ${gate.decision}`, details);
          for (const [key, passed] of Object.entries(gate.checks)) text('p', `${key}: ${passed ? '通过' : '未通过'}`, details);
          for (const key of ['target', 'non_target']) if (gate[key]) text('p', `${key}: 原策略 ${gate[key].parent_hits}/${gate[key].total} → 候选 ${gate[key].candidate_hits}/${gate[key].total}`, details);
        }
        card.append(details);
      }
      text('small', `审计 ${row.audit_record_hash}`, card); target.append(card);
    }
    el('arena-position').textContent = `${count} / ${data.rounds.length} 轮`;
    el('arena-step').disabled = count >= data.rounds.length;
    el('arena-result').hidden = count < data.rounds.length;
  }
  async function load() {
    try {
      const response = await fetch('/api/arena/status');
      if (!response.ok) throw new Error('读取证据失败');
      data = await response.json();
      if (!data.available) { el('arena-status').textContent = data.message; return; }
      const offline = data.mode === 'offline_protocol_demo';
      el('arena-status').className = offline ? 'notice' : '';
      el('arena-status').textContent = data.message || '已核验的 A/B 冻结实验回放 · 非实时模型执行；物理双机部署需独立核实';
      el('arena-provenance').textContent = `${data.model} · 候选预算 ${data.candidate_budget} · Baseline ${data.baseline_hash}`;
      if (data.design_count !== undefined) el('arena-provenance').textContent += ` · ${data.rounds.length} 回合实际覆盖 ${data.design_count} 个设计`;
      el('arena-result-title').textContent = offline ? '工程回归检查（非能力评测）' : '最终冻结测试';
      if (data.acceptance && Object.keys(data.acceptance).length) {
        const a = data.acceptance;
        text('p', `验收观察：五轮完成 ${a.five_rounds_completed ? '是' : '否'}；实际晋升 ${a.audited_promotion_observed ? '有' : '无'}；Red 留出提升 ${a.heldout_positive_gain ? '有' : '无'}；Strider 提升 ${a.strider_positive_gain ? '有' : '无'}。主机记录不同 ${a.distinct_reported_hosts ? '是' : '否'}（物理部署仍需核实）。`, el('arena-metrics'));
      }
      for (const [arm, label] of [['static', 'Machine A · 静态修复'], ['adversarial', 'Machine B · 对抗演化']]) {
        if (!data.machines[arm]) continue;
        const card = document.createElement('article'); card.className = `card machine-${arm}`;
        text('h3', label, card);
        text('p', arm === 'static' ? 'B0 固定 · Red 关闭 · 记忆 M0 固定' : 'Red 发现缺陷 → Blue 修复 → EDA → 安全重放 → 策略更新', card);
        text('p', `完整记录中晋升 ${data.machines[arm].promotion_count} 次`, card);
        text('small', data.machines[arm].policy_hash, card); el('arena-machines').append(card);
      }
      for (const [name, metric] of Object.entries(data.metrics)) {
        const card = document.createElement('article'); card.className = 'card'; text('h4', name, card);
        for (const [arm, label] of [['static', '静态'], ['adversarial', '对抗']]) {
          text('p', `${label}: ${metric[arm + '_repaired']}/${metric.denominator} (${(metric[arm + '_rate'] * 100).toFixed(1)}%)`, card);
          const bar = document.createElement('progress'); bar.max = 1; bar.value = metric[arm + '_rate']; bar.setAttribute('aria-label', `${name} ${label}修复率`); card.append(bar);
        }
        text('p', `变化 ${(metric.delta * 100).toFixed(1)} 个百分点${offline ? '（预置模型行为，不代表泛化提升）' : ''}`, card); el('arena-metrics').append(card);
        if (data.case_results?.[name]) {
          const details = document.createElement('details'); text('summary', '展开每个案例、每个种子的 A/B 结果', details);
          const table = document.createElement('table');
          const head = document.createElement('tr'); ['案例', '种子', 'A 静态', 'B 对抗'].forEach(v => text('th', v, head)); table.append(head);
          for (const result of data.case_results[name]) {
            const tr = document.createElement('tr'); text('td', result.case_id, tr); text('td', result.seed, tr);
            for (const arm of ['static', 'adversarial']) text('td', result[arm].oracle_ok ? '修复通过' : (result[arm].status === 'evaluated' ? '未修复' : '基线无法评测（计入分母）'), tr);
            table.append(tr);
          }
          details.append(table); card.append(details);
        }
      }
      rounds(data.rounds.length);
      el('arena-replay').disabled = !data.rounds.length;
      el('arena-reset').disabled = !data.rounds.length;
      el('arena-replay').onclick = () => {
        if (timer) { stop(); return; }
        if (cursor >= data.rounds.length) rounds(0);
        el('arena-replay').textContent = '暂停回放';
        timer = setInterval(() => { rounds(cursor + 1); if (cursor >= data.rounds.length) stop(); }, 3000);
      };
      el('arena-step').onclick = () => { stop(); if (cursor < data.rounds.length) rounds(cursor + 1); };
      el('arena-reset').onclick = () => { stop(); rounds(0); el('arena-replay').textContent = '开始回放'; };
    } catch (error) { el('arena-status').textContent = `证据不可用：${error.message}`; }
  }
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  load();
})();
