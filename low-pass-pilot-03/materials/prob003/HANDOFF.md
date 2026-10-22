# Prob003 连续红蓝对抗实验交接

## 代码版本

GitHub main 已更新至 `a1f3d61967a3fcab870379c8c8f1d7197a779d7a`：
https://github.com/ShenShan123/R3E/commit/a1f3d61967a3fcab870379c8c8f1d7197a779d7a

执行时使用该提交。交接启动脚本会逐一检查冻结的 57 个代码文件，版本不符会拒绝。
完整测试：367 passed，0 skipped；发布审计 PASS。真实 RTL 的离线端到端验收为 25 个假请求，未调用模型，不代表已发现困难缺陷或学习增益。

## 测试集与具体 Bug

- 数据集：**ChipBench**。
- RTL：**Prob003_non-overlapping_sequence_detect**，目标序列 `011100`，每组六位、不重叠。
- 选取干净实现的 manifest 行：`chipbench:assignment:Prob003_non-overlapping_sequence_detect`。
- 仓库中的干净 RTL：`datasets/chipbench/assignment/Prob003_non-overlapping_sequence_detect/golden.sv`。
- 本次困难种子是 Red 历史生成的 **`RC_406d811b4d61a2`**，不是直接运行该行原始 `buggy.sv`。
- 种子把 `s6` 和 `sf6` 的 `nstate=data?sf1:s1` 改为 `nstate=idle`，丢弃下一组六位输入的首位。
- 历史 Part A 中 3 次运行有 2 次在预算内未修复，并经 PASS 审核；后续复验曾变为 3 次中仅 1 次失败。此处标记为历史开发线索，不声称当前 Blue 已重新确认失败。
- 本轮 Red 必须从干净实现生成新变体；历史种子和保留变体的规范化重复会被拒绝。

交接包中的实际文件：

| 内容 | 路径 |
| --- | --- |
| 干净 RTL | `materials/package/src/rtl/sequence.sv` |
| 历史 Red 缺陷 RTL | `materials/package/variants/defect/rtl/sequence.sv` |
| 公开规范 | `materials/package/spec.md` |
| 公开功能检查 | `materials/package/suites/W_bug/tb.sv` |
| 公开保持性检查 | `materials/package/suites/W_preserve/tb.sv` |
| 冻结补充检查 | `materials/evaluator/tb.sv`；只允许用于离线资格检查和收集结束后的评估 |
| 两个保留变体 | `materials/reserved/eval_match_branch/`、`materials/reserved/eval_miss_branch/` |
| 种子与来源摘要 | `materials/materials.json` 中的 `mechanism_focus` |
| 原冻结方案与代码快照 | `plan/` |
| 固定分词器 | `tokenizer/tokenizer.json` |

新公开任务保留原 ChipBench 规范，并明确补充输出采样时机。这是前瞻的新实验定义，不能把新检查结果回写旧运行。补充检查与公开检查由同一作者分别实现，不声称作者独立。

## 需要的脚本

| 功能 | GitHub 仓库路径 |
| --- | --- |
| 交接统一入口 | 本交接包的 `run_prob003.py` |
| 冻结、检查与实际启动 | `experiments/loop_probes/continuous_launch.py` |
| 连续回合调度 | `experiments/loop_probes/continuous_loop.py` |
| Prob003 材料准备、离线验收与报告 | `experiments/loop_probes/sequence_curriculum.py` |
| Red 的状态条件化生成 | `r3e/loop/red_continuous.py` |
| Blue 状态与经验更新 | `r3e/loop/continuous_state.py` |
| Blue 修复执行 | `r3e/loop/repo_blue.py` |
| 公开准入与见证矩阵 | `experiments/loop_probes/red907.py`、`witness_matrix.py` |
| 事后审计 | `experiments/loop_probes/continuous_audit.py` |
| 对应回归测试 | `tests/test_sequence_curriculum.py` 及 `tests/test_continuous_*.py` |

`red907.py` 是复用的准入工具名称；本次目标机制是 Prob003 组边界处理，不要求复现 Ibex 907 的容量错误。交接包中的 `reset_control` 仅检查验证链路，不是预想的 Blue 修法。

## 固定执行范围

三轮，每轮 1 次 Red 提案、1 次当前 Blue 修复、1 次冻结 B₀ 修复。Blue 采用一次尝试、零重试；Red 不预测 Blue 修法。只有已结束的在线公开交互可以用于下一轮状态更新。

两份保留变体不参与学习。在 B₀、B₁、B₂、B₃ 上，每份运行两次，共 16 次延后测量。它们可能与训练变体共享修改位置，须报告暴露情况，不能称为跨设计迁移。

**总上限：25 次调用；支出上限：¥12。**按方案中冻结的高峰费率计算，全上下文和全输出额度上界为 ¥11.430952，这不是预期账单。真实启动前复核官方价格并确认预算授权。余额预检在创建运行目录前执行；A/B/HWE 旧储备不划入本次实验。

模型：`deepseek-v4-flash`，thinking low，temperature 0.2，超时 1500 秒。Red 输出上限 16,384；Blue 32,768。服务错误、无回答、编辑格式失败、上下文限制等分别记录，不当作功能性困难。无隐式恢复、替换槽位或追加确认运行。

## 同一台服务器：复用原冻结方案

在本机使用冻结的 Python 3.11 解释器；启动入口自动绑定分词器并加载用户站点依赖。
执行者自己的凭据文件需提供 `DEEPSEEK_API_KEY`；`DEEPSEEK_BASE_URL` 使用
`https://api.deepseek.com`。模型名由启动程序按冻结方案覆盖。交接包不提供凭据。

```bash
PY=/opt/OpenROAD/oss-cad-suite/bin/tabbypy3
REPO=/data1/zhangdy/R3E
ENTRY=/data1/zhangdy/R3E-local-artifacts/prob003_handoff_20261013/run_prob003.py
PLAN=/data1/zhangdy/R3E-local-artifacts/sequence_curriculum_plan_v1_20261013

# 离线检查，不读取凭据、不调用模型。
"$PY" "$ENTRY" check --repo-root "$REPO" --plan-dir "$PLAN"

# 确认调用/费用授权后才运行；ENV_FILE 是执行者单独保存的凭据文件。
# RUN_DIR 必须是从未存在的新目录。
"$PY" "$ENTRY" collect --repo-root "$REPO" --plan-dir "$PLAN" \
  --env-file ENV_FILE --run-dir RUN_DIR

# 只在 collection 完整结束后运行；全部离线。
"$PY" "$ENTRY" report --repo-root "$REPO" --run-dir RUN_DIR
"$PY" "$ENTRY" audits --repo-root "$REPO" --run-dir RUN_DIR
```

## 其他机器：重新冻结路径和环境

不要直接编辑原 `plan.json` 中的绝对路径。复制整个交接包并校验清单，取得指定 GitHub 提交，使用 Python ≥3.11，安装 `openai`、`tokenizers`；需要 Icarus Verilog、Yosys 和 Git。若还要跑完整仓库测试，则需要 pytest、Verilator 以及对应构建工具。

```bash
git clone --branch main https://github.com/ShenShan123/R3E.git
cd R3E
git checkout a1f3d61967a3fcab870379c8c8f1d7197a779d7a
python3 -m pip install -e . tokenizers

# ENTRY 指向解压后的 run_prob003.py，REPO 指向此 checkout。
# NEW_PLAN_DIR 必须不存在。freeze 只重绑材料路径并生成新冻结方案，不调用模型。
python3 "$ENTRY" freeze --repo-root "$REPO" --plan-dir NEW_PLAN_DIR
python3 "$ENTRY" check --repo-root "$REPO" --plan-dir NEW_PLAN_DIR

# 新环境的冻结方案复核和授权后，再 collect；命令同上一节。
```

后续使用重新冻结时的同一解释器。重新冻结可以改变路径、解释器及本地工具身份；源代码、Bug 机制、公开/补充材料、回合数、模型设置、调用上限和输出额度必须保持本方案范围。

## 交付结果

- `collection/slots.jsonl`：所有生成槽位、准入、原因与在线/参考结果。
- `collection/rounds/*/commit.json`：R/Blue 的回合边界状态。
- `collection/calls.jsonl` 和运行根目录用量日志：调用、token 与费用。
- `collection/report.json`：有效且不同的挑战数、当前 Blue 对比 B₀、保留变体按快照结果。
- `collection/audits/`：重复/位置暴露与学习来源补充检查。
- 功能性失败候选须盲评；一次失败不直接记为确认命中。补充检查未发现不匹配也不等于完整正确性证明。

交接包不包含 API key 或凭据文件。临时模拟目录自动清理；保留冻结材料、候选补丁、账本和评估证据。
