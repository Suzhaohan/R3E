# 三题经验独立：全部训练完成后统一考试

保留从 `09_Low_Pass_Rate_RTL_Cases.md` 选择的3道题：Prob001 arithmetic、Prob023 Gray计数器、Prob003 历史 RC_406d811b4d61a2 双边界缺陷。考试原件、验证材料与 V3-0324 模型不变。当前计划 `plan-v3-0324-reliable-v1/`，源码 `source-promotion-reliable-v1/`，源码清单 `promotion_code_reliable_v1.json`。

## 运行

```bash
bash hard-case-five-round-01/start_all.sh --check-only
bash hard-case-five-round-01/start_all.sh
```

第一条只做本地检查，无需密钥、不调用模型。第二条按提示输入 OpenRouter API Key；也可加 `--env-file /绝对路径/openrouter.env`。新建批次，不覆盖旧运行、不隐式续跑。模型 ID 固定为 `deepseek/deepseek-chat-v3-0324`，若凭据文件显式设置 OPENROUTER_MODEL，须与之相同。输出16000、上下文128000 tokens。

## 准确的实验机制

1. 三题各自建立验证基线，并独立做五轮对抗练习。对抗组只读取本题获准保留的经验；静态组每次从无经验 B₀ 开始，三题之间不共享经验。
2. 每轮 Red 提案先通过本地检查，确认能编译、W_bug失败且W_preserve通过，再交给两组修复。只有对抗组在线公开修复结果能产生候选经验。固定验证只负责决定经验晋升，不是最终考试。
3. 三题各完成五轮后，写入 `training_barrier.json`，绑定各自 B₅ 状态。在此之前不发送任何独立考试请求。
4. 统一考试阶段，两组做同一套3道独立考试题。静态组使用各题 B₀，对抗组使用各题 B₅；考试期间不更新经验、不调参、不回流结果。只测 B₀/B₅，不再补测 B₁至B₄。

每道考试题每组重复2次，所以是**3道题、每组6次作答**，不是6道不同题。不同题的考试请求仍顺序执行，但都属于全部训练完成后的统一考试阶段。固定验证仍为每题2道、各重复2次；验证4/4不能称为考试满分。

即使初始验证满分，或连续两轮未形成经验，也继续完成五轮和最终考试。没有提升本身就是实验结果，不再以此取消考试。正常完整请求预算129次，包含纠错的硬上限288次（每题96次），低于旧版336次。

## 出题失败的可靠处理

在线 Red 每轮最多4次请求；编译失败会收到真实日志、行号、源码上下文及失败编辑，要求优先纠正。括号外条件链可本地保守纠正，原始输出与纠正记录保留。语法通过仍必须通过功能缺陷资格检查。

在线提案全部无效或主动放弃时，自动使用**预先通过公开测试的备用练习**。每题预留5份，在线 Red 不能占用；它们与考试、验证和开发种子分离，各轮选择不同的备用练习。备用池在冻结计划时逐一做真实编译、仿真和结构检查，运行时再次验证。备用选择不读取隐藏评测、验证分数或考试结果，不增加模型请求。

`fallbacks.jsonl`、各轮 `generation_source` 和汇总 `fallback_practice_count` 明确标记 `prequalified_human_seeded_fallback`。备用题是人为准备的练习，不算 Red 在线成功出题，不可据此宣称纯自动对抗生成效果。模型仍可能提交错误提案，但不会再仅因冗余或编译失败提案耗尽重试而中止整批。

真正的凭据、请求预算、材料篡改、仿真环境或备用题资格异常仍停止，不会拿无效题继续或伪造考试成绩。

## 提示与验证

Prob001 的专项提示覆盖历史位序/位宽、比较与寄存器时序、输出保持；Prob003 覆盖逐拍状态转移与分组边界，并要求失败后简化练习。Blue 调试提示在两组中一致；Prob023 保持原提示。代码见 `r3e/loop/targeted_prompts.py`、`red_continuous.py`、`reliable_practice.py`。

```bash
.venv/bin/python -m pytest -q hard-case-five-round-01/tests
bash hard-case-five-round-01/run.sh smoke --run-dir /tmp/r3e-reliable-fresh
```

smoke 使用假模型回答与真实本地编译/仿真，只证明流程和隔离约束，不证明真实模型成绩改善。本次未启动付费运行。旧入口归档为 `experiment-syntax-v1.py`，旧源码、计划及所有真实结果保留。
