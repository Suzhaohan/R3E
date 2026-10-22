# Blue 低通过率 RTL 与具体缺陷清单

本清单依据现有运行记录、审核决策和实际 RTL 差异整理，未进行新的模型调用。这里的通过率指各次实验原有可见测试口径，不等同于完整功能正确率。历史低通过率不能保证当前 Blue 仍然难以修复。

## 测试集来源与实验归属

本清单中的 RTL 来自 **ChipBench** 和 **HWE-bench** 两个数据集。必须进一步区分“RTL 设计来自哪个数据集”和“待修复 Bug 是数据集原有的，还是 Red 新生成的”。

| 本文案例 | RTL 来源 | Bug 来源 | 产生本文结果的实验 |
| --- | --- | --- | --- |
| 第 1 节：Prob003 非重叠序列检测器 | ChipBench 的设计与规范 | Red 新生成的状态转换缺失，不是直接使用 ChipBench 原有缺陷 | `partA_chipbench_20261005/aware`；后续在 `red_search_pilot_v1`、`v2` 中复验同一种子 |
| 第 1 节：Prob015 投币、出货控制器 | ChipBench 的设计与规范 | Red 新生成的金额状态转移错误 | `partA_chipbench_20261005/blind` |
| 第 2 节：Prob001、Prob002、Prob023、Prob015、Prob017，共 8 个 Bug | ChipBench | ChipBench 原有缺陷，类别为 arithmetic、timing、assignment 或 state_machine | `register_probe_20261004`；本文采用清理后的 46 个 Bug 分析子集中的低通过率案例 |
| 第 3 节：Prob004 连续序列检测器 | ChipBench 的设计与规范 | Red 新生成的复合变异；补充验证发现 Blue 修复仍残留错误 | `red_search_pilot_v1` 的 warm-slot-3 |
| 第 3 节：Ibex 907 | HWE-bench，`lowRISC/ibex` 仓库，任务 `lowRISC__ibex-907` | 数据集中的真实仓库修复任务；容量回归是 Blue 修复时引入的错误 | `hwe_dev_run_20261007` 开发试点与事后审核 |
| 第 3 节：Ibex 2232 | HWE-bench，`lowRISC/ibex` 仓库，任务 `lowRISC__ibex-2232` | 数据集中的真实仓库修复任务；字段与初始化不一致发生在 Blue 修复过程中 | `hwe_dev_run_20261007` 开发试点与事后审核 |

第 2 节的低通过率来自 **ChipBench 寄存器轨迹探测**，不是 Part B 的 21 个 holdout Bug 结果；也不是整个 ChipBench 数据集的通过率。HWE 两项来自开发集，不是正式留出集。本文没有将 CirFix、VerilogEval 或 RTLLM 案例列入低通过率清单。

数据集说明：[测试集与设计概览](02_test_sets.md)。具体运行、缺陷文件及审核证据见各节链接。

## 1. Red 生成且经过审核的两个历史困难案例

这两个案例均来自探索阶段，达到过“3 次独立运行中至少 2 次未修复”的规则，并经人工审核为 PASS。每次运行最多允许 3 次修复尝试，不能与下文的一次尝试探测直接比较。

| RTL 设计 | Red 实际生成的 Bug | 历史修复通过情况 | Blue 暴露的问题 |
| --- | --- | --- | --- |
| `Prob003_non-overlapping_sequence_detect`：非重叠序列检测器 | 将 `s6`、`sf6` 的 `nstate=data?sf1:s1` 改成 `nstate=idle`，丢掉下一组六位输入的首位，破坏组边界 | Part A 为 **1/3**；后续种子复验 v1 为 **1/3**，v2 为 **2/3** | 多次修改输出断言时机，却未正确恢复跨组状态转换；失败运行还夹杂输出预算耗尽。属于历史有效命中，难度有明显采样波动 |
| `Prob015_vending_machine2`：投币、出货控制状态机 | `S0_5 + d2` 从 `S1_5` 改为 `S1`；`S1_5 + d2` 从 `S2_5` 改为 `S2`。`d2` 表示投入 1 元，两个转移少计了 0.5 元 | Part A 为 **1/3** | 能识别金额转移错误，但部分修复又改动原有保持逻辑、输出或复位行为，引入新的不一致；不能解释成不会做金额计算 |

挑战 ID 分别为 `RC_406d811b4d61a2`、`RC_02caa510ba2821`。后者的审核仅适用于保留原上下文的这份变异，不代表该设计的任意变异都有效。这两个案例尚未证明 Red 的针对性优势或跨设计迁移。

证据：[序列检测器审核及差异](../../../R3E-local-artifacts/partA_chipbench_20261005/aware/hit_review.md)、[审核决策](../../../R3E-local-artifacts/partA_chipbench_20261005/aware/hit_decisions.json)；[投币控制器审核及差异](../../../R3E-local-artifacts/partA_chipbench_20261005/blind/hit_review.md)、[审核决策](../../../R3E-local-artifacts/partA_chipbench_20261005/blind/hit_decisions.json)；[种子 v1](../../../R3E-local-artifacts/red_search_pilot_v1/pilot_result.json)、[种子 v2](../../../R3E-local-artifacts/red_search_pilot_v2/pilot_result.json)。

## 2. 真实 ChipBench 缺陷：5 个 RTL 设计、8 个低通过率 Bug

统一条件：DeepSeek V4 Flash、low thinking、32k 输出预算、提供规范、每个 Bug 仅一次修复尝试，种子为 7 和 1016。无寄存器轨迹和有寄存器轨迹是两种不同的反馈设置，各有两次观察，不能合并成同一设置下的四次重复。

下表从经过清理的 46 个 Bug 探测子集中，列出两种设置下通过数均不超过 1/2 的全部案例。它们是数据集原有 Bug，不是 Red 新发现的有效命中。RTL 链接指向实际缺陷文件。

| RTL / 数据集标签 | 实际代码错误 | 无寄存器轨迹 | 有寄存器轨迹 |
| --- | --- | ---: | ---: |
| [Prob001 连续输入序列检测器](../../datasets/chipbench/arithmetic/Prob001_continuous_input_sequence_detect/buggy.sv)，arithmetic | `{a_tem[6:0],a}` 改成 `{a,a_tem[6:0]}`；新输入位插入错误一端，历史位序错误 | **1/2（50%）** | **0/2（0%）** |
| [Prob002 extraneous-items 序列检测器](../../datasets/chipbench/arithmetic/Prob002_extraneous_items_sequence_detect/buggy.sv)，arithmetic | `{a_tem[7:0],a}` 改成 `{a,a_tem[7:0]}`；序列历史的拼接顺序错误 | **0/2（0%）** | **1/2（50%）** |
| [Prob023 格雷码计数器](../../datasets/chipbench/arithmetic/Prob023_gray_code_counter/buggy.sv)，arithmetic | 二进制转格雷码表达式由 `(bin_add_wire >> 1) ^ bin_add_wire` 改成右移 2 位，破坏相邻位异或关系 | **1/2（50%）** | **0/2（0%）** |
| [Prob015 投币、出货控制器](../../datasets/chipbench/timing/Prob015_vending_machine2/buggy.sv)，timing | 组合输出译码改成时钟沿触发的寄存器输出，改变出货和找零输出的响应时序 | **0/2（0%）** | **1/2（50%）** |
| [Prob015 投币、出货控制器](../../datasets/chipbench/state_machine/Prob015_vending_machine2/buggy.sv)，state_machine | `S1+d2` 应到 `S2` 却到 `S3`；`S1_5+d2` 应到 `S2_5` 却到 `S1`。注意这与上节 Red 变异不同 | **1/2（50%）** | **1/2（50%）** |
| [Prob017 分数分频器](../../datasets/chipbench/assignment/Prob017_arbitrary_fractional_frequency_division/buggy.sv)，assignment | 输出比较阈值中的 `div_e >> 2` 改成 `div_e >> 3`，改变高电平持续区间 | **1/2（50%）** | **1/2（50%）** |
| [Prob017 分数分频器](../../datasets/chipbench/arithmetic/Prob017_arbitrary_fractional_frequency_division/buggy.sv)，arithmetic | 同一输出阈值的 `div_e >> 2` 改成 `div_e >> 1`，改变输出波形时序 | **1/2（50%）** | **1/2（50%）** |
| [Prob017 分数分频器](../../datasets/chipbench/timing/Prob017_arbitrary_fractional_frequency_division/buggy.sv)，timing | `div_flag` 的时钟沿非阻塞更新改成组合块内的自引用阻塞赋值，丢失原有时序状态语义 | **1/2（50%）** | **1/2（50%）** |

每格只有两次观察，0/2 也不表示稳定无法修复。非通过结果需要继续按无回答、格式失败、编译失败和功能性误修拆分，不能全部称为推理失败。原记录中，Prob002 的无轨迹 seed 7 和 Prob017 timing 的无轨迹 seed 7 均曾出现一次 provider failure；后者最终通过。这里保留记录的最终通过口径，不把服务商错误归为功能错误。

Prob017 timing 含组合自引用，应作为真实缺陷诊断案例；若用于新的 Red 实验，需重新检查是否满足该实验的无组合环路等准入要求。

统计证据：[清理后的逐项分析](../../../R3E-local-artifacts/bug_type_analysis_20261008/analysis.json)、[原始双种子探测](../../../R3E-local-artifacts/register_probe_20261004/results.json)、[当前 manifest](../../datasets/manifests/chipbench89.jsonl)。

## 3. 有具体错误修复证据，但不足以给出稳定低修复率的案例

| RTL / 任务 | 具体问题 | 已有证据与限制 |
| --- | --- | --- |
| `Prob004_continuous_input_sequence_detect2`，Red warm-slot-3 | Red 删除检测结束后接收下一组首个零的转换，并增加一个输出时序错误。Blue 只修输出，留下状态转换缺失 | 通过原可见测试，但合法输入 `01100110` 只报告第一个 `0110`，漏掉第二个；只有一份实际错误补丁，不能记为重复确认的新命中 |
| Ibex 907，prefetch/FIFO | Blue 为恢复请求推进，允许“没有在途请求”时继续取指，即使 FIFO 已满；背压下响应丢失、地址与数据不对应 | 3/3 通过可见测试，其中一份补丁经合法见证确认错误，另两份在补充检查范围内未发现不匹配；属于真实任务修复引入的问题，不是 Red 生成命中 |
| Ibex 2232，debug-mode PMP / `ibex_pkg.sv` | 增加结构体字段后未同步聚合初始化；回退字段时又留下初始化项 | 2/3 在预算内通过可见测试，1/3 未修复；同时存在文件选择超预算消耗尝试的影响，不能将全部失败归因于修复推理 |

证据：[Prob004 的 Red RTL](../../../R3E-local-artifacts/red_search_pilot_v1/generator_review/red.sv)、[Blue 补丁](../../../R3E-local-artifacts/red_search_pilot_v1/generator_review/blue.sv)、[可重放见证与分析](../../../R3E-local-artifacts/red_search_pilot_v1/generator_review/review.md)；[Ibex 审核及见证链接](../../../R3E-local-artifacts/hwe_dev_run_20261007/review/REVIEW.md)。

## 4. 当前可支持的判断

最明确的历史困难案例是 **Prob003 的组边界状态转换缺失**和 **Prob015 的金额状态转移变异**。真实 Bug 的低首次通过率还集中在 **Prob001/002 的序列位序、Prob023 的格雷码转换，以及 Prob017 的分频状态和输出阈值**。

这些证据更具体地指向“历史数据位序—状态演化—输出时机”的关联，而不是证明所有 arithmetic 或 FSM Bug 都难。投币控制器是 RTL 设计用途，不是新定义的 Bug 类型。

data_accumulation、Traffic_lights 等参考实现与规范冲突的案例不应充当低修复率证据。signal_generator、Simple RAM 的未决差异，以及 Ibex 1816 未被消费者采纳的输出差异，也不列为已确认困难案例。以上清单没有把格式错误、服务商故障、人工构造的载体验收变体或单纯较长的代码当成 Red 的有效困难命中。
