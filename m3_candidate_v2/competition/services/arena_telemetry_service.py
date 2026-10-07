"""Read-only observer: reconstruct frozen comparison, expose no mutable state."""
from pathlib import Path
from competition.arena.evidence import read
from competition.services.arena_comparison_service import verify_comparison

class ArenaTelemetryService:
    def __init__(self, root, comparison_path=None):
        self.path=Path(comparison_path) if comparison_path else Path(root)/"competition/results/frozen/comparison/comparison.json"

    def snapshot(self):
        if not self.path.is_file():
            return {"available":False,"message":"尚无通过核验的双机冻结证据；未展示能力提升。","rounds":[],"metrics":{}}
        try:
            data=verify_comparison(read(self.path))
        except (ValueError,KeyError,TypeError,OSError) as exc:
            return {"available":False,"message":"双机证据校验失败。","rounds":[],"metrics":{}}
        baseline=data["static"]["baseline"]
        # Explicit allowlist: no prompt, candidate RTL, memory bank or trajectories.
        return {"available":True,"mode":data["mode"],"experiment_id":data["experiment_id"],
            "baseline_hash":data["baseline_hash"],"comparison_hash":data["comparison_hash"],
            "model":baseline["provider"]["model_id"],"candidate_budget":3,"memory_fixed":True,
            "machines":{arm:{"policy_hash":data[arm]["final_policy_hash"],"promotion_count":data[arm]["promotion_count"],
                "red_enabled":arm=="adversarial"} for arm in ("static","adversarial")},
            "rounds":[{k:r[k] for k in ("round_id","parent_policy_id","active_policy_id","parent_policy_hash","active_policy_hash","promoted","audit_record_hash")} for r in data["adversarial"]["rounds"]],
            "metrics":data["metrics"]}
