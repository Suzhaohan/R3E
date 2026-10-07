# R³E-AIC Competition M3：双机红蓝对抗与动态修复能力演示设计方案

> 仓库：`ShenShan123/R3E`  
> 分支：`competition/aic-ic-2026`  
> 本方案审查基线 Commit：`7aa1250cdf93632a4dda60de21b4220835dfe41c`  
> 当前 Competition 版本：M2  
> 目标版本：**M3 — Dual-Machine Adversarial Evolution Demo**
>
> 核心演示问题：
>
> **在模型权重、候选预算、EDA 验证工具链和初始修复策略保持一致的条件下，引入 Red–Blue 对抗式缺陷发现与正确性门控策略更新，是否能够让 RTL Repair Agent 在后续冻结测试集上获得更高的修复成功率？**

---

# 0. 设计结论

当前 `competition/aic-ic-2026` 已经完成 Competition M2 的主修复链：

```text
Buggy RTL
   ↓
Runtime Evidence
   ↓
Failure Descriptor
   ↓
Descriptor Router
   ↓
R³E Blue Candidate Portfolio
   ↓
Scope Gate
   ↓
Parse
   ↓
Compile
   ↓
Simulation
   ↓
Differential Oracle
   ↓
Yosys Structural Check
   ↓
Repeatability
   ↓
Accept / Reject
```

M3 **不应该重新实现一套 Red–Blue 框架**。

现有 `r3e/` 中已经存在：

- `r3e/arena/runner.py`：Whole-Policy Evolution Round Runner；
- `r3e/arena/round_state.py`：16-stage 可恢复、hash-bound evolution state machine；
- `r3e/arena/paired_replay.py`：parent/candidate paired replay；
- `r3e/policy/promotion.py`：policy promotion gate；
- `r3e/policy/registry_v2.py`：active policy registry / atomic promotion / rollback；
- `r3e/red/`：challenge、archive、novelty、learnability、lineage；
- `r3e/red/grounded/`：Grounded Red 的 proposal、materialization、validity、coverage、formal rejection；
- `r3e/arena/real_grounded_adapter.py`：真实 provider 驱动的 Grounded Red target selection/materialization；
- `r3e/blue/portfolio/`：当前 Competition M2 已经实际使用的 Blue Candidate Portfolio；
- `r3e/memory/`：经验记忆与 activation gate。

因此 M3 的原则是：

> **Competition 层只新增“双机实验编排、真实 evolution adapter、评估、冻结证据与 Arena UI”，真正的 Red / Blue / Promotion / Replay authority 继续复用现有 R³E Core。**

---

# 1. 这次比赛演示要证明什么

## 1.1 主命题

比赛现场不要把问题讲成：

> “我们做了一个红队攻击蓝队的系统。”

应该讲成：

> **R³E 利用 Red 主动寻找当前 Repair Policy 尚未解决的 RTL 功能缺陷，将这些失败转换为可验证修复经验，再经过 replay 和 regression gate 更新运行时修复策略，从而在不更新模型权重的情况下动态增强 RTL Repair Agent。**

整个演示的重点不在“攻击”，而在：

```text
New Failure Discovery
       ↓
Verified Repair
       ↓
Policy Update
       ↓
Capability Change
```

## 1.2 两台机器回答的问题

### Machine A：Static RTL Repair

```text
相同模型
相同 B0
相同 M0
相同 Blue Portfolio
相同 Candidate Budget
相同 EDA Gate

Red OFF
Policy Update OFF
Memory Activation OFF
```

它：

> **会修，但不会通过新失败更新运行时策略。**

### Machine B：Adversarial Evolving RTL Repair

初始条件与 A 完全相同：

```text
same model
same B0
same M0
same candidate budget
same verification
```

但开启：

```text
Red Challenge
       ↓
Admitted Failure
       ↓
Blue Repair
       ↓
Target Replay
       ↓
Non-target Regression
       ↓
Policy Promotion
       ↓
B0 → B1 → B2 ...
```

它：

> **不仅修，而且围绕当前不会修的问题持续更新运行时 Repair Policy。**

---

# 2. 当前代码状态与 M3 的真实缺口

## 2.1 当前 Competition M2 已经可以直接复用

### `competition/services/diagnosis_service.py`

当前已经：

```text
Oracle mismatch
→ first divergence
→ runtime RTL context
→ Grounded FailureDescriptor
→ r3e.blue.portfolio.router
```

因此 M3 不需要重新开发 diagnosis。

### `competition/services/repair_service.py`

当前已经实际使用：

```text
CandidatePortfolioExecutor
Lens Registry
Descriptor Router
OpenAICompatibleCandidateProvider
CompetitionCandidateVerifier
```

即：

```text
Competition Repair
→ R³E Blue Portfolio
```

M3 应继续复用。

### `competition/services/scope_service.py`

已经实现：

```text
module identity
interface preservation
changed lines
AST semantic patch
forbidden constructs
```

M3 所有 policy replay candidate 也必须经过这个 gate 或 Core 等价 gate。

### `competition/services/verification_service.py`

当前完整 gate：

```text
parse
scope
compile
simulation
oracle
structural_check
repeatability
```

对于批量公开 benchmark / Red-Heldout evaluation，则优先使用：

```text
r3e.blue.portfolio.oracle_gate_verifier.PublicManifestOracleVerifier
```

避免把所有 benchmark case 强行塞进 `Competition CaseCatalog`。

## 2.2 当前 Evolution UI 还不是运行引擎

`competition/services/evolution_service.py` 当前只是：

```text
读取 competition/results/frozen/evolution/manifest.json
→ 有 verified evidence 则展示
→ 否则 unavailable
```

它适合**回放层**，但不运行真正 evolution。

M3 需要新增：

```text
AdversarialArenaService
```

作为：

```text
Competition
      ↓
r3e.arena.EvolutionRoundRunner
```

的真实编排 facade。

## 2.3 不能简单把 `evolution.enabled=false` 改成 true

当前 `competition/configs/competition.yaml` 仍是：

```yaml
evolution:
  enabled: false

memory:
  enabled: false
```

M3 不建议直接改开关，因为当前 Competition M2 的 `RepairService` 中 `_policy()` 会构造固定 `B_AIC_M2`，它不会自动读取已经 promotion 的 active registry。

如果只是打开 `evolution.enabled`：

> Arena 即使生成了 B1，Repair Studio 和 Final Evaluation 仍可能继续使用 B_AIC_M2。

因此必须先解决：

```text
Policy Runtime Binding
```

## 2.4 当前 `RealGroundedArenaAdapter` 是 Shadow Adapter

当前 `r3e/arena/real_grounded_adapter.py` 可以真实完成：

```text
Grounded Red target selection
mutation plan
operator materialization
provider receipt
```

但它当前的：

```python
screen_child(...)
```

固定返回：

```text
survive = False
shadow_only = True
```

而：

```python
replay(...)
```

固定返回：

```text
oracle_ok = False
```

因此它**不能直接承担真正 B0→B1 promotion**。

M3 必须增加：

```text
CompetitionEvolutionAdapter
```

把：

```text
真实 Red generation
+
真实 Blue child screening / replay
```

接起来。

这是 M3 后端开发的 P0。

---

# 3. M3 总体架构

```text
                          OBSERVER / COMPETITION UI
                      read-only telemetry + frozen evidence
                              ↑               ↑
                              │               │
                     HTTP GET / artifact export only
                              │               │
           ┌──────────────────┘               └──────────────────┐
           │                                                     │
           ▼                                                     ▼
┌──────────────────────────┐                         ┌────────────────────────────┐
│ MACHINE A                │                         │ MACHINE B                  │
│ STATIC REPAIR            │                         │ ADVERSARIAL EVOLUTION      │
│                          │                         │                            │
│ Git Commit = X           │                         │ Git Commit = X             │
│ Model = M                │                         │ Model = M                  │
│ Policy = B0 fixed        │                         │ Policy = B0 → B1 → B2      │
│ Memory = M0 fixed        │                         │ Memory = M0 fixed in M3-A  │
│ Candidate Budget = 3     │                         │ Candidate Budget = 3       │
│ Red = OFF                │                         │ Red = ON                   │
│ Promotion = OFF          │                         │ Promotion = ON             │
└──────────────────────────┘                         └────────────────────────────┘
           │                                                     │
           └──────────────────────┬──────────────────────────────┘
                                  ▼
                           FROZEN EVALUATION
                         ┌────────────────────┐
                         │ Strider-14         │
                         │ Red-Heldout-N      │
                         └────────────────────┘
                                  │
                                  ▼
                            Repair Rate Δ
```

---

# 4. M3 首版建议：只做 Policy Evolution，不同时开启 Memory Promotion

虽然 R³E Core 已有完整 memory/RAAM infrastructure，但比赛首版双机对比不要同时打开：

```text
Red
Policy Evolution
Memory Activation
```

否则 B 变强时，评委无法判断来自 Red exposure、Policy 还是 Memory。

## M3-A：主比赛演示

```text
Red ON
Policy Promotion ON
Memory Promotion OFF
```

即：

```text
B0 → B1 → B2
M0 保持不变
```

## M3-B：后续增强，可选

再增加：

```text
Verified Episode
→ Shadow
→ Qualification
→ Active Memory
```

作为单独展示，不与首轮双机主实验混合。

---

# 5. 两台机器的强公平性约束

| 项目 | Machine A | Machine B |
|---|---|---|
| Git Commit | 相同 | 相同 |
| Docker/Image Hash | 相同 | 相同 |
| Python | 相同 | 相同 |
| Icarus | 相同 | 相同 |
| VVP | 相同 | 相同 |
| Yosys | 相同 | 相同 |
| Provider | 相同 | 相同 |
| Model ID | 相同 | 相同 |
| Model Version | 相同 | 相同 |
| Temperature | 相同 | 相同 |
| Candidate Budget | 3 | 3 |
| Evaluation Seeds | 相同 | 相同 |
| Lens Registry | 相同 | 相同 |
| Descriptor Router | 相同 | 相同 |
| Candidate Portfolio | 相同 | 相同 |
| Initial Policy Hash | B0 hash | B0 hash |
| Initial Memory Hash | M0 hash | M0 hash |
| Final Evaluation Dataset | 相同 | 相同 |
| Red | OFF | ON |
| Policy Commit | OFF | ON |

唯一核心 treatment difference：

```text
ADVERSARIAL EVOLUTION ENABLED
```

---

# 6. 两机物理隔离建议

## Machine A

```text
/opt/r3e-aic/
├── repo/
├── runtime_static/
│   ├── registry/
│   ├── runs/
│   └── eval/
└── export/
```

## Machine B

```text
/opt/r3e-aic/
├── repo/
├── runtime_adversarial/
│   ├── registry/
│   ├── rounds/
│   ├── archives/
│   ├── red/
│   ├── events/
│   └── eval/
└── export/
```

Evaluation 数据推荐作为：

```text
/eval_ro/
```

read-only mount。

Evolution 期间最好：

```text
Machine B 不挂载 Red-Heldout
Machine B 不读取 Strider-14 evaluation result
```

到 final evaluation 再挂载。

---

# 7. 数据集设计

当前公开仓库已经存在：

```text
datasets/manifests/strider14.jsonl
```

因此 Strider-14 可以直接作为 public external evaluation。

但当前公开 `datasets/manifests/` 中没有：

```text
red_evolve.jsonl
red_heldout.jsonl
```

所以这两套必须单独冻结。

推荐：

```text
                     ALL DATA
                        │
        ┌───────────────┴────────────────┐
        │                                │
        ▼                                ▼
   EVOLUTION                         EVALUATION
        │                                │
 Red-Evolve-N               ┌────────────┴───────────┐
                            │                        │
                            ▼                        ▼
                       Strider-14              Red-Heldout-N
```

## Red-Evolve-N

只给 Machine B，用于：

```text
Red challenge
residual discovery
policy search
promotion replay target
```

不能作为 final generalization result。

## Red-Heldout-N

只用于 A/B final evaluation，不进入：

```text
Red archive
Target replay
Policy search
Memory
```

## Strider-14

用于：

> 外部公开数据分布上的 generalization evaluation。

M3 不复制 RTL，只引用现有 manifest。

---

# 8. Red-Evolve / Red-Heldout 防泄漏

至少检查：

```text
case_id 不重复
poison_id 不重复
normalized_diff_hash 不重复
failure_signature 不重复
```

最好进一步做到：

```text
source design disjoint
```

例如：

```text
Red-Evolve:
Design A / B / C / D

Red-Heldout:
Design E / F / G
```

如果现有论文 Red 数据无法 design-disjoint，则至少：

```text
不同 poison
不同 normalized diff
不同 generation seed
不进入任何 promotion artifact
```

正式报告明确实际采用哪一级别。

---

# 9. 不建议用 Red-Evolve 本身作为最终测试

错误实验：

```text
Red 生成 Bug
→ B 修
→ B promotion
→ 再测同一批 Bug
→ B 很高
```

这只能证明：

```text
failure absorption
```

不能证明：

```text
unseen failure transfer
```

所以最终拆成：

```text
Absorption:
Red-Evolve replay

Generalization:
Strider-14
Red-Heldout
```

---

# 10. Final Evaluation 指标

主指标统一：

```text
Repair Success within 3 candidates
```

因为 Competition 当前：

```text
candidate_budget = 3
```

UI 可以叫：

> **三候选自动修复成功率**

论文统计内部继续保留：

```text
pass@3 / RR@3
```

---

# 11. M3 新增 Competition 文件

```text
competition/
├── arena_config.py
├── arena/
│   ├── __init__.py
│   ├── baseline.py
│   ├── protocol.py
│   └── isolation.py
├── services/
│   ├── policy_runtime_service.py
│   ├── adversarial_arena_service.py
│   ├── arena_evaluation_service.py
│   ├── arena_comparison_service.py
│   └── arena_telemetry_service.py
├── adapters/
│   ├── __init__.py
│   ├── competition_evolution_adapter.py
│   └── competition_red_adapter.py
├── schemas/
│   ├── arena_experiment.py
│   ├── arena_round.py
│   ├── arena_evaluation.py
│   └── arena_comparison.py
├── configs/
│   └── arena/
│       ├── static.yaml
│       ├── adversarial.yaml
│       ├── evaluation.yaml
│       └── observer.yaml
├── manifests/
│   ├── red_evolve.jsonl
│   └── red_heldout.jsonl
├── results/frozen/
│   ├── arena/
│   └── comparison/
└── scripts/
    ├── arena_init.py
    ├── arena_run_round.py
    ├── arena_evaluate.py
    ├── arena_compare.py
    ├── freeze_arena_evidence.py
    └── validate_arena_evidence.py
```

不要复制出新的 `competition/red/`、`competition/policy/`、`competition/memory/` Core。

---

# 12. P0：PolicyRuntimeService

当前 Competition `RepairService._policy()` 固定生成：

```text
B_AIC_M2
```

M3 必须支持：

```text
Machine A:
Fixed Policy B0

Machine B:
Current Active Policy from Registry
```

新增：

```text
competition/services/policy_runtime_service.py
```

建议接口：

```python
class PolicyRuntimeService:
    def fixed_policy(self) -> PolicyState:
        ...

    def active_policy(self, registry_path: Path) -> PolicyState:
        ...

    def policy_snapshot(self, policy: PolicyState) -> dict:
        ...
```

RepairService 当前：

```python
def _policy(self) -> PolicyState:
```

改成：

```python
def _policy(
    self,
    policy_override: PolicyState | None = None,
) -> PolicyState:
```

逻辑：

```text
policy_override is None
    → 当前 Competition Demo B_AIC_M2

policy_override exists
    → 使用指定 active policy
```

这样不会破坏现有 Repair Studio。

再增加批量 Core 入口：

```python
evaluate_case_with_policy(
    policy,
    case,
    seed,
    provider,
    verifier,
)
```

Arena Evaluation 不绕 HTTP API。

---

# 13. P0：CompetitionEvolutionAdapter

新增：

```text
competition/adapters/competition_evolution_adapter.py
```

满足 `EvolutionRoundRunner` adapter contract：

```python
generate_red(...)
probe_learnability(...)
screen_child(...)
replay(...)
```

---

# 14. `generate_red()`

不要重写 mutation engine。

使用：

```text
r3e.arena.real_grounded_adapter.RealGroundedArenaAdapter
```

但增加：

```text
CompetitionGroundedRedAdapter
```

做多 target composition。

原因是当前 `RealGroundedArenaAdapter` 一个实例要求 Grounded target manifest 中正好一个 eligible case。

Competition wrapper 可以：

```text
Target Manifest A
Target Manifest B
Target Manifest C
        │
        ├─ RealGroundedArenaAdapter A
        ├─ RealGroundedArenaAdapter B
        └─ RealGroundedArenaAdapter C
        │
        ▼
Merged Red Candidates
```

每个 candidate 仍由 Core 的：

```text
mutation plan
materializer
AST scope
provider receipt
Grounded validity
```

约束。

---

# 15. 每个 Promotion Epoch 最好至少覆盖 2 个 design

当前 `r3e/policy/promotion.py` 默认 gate 包含：

```text
min_prior_failure_recovery = 2
min_target_recovery_ratio = 0.50
min_covered_designs = 2
non_target_epsilon = 0.02
max_cost_ratio = 1.5
```

如果每轮只有：

```text
1 design
1 target failure
```

就无法通过默认 strong promotion。

比赛版不要为了方便把 `min_covered_designs` 主动降为 1 作为第一方案。

优先：

```text
每个 Promotion Epoch
至少积累 2 个 design 上的 unresolved failures
```

再触发 promotion。

---

# 16. 推荐 Round 结构

```text
Round R0
Collect unresolved failures

Round R1
Collect additional unresolved failures

Promotion Epoch P1
B0 → B1

Round R2
Challenge B1

Round R3
Collect additional failures

Promotion Epoch P2
B1 → B2
```

UI 可简化为：

```text
R0 → B0
R1 → B1
R2 → B1
R3 → B2
```

---

# 17. `probe_learnability()` 不能继续使用 Shadow Stub

当前 `RealGroundedArenaAdapter.probe_learnability()` 是固定 `reachable`，且 `provider_calls = 0`。

M3 如果要把 learnability 当真实证据，必须执行：

```text
same model
expanded but frozen teacher budget
actual repair attempt
actual oracle
```

返回真实：

```json
{
  "label": "reachable",
  "attempts": 2,
  "successes": 1,
  "budget_exhausted": false,
  "evidence": {
    "provider_calls": 2,
    "oracle_result_hash": "..."
  }
}
```

如果比赛前没有完成真实 learnability：

> 从比赛 claim 中移除 learnability，不得把 shadow stub 当真实结果展示。

---

# 18. `screen_child()`

Child Policy 不能凭文本判断。

流程：

```text
Parent Policy
Candidate Policy
      │
      ▼
Adaptation Manifest
      │
      ▼
Executable screening slice
      │
      ├─ target failures
      └─ sanity cases
      │
      ▼
EDA Oracle
      │
      ▼
survive / reject
```

调用：

```text
CandidatePortfolioExecutor
+
PublicManifestOracleVerifier
```

真正跑 child policy。

---

# 19. `replay()`

这是 promotion 最关键的一步。

`r3e.arena.paired_replay` 最终需要 `parent` 和 `candidate` 在完全同一：

```text
case
seed
model
budget
verifier
```

下成对执行。

Competition adapter：

```python
replay(policy, case, seed)
```

必须返回真实：

```json
{
  "policy_hash": "...",
  "seed": 1,
  "oracle_ok": true,
  "cost": 1.0,
  "model_id": "...",
  "budget_hash": "...",
  "verifier_hash": "..."
}
```

不能返回 stub。

---

# 20. 批量评估优先使用 `PublicManifestOracleVerifier`

对于：

```text
Strider-14
Red-Evolve
Red-Heldout
```

不要使用 `Competition CaseCatalog`。

`CaseCatalog` 当前故意限制：

```text
demo_counter
demo_fsm
demo_shift
```

批量 evaluation 应走：

```text
public_case_from_manifest(...)
        ↓
PublicManifestOracleVerifier
```

其特点：

```text
golden RTL 不暴露给 provider
manifest hash 校验
isolated workspace
Yosys elaboration
differential oracle
hash-bound receipt
```

---

# 21. Static Machine Config

```yaml
schema_version: r3e-aic-arena-config-v1

experiment:
  id: aic-dual-machine-v1
  arm: static

policy:
  mode: fixed
  initial_registry: competition/baselines/policy_registry_b0.json
  allow_promotion: false

red:
  enabled: false

memory:
  enabled: false
  allow_activation: false

repair:
  candidate_budget: 3

evaluation:
  seeds: [1, 2, 3]
```

---

# 22. Adversarial Machine Config

```yaml
schema_version: r3e-aic-arena-config-v1

experiment:
  id: aic-dual-machine-v1
  arm: adversarial

policy:
  mode: evolving_registry
  initial_registry: competition/baselines/policy_registry_b0.json
  allow_promotion: true

red:
  enabled: true
  authority: grounded_runtime_authority_v1
  proposal_budget: 4
  family_quota: 2
  maximum_difficulty_band: D3

blue:
  evaluation_authority: candidate_portfolio_v1

memory:
  enabled: false
  allow_activation: false

repair:
  candidate_budget: 3

evolution:
  rounds: 4
  challenge_seeds: [1, 2, 3]
  promotion_seeds: [1, 2, 3]
```

---

# 23. Arena Config 独立于 `competition.yaml`

保留：

```text
competition/configs/competition.yaml
```

用于：

> Repair Studio / normal demo

新增：

```text
competition/configs/arena/
```

原因：

```text
M2 normal demo
≠
M3 multi-round experiment
```

新增 `competition/arena_config.py`，单独校验：

```text
arm
baseline binding
seed schedule
immutable paths
red/eval split
```

---

# 24. Baseline Snapshot

实验前生成：

```text
competition/baselines/
└── dual_machine_v1/
    ├── baseline_manifest.json
    ├── policy_registry_b0.json
    ├── memory_state_m0.json
    ├── blue_binding.json
    └── toolchain.json
```

`baseline_manifest.json` 至少：

```json
{
  "schema_version": "r3e-aic-dual-baseline-v1",
  "git_commit": "...",
  "container_image_hash": "...",
  "provider_id": "...",
  "model_id": "...",
  "model_version": "...",
  "temperature": 0.0,
  "candidate_budget": 3,
  "policy_id": "B0",
  "policy_hash": "sha256:...",
  "memory_hash": "sha256:...",
  "lens_registry_hash": "sha256:...",
  "router_hash": "sha256:...",
  "portfolio_hash": "sha256:...",
  "strider_manifest_hash": "sha256:...",
  "red_heldout_manifest_hash": "sha256:..."
}
```

A、B 启动时必须验证同一个 baseline hash。

---

# 25. Machine Isolation Manifest

每台机器生成：

```text
runtime/<arm>/machine_manifest.json
```

例如：

```json
{
  "experiment_id": "aic-dual-machine-v1",
  "arm": "adversarial",
  "baseline_hash": "sha256:...",
  "git_commit": "...",
  "hostname_hash": "...",
  "state_root": "...",
  "registry_hash": "...",
  "cross_arm_state_import": false
}
```

最终匿名材料不保存真实 hostname，只保存 hash。

---

# 26. Red Grounded Validity

Red 不是让 LLM 随便改坏 RTL 就算成功。

现有 Arena 已支持：

```text
RED_GENERATE
      ↓
VALIDITY_GATE
```

M3 必须继续使用。

一个 Red poison 至少应满足：

```text
Golden valid
Buggy compile/elaborate valid
Buggy functional behavior differs
Oracle output complete
Mutation provenance valid
Scope valid
```

只有 admitted Red failure 才进入 `BLUE_CHALLENGE`。

---

# 27. Core 16-stage State Machine 直接复用

当前 `r3e/arena/round_state.py` 已定义：

```text
INIT
LOAD_ACTIVE_POLICY
RED_GENERATE
VALIDITY_GATE
BLUE_CHALLENGE
ARCHIVE_UPDATE
FREEZE_RESIDUAL_MANIFEST
SPLIT_ADAPT_TARGET
PROPOSE_CHILDREN
SCREEN_CHILDREN
FREEZE_PROMOTION_MANIFEST
PAIRED_REPLAY
DECIDE
ATOMIC_COMMIT
RENEWED_CHALLENGE
COMPLETE
```

Competition 前台简化为：

```text
1 Discover
2 Admit
3 Challenge
4 Adapt
5 Replay
6 Promote
7 Renew
```

映射：

```text
Discover = RED_GENERATE
Admit = VALIDITY_GATE
Challenge = BLUE_CHALLENGE + ARCHIVE_UPDATE
Adapt = SPLIT_ADAPT_TARGET + PROPOSE_CHILDREN + SCREEN_CHILDREN
Replay = PAIRED_REPLAY
Promote = DECIDE + ATOMIC_COMMIT
Renew = RENEWED_CHALLENGE
```

---

# 28. AdversarialArenaService

新增：

```text
competition/services/adversarial_arena_service.py
```

职责：

```python
initialize_experiment()
run_round()
resume_round()
round_status()
freeze_round()
active_policy()
```

不要让它拥有 Red mutation、Blue candidate generation、Promotion decision authority。

它只编排：

```python
runner = EvolutionRoundRunner(
    config=round_config,
    round_id=round_id,
    adapter=competition_evolution_adapter,
    project_root=runtime_root,
    candidate_provider=provider,
    candidate_verifier=verifier,
)
summary = runner.run()
```

如果 Core runner 要求 repo root，runtime 路径统一放：

```text
runtime/competition_arena/<experiment>/<arm>/
```

并加入 `.gitignore`。

---

# 29. Policy Search

Competition 不自己写：

```text
if temporal bug → append temporal prompt
```

继续使用：

```text
r3e.policy.search.propose_children
```

但建议新增 Competition 专用 search space：

```text
competition/configs/arena/policy_search_space_v1.json
```

锁定：

```text
candidate budget = 3
EDA gate 不变
provider 不变
model 不变
```

只允许策略层变化：

```text
routing preference
specialist priority
evidence interpretation
strategy prompt
portfolio template preference
```

不要允许：

```text
candidate_budget 3 → 8
timeout 增长 10 倍
更换模型
关闭 gate
```

---

# 30. 不允许把更多预算伪装成能力提升

B1/B2 仍必须：

```text
candidate_budget = 3
```

A/B Final Evaluation 都：

```text
3 candidates
```

如果 search space 允许其它 cost 变化，则必须保留 `max_cost_ratio` gate 并在技术报告显示成本。

比赛首版优先直接锁死预算。

---

# 31. Promotion Gate

继续使用：

```text
r3e/policy/promotion.py
```

Core gate 已包括：

```text
target gain
prior failure recovery
target recovery ratio
covered designs
non-target regression
critical regressions
candidate cost
provenance complete
```

只有全部满足：

```text
strong_promotion
```

才允许 `ATOMIC_COMMIT`。

---

# 32. Non-target Regression Dataset

Promotion 的 `non_target_manifest` 不能使用 Strider-14 final evaluation。

应单独准备：

```text
Red-Regression / NonTarget-Regression
```

整体数据结构：

```text
Evolution:
  Red-Evolve

Promotion Regression:
  NonTarget-Regression

Final Eval:
  Strider-14
  Red-Heldout
```

---

# 33. ArenaEvaluationService

新增：

```text
competition/services/arena_evaluation_service.py
```

接口：

```python
evaluate_policy(
    policy,
    manifest,
    seeds,
    run_id,
)
```

Strider-14 直接使用：

```text
datasets/manifests/strider14.jsonl
```

逐 case：

```text
public_case_from_manifest
      ↓
Failure Descriptor
      ↓
Candidate Portfolio
      ↓
PublicManifestOracleVerifier
      ↓
pass/fail
```

---

# 34. Red-Heldout Manifest

建议：

```text
competition/manifests/red_heldout.jsonl
```

每条包含：

```text
case_id
design
buggy_rtl
golden_rtl
tb_sources
deps
tb_output
top_module
sim_timeout
poison_id
failure_signature
normalized_diff_hash
generation_provenance
```

Red-Heldout 最好保存 Materialized Poison，不在 final eval 时重新随机生成。

流程：

```text
generate
→ validity
→ freeze
→ final replay
```

这样 A/B 输入完全一致。

---

# 35. Evaluation 期间禁止更新

Final Evaluation 强制：

```text
read_only_policy = true
promotion = false
memory_write = false
archive_write = false
red = false
```

Machine B final eval 只使用 `B_final`，不能边测试边学。

---

# 36. 两阶段 Evaluation

## T0：Baseline

Evolution 前：

```text
A(B0)
B(B0)
```

分别跑：

```text
Strider-14
Red-Heldout
```

得到：

```text
A0
B0
```

由于 policy 完全相同，paired case 结果应接近；若固定 provider 能稳定 seed，最好完全一致。

## T1：Final

B 完成 evolution 后：

```text
A(B0)
B(Bfinal)
```

再跑相同 frozen evaluation。

Baseline eval 允许做，但必须：

```text
实验配置在 T0 前冻结
T0 case-level result 不进入 B runtime
不调整 Red target
不调整 threshold
不调整 search space
```

---

# 37. 主比较结果

最终 Dashboard：

| Dataset | Static B0 | Adversarial Bfinal | Δ |
|---|---:|---:|---:|
| Strider-14 | X/14 | Y/14 | +Z pp |
| Red-Heldout-N | X/N | Y/N | +Z pp |

不要提前填数字。

再展示：

```text
Policy
B0 → B1 → B2
```

以及每次 promotion 的：

```text
Recovered failures
Non-target regression
Promotion decision
```

---

# 38. Evolution Timeline Artifact

每 round 保存：

```json
{
  "round_id": "R002",
  "policy_before": "B1",
  "policy_after": "B2",
  "red_generated": 4,
  "red_admitted": 3,
  "blue_unresolved": 2,
  "target_recovered": 2,
  "non_target_delta": 0.0,
  "promotion": true,
  "policy_hash_before": "...",
  "policy_hash_after": "..."
}
```

不建议每 round 测 Strider-14。

Evolution Timeline 用：

```text
Red discovery
target replay
non-target regression
policy hash
```

已经足够。

Strider-14 只 T0/T1。

---

# 39. ArenaComparisonService

新增：

```text
competition/services/arena_comparison_service.py
```

只读取：

```text
Machine A frozen eval
Machine B frozen eval
baseline_manifest
```

输出：

```json
{
  "same_baseline": true,
  "same_model": true,
  "same_budget": true,
  "same_eval_manifest": true,
  "strider14": {
    "static": 0.0,
    "adversarial": 0.0,
    "delta_pp": 0.0
  },
  "red_heldout": {
    "static": 0.0,
    "adversarial": 0.0,
    "delta_pp": 0.0
  }
}
```

因为 A/B 在相同 case 上比较，可计算 paired：

```text
A fail / B pass = wins
A pass / B fail = losses
McNemar exact p
```

比赛现场不必强调 p-value，技术报告放。

---

# 40. Frozen Evidence 扩展

当前：

```text
competition/results/frozen/
├── demo/
├── benchmark/
├── evolution/
└── memory/
```

M3：

```text
competition/results/frozen/
├── demo/
├── benchmark/
├── evolution/
├── memory/
├── arena/
│   └── dual_machine_v1/
│       ├── baseline.json
│       ├── static.json
│       ├── adversarial.json
│       ├── rounds.json
│       └── manifest.json
└── comparison/
    └── dual_machine_v1/
        ├── strider14.json
        ├── red_heldout.json
        ├── paired_cases.json
        └── manifest.json
```

现有 `frozen/evolution/` 继续作为 UI-compatible summary。

真正完整证据放 `frozen/arena/`，再由 `freeze_arena_evidence.py` 生成 `frozen/evolution/manifest.json`，无需推翻当前 `EvolutionService`。

---

# 41. M3 Frozen Manifest

```json
{
  "schema_version": "r3e-aic-dual-arena-evidence-v1",
  "experiment_id": "aic-dual-machine-v1",
  "baseline_hash": "sha256:...",
  "static": {
    "final_policy_hash": "sha256:...",
    "promotion_count": 0
  },
  "adversarial": {
    "initial_policy_hash": "sha256:...",
    "final_policy_hash": "sha256:...",
    "promotion_count": 2,
    "round_hashes": []
  },
  "evaluation": {
    "strider14_manifest_hash": "sha256:...",
    "red_heldout_manifest_hash": "sha256:..."
  },
  "comparison_hash": "sha256:..."
}
```

---

# 42. 双机交换数据边界

只允许交换：

```text
read-only telemetry
frozen result summary
hash
```

不允许 B→A 同步：

```text
policy registry
memory bank
red archive
repair trajectory
prompt
candidate RTL
```

Observer 只提供：

```text
GET /api/arena/status
GET /api/arena/rounds
GET /api/arena/evaluation
```

不提供远程 `POST /api/arena/promote`。

Promotion 只能由 Machine B 本地 runner 执行。

---

# 43. Web UI 新页面

当前：

```text
Repair Studio
Verification Trace
Evolution Lab
Experience Memory
Benchmark Dashboard
```

M3 建议：

```text
Repair Studio
Adversarial Arena
Verification Trace
Experience Memory
Benchmark
```

将 Evolution Lab 主展示能力并入 `Adversarial Arena`。

---

# 44. Adversarial Arena 页面布局

```text
┌─────────────────────────────────────────────────────────────┐
│ SAME INITIAL AGENT                                          │
│ Model: XXX | Candidate Budget: 3 | Initial Policy: B0       │
│ Baseline Hash: 9fd... | Toolchain: MATCHED                  │
└─────────────────────────────────────────────────────────────┘

┌──────────────────────────┬──────────────────────────────────┐
│ STATIC AGENT             │ ADVERSARIAL AGENT               │
│ MACHINE A                │ MACHINE B                       │
│                          │                                  │
│ Policy: B0               │ Policy: B0 → B1 → B2           │
│ Evolution: OFF           │ Evolution: ON                    │
│ Red: OFF                 │ Red: ON                          │
│ Memory: M0               │ Memory: M0                       │
│ Current State: READY     │ Current State: ROUND R3          │
└──────────────────────────┴──────────────────────────────────┘

              ADVERSARIAL EVOLUTION TIMELINE

R0                  R1                  R2
●───────────────────●───────────────────●
B0                  B1                  B2
                    ↑                   ↑
             New unresolved bug   New unresolved bug
             Replay PASS          Replay PASS
             Regression PASS      Regression PASS

FINAL EVALUATION

                    Static          Adversarial
Strider-14          ██████          █████████
Red-Heldout         █████           ██████████
```

---

# 45. Round Detail Card

```text
Round R2
----------------------------
Active Policy
B1

Red Generated
4

Admitted Valid Failures
3

Current Blue Could Not Repair
2

Candidate Policy
B2-candidate

Target Replay
2 recovered

Non-target Regression
PASS

Promotion
B1 → B2

Policy Hash
98ab... → e42c...
```

前端不展示 Chain-of-Thought，只展示：

```text
failure family
mutation operator
first mismatch
candidate diff
oracle result
promotion evidence
```

---

# 46. Repair Studio 仍保留

Arena 演示前先用 Counter 证明：

```text
系统真的会修 RTL
```

流程：

```text
Counter Bug
→ runtime diagnosis
→ Blue Portfolio
→ Candidate Diff
→ EDA Gate
```

30–45 秒。

然后切换：

> “单次修复只是第一层，我们进一步让系统主动寻找当前不会修的新缺陷。”

进入 Arena。

---

# 47. 4–5 分钟比赛演示脚本

| 时间 | 内容 |
|---:|---|
| 0:00–0:30 | Compile ≠ Functional Correctness；静态 Repair 的局限 |
| 0:30–1:10 | Counter：Diagnosis → Portfolio → Diff → EDA Gate |
| 1:10–1:30 | 双机初始化：Same model / Same B0 / Same budget / Same EDA |
| 1:30–2:40 | Verified Evolution Replay：Red 找新问题，B0→B1→B2 |
| 2:40–3:20 | Final Evaluation：Strider-14 + Red-Heldout |
| 3:20–3:50 | No Weight Update；变化的是 Runtime Policy |
| 3:50–4:20 | Git/Policy/Data/Seed/Toolchain/Replay/Result Hash 证据 |
| 4:20–4:40 | RTL Debug / Verification / EDA R&D 应用 |

---

# 48. Live 与 Replay

不要现场跑完整 multi-round Red–Blue。

推荐：

## Live

跑一个：

```text
Counter Live Repair
```

证明模型真实进入系统。

## Verified Replay

双机 Evolution 提前真实跑完、冻结 artifact，现场 5–8 秒/round 回放，并明确标：

```text
VERIFIED EVOLUTION REPLAY
```

这不是假动画，因为每 round 都有：

```text
policy hash
poison hash
oracle receipt
paired replay
promotion decision
toolchain
```

---

# 49. CLI 扩展

建议：

```bash
python -m competition.cli arena-init \
  --config competition/configs/arena/static.yaml

python -m competition.cli arena-init \
  --config competition/configs/arena/adversarial.yaml

python -m competition.cli arena-round \
  --experiment aic-dual-machine-v1 \
  --round R000

python -m competition.cli arena-eval \
  --dataset strider14

python -m competition.cli arena-eval \
  --dataset red-heldout

python -m competition.cli arena-compare \
  --left static.json \
  --right adversarial.json
```

---

# 50. Experiment ID 与 Seeds

统一：

```text
experiment_id = aic-dual-machine-2026-v1
```

所有 artifact 都绑定它。

正式结果至少使用：

```text
3 seeds
```

paired：

```text
A seed1 ↔ B seed1
A seed2 ↔ B seed2
A seed3 ↔ B seed3
```

Competition Live UI 可以展示一个 seed，技术报告汇总多 seed。

如果时间有限，最小可行：

```text
3 evolution rounds
3 seeds final eval
Strider-14
Red-Heldout 12–24 cases
```

---

# 51. Red Generated Bug Set 构建

如果复用论文时期 Red 数据：

```text
旧实验 artifacts
      ↓
重新核对 source / oracle / hashes
      ↓
去掉与 Red-Evolve 重叠
      ↓
建立 Red-Heldout manifest
      ↓
freeze
```

不能只把旧 JSON 数字复制过来。

如果重新生成 Red-Heldout：

```text
Clean Design Pool
      ↓
Grounded Red
      ↓
Validity Gate
      ↓
Accepted poison
      ↓
Deduplicate
      ↓
Freeze
      ↓
Red-Heldout manifest
```

生成后立即 seal。

---

# 52. Manifest Seal

```json
{
  "sealed": true,
  "sealed_at": "...",
  "manifest_hash": "sha256:...",
  "allowed_usage": "final_evaluation_only"
}
```

代码检测 `final_evaluation_only` 时，Arena Runner/adapter 禁止导入 Red archive。

---

# 53. Schema

## `arena_experiment.py`

```text
experiment_id
arm
baseline_hash
config_hash
start_commit
```

## `arena_round.py`

```text
round_id
policy_before
red_summary
replay_summary
promotion
policy_after
round_hash
```

## `arena_evaluation.py`

```text
dataset
manifest_hash
policy_hash
seed
cases
repair_rate
```

## `arena_comparison.py`

```text
static
adversarial
paired cases
delta
same baseline checks
```

---

# 54. Static Machine 也必须 Frozen

不能只冻结 B。

A 也保存：

```text
policy hash
model
budget
case results
verifier
toolchain
result hash
```

否则 A/B 对比证据不对称。

---

# 55. Freeze Fail-Closed

`freeze_arena_evidence.py` 必须拒绝：

```text
different git commit
different model
different candidate budget
different eval manifest
different verifier
different seed list
dirty workspace
missing policy hash
missing round audit
B final policy == unknown
A policy changed
```

A 强不变式：

```text
A.initial_policy_hash == A.final_policy_hash
promotion_count = 0
red_archive_count = 0
```

B 如果声称 evolution：

```text
final_policy_hash != initial_policy_hash
promotion_count >= 1
```

且每个 promotion 都有：

```text
paired replay
promotion decision
registry commit
renewed challenge
```

---

# 56. Promotion Rejection 也要支持展示

如果：

```text
Red 找到新 Bug
但 child policy 没通过 promotion
```

UI 显示：

```text
Round R2
Red found new failure
Candidate strategy proposed
Regression FAIL
Promotion REJECTED
Policy remains B1
```

这反而强化：

> **系统不会为了学习而无条件污染自己。**

建议最终演示中保留一次真实 Promotion Rejection（如果实验自然出现），不要人工伪造。

---

# 57. 统计与辅助指标

主指标：

```text
Final Repair Success Rate
```

辅助：

```text
Admitted new failures
Blue unresolved failures
Recovered prior failures
Promotion count
Critical regressions
Cost ratio
```

技术报告可补：

```text
n/N
mean ± SD
Wilson CI
paired McNemar
```

Red Admission Rate 不能当主收益。

---

# 58. 实验解释边界

双机实验支持：

> **整个“对抗式缺陷发现 + 验证修复 + policy evolution”系统相较静态 Repair Agent 的运行时能力变化。**

它不能单独严格证明：

> Red adaptive generation 一项机制本身优于所有普通数据增强。

如果要进一步排除“只是多见了 Bug”，后续增加离线第三控制组：

```text
Arm A: Static
Arm B: Random/Frozen Bug Exposure
Arm C: Adaptive Red
```

预算 matched。

现场仍只展示 A vs C，PPT/技术报告放 B。

第三组不是 M3 P0。

---

# 59. Tests

新增：

```text
tests/competition/
├── test_arena_config.py
├── test_policy_runtime.py
├── test_dual_baseline.py
├── test_static_arm_invariant.py
├── test_adversarial_round.py
├── test_real_replay_adapter.py
├── test_red_eval_separation.py
├── test_red_heldout_seal.py
├── test_arena_freeze.py
├── test_arena_comparison.py
└── test_arena_visibility.py
```

必须覆盖：

```text
A policy changed → FAIL
B imported Red-Heldout → FAIL
A/B model mismatch → FAIL
A/B candidate budget mismatch → FAIL
B promotion without paired replay → FAIL
Evolution UI available without frozen audit → FAIL
Observer writes B policy → FAIL
same poison exists in evolve + heldout → FAIL
```

---

# 60. CI

现有 `.github/workflows/competition.yml` 已经跑：

```text
tests/competition
anonymization
release audit
frozen evidence validation
dataset verification
```

M3 增加：

```text
arena schema tests
arena static invariant tests
arena frozen evidence validator
```

真实 provider/evolution 不在普通 CI 自动跑，只跑离线 contract tests。

---

# 61. P0 / P1 / P2 开发计划

## P0 — 真正让 B0→B1 可执行

- [ ] `PolicyRuntimeService`
- [ ] RepairService 支持 `policy_override`
- [ ] generic manifest evaluation path
- [ ] `CompetitionEvolutionAdapter`
- [ ] real `screen_child`
- [ ] real `replay`
- [ ] real learnability 或移除其经验 claim
- [ ] Arena Config
- [ ] Static / Adversarial baseline binding

## P1 — 数据与双机实验

- [ ] Red-Evolve manifest
- [ ] Red-Heldout manifest
- [ ] overlap checker
- [ ] non-target regression manifest
- [ ] Machine A runtime
- [ ] Machine B runtime
- [ ] 3-round smoke
- [ ] policy promotion evidence
- [ ] final Strider-14 evaluation
- [ ] final Red-Heldout evaluation

## P2 — 比赛可视化

- [ ] Adversarial Arena Tab
- [ ] side-by-side machine cards
- [ ] evolution timeline
- [ ] round detail
- [ ] final comparison bars
- [ ] baseline hash card
- [ ] verified replay mode
- [ ] video script update

---

# 62. 推荐开发顺序

```text
Step 1
先在一台机器本地跑通真正 B0→B1

Step 2
验证 B1 能被 Repair/Eval Service 实际加载

Step 3
冻结 Red-Evolve / Red-Heldout

Step 4
复制相同 baseline 到两台机器

Step 5
跑 Static / Adversarial

Step 6
Final Evaluation

Step 7
Frozen Evidence

Step 8
最后开发 Arena UI
```

不要先做漂亮双机动画。

---

# 63. 单机 M3 Smoke Acceptance

上双机前必须做到：

```text
B0
 ↓
Red admitted failure
 ↓
B0 fails
 ↓
child proposed
 ↓
screen survives
 ↓
paired replay
 ↓
promotion pass
 ↓
registry active = B1
 ↓
RepairService(policy=B1)
真实运行
```

如果最后 RepairService 仍加载 B_AIC_M2，M3 不算完成。

---

# 64. 双机 Acceptance Criteria

## Baseline

- [ ] A/B commit 相同
- [ ] A/B model 相同
- [ ] A/B B0 hash 相同
- [ ] A/B M0 hash 相同
- [ ] A/B candidate budget = 3
- [ ] A/B toolchain fingerprint 匹配

## Machine A

- [ ] Red disabled
- [ ] Promotion disabled
- [ ] Policy hash 全程不变
- [ ] Memory hash 全程不变

## Machine B

- [ ] Red 真正运行
- [ ] Red poison 通过 validity
- [ ] unresolved failure 被 archive
- [ ] child policy 真正生成
- [ ] child screening 真正运行
- [ ] paired replay 真正运行
- [ ] 至少一次 strong promotion
- [ ] registry atomic commit
- [ ] renewed challenge 绑定新 policy hash

## Evaluation

- [ ] Strider-14 manifest frozen
- [ ] Red-Heldout manifest frozen
- [ ] A/B identical eval case list
- [ ] A/B identical seeds
- [ ] evaluation read-only
- [ ] no learning during final eval

## Evidence

- [ ] round audit reconstructable
- [ ] final comparison hash reconstructable
- [ ] no dirty workspace frozen
- [ ] no guided/fake result mixed into live result

---

# 65. 比赛术语建议

内部：

```text
Red
Blue
Policy Promotion
Residual Archive
Paired Replay
```

比赛页面：

```text
Adversarial Bug Discovery
Intelligent Repair
Strategy Upgrade
Unresolved Failure Pool
Safety Replay
```

推荐一句话：

> **R³E 不更新大模型权重，而是让 Red 持续寻找当前 Repair Agent 仍无法解决的新型 RTL 功能缺陷；只有经过真实 EDA 验证、目标重放和非目标回归检查的修复经验，才能推动运行时修复策略升级。**

---

# 66. 双机结果的正确表述

如果 B 最终确实提升，可以说：

> **在相同模型、相同候选预算和相同 EDA 验证条件下，对抗式演化 Agent 经历多轮新缺陷发现与策略更新后，在冻结的 Strider-14 和未参与演化的 Red-Heldout 测试集上获得了更高的修复成功率。**

不要说：

```text
大模型能力被训练提升了
```

因为模型权重没变。

应说：

```text
runtime repair capability improved
```

---

# 67. 最终比赛主故事

```text
传统 Repair Agent
      │
      │ 每次遇到 Bug
      ▼
同一个静态修复策略
      │
      └──────────────→ 能力状态基本固定


R³E
      │
      ▼
当前 Repair Policy
      │
      ▼
Adversarial Bug Discovery
      │
      ▼
发现新的 unresolved failure
      │
      ▼
Verified Repair
      │
      ▼
Safety Replay
      │
      ▼
Policy Promotion
      │
      ▼
新的 Repair Policy
      │
      └──────────────→ 再面对新的 Bug
```

---

# 68. M3 最终目录建议

```text
competition/
├── README.md
├── cli.py
├── config.py
├── arena_config.py
├── app/
│   ├── backend/
│   │   ├── api.py
│   │   ├── health.py
│   │   └── arena_api.py
│   └── frontend/
│       ├── index.html
│       ├── app.js
│       ├── arena.js
│       └── styles.css
├── adapters/
│   ├── competition_evolution_adapter.py
│   └── competition_red_adapter.py
├── services/
│   ├── diagnosis_service.py
│   ├── repair_service.py
│   ├── verification_service.py
│   ├── scope_service.py
│   ├── policy_runtime_service.py
│   ├── adversarial_arena_service.py
│   ├── arena_evaluation_service.py
│   ├── arena_comparison_service.py
│   └── arena_telemetry_service.py
├── configs/
│   ├── competition.yaml
│   └── arena/
│       ├── static.yaml
│       ├── adversarial.yaml
│       ├── evaluation.yaml
│       └── observer.yaml
├── manifests/
│   ├── red_evolve.jsonl
│   ├── red_regression.jsonl
│   └── red_heldout.jsonl
├── baselines/
│   └── dual_machine_v1/
├── schemas/
│   ├── failure_descriptor.py
│   ├── arena_experiment.py
│   ├── arena_round.py
│   ├── arena_evaluation.py
│   └── arena_comparison.py
├── results/
│   └── frozen/
│       ├── demo/
│       ├── benchmark/
│       ├── evolution/
│       ├── memory/
│       ├── arena/
│       └── comparison/
└── scripts/
    ├── arena_init.py
    ├── arena_run_round.py
    ├── arena_evaluate.py
    ├── arena_compare.py
    ├── freeze_arena_evidence.py
    └── validate_arena_evidence.py
```

---

# 69. 现有 Core 到 Competition M3 的映射

| Competition M3 能力 | 直接复用 Core |
|---|---|
| Red Challenge | `r3e/red/` |
| Grounded Red | `r3e/red/grounded/` |
| Red materialization | `r3e/arena/real_grounded_adapter.py` + grounded materializers |
| Validity | `r3e/arena/grounded_authority.py` |
| Evolution state machine | `r3e/arena/runner.py` |
| Round checkpoints | `r3e/arena/round_state.py` |
| Blue Repair | `r3e/blue/portfolio/` |
| Policy Candidate | `r3e/policy/search.py` |
| Promotion | `r3e/policy/promotion.py` |
| Registry | `r3e/policy/registry_v2.py` |
| Paired Replay | `r3e/arena/paired_replay.py` |
| Public benchmark verifier | `r3e/blue/portfolio/oracle_gate_verifier.py` |
| Memory | M3-A 暂不启用；后续复用 `r3e/memory/` |

---

# 70. 最重要的工程边界

M3 不应该做成：

```text
Machine B:
多喂一些 Bug
然后把这些 Bug 的答案塞进 Prompt
```

而应该真正体现：

```text
Red conditioned on current policy
        ↓
new unresolved failure
        ↓
child policy
        ↓
paired executable replay
        ↓
atomic promotion
        ↓
new active policy loaded
```

这才是 R³E 的核心。

---

# 71. 最终执行原则

> **先让真实 B0→B1 的 authority path 完整跑通，再做双机；先让双机 frozen evaluation 有真实差异，再做比赛动画；任何没有真实 artifact 支撑的 Evolution / Memory / Capability Gain 都保持 unavailable。**

M3 的目标不是增加一个“红蓝对抗页面”。

M3 的目标是：

> **把当前已经成熟的 Competition M2 修复系统，与 R³E Core 已有的 Arena/Policy/Red authority 真正接通，使两台隔离机器从同一个 B0 出发，一台保持静态，一台经历可审计的对抗式策略演化，最终在相同冻结测试集上直接比较修复能力变化。**
