# M3 独立候选版运行手册

本目录是可单独运行的候选副本。原仓库和已有 `m3_review_copy` 均未被替换。
所有以下命令都应在 **候选副本根目录** 执行，避免误用原项目的 Python 模块。

## 已接通的路径

- `PolicyRuntimeService` 读取固定 B0 或 Core registry 的 active policy；RepairService 接受 `policy_override`。
- `PolicyCandidateProvider` 将搜索得到的证据解释模式和依赖检查深度写入实际请求。模型、三候选预算、one-shot 和验证器固定。
- `CompetitionGroundedRedAdapter` 复用 Core 的节点选择、mutation plan 和 materializer，按轮次轮换干净设计。
- `CompetitionEvolutionAdapter` 对真正生成的 poison 做 teacher probe、child screening 和 paired replay；生成物按 poison ID 精确解析，不能偷换成原始 benchmark bug。
- `EvolutionRoundRunner` 保留原有 admission、16 阶段状态机、strong promotion、atomic registry commit、回滚快照和离线重建。
- M3 开启按 design 分组的 residual elite selection，防止同类故障只保留一个 design、永久无法满足跨设计晋升。默认 Core 行为不变，审计器使用同一冻结配置重建。
- A/B 共享 baseline，独立本地状态；M0 固定；final evaluation 开始后禁止继续演化。
- 批量评估固定 case × seed 分母，不可执行案例保留为失败；不能通过移除难题抬高修复率。
- Observer 只读；页面只在双机冻结证据验证通过时显示指标。

## 环境与离线检查

需要 Python 3.11+、Icarus Verilog、VVP、Yosys。创建候选版自己的虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q -p no:cacheprovider tests/competition
.venv/bin/python -m competition.cli run-demo
.venv/bin/python scripts/verify_datasets.py
```

三轮测试使用离线模型替身和真实 EDA，验证协议可执行性；它不是模型能力实验。

打开界面：

```bash
.venv/bin/python -m competition.app.backend.api --port 8081
```

访问 `http://127.0.0.1:8081`。没有正式冻结比较文件时，Adversarial Arena 明确显示不可用。

## 数据边界

`competition/manifests/` 已包含：4 个 Red-Evolve、2 个非目标回归、12 个 Red-Heldout 合成案例，以及对现有 Strider-14 的封存引用。
合成集合的 design instance、poison、diff 和签名分离，但共享 comparator 模板家族。它们用于工程验证及有限范围的演示，不代表广泛的未知设计泛化能力。

当前 Grounded wrapper 的冻结 mutation 范围是 comparator replacement 和 boundary constant shift。扩展更多 family 需要提供相应 clean design、testbench、formal property，并重新生成 baseline。

重新核对/生成同一批源文件：

```bash
.venv/bin/python -m competition.scripts.build_arena_datasets
```

已有文件不一致时拒绝覆盖。真正运行 Red 后产生的新 poison 只保存在 B 本地运行目录。
演化进程只读取演化/回归 manifest 和启动时的隔离证明；部署时应将 heldout 资产在 final evaluation 前保持不可挂载，并在最终阶段只读挂载。

## 真实双机实验

以下操作会调用模型，必须自行配置 provider，并明确设置调用/token 预算。代码默认不自动执行。

1. 将 `configs/providers/openai_compatible_pilot_template_v1.json` 复制到仓库外的配置文件，填写 provider/model/version/endpoint 等公开标识。API key 和 base URL 通过模板指定的环境变量提供，不写入 JSON。
2. 将评审通过的候选代码置于**独立 Git 仓库或分支并提交**。此交付目录是未提交副本，故意不能冒用父仓库 commit；正式 freeze 会拒绝它。
3. 两台机器使用同一提交、同一 Python/EDA 版本和镜像，分别部署同一 baseline 文件。不要复制 B 的 registry、archive、prompt、轨迹或候选 RTL 给 A。

下面用 `$M3_CLIENT_CONFIG` 指代仓库外的 provider JSON，`$M3_STATE` 指代当前机器独占的运行目录；路径由操作者设置。

创建共享 baseline（只读 provider 配置，不调用模型）：

```bash
.venv/bin/python -m competition.cli arena-baseline \
  --client-config "$M3_CLIENT_CONFIG" --output /tmp/m3-baseline.json \
  --seeds 1 2 3 --image-hash sha256:YOUR_IMAGE_DIGEST
```

机器 A 初始化：

```bash
.venv/bin/python -m competition.cli arena-init \
  --config competition/configs/arena/static.yaml \
  --baseline /tmp/m3-baseline.json --state-root "$M3_STATE"
```

机器 B 初始化时改用 `competition/configs/arena/adversarial.yaml`，并使用另一独占目录。

B 本地执行轮次，示例预算为上限，不是预期用量；实际预算应按所选模型和可承受费用配置：

```bash
.venv/bin/python -m competition.cli arena-round \
  --config competition/configs/arena/adversarial.yaml \
  --state-root "$M3_STATE" --client-config "$M3_CLIENT_CONFIG" \
  --round R000 --max-calls 400 --max-tokens 6000000
```

依次执行 `R001`、`R002`。同一轮再次执行是恢复；保留原 budget 参数，不能通过重启重置预算。每次调用前持久化保守 token 预留；耗尽预算后不再发起请求。

每轮都可能被 EDA、learnability 或 promotion 拒绝。真实模型未产生晋升时，必须如实展示 B0 保持不变。

最终评估，两台机器分别执行两套数据：

```bash
.venv/bin/python -m competition.cli arena-eval \
  --state-root "$M3_STATE" --client-config "$M3_CLIENT_CONFIG" \
  --dataset strider14 --max-calls 126 --max-tokens 6000000
.venv/bin/python -m competition.cli arena-eval \
  --state-root "$M3_STATE" --client-config "$M3_CLIENT_CONFIG" \
  --dataset red-heldout --max-calls 108 --max-tokens 6000000
```

评估开始会永久封住当前实验的演化入口。全部评估从同一固定 policy 快照执行。不同实验应使用新的 experiment ID 和状态目录。

双方各自冻结：

```bash
.venv/bin/python -m competition.cli arena-freeze \
  --state-root "$M3_STATE" \
  --evaluation "$M3_STATE/eval/strider14.json" \
  --evaluation "$M3_STATE/eval/red-heldout.json" \
  --output /tmp/arm-frozen.json
```

只有 B 有真实审计通过的晋升时，才可增加 `--claim-evolution`。将双方冻结摘要分别保存为 `static.json` 和 `adversarial.json`，交给 Observer：

```bash
.venv/bin/python -m competition.cli arena-compare \
  --left /tmp/static.json --right /tmp/adversarial.json \
  --output /tmp/comparison.json
.venv/bin/python -m competition.cli arena-validate /tmp/comparison.json
.venv/bin/python -m competition.app.backend.api \
  --observer --comparison /tmp/comparison.json --port 8081
```

Observer 没有远程晋升接口，`--observer` 禁止所有 POST。输出包含每个 seed 的修复率、均值对应的总体率、seed 标准差、配对改善/退化数和描述性区间。重复 seed 与同一 case 有相关性，不把合并区间当独立样本显著性检验。

## 证据与回退

- 原代码未改；返回原项目根目录即使用原版本。
- `ORIGINAL_SHA256.json` 记录开发前原文件内容；验收报告说明核验情况。
- 模型响应、候选、仿真和 formal 产物仅在独占 runtime 下保存；Observer 只导出允许的摘要字段。
- 凭据、dirty checkout、缺失审计、不同模型/预算/manifest/seeds、A 状态改变和 injected/guided 结果不能冻结为正式对比。
- 不自动提交、不自动合并、不自动替换原目录。
