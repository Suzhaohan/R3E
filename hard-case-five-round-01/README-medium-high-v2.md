# 三道固定原题，缓存验证成绩后晋升

全部运行：

```bash
bash hard-case-five-round-01/start_all.sh
```

当前固定使用**最早 DeepSeek V3（2024年12月版）**，OpenRouter 模型 ID 为 `deepseek/deepseek-chat`，不是 V3-0324、V3.1、V3.2 或 V4。启动时输入 **OpenRouter API Key**，原 DeepSeek 官方密钥不能使用。程序不再请求 DeepSeek 官方余额接口，也不发送 V4 thinking 参数。

如使用已有凭据文件，格式为：

```text
OPENROUTER_API_KEY=你的OpenRouter密钥
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

然后执行 `bash hard-case-five-round-01/start_all.sh --env-file /绝对路径/openrouter.env`。凭据文件可省略地址，默认固定为上述 OpenRouter 地址；可选 `OPENROUTER_MODEL` 只能为 `deepseek/deepseek-chat`。

输入一次密钥，顺序执行 Arbiter、VendingTiming、VendingState 三个题目实例，各自五轮。静态组一直使用空经验 B₀；晋升组只使用通过验证的经验。新方案尚未启动付费运行。只做本地检查：

```bash
bash hard-case-five-round-01/start_all.sh --check-only
```

## 不退步保护与缓存

每个电路固定两道独立验证题，每题两个固定种子，共四个样本。验证缺陷与最终考试缺陷、开发种子不同。最终考试不参与晋升选择。

先真实测量 B₀ 的四个验证样本，保存成绩、完整回答、实际仿真记录和状态哈希作为基线。以后只测试新经验候选，不重测旧状态，不再扩充逐轮练习回归题集。每轮候选仍使用相同验证题、种子、模型及预算。

只有同时满足以下条件才晋升：

1. 已认证的每个成功样本，候选全部成功；不能以其他题的增益抵消退步。
2. 候选至少新增一个成功样本。
3. 公开测试和独立参考仿真均通过，才计成功；格式失败、无答案或参考失败均不算通过。

否则保留旧经验、检索配置和成绩缓存。晋升后保存新的不可覆盖缓存；拒绝候选不更新缓存。持平不晋升，无新有效经验则跳过候选验证。缓存绑定实际状态哈希，读取时验证；晋升记录绑定提交，事后审计检查缓存哈希与成功证书。

因此，保留状态在这四个固定样本上的**已认证成绩单调不下降**。这不是“每次随机重新生成都必然成功”，也不保证未知考试题不退化。两次重复是两个样本，并非统计可靠性保证。若 B₀ 已四个样本全对，后续没有严格增益空间，会一直保留 B₀，不虚构晋升。

验证回答、参考组回答及考试回答均不进入经验库。五轮结束后仍独立测试 B₀～B₅，每道考试题每状态两次，输出静态组和最终保留组成绩，不按考试结果回选状态。

## 题目与输出额度

固定测试仍为 **3 道**，新题包为 `materials-medium-high-v2/`：

| 固定题 | 历史依据 | 五轮出题重点 |
| --- | --- | --- |
| Strider `fsm_full_3`（Arbiter） | 5 状态/4 路请求，106 行非注释 RTL；保存候选 9 份中 8 份功能失败、1 份通过 | state 敏感列表、保持请求、默认状态、注册 grant 的周期时序 |
| ChipBench `Prob015 timing`（VendingTiming） | 7 状态售货机；近期静态 B₀ 多次失败 | 组合与寄存输出、当前/下一状态、异步复位、边沿间变化 |
| 历史 `selected_Prob015__083cb0fcc7f0d5d3`（VendingState） | 已完成运行第4轮的投币状态转换缺陷，静态参考功能失败且候选重放失败 | 多周期投币、0.5/1元转换、优先级、余额与找零、保持行为 |

两道售货机题同属一个设计，检验不同缺陷机制；仍各自实例化原五轮流程，不新增跨题共享经验。替换简单 Mux 和较新静态已 2/2 的 Counter，保留时序难题。题目、答案和已有缺陷代码不改写，历史资产绑定见 `cases-medium-high-v2.jsonl`、`selection-medium-high-v2.json`。

本次重扫得到 312 份无经验观察、128 个设置组合，选择解释见 `analysis/medium-high-selection-20261016/SELECTION_REPORT.md`。不同模型、预算和评测不混成一个难度概率；并未重新调用 V3 测量，不保证固定题或验证题在 V3 下的通过率。

Red 通过原有 `mechanism_focus` 接收针对性出题要求：五轮围绕上述能力生成不同的相邻/组合缺陷，根据真实前轮表现调整后续题，争取形成直接有助于最终题的诊断和修复经验；不得复制固定考试变体。固定验证材料也替换为相关能力组合题，仍为每题两个验证题、每题两次，晋升规则和调用数不变。


为兼容所列旧 V3 服务商，Blue 和 Red 输出额度均为 **16000 tokens**，本地上下文 **128000 tokens**。客户端、实际请求、上下文检查、用量保护和预算同步配置。保留一次格式纠正，不增加功能失败重试。

## 请求预算

| 范围 | 原在线与完整考试 | B₀ 验证基线 | 五轮候选验证 | 正常完整合计 |
| --- | ---: | ---: | ---: | ---: |
| 每个电路 | 27 | 4 | 20 | 51 |
| 三个电路 | 81 | 12 | 60 | **153** |

上次回答的 141 次漏算了首次必须测量的 12 次基线；本版本不假设已有真实基线。

- 相比刚才 321 次重验证方案：减少 **168 次**。
- 相比上次实际 91 次请求：增加 **62 次**。
- 相比原完整正常预算 81 次：增加 **72 次**，即 12 次初始基线加 60 次候选验证。
- 含原格式纠正、撞题重出的硬上限：每个电路 **112 次**，合计 **336 次**，原重验证方案为 672 次。

未产生新有效经验、未准入等情况会减少实际请求；153 是无格式纠正和撞题重出时的正常完整预算。输出额度不影响请求次数，但会影响每次可能消耗的 tokens。

## 结果与复核

默认冻结方案为 `plan-v3-medium-high-v2/`，V3 每次运行重新建立基线，不复用 V4 缓存。原 V3 题单与方案 `plan-v3-original-v1/` 保留，旧 V4 源码副本为 `source-promotion-v4-cached-v2/`、`experiment-v4-cached-v2.py`、`launcher-v4-cached-v2.py`，原冻结方案和运行记录保留。代码为 `source-promotion/` 与 `launcher-promotion.py`，源码由 `promotion_code.json` 绑定。上个重验证实现保留在 `source-promotion-paired-v1/`、`experiment-paired-v1.py` 和旧冻结方案中，历史运行不改。

运行自动生成：

- `<run>/promotion_results.json`：两组最终考试成绩、完成状态、调用次数；同时标明固定验证基线与最终认证成绩。
- `<run>/<design>/collection/validation_baseline.json`：B₀ 的实际验证记录。
- `promotions.jsonl`：每轮候选成绩、旧缓存引用、退步／增益样本、晋升原因和保留证书。
- `promotion/<round>/accepted_cache.json`：仅晋升时创建的已认证状态缓存。
- `promotion_result.json`、`rounds/5/commit.json`、`report.json` 和 `audits/`：最终保留状态、独立考试和完整来源审计。

真实运行中断后也汇总已完成电路，未完成成绩不填成成功或失败。离线重做汇总：

```bash
bash hard-case-five-round-01/run.sh results --run-dir /绝对路径/运行目录
```

本地测试与模拟（假回答加真实 Icarus/Yosys，不代表真实模型成绩）：

```bash
.venv/bin/python -m pytest -q hard-case-five-round-01/tests
bash hard-case-five-round-01/run.sh smoke --run-dir hard-case-five-round-01/smoke-fresh
```

日志中保留的 CNY 数值为历史 token 暴露代理，不是 OpenRouter 报价或账单。

此次题单调整没有修改 `source-promotion/` 核心源码；模型仍为最早 V3。新方案与原 V3 方案的流程字段、模型、输出额度、晋升和检索逐项相同。
