# 三道较简单题：有效练习与停止保护

当前默认题单为 `materials-simple-v1/`，冻结计划为 `plan-v3-simple-v1/`：

| 题目 | 固定原题 | 简化依据 |
| --- | --- | --- |
| Mux | Strider mux_4_1_1 | 四选一组合逻辑，重复 case 标签缺陷；历史独立设置记录为 3/3、9/9 修复成功 |
| Counter | Strider first_counter_overflow_2 | 四位计数器及溢出条件；近期历史静态组两批分别 2/2 成功 |
| Prob001 | ChipBench 连续序列检测 arithmetic 原题 | 八位历史寄存器；近期历史静态组 2/2 成功 |

这些记录来自旧模型与旧运行，**不是当前 V3 通过率**。三道题都比仲裁器和七状态售货机结构简单，但不保证模型每次都能修复。

启动三题（顺序运行，各五轮）：

```bash
bash hard-case-five-round-01/start_all.sh
```

先做完全离线的启动检查：

```bash
bash hard-case-five-round-01/start_all.sh --check-only
```

模型仍是最早 V3：OpenRouter `deepseek/deepseek-chat`；Red/Blue 输出各 16000、上下文 128000 tokens。启动时输入 OpenRouter 密钥，或提供已有文件 `--env-file /绝对路径/openrouter.env`。凭据文件只需 `OPENROUTER_API_KEY=...`，可选 `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`。

## 针对上次失败的修复

- 每条 find 必须唯一定位。补丁定位、编译/准入、重复题、保留题碰撞等失败，会把明确原因反馈给 Red；本轮最多四次生成，使用原有重出题额度。
- 先前尝试过的编辑跨轮传递给 Red，重复题不能进入 Blue 练习。不会自动接受无效补丁或降低原准入标准。
- 一轮四次仍无法产生有效题，立即停止整批；连续两轮没有形成有效修复经验，立即停止；均跳过后续考试。
- 首次四个固定验证样本若全过，立即停止：严格新增成功的晋升规则已经没有空间，不能再空跑五轮或声称发生学习。需要另行复核验证题。
- 修复提示明确保留周期、复位、延迟与保持语义，避免把 current-state 输出改成 next-state 输出。
- 页面和汇总显示明确停止原因；停止不是训练完成，不会自动重跑。

## 题目与验证隔离

原始考试缺陷未改写，原参考代码保持。每题有两道独立验证变体、各两次重复；另有五个独立练习变体。练习、验证、历史开发种子与考试互不相同。十五个练习已通过真实 Icarus/Yosys 准入检查，原题和验证题均已验证参考通过、缺陷失败；这些是离线材料检查，不能冒充真实 Red 的生成能力或当前模型成绩。

先真实测量 B₀ 四个验证样本，缓存旧成绩；只验证新候选。既有成功证书全部保留且至少新增一个成功才晋升，否则回退。最终考试不参与晋升选择。五轮完整结束后才运行 B₀～B₅ 独立考试，各两次。

正常完整请求仍最多 153 次；含格式纠正、出题重试的硬上限 336 次。质量停止可提前结束；没有扩大请求或输出预算。

## 复核与历史

新实现位于 `source-promotion-simple-v1/`，清单为 `promotion_code_simple_v1.json`；旧实现 `source-promotion/`、旧题包、旧冻结计划和已停止批次保留。上版入口归档为 `experiment-medium-high-v2.py`，说明归档为 `README-medium-high-v2.md`。

选择与历史成功证据：`selection-simple-v1.json`。本地假回答加真实仿真 smoke 仅验证流程，不代表模型学习效果。

```bash
.venv/bin/python -m pytest -q hard-case-five-round-01/tests
bash hard-case-five-round-01/run.sh smoke --run-dir hard-case-five-round-01/smoke-simple-fresh
```

质量停止时保存 `collection/stop_reason.json`、`collection/collection.json`、每次生成与准入证据。离线汇总：

```bash
bash hard-case-five-round-01/run.sh results --run-dir /绝对路径/运行目录
```

当前仅完成离线检查，未启动新真实批次。旧失败分析见 `analysis/run-stop-audit-20261016.md`。
