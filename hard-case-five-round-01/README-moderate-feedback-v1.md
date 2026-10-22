# 三道中等难度序列题

当前默认题单为 `materials-moderate-v1/`，冻结计划为 `plan-v3-moderate-feedback-v1/`。替换过于简单的 Mux、Counter，保留 Prob001 作较低难度对照：

| 题目 | 固定考试题 | 历史依据与新增难点 |
| --- | --- | --- |
| Prob001 | ChipBench 连续八位序列检测 arithmetic 原题 | 某旧模型设置 1/3 成功；其他较新模型设置也有全对记录。保留作对照，考试题未加难；验证题增加移位方向、匹配条件、输出保持的组合缺陷 |
| Prob002 | ChipBench 九位通配序列 011XXX110 arithmetic 原题 | 某旧模型设置 2/3 成功；涉及两段比较、通配位、组合条件及寄存周期 |
| Prob003 | 既有六位分组检测 eval_miss_branch | 两个旧运行设置分别 1/2 成功；涉及成功/失败路径、分组边界和下一位消费 |

这些是分开记录的历史结果，不混成当前通过率。**未调用当前 V3 校准，不能保证新验证题不会满分，也不能保证对抗组获益。**难度提升以更复杂机制和组合缺陷为依据，不是已测量出的当前模型难度。

## 运行

```bash
bash hard-case-five-round-01/start_all.sh --check-only
bash hard-case-five-round-01/start_all.sh
```

第一条完全离线、不需要密钥、不消耗模型额度。第二条按提示输入 OpenRouter API Key，顺序运行 Prob001、Prob002、Prob003；也可加 `--env-file /绝对路径/openrouter.env` 使用已有凭据。

模型仍是最早 V3：OpenRouter `deepseek/deepseek-chat`。Red/Blue 输出各 16000、上下文 128000 tokens。正常完整预算 153 次请求、硬上限 336 次；没有扩大请求预算。网页地址由终端打印，远程需转发对应端口。

## 验证和停止条件

每题两道独立验证题、各两次重复，建立无经验 B₀ 验证基线；五轮练习来自 Red。只有不丢失已认证成功、且至少新增一个验证成功才晋升；独立考试不用于经验筛选。

本次每道验证题包含两个源码缺陷，替代上一版单个常量替换。验证题、练习、开发种子与考试按代码 token 身份互不重复。十五个练习和全部参考/缺陷材料经过真实 Icarus/Yosys 本地检查；本地假回答的完整 smoke 只验证流程，不代表模型成绩。

出题纠错使用以下保护机制：

- 明确要求 Red 在公开测试的可达输入/状态路径上制造可观察的功能错误；重复条件后面的不可达分支、冗余赋值不构成有效出题。
- 每次准入失败反馈公开测试的要求与实测结果：W_bug 应失败、W_preserve 应通过，并附公开仿真日志及具体纠正要求，不再只有抽象拒绝标签。
- 对此前测试过的相同 token 化实现复用确定性的公开结果，直接拒绝重复无效提案，保留来源与哈希；不会反复仿真同一道无效题。
- 定位失败、重复题和准入失败继续使用原有重出题额度，每轮最多四次生成；仍不接纳无效题。
- 四次仍无有效题，或连续两轮没有有效经验，则停止且不继续考试。
- B₀ 四个验证样本全过，仍会以 `validation_baseline_saturated` 停止。此时尚未测试最终考试题，也不代表最终考试全对。当前启动器会停止整批，而非跳过该题。
- 不放宽准入、晋升标准或考试判定；失败记录保留，不自动重跑。

## 复核

```bash
.venv/bin/python -m pytest -q hard-case-five-round-01/tests
bash hard-case-five-round-01/run.sh smoke --run-dir hard-case-five-round-01/smoke-moderate-fresh
```

题单构建脚本为 `prepare_moderate.py`；来源、历史记录和哈希见 `selection-moderate-v1.json`。源码为 `source-promotion-effective-v1/`、清单 `promotion_code_effective_v1.json`。本次只更新 Red 的可达行为出题指令、公开结果反馈和重复提案处理；题单、Blue、晋升规则、模型和预算保持。旧源码和冻结计划保留，入口归档为 `experiment-moderate-v1.py`。

上一版简单题入口/说明归档为 `experiment-simple-v1.py`、`README-simple-v1.md`；所有旧计划、题包、已停止批次记录保留。已用真实失败记录做离线重放，并测试“无效提案—具体反馈—重复识别—有效新提案”控制流。离线测试不能证明真实 Red 一定会按反馈生成有效题，也不保证最终考试收益。当前未启动新真实运行。
