"""Executable Core adapter; generated poisons are resolved by exact identity."""
from copy import deepcopy
from pathlib import Path
from r3e.arena.conformance import bind_adapter_output
from r3e.protocol.hashing import hash_payload, hash_file
from competition.arena.evidence import freeze, read, signed, verify_signed
from competition.arena.isolation import require_evolution_manifest

class CompetitionEvolutionAdapter:
    def __init__(self, *, red_adapter, evaluator, cases, regression, index_path, screening_seeds=(1,2,3), replay_cache_root=None, supplied_cases=None):
        require_evolution_manifest(cases)
        require_evolution_manifest(regression)
        self.cases = {r["case_id"]: deepcopy(r) for r in cases["rows"] + regression["rows"]}
        if supplied_cases is not None:
            require_evolution_manifest(supplied_cases)
            self.cases.update({r["case_id"]: deepcopy(r) for r in supplied_cases["rows"]})
        self.index_path = Path(index_path)
        self.generated = verify_signed(read(self.index_path))["cases"] if self.index_path.exists() else {}
        if len(screening_seeds) < 2 or any(type(s) is not int for s in screening_seeds) or len(set(screening_seeds)) != len(screening_seeds):
            raise ValueError("at least two unique screening seeds required")
        self.red_adapter, self.evaluator = red_adapter, evaluator
        self.seeds = tuple(screening_seeds)
        self.replay_cache_root = Path(replay_cache_root) if replay_cache_root is not None else None
        self.toolchain_fingerprint = evaluator.provider.toolchain_fingerprint
        self.conformance_fingerprints = [self.toolchain_fingerprint, red_adapter.toolchain_fingerprint]

    def generate_red(self, parent, config, red_search_context):
        rows = list(self.red_adapter.generate_red(parent, config, red_search_context))
        for row in rows:
            if row["case_id"] not in self.cases:
                raise ValueError("Red selected a case outside evolution membership")
            frozen = {**deepcopy(row), "generated_poison_sha256": hash_file(row["buggy_rtl"])}
            prior = self.generated.get(row["poison_id"])
            if prior and prior != frozen:
                raise ValueError("generated poison identity collision")
            self.generated[row["poison_id"]] = frozen
        # Index is an append-only map, needed for recovery after process restart.
        from r3e.protocol.hashing import atomic_write_json
        atomic_write_json(self.index_path, signed({"cases": self.generated}))
        return rows

    def _case(self, row):
        if row.get("poison_id"):
            key = row["poison_id"]
            if key not in self.generated:
                original = self.cases.get(row.get("case_id"))
                if original and original.get("poison_id") == key:
                    return original
                raise ValueError("unknown generated poison; never substitute its source bug")
            result = self.generated[key]
            for field in ("normalized_diff_hash", "failure_signature"):
                if row.get(field) and row[field] != result[field]:
                    raise ValueError("archived poison binding mismatch")
            return result
        key = row.get("case_id")
        if key not in self.cases:
            raise ValueError("case not in evolution/regression membership")
        return self.cases[key]

    def replay(self, policy, case, seed):
        resolved = self._case(case)
        if self.replay_cache_root is None:
            receipt = self.evaluator.evaluate_case_with_policy(policy, resolved, seed)
        else:
            receipt = self.evaluator.evaluate_case_cached(
                policy, resolved, seed, cache_root=self.replay_cache_root)
        if receipt["model_id"] != self.toolchain_fingerprint["model_id"]:
            raise ValueError("replay model mismatch")
        return bind_adapter_output(receipt, "replay", self.toolchain_fingerprint,
            budget_hash=hash_payload(policy.budgets), verifier_hash=receipt["verifier_hash"])

    def screen_child(self, parent, child, adaptation_manifest):
        require_evolution_manifest(adaptation_manifest)
        if adaptation_manifest["split"] != "adaptation" or parent.budgets != child.budgets:
            raise ValueError("invalid screening split or child budget")
        pairs = [(self.replay(parent, case, seed), self.replay(child, case, seed))
                 for case in adaptation_manifest["rows"] for seed in self.seeds]
        recovered = sum(not p["oracle_ok"] and c["oracle_ok"] for p,c in pairs)
        regressions = sum(p["oracle_ok"] and not c["oracle_ok"] for p,c in pairs)
        return bind_adapter_output({"survive": recovered > 0 and regressions == 0,
            "recovered": recovered, "regressions": regressions, "pairs": pairs,
            "paired_execution_hash": hash_payload(pairs)}, "screen_child", self.toolchain_fingerprint)

    def probe_learnability(self, policy, poison):
        # Frozen expanded teacher search: same model, multiple executable
        # evidence strategies. Repeating the identical deterministic primary
        # seeds would never establish learnability for a hard residual.
        rows = []
        strategies = [(mode, depth) for mode in ("raw", "hybrid") for depth in (1, 3, 6)]
        for index, (mode, depth) in enumerate(strategies):
            seed = self.seeds[index % len(self.seeds)]
            teacher = policy.with_updates(policy_id=policy.policy_id + f"_teacher_{index}",
                parent_policy_id=policy.policy_id, parent_policy_hash=policy.policy_hash,
                configuration={**policy.configuration, "evidence_mode":mode, "evidence_k":depth})
            rows.append(self.replay(teacher, poison, seed))
        successes = sum(r["oracle_ok"] for r in rows)
        return bind_adapter_output({"label": "reachable" if successes else "unlearnable_or_budget_exceeded",
            "challenged_policy_hash": policy.policy_hash, "teacher_mode": "same_model_expanded",
            "teacher_budget": {k:v*len(rows) for k,v in policy.budgets.items()},
            "attempts": len(rows), "successes": successes, "budget_exhausted": not bool(successes),
            "evidence": {"provider_calls": sum(r["resource_usage"]["provider_calls"] for r in rows),
                         "receipts": rows}}, "probe_learnability", self.toolchain_fingerprint)
