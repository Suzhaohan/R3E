低通过率 RTL 五轮预实验

在项目根目录运行：
  bash low-pass-pilot-01/run.sh check
  bash low-pass-pilot-01/run.sh start

start 会在终端提示安全输入 DeepSeek API 密钥（不回显、不保存到文件）。
已经设置 R3E_PILOT_API_KEY 或 DEEPSEEK_API_KEY 时直接使用。
不需要向聊天发送密钥，也不要求先创建密钥文件。
默认接口 https://api.deepseek.com，模型 deepseek-flash；可在首次启动前
通过 DEEPSEEK_BASE_URL / DEEPSEEK_MODEL 设置自己的配置。运行后不可更改。
如已有配置文件，也支持 start --llm-env /实际路径。
建议先进入 tmux 会话再启动；实验在前台运行，断开终端可能中断。

查看进度：
  bash low-pass-pilot-01/run.sh status
  tail -f low-pass-pilot-01/logs/start.log

不调用 API 的命令：
  bash low-pass-pilot-01/run.sh plan
  bash low-pass-pilot-01/run.sh check
  bash low-pass-pilot-01/run.sh smoke --state-dir /tmp/自己的新模拟目录
  .venv/bin/python -m pytest -q low-pass-pilot-01/tests
plan/check/smoke 禁止 Python 网络连接；模拟结果不是学习效果证据。

固定分区（缺陷条数，不是独立电路数量）：
  学习 4：Prob015 原始 timing、state_machine；Prob003/Prob015 重建 Red 缺陷。
  晋升 4：Prob017 assignment/arithmetic/timing，Prob023 arithmetic。
  最终 2：Prob001/Prob002 arithmetic，保守合并为一个相近设计家族。
  防退化 3：旧 run06 锁存器、译码器、时序计数器各一题。
晋升题、防退化题不进入学习案例库或 Red 输入；最终题只在五轮结束后评分。
所有分区按设计家族和标准化 RTL 结构检查冲突。
Prob017 timing 在此是既有缺陷诊断题，不计为 Red 新发现命中；已离线检查
参考通过、缺陷失败，并记录 Yosys 检查结果。Yosys 未报告环路不代表完整语义认证。

执行机制：
  使用 integrated-main 的独立源码快照，不修改旧 run06 或其状态。
  这里晋升的是经过配对验证的案例经验，不是旧 run06 的参数搜索策略。
  第 1 轮学习四个固定缺陷；第 2～5 轮各复验两题，并让 Red 在学习电路上
  提出两次新变异。生成题必须通过原有准入检查，拒绝提案也如实记录。
  每轮最多验证 2 个候选经验；三次配对验证，沿用新版 solve_rate 门槛：
  至少 1 题实际收到经验、净增加至少 2 个成功配对、单侧符号检验 p<=0.2，
  不允许超过原门槛的退化。p<=0.2 是预实验晋升阈值，不是最终显著性结论。
  验证有基础设施缺失结果时不晋升；候选通过上述门槛后，再检查全部三道
  防退化题，每题三次配对；任一退化或无法判定均拒绝激活。
  每题最多 3 次修复，只有学习阶段失败后可额外尝试 3 次以获取学习经验。
  记忆从第二次修复起提供，配对分支共享首个失败尝试，双方剩余预算相同。
  记忆库和经验来自本场学习，不导入旧状态。

预算与指标：
  五轮、每轮四个学习槽、每轮最多两个候选、配对重复三次。
  DeepSeek low thinking；每次输出上限 32768 tokens；温度 0.2。
  本次最多 1300 次 API 调用，失败调用也计入上限；不会自动扩容。
  在无额外重跑的配置下，保守调用数上界为 1256：Red 8 + 学习 120 +
  晋升 600 + 防退化 450 + 最终评分 78。实际通常因提前成功、检索未命中、
  无候选或未通过晋升而少得多。1300 是硬上限，不是消费计划或费用报价。
  provider 故障不自动重试；记录为 inconclusive，不冒充功能修复失败。
  真实费用按服务商实际输入/输出 token 计费，调用数上限不能直接换算金额。

  五轮结束后统一比较空记忆基线与各轮结束快照，主比较为第5轮对基线。
  最终每题三次，共六个配对；报告成功率、gained/lost、无法判定数量。
  无激活经验的快照与空记忆系统相同，复用基线并明确记录原因，不伪造
  独立模型运行；首试成功也复用公共首试。有效配对不足时如实缩小分母。
  各轮评测仅使用该轮之前的经验内容、类型推断和使用记录，避免未来信息泄漏。
  评分使用既有可见测试，不宣称完整功能正确性；最终仅一个相近设计家族，
  不能据此声称普遍泛化，也不把六次配对当作六个独立电路。

数据真实性：
  两道 Red 种子来自 datasets/low_pass_rate_rtl_cases/reconstructed_red。
  原历史 Red 文件缺失；这些是根据文档描述重建且经仿真检查的新输入。
  不继承历史审核 PASS、挑战 ID 或 1/3 修复率。需要重新测量当前难度。
  Prob004、HWE/Ibex 不计入本场主实验。

结果文件：
  protocol.json / preflight.json：固定设置、文件哈希、工具版本、逐题离线检查。
  real-state/binding.json：真实运行模型、数据、源码、设置绑定。
  real-state/rounds.jsonl / qualification.jsonl：逐轮、晋升和防退化决策。
  real-state/guards/：防退化逐题配对记录。
  real-state/calls.jsonl：调用和成本记录，不包含密钥。
  real-state/comparison.json：完成五轮后的最终比较。
  smoke-state*/：离线模拟状态，不是 DeepSeek 结果。

运行中断：
  完整轮次边界和评分阶段可重复 start 继续，累计调用上限不会重置。
  轮次中途异常保留 inflight.json 和所有证据，并拒绝静默重跑，防止把
  半轮经验当作新起点。出现该提示请保留目录并检查原因，不要手动删标记。
  fake 与 real 使用不同目录；数据、模型或源码变更必须新建实验状态。

源码改动：
  快照中的 qualification 增加激活前防退化回调，并拒绝缺失配对的晋升。
  快照中的 orchestrator 传入回调；原仓库代码不变。
  pilot.py 固定分区、种子课程、调用预算、评分阶段和数据哈希。
