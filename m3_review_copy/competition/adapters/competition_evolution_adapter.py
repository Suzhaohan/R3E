"""Use real repair executions for screening, learnability and paired replay.

The resolver must resolve archived identities to frozen materialized cases;
it must never resolve final-only cases. Core still owns validity/promotion.
"""
from r3e.arena.conformance import bind_adapter_output
from r3e.protocol.hashing import hash_payload
from competition.arena.isolation import require_evolution_manifest


class CompetitionEvolutionAdapter:
    def __init__(self, *, red_adapter, evaluator, cases, screening_seeds=(1, 2, 3)):
        require_evolution_manifest(cases)
        self.cases = {r["case_id"]: dict(r) for r in cases["rows"]}
        for row in cases["rows"]:
            if row.get("poison_id"):
                if row["poison_id"] in self.cases and self.cases[row["poison_id"]] != row:
                    raise ValueError("ambiguous poison identity")
                self.cases[row["poison_id"]] = dict(row)
        if not screening_seeds or any(type(s) is not int for s in screening_seeds) or len(set(screening_seeds)) != len(screening_seeds):
            raise ValueError("unique screening seeds required")
        self.red_adapter = red_adapter
        self.evaluator = evaluator
        self.seeds = tuple(screening_seeds)
        self.toolchain_fingerprint = red_adapter.toolchain_fingerprint

    def generate_red(self, parent, config, red_search_context):
        return self.red_adapter.generate_red(parent, config, red_search_context)

    def _case(self, row):
        key = row.get("case_id") or row.get("poison_id")
        if key not in self.cases:
            raise ValueError("case is not in frozen evolution membership")
        return self.cases[key]

    def replay(self, policy, case, seed):
        row = self.evaluator.evaluate_case_with_policy(policy, self._case(case), seed)
        if row["model_id"] != self.toolchain_fingerprint["model_id"]:
            raise ValueError("Red/Blue model mismatch")
        return bind_adapter_output(row, "replay", self.toolchain_fingerprint,
            budget_hash=hash_payload(policy.budgets))

    def screen_child(self, parent, child, adaptation_manifest):
        require_evolution_manifest(adaptation_manifest)
        if adaptation_manifest["split"] != "adaptation":
            raise ValueError("screening requires adaptation split")
        if parent.budgets != child.budgets:
            raise ValueError("child budget changed")
        pairs = []
        for case in adaptation_manifest["rows"]:
            for seed in self.seeds:
                pairs.append((self.replay(parent, case, seed), self.replay(child, case, seed)))
        recovered = sum(not p["oracle_ok"] and c["oracle_ok"] for p, c in pairs)
        regressions = sum(p["oracle_ok"] and not c["oracle_ok"] for p, c in pairs)
        return bind_adapter_output({"survive": recovered > 0 and regressions == 0,
            "recovered": recovered, "regressions": regressions,
            "paired_execution_hash": hash_payload(pairs), "pairs": pairs},
            "screen_child", self.toolchain_fingerprint)

    def probe_learnability(self, policy, poison):
        # Multiple real, fixed-budget attempts; never use the shadow reachable stub.
        rows = [self.replay(policy, poison, seed) for seed in self.seeds]
        successes = sum(r["oracle_ok"] for r in rows)
        return bind_adapter_output({"label": "reachable" if successes else "unresolved",
            "challenged_policy_hash": policy.policy_hash,
            "teacher_mode": "same_model_expanded",
            "teacher_budget": {k: v * len(rows) for k, v in policy.budgets.items()},
            "attempts": len(rows), "successes": successes, "budget_exhausted": not bool(successes),
            "evidence": {"provider_calls": sum(r["resource_usage"]["provider_calls"] for r in rows),
                         "replay_hash": hash_payload(rows), "receipts": rows}},
            "probe_learnability", self.toolchain_fingerprint)
