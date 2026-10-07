"""Read Core policy authority without owning promotion decisions."""
from pathlib import Path
from r3e.policy.schema import PolicyState
from r3e.policy.registry_v2 import get_active_policy, load_registry
from r3e.protocol.hashing import hash_payload
from r3e.blue.portfolio.schema import build_candidate_portfolio_binding


def validate_repair_policy(policy, portfolio):
    policy = PolicyState.from_dict(policy.to_dict())
    if policy.configuration["n_candidates"] != 3 or policy.budgets["max_llm_calls_per_case"] != 3:
        raise ValueError("M3 requires exactly three candidates and model calls")
    if policy.configuration["candidate_selection"] != "verifier_guided":
        raise ValueError("M3 requires verifier-guided selection")
    if policy.configuration["patch_scope"] != "local_block":
        raise ValueError("M3 requires local_block scope")
    if policy.candidate_portfolio_binding != build_candidate_portfolio_binding(portfolio):
        raise ValueError("policy requires a different frozen portfolio; load its bound assets")
    if policy.memory_binding:
        raise ValueError("M3-A does not activate memory")
    return policy


class PolicyRuntimeService:
    def __init__(self, registry_path, *, arm, initial_policy_hash):
        if arm not in {"static", "adversarial"} or not initial_policy_hash:
            raise ValueError("arm and initial policy binding required")
        self.registry_path = Path(registry_path)
        self.arm = arm
        self.initial_policy_hash = initial_policy_hash

    def active_policy(self):
        registry = load_registry(self.registry_path)
        policy = get_active_policy(registry)
        if self.arm == "static":
            if policy.policy_hash != self.initial_policy_hash or len(registry["policies"]) != 1:
                raise ValueError("static policy registry changed")
        return policy

    def fixed_policy(self):
        policy = self.active_policy()
        if policy.policy_hash != self.initial_policy_hash:
            raise ValueError("fixed policy differs from baseline")
        return policy

    @staticmethod
    def policy_snapshot(policy):
        return {"policy_id": policy.policy_id, "policy_hash": policy.policy_hash,
                "budget_hash": hash_payload(policy.budgets),
                "portfolio_binding": policy.candidate_portfolio_binding}
