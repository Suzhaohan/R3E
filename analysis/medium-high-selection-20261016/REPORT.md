# 已有静态失败记录核查

去重后 312 份无经验观察，分为 128 个题目/模型/检查设置组合。新增模型调用：0。

这是对已有失败证据的盘点，不是当前配置下的难度承诺。所有不同设置分别统计，不把重复缓存当独立样本。

## 已离线重放的候选

| 原题 | 原静态成绩 | 保存候选重放 | 参考答案 / 原缺陷 |
|---|---:|---|---|
| strider:fsm_full_3 | 原账本记为 0/3 | 1/9 个候选功能通过 | 参考通过，原缺陷失败 |
| strider:mux_4_1_2 | 原账本记为 0/3 | 0/9 个候选功能通过 | 参考通过，原缺陷失败 |
| strider:first_counter_overflow_2 | 原账本记为 0/3 | 0/9 个候选功能通过 | 参考通过，原缺陷失败 |

## 各设置中的功能失败证据

| 题目 | 模型 | 通过 / 观察数 | 功能失败 | 其他失败 | 证据文件 |
|---|---|---:|---:|---:|---|
| assignment4v:counter6bit_11 | deepseek-flash | 0/9 | 9 | 0 | `deepseek-run-03/arm-a/eval/red-heldout/case-2c6572c782a245dc918b05065ce7d7ba/evaluation.json` |
| assignment4v:counter6bit_1 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-3ae6a5de73b74323b34524451cbff94c/evaluation.json` |
| assignment4v:counter6bit_10 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-00a2c4873dfe4facb81929ed829faa71/evaluation.json` |
| assignment4v:counter6bit_11 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-707eb8cbd0e345f4aca5b3a26441a706/evaluation.json` |
| assignment4v:counter6bit_12 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-37f825b91de043e9b603c93f04217f8f/evaluation.json` |
| assignment4v:counter6bit_13 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-20d6bda050a84da69c5676a6c4a1e160/evaluation.json` |
| assignment4v:counter6bit_14 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-1c8ac48c49ce48a79c8aecf94202e7a0/evaluation.json` |
| assignment4v:counter6bit_15 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-21cfcdce25644a9fa2fc613f4c2c45b4/evaluation.json` |
| assignment4v:counter6bit_16 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-0460d40098df4b17bada0b486fc16f28/evaluation.json` |
| assignment4v:counter6bit_17 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-b30fc19101854e309943df668eda1303/evaluation.json` |
| assignment4v:counter6bit_18 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-7dc9f6588a2c426290b2dbb0cacca608/evaluation.json` |
| assignment4v:counter6bit_19 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-07307595c94f436db47d7d37e55b969d/evaluation.json` |
| assignment4v:counter6bit_2 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-2430f380233c4f239ab5317938081480/evaluation.json` |
| assignment4v:counter6bit_20 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-1d2a6e72b95e42a0a6e78299dc5ceebf/evaluation.json` |
| assignment4v:counter6bit_21 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-3ec3d84baac94d01bdb926700f204b06/evaluation.json` |
| assignment4v:counter6bit_23 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-0dd4f7624d87418c8856a7ab600db290/evaluation.json` |
| assignment4v:counter6bit_3 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-7090b2381be74b43a98dc7644ba08693/evaluation.json` |
| assignment4v:counter6bit_4 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-8898729b67144cfe8752e1ceac19db95/evaluation.json` |
| assignment4v:counter6bit_5 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-845bdcf6b61843e1a9320d2f75ebccac/evaluation.json` |
| assignment4v:counter6bit_6 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-0f913076ac6d49daa634a7ef12d5bb34/evaluation.json` |
| assignment4v:counter6bit_7 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-326872d3c9d04fca9d587f1c407d4cab/evaluation.json` |
| assignment4v:counter6bit_8 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-2f1947ecfd234fef86fd927417bc2603/evaluation.json` |
| assignment4v:counter6bit_9 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/red-heldout/case-019386570f2943b399f084d75d21b826/evaluation.json` |
| chipbench:arithmetic:Prob001_continuous_input_sequence_detect | deepseek-flash | 0/3 | 3 | 0 | `low-pass-pilot-02/real-state/eval-cache/baseline_7786242c7d69e4ac.json` |
| strider:first_counter_overflow_2 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/strider14/case-351d1fa8f2714d9f8e353b8972ee9b8b/evaluation.json` |
| strider:mux_4_1_2 | deepseek-flash | 0/3 | 3 | 0 | `deepseek-run-01/arm-a/eval/strider14/case-52331d3cbf4240b29139768e65b96feb/evaluation.json` |
| strider:fsm_full_3 | deepseek-flash | 0/3 | 2 | 1 | `deepseek-run-01/arm-a/eval/strider14/case-5c893a1fa2d24a6c8efe57f4e5eb8f28/evaluation.json` |
| strider:lshift_reg_1 | deepseek-flash | 0/3 | 2 | 1 | `deepseek-run-01/arm-a/eval/strider14/case-255c35b234744937bbd6a0f121d18e38/evaluation.json` |
| chipbench_Prob015_fixed_hard_questions__exam_timing | deepseek-v4-flash | 0/2 | 2 | 0 | `hard-case-five-round-01/real-all-20261015-034425/Prob015/collection/anchors/b0_a0_repeat0/blue/encounters.jsonl` |
| selected_Prob015__exam_defect | deepseek-v4-flash | 0/2 | 2 | 0 | `hard-case-five-round-01/real-all-20261015-224806/Prob015/collection/anchors/b0_a0_repeat0/blue/encounters.jsonl` |
| selected_Mux__exam_defect | deepseek-v4-flash | 0/2 | 1 | 1 | `hard-case-five-round-01/real-all-20261015-224806/Mux/collection/anchors/b0_a0_repeat0/blue/encounters.jsonl` |
| chipbench_Prob015_fixed_hard_questions__b81fea8696b8c049 | deepseek-v4-flash | 0/1 | 1 | 0 | `hard-case-five-round-01/real-all-20261015-034425/Prob015/collection/rounds/4/r4_s0/reference/blue/encounters.jsonl` |
| selected_Prob015__083cb0fcc7f0d5d3 | deepseek-v4-flash | 0/1 | 1 | 0 | `hard-case-five-round-01/real-all-20261015-224806/Prob015/collection/rounds/4/r4_s0/reference/blue/encounters.jsonl` |
| chipbench:arithmetic:Prob001_continuous_input_sequence_detect | deepseek-flash | 1/3 | 2 | 0 | `low-pass-pilot-03/real-focused-state/calibration-cache/3b094641a8ed4a61.json` |
| chipbench:state_machine:Prob015_vending_machine2 | deepseek-flash | 1/3 | 2 | 0 | `low-pass-pilot-03/real-focused-state/calibration-cache/9d3ee2711e4b02c2.json` |
| chipbench:timing:Prob015_vending_machine2 | deepseek-flash | 1/3 | 2 | 0 | `low-pass-pilot-03/real-focused-state/calibration-cache/205a5fe78d74633b.json` |

机器可读完整证据：`summary.json`、`records.jsonl`。两个重放候选的原始材料位于 `selected_originals/`；不修改运行代码、冻结题单或既有成绩。

原始 oracle_ok=false 不直接当成功能失败：逐候选比较保存的 golden/cand 轨迹，发现正确轨迹但仍被旧范围规则拒绝的，单列 functionally_correct_but_rejected。不能因为账本零通过就推荐为功能难题。

fsm_full_3 重放有一个完整文件答案通过功能测试，但原记录 scope_ok=false；因此它不再列为纯功能 0/3 的首选。mux_4_1_2 和 first_counter_overflow_2 的原候选重放结果见上表。推荐名单为 selected_candidates.json，只接受九个候选均失败且参考答案通过的候选。

这些题已有结果被查看，后续可作为开发/定向验证题，不能再宣称是未见留出集。
