09_Low_Pass_Rate_RTL_Cases 对应题包
整理日期：2026-10-12

已取到：8 道 ChipBench 原始缺陷题 + 2 道 HWE Ibex 原始任务。
未取到：清单中 3 份特定 Red 变异的原始实验文件。
新增：已依据描述重建 Prob003、Prob015 两份 Red 缺陷代码，并通过定向和可见测试验证；
见 reconstructed_red/README.txt。这是重建题，不是取回的原实验文件。

ChipBench 题目目录（每个目录的 spec.txt 是英文题面，buggy.sv 是待修复代码）：

chipbench:arithmetic:Prob001_continuous_input_sequence_detect
  连续输入检测：最近 8 位为 01110001 时输出 match。
  chipbench/arithmetic/Prob001_continuous_input_sequence_detect/

chipbench:arithmetic:Prob002_extraneous_items_sequence_detect
  带任意位序列检测：检测 011XXX110，中间三位不限。
  chipbench/arithmetic/Prob002_extraneous_items_sequence_detect/

chipbench:arithmetic:Prob023_gray_code_counter
  4 位格雷码计数器：低有效异步复位，每两个时钟周期递增。
  chipbench/arithmetic/Prob023_gray_code_counter/

chipbench:timing:Prob015_vending_machine2
  售货机：接收 0.5/1 元，出售 1.5/2.5 元饮料并找零。
  chipbench/timing/Prob015_vending_machine2/

chipbench:state_machine:Prob015_vending_machine2
  售货机：同一设计的状态转移缺陷题。
  chipbench/state_machine/Prob015_vending_machine2/

chipbench:assignment:Prob017_arbitrary_fractional_frequency_division
  分数分频器：实现平均 8.7 倍分频；原题面存在矛盾，见下文。
  chipbench/assignment/Prob017_arbitrary_fractional_frequency_division/

chipbench:arithmetic:Prob017_arbitrary_fractional_frequency_division
  分数分频器：同一设计的运算缺陷题。
  chipbench/arithmetic/Prob017_arbitrary_fractional_frequency_division/

chipbench:timing:Prob017_arbitrary_fractional_frequency_division
  分数分频器：同一设计的时序缺陷题。
  chipbench/timing/Prob017_arbitrary_fractional_frequency_division/

每道 ChipBench 题附 golden.sv（参考实现）、ref.sv（测试参考模块）、
tb_visible.sv（已有转换器改造的可见测试）。五个文件均逐字节复制本地题库。
chipbench8.jsonl 中的路径相对于项目根目录，兼容现有 manifest 路径约定。
给修复模型的题面和代码是 spec.txt + buggy.sv；golden/ref 属于评分侧材料。

HWE 题目：
  hwe/lowRISC__ibex-907/public/spec.txt
    取指缓冲与 FIFO 协调：压缩指令之后的 32 位指令跨越两个取指字时，
    及时请求补全指令所需的下一字，避免多一个取指停顿。
  hwe/lowRISC__ibex-2232/public/spec.txt
    调试模式下允许 Debug Module 地址范围内的读、写和取指绕过 PMP 拒绝；
    范围外的地址仍需遵守正常 PMP 检查。
每题 public/baseline-source.tar.gz 为固定基线源码；public/upstream_tb_script.sh
为原始测试脚本，setup/ 为原始环境准备脚本；oracle/ 含标准补丁和完整数据记录。
脚本按原样保存，未执行；其中使用上游容器绝对路径，不能视为本机直接运行入口。
源码压缩包不包含 Git 子模块内容和工具链依赖。本次没有运行 HWE 仿真。

需要保留的限制：
1. Red 的 RC_406d811b4d61a2、RC_02caa510ba2821、warm-slot-3 原始 RTL
   尚未取到。missing_red_artifacts/ 仅保存对应设计规范，不可替代历史变异。
   需要原文所指 R3E-local-artifacts/partA_chipbench_20261005/{aware,blind}/
   和 R3E-local-artifacts/red_search_pilot_v1/generator_review/ 等实验产物。
2. Prob017 原文同时写平均 8.7 倍分频、10 个输入周期产生 53 个输出周期，
   并写 1/5.3 约等于 1/8.7，彼此明显矛盾。本题包保留原文，不擅自更改题意。
   用作严格规范评分前需明确预期；timing 变体还有组合自引用，需限时仿真。
3. 历史低通过率是原清单的旧实验结果；本次未调用模型、未重测修复率。
   两道 HWE 任务是原始修复题，不包含历史 Blue 误修补丁或补充见证。

来源：
  本地 ChipBench：integrated-main/datasets/chipbench/
  本地来源记录：integrated-main/datasets/external/SOURCES.md（ChipBench b4ba3a0）
  https://github.com/zhongkaiyu/ChipBench
  https://huggingface.co/datasets/henryen/hwe-bench/resolve/main/lowRISC__ibex.jsonl
  https://github.com/lowRISC/ibex/pull/907
  https://github.com/lowRISC/ibex/pull/2232
HWE 当前公开下载的完整记录保存在各 oracle/upstream_record.json；不是原实验数据快照。
文件 SHA-256 见 SHA256SUMS.json。
