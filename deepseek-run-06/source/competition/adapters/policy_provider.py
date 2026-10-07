"""Bind searched evidence interpretation to actual model requests."""
from r3e.blue.portfolio.openai_provider import OpenAICompatibleCandidateProvider
from r3e.knowledge import KnowledgeInjectingClient

class PolicyCandidateProvider(OpenAICompatibleCandidateProvider):
    requires_runtime_evidence = True
    requires_memory_context = True
    def __init__(self, *args, memory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.memory = memory
        self.memory_hash = memory.memory_hash if memory else ""

    def generate_candidate(self, **kwargs):
        previous = kwargs.pop("memory_context", {}).get("previous_verified", [])
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
            + f" Use the supplied observations (up to {depth} actual/expected mismatches)."
            + " Return only the requested candidate and concise edit description.")
        # The runner supplies actual preceding verdicts. A slot number alone
        # cannot establish that Blue has already tried and failed on this case.
        if self.memory and previous and not any(previous):
            bundle = self.memory.bundle(kwargs["current_case_artifact"],
                                        evidence=kwargs["current_case_evidence"])
            if bundle is not None and not bundle.is_empty:
                original = self.client
                wrapper = KnowledgeInjectingClient(original)
                try:
                    self.client = wrapper
                    with wrapper.active(bundle):
                        return super().generate_candidate(**kwargs)
                finally:
                    self.client = original
        return super().generate_candidate(**kwargs)
