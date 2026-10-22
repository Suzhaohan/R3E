# 独立无经验静态测试

模型：`deepseek/deepseek-chat-v3-0324`。每题空经验，一次功能作答；最多一次 JSON 格式纠正。Ibex 额外一次文件选择。无红队、无训练、无历史经验。

| 题目 | 状态 | 不一致采样 / 总采样 | 模型请求阶段数 |
|---|---|---|---|
| chipbench:arithmetic:Prob002_extraneous_items_sequence_detect | 通过 | 0 / 237 | 1 |
| chipbench:timing:Prob015_vending_machine2 | 功能测试失败 | 53 / 181 | 1 |
| chipbench:state_machine:Prob015_vending_machine2 | 功能测试失败 | 58 / 181 | 1 |
| chipbench:assignment:Prob017_arbitrary_fractional_frequency_division | 通过 | 0 / 2021 | 2 |
| chipbench:arithmetic:Prob017_arbitrary_fractional_frequency_division | 功能测试失败 | 230 / 2021 | 2 |
| chipbench:timing:Prob017_arbitrary_fractional_frequency_division | 通过 | 0 / 2021 | 2 |
| lowRISC__ibex-907 | 功能测试失败 | — | 2 |
| lowRISC__ibex-2232 | 功能测试失败 | — | 3 |
| RC_02caa510ba2821 | 缺少原始 RTL，无法运行 | — | 0 |
| warm-slot-3 | 缺少原始 RTL，无法运行 | — | 0 |

已保存模型响应：14；返回的总 token：194746；服务返回的已知费用合计：$0.068976（网络未返回响应的请求费用未知）。

首次 urllib 传输遇到沙箱限制和 TLS 错误，随后切换 curl。已有答案原样保留；仅补发没有响应的请求阶段。网络失败记录另存 sandbox_network_error.json / urllib_network_error.json，不能算模型答错。

通过仅表示本地基准测试通过；不代表完整形式验证。Prob017 原题面与参考实现存在矛盾，以原始参考实现和测试为评分标准。缺少历史原始 RTL 的案例不会以重建版本替代。
