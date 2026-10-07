"""Bind searched evidence interpretation to actual model requests."""
from r3e.blue.portfolio.openai_provider import OpenAICompatibleCandidateProvider

class PolicyCandidateProvider(OpenAICompatibleCandidateProvider):
    def generate_candidate(self, **kwargs):
        policy = kwargs["policy"]
        mode = policy.configuration["evidence_mode"]
        depth = policy.configuration["evidence_k"]
        instructions = {
            "raw": "Prioritize the observed mismatch and the directly affected assignment.",
            "hybrid": "Combine the observed mismatch with RTL control dependencies and sequential dataflow; inspect upstream causes before proposing a local edit.",
        }
        if mode not in instructions or depth not in (1, 3, 6):
            raise ValueError("unsupported M3 evidence strategy")
        if policy.configuration["repair_loop"] != "one-shot":
            raise ValueError("M3 fixes one-shot repair and three candidates")
        kwargs["prompt_asset"] += ("\nRuntime strategy: " + instructions[mode]
            + f" Inspect up to {depth} dependency steps or clock transitions implicated by the failure."
            + " Return only the requested candidate and concise edit description.")
        return super().generate_candidate(**kwargs)
