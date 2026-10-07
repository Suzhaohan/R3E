"""Local facade: all state transitions are delegated to EvolutionRoundRunner."""
from copy import deepcopy
from pathlib import Path
import re
from r3e.arena.runner import EvolutionRoundRunner
from competition.arena.isolation import require_evolution_manifest


class AdversarialArenaService:
    def __init__(self, *, arena_config, project_root, runtime, adapter, provider, verifier):
        if arena_config.arm != "adversarial":
            raise ValueError("only Machine B can run evolution")
        self.config = arena_config
        self.root = Path(project_root).resolve()
        self.runtime = runtime
        self.adapter, self.provider, self.verifier = adapter, provider, verifier

    def run_round(self, round_id, round_config, *, evolution_manifest, regression_manifest):
        if not re.fullmatch(r"R[0-9]{3,6}", round_id):
            raise ValueError("invalid round id")
        require_evolution_manifest(evolution_manifest)
        require_evolution_manifest(regression_manifest)
        config = deepcopy(round_config)
        if config.get("validity_authority") != "grounded_runtime_authority_v1" or config.get("blue_evaluation_authority") != "candidate_portfolio_v1":
            raise ValueError("real Grounded/portfolio authorities required")
        registry = (self.root / config["policy_registry"]).resolve()
        if registry != self.runtime.registry_path.resolve():
            raise ValueError("round registry differs from active runtime")
        # Keep every mutable Core path within this arm's private runtime.
        state_root = self.runtime.registry_path.resolve().parent
        for field in ("rounds_root", "decision_ledger", "red_archive"):
            path = (self.root / config[field]).resolve()
            if state_root not in path.parents:
                raise ValueError(f"{field} escapes private state root")
        self.runtime.active_policy()
        return EvolutionRoundRunner(config, round_id=round_id, adapter=self.adapter,
            project_root=self.root, candidate_provider=self.provider,
            candidate_verifier=self.verifier).run()

    resume_round = run_round

    def active_policy(self):
        return self.runtime.active_policy()
