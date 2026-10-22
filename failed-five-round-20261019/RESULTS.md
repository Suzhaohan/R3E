# 五轮对抗结果

| 案例 | 状态 | 静态考试 | 对抗考试 | 冻结经验条数 |
|---|---|---|---|---|
| chipbench:timing:Prob015_vending_machine2 | complete | 0/2 | 0/2 | 0 |
| chipbench:state_machine:Prob015_vending_machine2 | complete | 0/2 | 0/2 | 0 |
| chipbench:arithmetic:Prob017_arbitrary_fractional_frequency_division | complete | 1/2 | 2/2 | 1 |
| lowRISC__ibex-907 | complete | 1/2 | 1/2 | 0 |
| lowRISC__ibex-2232 | complete | 0/2 | 0/2 | 0 |

HTTP 请求尝试：209；已保存响应：209；服务返回已知费用：$1.545314。

每题独立空经验；五轮在线出题、双组等额反馈修复；仅自身成功修复摘要可成为经验候选，两个保留缺陷各重复两次检验严格提升且无退步才晋升。全部训练结束后统一冻结，再各做两次原始题考试。训练、验证、考试均使用本地原始测试；保留的是不同缺陷，不是独立测试集。

这是适配这些案例的独立流程，未复用 01 中绑定原三题的启动器。与旧流程相比：沿用私有原始基准而未额外建立独立 evaluator；不做跨题经验共享；原静态结果仅用于选题，不作为训练经验。最终两组预算一致，最多两次功能作答及每次一次格式纠正。Prob017 仍有题面与参考矛盾；通过仅表示参考测试通过。
