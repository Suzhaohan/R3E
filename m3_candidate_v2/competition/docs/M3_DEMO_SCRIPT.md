# M3 演示脚本（约 4 分钟）

1. **0:00–0:35**：展示 Counter guided repair，说明编译通过不等于功能正确，明确当前是否调用真实模型。
2. **0:35–1:05**：打开 Arena，展示 shared baseline、相同模型和三候选预算、固定 M0。
3. **1:05–2:20**：播放已经冻结并核验的真实轮次，说明新缺陷、paired replay、非目标回归和晋升。未晋升的轮次如实保留。
4. **2:20–3:15**：分别展示 Strider-14 与 Red-Heldout，给出 n/N、seed 和能力变化；说明合成 heldout 共享模板家族的限制。
5. **3:15–4:00**：展示 policy hash、round audit 和 comparison hash；强调模型权重不变，变化的是运行时策略。

没有通过验证的真实双机产物时，Arena 保持 unavailable；只能演示离线工程协议，不能使用替身测试数字替代实验效果。
