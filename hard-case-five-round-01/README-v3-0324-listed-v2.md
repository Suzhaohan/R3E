# 三道清单题：各题独立运行

当前题单严格来自仓库根目录 `09_Low_Pass_Rate_RTL_Cases.md`，题目总数仍为 **3**：

| 题目 | 清单位置 | 固定考试缺陷 |
| --- | --- | --- |
| Prob001 | 第2节，ChipBench arithmetic | 八位输入历史拼接位序错误，保留原始缺陷文件 |
| Prob023 | 第2节，ChipBench arithmetic | 四位格雷码计数器，二进制转格雷码的右移1位被改成右移2位，保留原始缺陷文件 |
| Prob003 | 第1节，RC_406d811b4d61a2 | 两个组边界分支 s6、sf6 都将下一状态改成 idle，使用交付的历史审核缺陷原件 |

Prob003 不再使用清单未单列的 eval_miss_branch 相邻变体。选择清单、原始 RTL、历史证据均由 `selection-listed-v2.json` 绑定哈希，检查时验证。历史通过率不是当前 V3 的修复概率。

## 修复：一题满分不再中止其他题

若某题首次四个验证样本全部通过，该题返回正常的 `skipped` 结果，原因 `validation_baseline_saturated`，不再向批量启动器抛出失败。记录验证基线和请求数，跳过该题训练与考试，继续下一题。

例如：任意一题完成 → 下一题若验证4/4则单独跳过 → 后续题仍会运行。页面显示“本题已跳过，批次继续下一题”。汇总明确区分已完成、已跳过和未开始；没有考试的题不会算作成功，不能宣称三题考试全部完成。

网络、凭据、请求上限、源码一致性等真正异常仍会中止，不会被伪装成正常跳过。此前的出题纠错额度耗尽、连续无有效经验保护保持；本次只将验证满分改为非致命的单题结果。

## 运行

```bash
bash hard-case-five-round-01/start_all.sh --check-only
bash hard-case-five-round-01/start_all.sh
```

第一条只检查本地，不需要密钥、不消耗模型额度。第二条输入 OpenRouter API Key，顺序处理 Prob001、Prob023、Prob003；可加 `--env-file /绝对路径/openrouter.env` 使用已有凭据。

已切换为 **DeepSeek-V3-0324（2025年3月24日版）**，OpenRouter 模型 ID 为 `deepseek/deepseek-chat-v3-0324`，Blue/Red 输出各16000、上下文128000 tokens。正常完整预算153次请求、硬上限336次；提前跳过的题只消耗已实际完成的基线请求。

## 出题、验证与考试

Red 必须生成在公开测试中可观察的功能缺陷；无效题收到实际测试结果和日志反馈，重复提案直接拒绝并复用确定性的公开结果，每轮最多四次生成。Blue 使用原有修复与经验流程。

每题两道独立验证题、每题两次重复，先建立 B₀ 验证基线；新经验必须保留已认证成功且新增成功才晋升。独立考试不参与经验选择。各题五个练习变体与验证、开发种子、考试按代码 token 身份分离。

Prob002 已替换为清单第2节的 Prob023。新题检查四位 Gray 序列、每两拍递增、循环回绕、异步复位及输出保持；参考通过、原缺陷失败，五个练习与独立验证变体均通过本地资格检查。

## 文件与复核

默认题包 `materials-listed-v2/`，验证包 `validation-listed-v2/`，计划 `plan-v3-0324-listed-v2/`，源码 `source-promotion-v3-0324-v1/`，清单 `promotion_code_v3_0324_v1.json`；构建脚本 `prepare_listed_v2.py`。

```bash
.venv/bin/python -m pytest -q hard-case-five-round-01/tests
bash hard-case-five-round-01/run.sh smoke --run-dir hard-case-five-round-01/smoke-listed-fresh
```

smoke 使用假模型回答和真实本地仿真，仅测试流程，不代表真实模型能力。回归测试专门覆盖“第一题完成、第二题验证满分、第三题仍完成”的完整流程，并检查跳过题没有伪造考试成绩。

旧题包、旧源码、冻结计划和真实运行结果保留。上版入口/说明归档为 `experiment-moderate-feedback-v1.py`、`README-moderate-feedback-v1.md`。本次未启动付费运行。

## V3-0324 接入

Red 和 Blue 都固定请求 `deepseek/deepseek-chat-v3-0324`；请求保护也校验该 ID，拒绝误用旧版本。继续使用原 OpenRouter API Key 与地址 `https://openrouter.ai/api/v1`，不需要 DeepSeek 官方密钥。

凭据文件如果只写 `OPENROUTER_API_KEY=...`，无需修改；如果显式写了 `OPENROUTER_MODEL`，请改为 `deepseek/deepseek-chat-v3-0324`，否则启动会明确拒绝，不会静默切回旧模型。

2026-10-17 核对 OpenRouter 的公开模型及服务商目录，所列服务商的额度支持现有上下文128000、输出16000。官方版本说明：[DeepSeek V3-0324](https://api-docs.deepseek.com/news/news250325/)；[OpenRouter 模型目录](https://openrouter.ai/deepseek/deepseek-chat-v3-0324/api)。这是公开目录核对，不是付费推理连通性或账户权限测试。

三道题、晋升规则、满分题单独跳过、出题反馈和请求预算均保持。新模型必须在新运行目录重新测基线，不复用旧模型成绩。旧模型入口归档为 `experiment-listed-v1.py`，对应源码和冻结计划保留。

## 本次替换与提示建议

保持3题，第二题改为 Prob023；Prob001、Prob003 的考试、验证和 mechanism_focus 提示保持原样，Blue/Red 模型、源代码、晋升规则和预算不变。旧题单入口归档为 `experiment-v3-0324-listed-v1.py`，旧批次证据保留；当前新题单尚未启动真实模型运行。

针对另外两题的出题/修复提示建议与证据见 `analysis/prompt-improvement-20261017.md`，属于建议，尚未应用或做真实效果验证。
