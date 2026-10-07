# AIC·AI\+集成电路比赛文档

> 参赛成员：张丹阳、黄予辰、王佳音
> 
> QQ交流群：
> 
> 官网链接：
> 
> 

# R³E：比赛版

现在的比赛主链：

```Plain Text
Buggy RTL + Testbench
        ↓
Icarus Runtime Evidence
        ↓
Failure Descriptor
        ↓
Descriptor Router
        ↓
R³E Blue Candidate Portfolio
        ↓
Candidate Proposal
        ↓
AST / Scope Gate
        ↓
Parse
        ↓
Compile
        ↓
Simulation
        ↓
Differential Oracle
        ↓
Yosys Structural Check
        ↓
Repeatability
        ↓
Accept / Reject
```

当前比赛架构：

```Plain Text
R3E/
│
├── competition/      ← 比赛产出层
    ├── __init__.py   ← Competition Python package 入口/版本信息
    ├── config.py     ← 统一配置加载器，读取并验证 competition.yaml
    ├── cli.py        ← 命令行入口，也就是本地开发和自动化复现的总入口
    └── app/          ← 比赛演示用的
│
├── r3e/              ← 核心算法层
│
├── configs/          ← 核心策略 /Blue/Memory 等冻结配置
│
├── datasets/         ← RTL benchmark 与 testbench
│
├── tests/            ← 测试用的目录，所有的测试脚本都在
│
├── scripts/          ← 数据完整性/发布时检查用的
│
├── experiments/      ← 这个时科研实验，不是比赛演示用的主路径
│
└── benchmarks/       ← benchmark 相关内容
```

---

## AIC·AI\+集成电路技术报告

> 赛题方向：芯片智能设计
> 比赛分支：`competition/aic-ic-2026`
> 
> 

# 一、作品概述

## 1\. 背景介绍

随着数字芯片复杂度持续提升，RTL 设计已经从简单组合逻辑扩展到包含复杂状态机、总线协议、缓存控制、时序交互和多模块协同的大规模系统。RTL 功能正确性直接影响后续综合、验证与流片质量，因此功能调试是芯片前端设计中的核心环节之一。

传统 RTL 调试通常经历：

```Plain Text
RTL 编写
  ↓
编译
  ↓
仿真
  ↓
波形分析
  ↓
人工定位
  ↓
代码修改
  ↓
回归验证
```

该流程存在一个核心问题：**“代码能够编译”并不意味着“硬件功能正确”。**

大量真实 RTL 缺陷属于功能语义错误，例如：

- 错误的状态转移条件；

- 时钟边沿或事件控制错误；

- 计数器比较条件错误；

- 位宽、索引或移位关系错误；

- dataflow 传播错误；

- 状态寄存器更新错误；

- 某一 FSM 分支缺失；

- 在局部 testcase 上修复后引入新的 regression。

近年来，大语言模型已经展现出代码理解与程序修复能力，但直接将通用 LLM 应用于 RTL 仍存在三类问题。

第一，LLM 容易把“语法合法”当成“功能正确”，无法独立承担硬件正确性判定。第二，单轮 prompt 修复存在明显随机性，同一个错误可能生成多个不同质量的 patch。第三，直接将历史修复案例放入上下文并不能保证持续提升，错误经验反而可能污染后续修复。

因此，本作品提出 **R³E\-AIC：自进化 RTL 智能纠错系统**，将大语言模型的代码推理能力与真实 EDA 工具链、对抗式缺陷发现、正确性门控和策略记忆相结合，形成一个面向 RTL 功能语义缺陷的闭环智能修复系统。

## 2\. 目标定位

R³E\-AIC 的目标不是构建一个单纯的 Verilog 代码生成工具，而是建立：**“缺陷发现—智能诊断—候选修复—EDA 验证—经验演化”闭环。**

系统目标包括以下五个方面。

### 2\.1 自动发现功能缺陷

利用 testbench、仿真输出、执行轨迹及结构化 failure descriptor，识别：

- temporal；

- control；

- dataflow；

- state\-transition；

- operator/comparator；

- bit/index；

- functional mismatch。

### 2\.2 自动生成修复候选

针对不同错误类型，由多个 repair lens 协同生成有限候选：

```Plain Text
Generic
Temporal
Control
Dataflow
```

避免把全部候选预算集中在一个通用 prompt 上。

### 2\.3 由 EDA 工具判断正确性

系统建立 Correctness Gate：

```Plain Text
Parse
 → Compile
 → Simulation
 → Functional Oracle
 → Formal Verification
 → Regression
```

模型只负责提出修复，**不拥有正确性判定权**。

### 2\.4 安全积累修复经验

将成功执行轨迹保存为 Verified Episode，并将经验抽象为策略级控制信息。只有通过 replay 与非目标回归验证的经验才允许进入 Active Memory。

### 2\.5 持续发现新的 unresolved failures

R³E\-AIC 的 Red Discovery Engine 根据当前 active policy 继续搜索尚未解决的 RTL 缺陷类型，使系统从静态修复器升级为持续演化的智能设计工具。

# 二、需求分析

## 1\. 问题剖析

### 1\.1 RTL 功能错误比语法错误更难

语法错误通常能够被编译器直接定位，而功能错误往往：

- 能正常 parse；

- 能通过 elaboration；

- 能成功 compile；

- 只有在特定输入序列或状态下产生错误输出。

因此，RTL Repair 的真正难点不是“把代码改到能编译”，而是：**在有限修改范围内恢复正确的时序和功能语义。**

### 1\.2 人工波形定位成本高

一个典型功能错误往往需要工程师：

1. 复现失败 testcase；

2. 找到首个 mismatch；

3. 对比相关寄存器和组合信号；

4. 分析状态机或数据通路；

5. 修改 RTL；

6. 重新编译和仿真；

7. 回归其他 testcase。

随着模块规模扩大，定位时间远高于代码修改时间。

### 1\.3 通用 LLM 缺乏硬件正确性闭环

通用 LLM 可以生成看似合理的 RTL，但可能出现：

- 不符合 testbench；

- 改错时序；

- 扩大修改范围；

- 破坏其他状态；

- 通过 compile 但 simulation fail；

- 修复一个 case 后造成 non\-target regression。

因此，系统需要“AI \+ EDA”协同，而不是仅调用通用模型。

### 1\.4 单次修复无法形成稳定能力

传统 LLM Repair 通常是：

```Plain Text
Bug
 ↓
Prompt
 ↓
Patch
 ↓
结束
```

下一个类似 bug 仍可能从头推理。

R³E\-AIC 希望实现：

```Plain Text
Bug
 ↓
Repair
 ↓
Verification
 ↓
Experience
 ↓
Replay
 ↓
Promotion
 ↓
Next Repair
```

核心需求不是单纯存储更多历史，而是：**保证经验被激活前经过 correctness gate。**

## 2\. 需求调研

本项目需求来源主要包括三类。

### 2\.1 科研实践需求

在 RTL 自动修复研究中发现，仅依赖编译通过率无法准确反映修复质量。部分方法可以恢复 syntax/compile，但仍不能解决：

- FSM；

- state transition；

- 时序；

- dataflow；

- 跨周期行为。

因此需要统一 functional oracle。

### 2\.2 公开 benchmark 需求

项目使用公开 RTL Repair 数据集和 testbench 作为评测基础，包括：

- CirFix；

- Literature 相关功能缺陷集合；

- Strider；

- RTLFixer compile recovery 数据。

正式提交版本将在附录中标注数据来源与许可证，并通过 SHA\-256 manifest 固定比赛使用的数据版本。

### 2\.3 目标用户需求

目标用户包括：

- 数字 IC 前端设计人员；

- RTL 验证工程师；

- FPGA 开发人员；

- EDA 算法研发人员；

- 数字电路教学和科研人员。

用户主要需求可归纳为：

正式提交前补充 1–3 份可公开的用户试用反馈，形成需求侧佐证。

# 三、AI 技术工具选择与运用

R³E\-AIC 采用“大语言模型 \+ Agentic Workflow \+ EDA Verification”的混合技术路线。

## 1\. 大语言模型

模型主要负责：

- 理解 RTL；

- 分析执行反馈；

- 提出有限候选 patch；

- 按不同 repair lens 生成差异化修复策略。

模型输出不直接成为最终答案，而是进入候选验证链。

## 2\. 多专家 Candidate Portfolio

系统将 RTL 修复拆分为多个 repair lens。

### Generic

适合一般 RTL 功能错误。

### Temporal

重点处理：

- clock edge；

- event\-control；

- cycle relation；

- nonblocking/sequential behavior。

### Control

重点处理：

- FSM；

- branch；

- condition；

- state transition。

### Dataflow

重点处理：

- bit propagation；

- signal assignment；

- width；

- index；

- operator；

- shift。

每次修复预算固定，由系统 router 根据当前结构化 FailureDescriptor 分配候选，而不是无限调用模型。

## 3\. EDA 工具

### Icarus Verilog

用于：

- parsing；

- elaboration；

- compile；

- simulation；

- testbench execution。

### Yosys

用于：

- synthesis/formal 相关检查；

- 部分 formal property；

- structural analysis。

EDA 工具负责输出真实执行结果，避免模型自评。

## 4\. Agentic Orchestration

R³E\-AIC 使用多个逻辑角色：

```Plain Text
Bug Discovery
Diagnosis
Repair
Verification
Memory
Evolution
```

这些角色由 runner 统一调度。

模型 adapter 不能：

- 自报 oracle success；

- 自报 formal pass；

- 自行修改 policy registry；

- 自行提升 memory 权限；

- 绕过 verifier。

## 5\. 正确性门控技术

候选 patch 必须经过：

```Plain Text
Candidate
   ↓
Parse
   ↓
Compile
   ↓
Simulation
   ↓
Oracle
   ↓
Formal / Regression
   ↓
Accepted Patch
```

任意关键证据缺失即 fail closed。

# 四、项目实施

## 1\. 实施方案设计

比赛版本基于现有 `dev/policy-evolution-v2` 分支构建 Competition Facade。

原则：**保留科研核心，新增产品层，不复制核心逻辑。**

总体结构：

```Plain Text
Web Demo
   ↓
Competition API
   ↓
Service Facade
   ↓
R³E Core
   ↓
LLM + Icarus + Yosys
```

## 2\. 软件模块

### 2\.1 Intelligent Repair Engine

对应：

```Plain Text
r3e/blue/portfolio/
```

主要模块：

- router；

- lens registry；

- candidate executor；

- model provider；

- RTL AST materializer；

- oracle gate verifier。

### 2\.2 Evolution Policy Engine

对应：

```Plain Text
r3e/policy/
```

负责：

- active policy；

- policy search；

- promotion；

- rollback；

- registry。

### 2\.3 Verification \& Evolution Runtime

对应：

```Plain Text
r3e/arena/
```

负责：

- round orchestration；

- manifest；

- paired replay；

- target / non\-target；

- audit。

### 2\.4 Adversarial Bug Discovery

对应：

```Plain Text
r3e/red/
```

负责：

- challenge generation；

- hard failure archive；

- novelty；

- learnability；

- lineage；

- grounded operator。

### 2\.5 Verified Experience Memory

对应：

```Plain Text
r3e/memory/
```

负责：

- Verified Episode；

- memory candidate；

- compatibility；

- activation；

- bank；

- revalidation。

## 3\. Competition Service Facade

比赛版新增：

```Plain Text
competition/services/
```

包括：

```Plain Text
diagnosis_service.py
repair_service.py
verification_service.py
evolution_service.py
memory_service.py
benchmark_service.py
```

该层的作用是把科研代码转换成稳定产品 API。

## 4\. Web Demo

比赛版提供五个页面。

### 4\.1 Repair Studio

展示：

- RTL；

- diagnosis；

- candidate；

- diff；

- verification result。

核心交互：

```Plain Text
Load Demo
→ Diagnose
→ Generate
→ Verify
→ Apply
```

### 4\.2 Verification Trace

展示：

```Plain Text
Parse
Compile
Simulation
Oracle
Formal
Regression
```

并对多个候选显示 Reject / Accept。

### 4\.3 Evolution Lab

展示：

```Plain Text
B0
 ↓
F1 discovered
 ↓
repair
 ↓
replay
 ↓
promotion
 ↓
B1
```

### 4\.4 Experience Memory

展示：

```Plain Text
Shadow
→ Qualified
→ Active
```

或：

```Plain Text
Shadow
→ Replay Fail
→ Rejected
```

### 4\.5 Benchmark Dashboard

展示：

- Repair Rate；

- verification funnel；

- evolution curve；

- case study。

## 5\. 三个典型应用案例

### 案例一：Counter Temporal Defect

案例：

```Plain Text
first_counter_overflow_wadden_buggy1
```

错误：

```Plain Text
always @(clk)
```

正确：

```Plain Text
always @(posedge clk)
```

该案例用于展示：

- event\-control diagnosis；

- temporal lens；

- minimal patch；

- simulation/oracle。

### 案例二：FSM Control Defect

案例：

```Plain Text
fsm_full_wadden_buggy1
```

错误表现：

- 状态机可以进入 GNT3；

- GNT3 的输出逻辑缺失；

- `gnt_3` 无法按预期拉高。

系统诊断：

```Plain Text
Failure type: control/FSM
State: GNT3
Affected signal: gnt_3
```

修复：

```Plain Text
GNT3 : begin
    gnt_3 <= #1 1'b1;
end
```

该案例用于证明：原 RTL 可以编译，但功能错误仍能被 R³E\-AIC 发现和修复。

### 案例三：Shift Register Dataflow Defect

案例：

```Plain Text
lshift_reg_wadden_buggy1
```

重点展示：

- bit\-level dataflow；

- index；

- shift semantics；

- blocking assignment side effects；

- Generic/Temporal/Dataflow 多候选比较。

### 案例四：Red\-Bule Adversarial Evolution for RTL Repair

在两台计算机/服务器隔离实验进行对比，意在展示对抗式的动态修复可以让 agent 见识到新的 bug，以此来增强 agent 的修复能力。测试集采用 Strider\-14 \+ Red 自生成 Bug 集。

```Plain Text
相同初始 Agent
        │
        ├────────────────────┐
        │                    │
        ▼                    ▼
 Machine A              Machine B
 Static Repair          Adversarial Repair
 修复但不进化           Red → Blue → Verify
                         ↓
                    Policy / Experience
                         ↓
                     动态更新
        │                    │
        └──────────┬─────────┘
                   ↓
             Frozen Test Sets
          Strider-14 + Red-Heldout
                   ↓
              Repair Rate
```

**Machine A：Static Repair Agent**

它具有：

```Plain Text
相同 LLM
相同 Candidate Budget
相同 Verification Gate
相同 Blue Portfolio
相同初始 Policy B0
相同初始 Memory M0
```

但：

```Plain Text
不运行 Red
不吸收新策略
Policy 固定
Memory 固定
```

它可以正常：

```Plain Text
Bug
 ↓
Diagnosis
 ↓
Repair
 ↓
EDA Verification
```

但是每一个 testcase 都从：B0 \+ M0 开始。

**Machine B：Adversarial Evolution Agent**

初始状态必须和 A **完全相同**：

```Plain Text
Model     = same
B0        = same
M0        = same
Candidates = same
Temperature = same
Budget    = same
Toolchain = same
```

然后开始：

```Plain Text
Blue B0
   ↓
Red 根据当前 B0 生成挑战
   ↓
执行 + Oracle
   ↓
找到当前 B0 无法解决的 Bug
   ↓
Blue Repair Search
   ↓
EDA Verification
   ↓
Verified Experience
   ↓
Replay / Regression
   ↓
Policy / Memory Promotion
   ↓
Blue B1
   ↓
Red 根据 B1 再找新的 Bug
   ↓
...
```

最后得到：B0 → B1 → B2 → B3。注意：**LLM 权重始终不变。**变化的是：

```Plain Text
Repair Policy
Routing
Strategy
Verified Experience
Memory Activation
```

这个地方就是整个演示应该重点强调的。

数据结构，例如：

```Plain Text
Red Pool
│
├── Red-Evolve-20
│      │
│      └── 只给 Machine B 的 Red/Blue evolution 使用
│
└── Red-Heldout-20
       │
       └── 两台机器直到最终测试前都不能使用
```

如果数据足够，甚至最好：

```Plain Text
Red-Evolve
    │
    └── Design A/B/C/D

Red-Heldout
    │
    └── Design E/F/G
```

这样比单纯 mutation instance 不重复更强。最终：

```Plain Text
Evaluation Set 1
Strider-14

Evaluation Set 2
Red-Heldout-N
```

## 6\. 实验可复现机制

正式比赛版本对所有核心结果冻结：

```Plain Text
Git Commit
Dataset Manifest
Model
Seed
Candidate Budget
Verifier
Icarus Version
Yosys Version
Result Hash
```

最终主表禁止手工填写，而由：

```Plain Text
competition/scripts/freeze_results.py
```

自动生成。

# 五、应用成效

## 1\. 成果展示

### 1\.1 系统能力

当前 R³E\-AIC 已形成以下核心能力：

### 1\.2 公共功能修复指标

以下为当前研究阶段已使用的公共功能修复结果参考值。**正式提交必须以 Competition Frozen Results 重新导出的数值为准。**

正式技术报告同时给出 seed 数量、均值±标准差和完全一致的 benchmark denominator。

### 1\.3 重点对比

R³E\-AIC 的主要意义不在于“模型生成更多代码”，而在于：

1. functional oracle；

2. correctness\-gated selection；

3. active\-policy\-conditioned bug discovery；

4. replay\-gated policy promotion；

5. memory activation safety。

因此，应用成效应同时包含：

- 修复率；

- regression；

- harmful activation；

- runtime；

- candidate budget；

- verification coverage。

### 1\.4 Correctness Gate 效果

比赛中建议展示以下 funnel：

```Plain Text
Generated Candidates
      ↓
Compile Pass
      ↓
Simulation Pass
      ↓
Oracle Pass
      ↓
Accepted
```

该图比单独报告“模型生成成功率”更符合 IC 设计场景。

### 1\.5 策略演化效果

建议展示冻结 Red\-Fixed replay：

```Plain Text
B0
 ↓
B1
 ↓
B2
 ↓
B3
```

并展示：

- target replay；

- non\-target regression；

- promotion；

- renewed challenge。

正式材料必须绑定原始 run artifact。

### 1\.6 记忆安全性

比赛版重点不是“记忆条目数量”，而是：**不让错误经验获得执行权限。**

展示：

```Plain Text
Raw History
BM25/RAG
Compile-only Memory
Correctness-gated Strategy Memory
```

重点指标：

- injection；

- harmful activation；

- replay pass；

- regression。

## 2\. 效益分析

### 2\.1 工程效率

传统 RTL 功能调试需要工程师反复：

- 看日志；

- 查波形；

- 猜测 root cause；

- 修改；

- 回归。

R³E\-AIC 将其中的：

```Plain Text
定位
候选生成
验证
候选筛选
```

自动化。

因此，其主要工程效益是：

- 降低重复调试成本；

- 缩短候选 patch 试错时间；

- 提高功能缺陷修复自动化程度；

- 为工程师提供结构化 failure evidence。

### 2\.2 可靠性

由于系统不允许模型自报成功，因此相比单纯 LLM Copilot：

- 更容易审计；

- 更容易复现；

- 更适合 EDA 工作流；

- 更容易控制 regression。

### 2\.3 科研价值

R³E\-AIC 可用于研究：

- LLM for EDA；

- RTL Repair；

- agentic hardware design；

- continual memory；

- red\-blue co\-evolution；

- correctness\-gated self\-improvement。

### 2\.4 教学价值

在数字逻辑、Verilog、计算机组成、EDA 相关课程中，可将系统用于：

- 自动批改；

- bug 定位；

- testbench 驱动纠错；

- 展示“编译正确 ≠ 功能正确”；

- FSM/debug 教学。

# 六、总结与展望

## 1\. 经验总结

本项目的核心经验可概括为三点。

### 第一，AI for RTL 不能只依赖语言模型

硬件代码具有严格的时序和功能语义，因此模型必须与：

- simulator；

- testbench；

- oracle；

- formal tool

共同工作。

### 第二，修复成功必须由工具链决定

R³E\-AIC 将：

```Plain Text
proposal authority
```

和：

```Plain Text
correctness authority
```

分离。

LLM 提出 patch，runner 与 EDA 判断结果。

### 第三，持续学习的关键不是“记住更多”，而是“安全激活”

未经 replay 和 regression 验证的经验只能停留在 Shadow 状态。

因此，系统避免：“一次错误经验导致后续多次错误修复”。

## 2\. 未来规划

### 2\.1 更完整的 SystemVerilog 支持

当前 parser/operator 覆盖仍是受控子集。

下一步扩展：

- generate；

- interface；

- assertion；

- package；

- parameterized modules；

- 更复杂 always\_ff/always\_comb。

### 2\.2 更大规模 RTL 工程

从单模块 benchmark 扩展到：

- multi\-module；

- SoC subsystem；

- protocol controller；

- open\-source CPU/IP。

### 2\.3 从功能修复扩展到 PPA\-aware Repair

结合：

- synthesis；

- critical path；

- area；

- timing；

- power。

形成：

```Plain Text
Correctness
  +
PPA Optimization
```

### 2\.4 Formal Property Generation

未来可让 AI：

1. 根据 specification 生成候选 property；

2. 由 formal tool 验证；

3. 用 counterexample 指导修复。

### 2\.5 工业 EDA 集成

形成：

```Plain Text
IDE / CI
  ↓
R³E Service
  ↓
Simulator / Formal / Synthesis
```

可以作为现有 EDA 流程中的智能辅助层，而不是替代底层 EDA。

# 七、附录

## 1\. 数据资料

正式提交附录应列出：

每套数据需绑定：

```Plain Text
dataset manifest
SHA-256
case count
oracle
testbench
```

## 2\. 代码与模型

### 2\.1 核心代码

```Plain Text
r3e/blue/portfolio/
r3e/policy/
r3e/arena/
r3e/red/
r3e/memory/
```

### 2\.2 Competition Layer

```Plain Text
competition/app/
competition/services/
competition/cases/
competition/configs/
competition/scripts/
```

### 2\.3 模型说明

正式提交填写：

```Plain Text
Provider:
Model:
Temperature:
Max tokens:
Candidate budget:
Timeout:
Seeds:
```

不得提交 API Key。

## 3\. 参考文献

正式版本建议至少包括：

1. CirFix 原论文；

2. RTL\-Repair 原论文；

3. Strider 原论文；

4. RTLFixer 原论文；

5. LLM for EDA 相关研究；

6. self\-improving agents / memory 相关研究；

7. Icarus Verilog；

8. Yosys；

9. 采用的模型技术文档。

## 4\. 其他材料

建议佐证材料 PDF 包含：

```Plain Text
A. 代码版本与 Git commit
B. 数据集来源
C. Frozen benchmark result
D. 关键运行截图
E. 复现说明
F. 论文/专利/软著
G. 用户反馈
H. 工具链版本
I. 三个 Demo 的完整 evidence
```

# 附：作品简介（≤300 字）

R³E\-AIC 面向芯片前端设计中“RTL 能通过编译但功能仍错误、人工波形定位与回归验证成本高”的痛点，融合大语言模型、多专家智能体与 Icarus Verilog/Yosys EDA 工具链，实现 RTL 功能缺陷的自动发现、结构化诊断、候选修复和正确性验证。系统采用对抗式缺陷发现机制持续搜索当前修复策略尚不能解决的错误，并通过 replay 与无回归门控安全吸收已验证经验，形成“缺陷发现—智能修复—EDA验证—策略演化”的闭环。作品可用于 RTL 调试、验证辅助、EDA 智能化及数字芯片教学科研场景。

# 附：建议插图清单

## 图 1 R³E\-AIC 总体架构

```Plain Text
Bug Discovery
    ↓
Diagnosis
    ↓
Candidate Portfolio
    ↓
Correctness Gate
    ↓
Verified Episode
    ↓
Memory / Policy Evolution
```

## 图 2 Repair Studio 页面截图

## 图 3 Correctness Gate

## 图 4 B0→B3 Policy Evolution

## 图 5 Correctness\-Gated Memory State Machine

## 图 6 三个 Demo Case 的 RTL Diff

## 图 7 Public Benchmark 主结果

## 图 8 Verification Funnel

