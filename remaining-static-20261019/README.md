# 剩余低通过率案例：独立静态测试

本目录独立运行，不导入或修改 `hard-case-five-round-01`。来源是
`datasets/low_pass_rate_rtl_cases/index.json`（对应 `09_Low_Pass_Rate_RTL_Cases.md`）。
排除当前三题 Prob001、Prob023、历史 Prob003；剩余十个缺陷案例。
同一设计的不同缺陷类别分别测试，每题使用独立请求、空经验。

模型固定 `deepseek/deepseek-chat-v3-0324`，OpenRouter，temperature 0.2。
每题一次功能作答，不根据评分反馈学习或重做；至多一次 JSON 格式纠正。
Ibex 在作答前增加一次公开 RTL 文件选择请求，最多选择十二个文件。
因此最多十八次模型请求（6×2 + 2×3 + 2×0）；实际 token 费用取决于响应。
每道题基础设施或模型失败不影响其他题。

首次配置：

```bash
python3 remaining-static-20261019/configure_key.py
```

离线准备与检查（零模型调用）：

```bash
python3 -u remaining-static-20261019/run.py
```

真实静态测试（调用模型、产生费用）：

```bash
python3 -u remaining-static-20261019/run.py --run
```

结果持续写入 `RESULTS.md` 和 `results.json`；完整题目、提示、响应、提交代码、
编译和仿真日志在 `work/`。再次执行会读取已完成结果，不重新作答。
若需要另一批全新测试，请另开目录，不能删除单题结果后把重试当首次作答。
凭据仅存 `.secrets/openrouter.key`（600），不写入请求和结果文件。

评分前检查参考版本通过、缺陷版本失败。ChipBench 隐藏参考代码和测试代码，
模型仅看到题面及缺陷 RTL。Ibex 仅提供题面和选中的公开 RTL；原始定向测试脚本
按经审核的哈希提取，不执行上游安装脚本。评分用 test.patch、fix.patch 不提供给模型。
所有运行有编译及仿真超时，超时停止整个子进程组。

历史 RC_02caa510ba2821 和 warm-slot-3 缺少原始 RTL，单独列为无法运行；
不以重建版本替代。Prob017 题面存在与参考实现矛盾的描述，因此其通过表示
原始参考测试通过。所有测试结果均不等同完整形式验证。
