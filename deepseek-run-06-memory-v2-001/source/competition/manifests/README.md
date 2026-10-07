# 当前运行清单：比赛演示版 demo18

| 文件 | 数量 | 用途 |
|---|---:|---|
| demo18_red_sources.json | 5 | 每个对抗 design 一个参考电路供 Red 生成，已包含在题库内 |
| demo18_supplied_assets.json / demo18_repair_bank.json | 10 | 同一批 10 题的完整资源和索引：2 个家族练习、3 个家族晋升考试 |
| demo18_regression.json | 2 | 一个寄存器设计，防退步检查 |
| demo18_heldout.json | 2 | 计数器两个版本，最终测试 |
| demo18_strider.json | 4 | 状态机与四选一选择器各两个版本，最终测试 |

合计 18 个不同原始案例、9 个家族；对抗主体 5 个家族，五轮 R000–R004。最终测试 6 题，每组每阶段 18 个重复测试结果，每次三个候选。

`demo18_selection.json` 记录理由和用途，`demo18_qualification.json` 记录 10 道已有演化题的资格。`inputs/demo18_sources.json` 是仅包含本轮题目的哈希绑定源快照；原始案例编号、文件路径及资源哈希均保留。

旧全量运行清单、构建脚本和未引用的生成文件已经删除；完整原始数据保留在 datasets，不会自动进入当前实验。重建本轮清单：

```bash
python -m competition.scripts.select_representative_cases
```

重建只读取本轮 18 题的输入快照，不调用 API。已有清单如与构建结果不同会拒绝覆盖；改变选题必须建立新基线。
