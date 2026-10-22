# R3E: Verifier-Mediated Red–Blue Policy Evolution for RTL Repair

R3E studies whether an LLM repair agent (Blue) improves from experience
gathered while an adversary (Red) probes its weaknesses. Neither side
changes model weights. Each side's strategy is an external memory that
the loop rewrites from verified outcomes:

- **Blue** repairs buggy RTL using visible test evidence. Its memory is
  case records of its own verified repairs, stored as causal chains
  (observed failure, fault, repair, what did not work, verification). Memory
  is offered as a reference only after Blue's own first attempt fails.
  Cases are activated only by paired qualification on other designs.
- **Red** proposes bugs and keeps an experience base of Blue's weak
  points. It decides whether to pursue a weak point on a new design (same,
  harder or simpler) or to explore.
- The runner only referees: admission checks, information boundaries,
  paired measurement and the call budget.

## Layout

| Path | Contents |
|---|---|
| `r3e/loop/` | The closed loop: Red, Blue, curriculum, qualification gate, mastery tests, evaluation, budget, CLI |
| `r3e/knowledge/` | Failure profiles, case memory, matching, delivery to Blue |
| `r3e/providers/`, `r3e/protocol/` | OpenAI-compatible JSON client; hashing and hash-chained ledgers |
| `datasets/` | Public bug benchmarks (CirFix, Literature-32, Strider, RTLFixer) and `generated/corpus_v1` (151 clean designs with testbenches) |
| `experiments/loop_probes/` | Diagnostic probes (transfer probe, match diagnosis, patch forensics) |
| `scripts/` | Dataset verification and release audit |
| `tests/` | Tests of the loop and the knowledge package |

## Requirements

- Python ≥ 3.11.
- `openai` and `pytest` (`requirements.txt`).
- Icarus Verilog (`iverilog`, `vvp`) and Yosys on `PATH`.

## Usage

```bash
# worst-case call budget of a run, with no model calls
python -m r3e.loop.cli --state-dir STATE --curriculum --rounds 4 --proposals 4 --plan

# plumbing check with scripted fake models
python -m r3e.loop.cli --state-dir STATE --curriculum --fake --rounds 2

# real run: needs explicit approval flags and a hard call cap
python -m r3e.loop.cli --state-dir STATE --curriculum --llm-env FILE \
    --allow-real-calls --max-calls 150 --rounds 4 --proposals 4
```

Credentials are read only from the `--llm-env` file (`export NAME=value`
lines). A run is resumable, and every model call is written to a
hash-chained `calls` ledger. `python -m r3e.loop.cli --help` lists the
options (memory order, cross-model checks, evaluation).

## Checks

```bash
python -m pytest
python scripts/verify_datasets.py
python scripts/check_release.py
```

## License

Code: see `LICENSE`. Datasets keep their upstream licenses (`datasets/licenses/`).

## 本地整合入口

本目录以 `ShenShan123/R3E` 的 main 提交 `268c4c984` 为基础。
新版与旧版不同的核心实现、配置、数据集和测试均采用新版；新版删除的
arena、policy、旧 memory 和 competition 依赖不恢复到新版运行路径。
本地备份提交 `8c1c2d7b2` 和原目录保留，旧 run06 的源码、日志、网页及
实验记录仍在原目录使用。旧运行状态不能作为新版闭环的状态或记忆导入。

迁移了 run06 的启动便利功能：自动选择已有 Python 环境、环境检查、
终端与文件同时记录日志、状态查询、阻止同一目录重复启动，以及使用新版
自身检查点恢复。没有移植旧版重试、预算、考试划分或记忆晋升规则。

在本目录执行：

```bash
bash local-run check
bash local-run plan --rounds 2 --proposals 1
bash local-run smoke
bash local-run test
```

`check` 不读取密钥也不请求服务；`plan` 只计算调用预算；`smoke` 使用
脚本模拟模型跑两轮最小闭环，不做学习效果评测；`test` 运行离线测试。
后三者的 Python 子进程禁止网络连接。模拟记录中的 calls 是模拟请求计数，
不是外部 API 调用次数。

保留一场可查询的模拟运行，随后重复同一条 start 命令由新版检查点恢复：

```bash
bash local-run start --state-dir runtime/my-fake-run --rounds 2 --proposals 1
bash local-run status --state-dir runtime/my-fake-run
```

`start` 默认使用模拟模型，日志保存在所选状态目录的 `logs/` 下。
恢复遵循新版的配置一致性检查；不会自动重试失败的模型请求。
新状态写在本目录的 `runtime/` 中，旧 run06 不受影响。
真实运行仍须显式提供新版 CLI 要求的 `--allow-real-calls`、正数
`--max-calls` 和 `--llm-env`；本次整合验证不执行真实运行。fake 与 real
必须使用不同状态目录。调用额度及恢复语义沿用上游 CLI，不重新定义。

启动器依次使用 `R3E_RUN_PYTHON`、本目录 `.venv/bin/python`、父目录
`.venv/bin/python`。它固定导入本目录的新核心，不使用旧 run06 的 PYTHONPATH。
旧实验继续使用原入口；当前目录的新入口是 `bash local-run`。
