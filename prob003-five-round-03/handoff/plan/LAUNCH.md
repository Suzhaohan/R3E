# Execution

Use the exact interpreter in plan.json and an environment with the pinned tokenizer. Run from the repository root; replace PLAN_DIR and RUN_DIR with the chosen directories.

```sh
<FROZEN_PYTHON> -m experiments.loop_probes.continuous_launch check --plan-dir PLAN_DIR
# Only after separate approval for 25 requests and the CNY 12 envelope:
<FROZEN_PYTHON> -m experiments.loop_probes.continuous_launch collect --plan-dir PLAN_DIR --env-file ENV_FILE --run-dir RUN_DIR
# Offline, only after complete collection:
<FROZEN_PYTHON> -m experiments.loop_probes.sequence_curriculum report --out RUN_DIR/collection
```

The balance pre-check runs before creating RUN_DIR. One shared transport enforces auth/balance halts, consecutive-failure halt, request-specific output and usage guards, and the spending reserve. Do not resume, substitute tasks or spend unused reserves on more requests. Reports do not modify state.
