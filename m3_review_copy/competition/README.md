# R³E：自进化RTL智能纠错系统

R³E-AIC 面向“RTL 能通过编译但功能仍错误”的芯片前端调试问题。比赛版把科研核心收敛成一条可审计链路：

```text
RTL → Runtime Evidence → Failure Descriptor → Blue Portfolio → Scope Gate → Parse → Compile → Simulation → Oracle → Structural Check → Repeatability
```

模型只提出候选，真实 EDA 工具链和 R³E `oracle_gate` 决定候选能否被接受。

## 30 秒了解作品

- Counter：发现 temporal/event-control 错误；
- FSM：发现可编译但状态输出错误；
- Shift：发现 blocking assignment 导致的 bit-level dataflow 错误；
- Experience / Evolution 页面只展示有冻结证据支持的回放，不把 deterministic fixture 当作模型效果。

## 最新运行入口

当前实验统一使用 run06，请按[最新运行指南](../../deepseek-run-06/source/运行指南.md)操作。本页其余内容保留为工程说明。

## 目录

- `app/`：轻量 HTTP API 和无构建依赖的演示界面；
- `services/`：diagnosis、repair、verification、evolution、memory、benchmark facade；
- `cases/`：三个可追溯到公开 CirFix 输入的演示案例；
- `configs/`：比赛模式、Demo 和 provider 配置模板；
- `results/frozen/`：按 demo、benchmark、evolution、memory 分离的冻结证据索引；
- `scripts/`：安装检查、演示、结果冻结、匿名化与提交包检查；
- `docs/`：架构、视频脚本和官方大纲对齐的提交材料。

## 真实性边界

第三方 benchmark、Icarus Verilog、Yosys 和 provider 均在材料中注明来源。当前仓库不内置模型响应、私有日志或 headline 实验数字；benchmark evidence 的 `available: false` 表示尚未冻结真实实验，而不是零结果。所有正式数字必须由 `freeze_results.py` 从 raw result artifact 生成。
