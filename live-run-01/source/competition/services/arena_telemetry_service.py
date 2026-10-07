"""Read-only observer: reconstruct frozen comparison, expose no mutable state."""
from pathlib import Path
from competition.arena.evidence import read
from competition.services.arena_comparison_service import verify_comparison

class ArenaTelemetryService:
    def __init__(self, root, comparison_path=None, *, demo_path=None, state_path=None):
        if comparison_path and demo_path:
            raise ValueError("choose formal comparison or offline demo, not both")
        self.demo_path = Path(demo_path) if demo_path else None
        self.state_path = Path(state_path) if state_path and not comparison_path and not demo_path else None
        self.path=Path(comparison_path) if comparison_path else Path(root)/"competition/results/frozen/comparison/comparison.json"

    def snapshot(self):
        if self.state_path is not None:
            from competition.arena.baseline import load_runtime
            from competition.arena.evidence import verify_signed
            from competition.arena.presentation import round_view
            try:
                runtime, machine, baseline = load_runtime(self.state_path)
                plan = verify_signed(read(self.state_path / "live_plan.json"))
                if plan["baseline_hash"] != baseline["baseline_hash"] or plan["arm"] != machine["arm"]:
                    raise ValueError("live plan mismatch")
                rows = [round_view(p, include_local_diffs=True) for p in sorted((self.state_path / "rounds").glob("R*"))
                        if (p / "round_summary.json").exists()]
                return {"available": True, "mode": "live_local_progress",
                    "message": "本机真实实验进度：仅展示已完成且通过审计的回合。最终 A/B 效果待两组冻结比较。刷新页面更新。",
                    "model": baseline["provider"]["model_id"], "baseline_hash": baseline["baseline_hash"],
                    "candidate_budget": 3, "memory_fixed": True, "planned_rounds": len(plan["round_ids"]),
                    "machines": {machine["arm"]: {"policy_hash": runtime.active_policy().policy_hash,
                        "promotion_count": sum(r["promoted"] for r in rows), "red_enabled": machine["arm"] == "adversarial"}},
                    "rounds": rows, "metrics": {}, "case_results": {}}
            except (ValueError, KeyError, TypeError, OSError, RuntimeError):
                return {"available": False, "message": "本机真实实验尚未初始化，或运行证据未通过核验。", "rounds": [], "metrics": {}}
        if self.demo_path is not None:
            from competition.arena.demo import demo_snapshot
            try:
                return demo_snapshot(self.demo_path)
            except (ValueError, KeyError, TypeError, OSError, RuntimeError):
                return {"available": False, "mode": "offline_protocol_demo", "message": "离线演示证据缺失或核验失败；请保留完整运行目录。", "rounds": [], "metrics": {}}
        if not self.path.is_file():
            return {"available":False,"message":"尚无通过核验的双机冻结证据；未展示能力提升。","rounds":[],"metrics":{}}
        try:
            data=verify_comparison(read(self.path))
        except (ValueError,KeyError,TypeError,OSError,RuntimeError) as exc:
            return {"available":False,"message":"双机证据校验失败。","rounds":[],"metrics":{}}
        baseline=data["static"]["baseline"]
        from competition.arena.presentation import paired_case_views
        # Explicit allowlist: no prompt, candidate RTL, memory bank or trajectories.
        return {"available":True,"mode":data["mode"],"experiment_id":data["experiment_id"],
            "baseline_hash":data["baseline_hash"],"comparison_hash":data["comparison_hash"],
            "model":baseline["provider"]["model_id"],"candidate_budget":3,"memory_fixed":True,
            "machines":{arm:{"policy_hash":data[arm]["final_policy_hash"],"promotion_count":data[arm]["promotion_count"],
                "red_enabled":arm=="adversarial"} for arm in ("static","adversarial")},
            "rounds":data["adversarial"].get("round_views", [{k:r[k] for k in ("round_id","parent_policy_id","active_policy_id","parent_policy_hash","active_policy_hash","promoted","audit_record_hash")} for r in data["adversarial"]["rounds"]]),
            "case_results": {name: paired_case_views(e, data["adversarial"]["evaluations"][name]) for name, e in data["static"]["evaluations"].items()},
            "acceptance": data.get("acceptance", {}),
            "metrics":data["metrics"]}
