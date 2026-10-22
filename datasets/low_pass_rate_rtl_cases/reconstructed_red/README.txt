根据 09_Low_Pass_Rate_RTL_Cases.md 第 1 节重建的两道 Red 缺陷题

这两份 RTL 使用本地 ChipBench golden.sv 作为基线，精确应用文档描述的两处修改。
它们复现文档所述 Bug，但没有原始实验文件可供逐字节比对；不能继承历史审核
PASS 或 1/3 修复率等结论。未调用模型，未重新测量修复率。

Prob003（对应历史挑战 RC_406d811b4d61a2）：
  s6:  nstate=data?sf1:s1;  -> nstate=idle;
  sf6: nstate=data?sf1:s1;  -> nstate=idle;
  后一组六位输入的第一位被丢弃。
  定向输入 011100011100 和 111111011100 分别覆盖 s6 与 sf6 边界。
  两条输入最后一组都是 011100，正确实现应在第 12 位报告 match。

Prob015（对应历史挑战 RC_02caa510ba2821）：
  S0_5 + d2: S1_5 -> S1
  S1_5 + d2: S2_5 -> S2
  两处转移都少计 0.5 元。其他保持、输出和复位代码原样保留。
  定向输入一：选择 1.5 元商品，依次投 0.5、1 元，应出货。
  定向输入二：选择 2.5 元商品，依次投 1、0.5、1 元，应出货。
  第二条输入绕过第一处被修改的转移，单独检验 S1_5 + d2。

每题文件：
  spec.txt          题面
  buggy.sv         重建的 Red 缺陷代码
  golden.sv        重建基线/参考实现（评分侧）
  ref.sv           可见测试使用的参考模块（评分侧）
  tb_visible.sv    已有 ChipBench 可见测试
  tb_witness.sv    本次新增、直接检查外部行为的定向测试
  mutation.diff    与本地基线之间的全部修改
  reconstruction.json  来源、哈希和真实性限制

重建：python datasets/low_pass_rate_rtl_cases/reconstructed_red/reconstruct.py
验证：python datasets/low_pass_rate_rtl_cases/reconstructed_red/verify.py
依赖本机 iverilog 和 vvp。验证结果保存于 validation.json。
两个设计 × 两类测试 × 两个 RTL 版本，共 8 次仿真：参考实现均通过，缺陷版
均出现预期的功能错误。编译错误、超时或无测试结果不计为成功检出 Bug。

Prob004 warm-slot-3 未生成：文档明确了组边界转移缺失，但没有指定附加输出
时序错误的代码变换。01100110 漏报第二次匹配是 Blue 修复后残留错误的见证，
不足以唯一确定原 Red 复合变异。不能把自行猜测的第二处修改当作原始题目。
