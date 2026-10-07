"""Execute frozen public cases with the real Core portfolio and oracle."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import uuid
from r3e.blue.portfolio.candidate_executor import CandidatePortfolioExecutor
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier, public_case_from_manifest
from r3e.blue.portfolio.audit import verify_blue_evaluation
from r3e.protocol.hashing import hash_payload, atomic_write_json
from r3e.semantic_repair_bench.oracle_gate import judge
from competition.arena.isolation import verify_evaluation_manifest
from .repair_service import RepairService
from .policy_runtime_service import validate_repair_policy


class ArenaEvaluationService:
    def __init__(self, repo_root, output_root, *, provider=None):
        self.root = Path(repo_root).resolve()
        self.output = Path(output_root).resolve()
        self.repair = RepairService(self.root, self.output)
        self.provider = provider

    def evaluate_case_with_policy(self, policy, row, seed, *, provider=None, verifier=None):
        policy = validate_repair_policy(policy, self.repair.portfolio)
        if type(seed) is not int:
            raise ValueError("seed must be integer")
        case = public_case_from_manifest(row, project_root=self.root)
        if row.get("manifest_file_hashes") and case["manifest_file_hashes"] != row["manifest_file_hashes"]:
            raise ValueError("case asset hash mismatch")
        work = self.output / ("case-" + uuid.uuid4().hex)
        work.mkdir(parents=True, exist_ok=False)
        outcome = judge(case, case["buggy_rtl_path"], work / "diagnosis", evidence_k=3)
        if outcome.ok or outcome.stage != "compare":
            raise ValueError("baseline must be a compiling functional mismatch")
        # Reuse Competition runtime diagnosis, with no annotations or golden source.
        view = SimpleNamespace(case_id=case["case_id"],
            source=lambda kind: case["buggy_rtl_source"],
            evidence=lambda: {"case_hash": hash_payload(case["manifest_file_hashes"])})
        descriptor, _ = self.repair.diagnosis._runtime_descriptor(view, {
            "core_oracle": {"mismatch": outcome.mismatch, "structured": outcome.structured},
            "authority": "runtime_differential_oracle"})
        grounded = descriptor.grounded_descriptor
        provider = provider or self.provider
        if provider is None:
            provider, _ = self.repair._live_provider()
        verifier = verifier or PublicManifestOracleVerifier(project_root=self.root,
            workspace=work / "verifier", run_context_hash=hash_payload({
                "policy": policy.policy_hash, "case": case["case_id"], "seed": seed}),
            timeout_seconds=self.repair.config.timeout_seconds)
        executor = CandidatePortfolioExecutor(registry=self.repair.registry,
            portfolio=self.repair.portfolio, provider=provider, verifier=verifier,
            project_root=self.root, router=self.repair.router)
        evaluation = executor.execute(policy=policy, case=case, descriptor=grounded, run_seed=seed)
        verify_blue_evaluation(evaluation, policy=policy, registry=self.repair.registry,
            portfolio=self.repair.portfolio, provider=provider,
            expected_verifier_hash=verifier.verifier_hash,
            router=self.repair.router, descriptor=grounded)
        receipt = {"policy_hash": policy.policy_hash, "seed": seed,
            "case_id": case["case_id"], "oracle_ok": evaluation["oracle_ok"],
            "cost": float(evaluation["resource_usage"]["input_tokens"] + evaluation["resource_usage"]["output_tokens"]),
            "model_id": provider.toolchain_fingerprint["model_id"],
            "budget_hash": hash_payload(policy.budgets), "verifier_hash": verifier.verifier_hash,
            "provider_fingerprint": provider.toolchain_fingerprint,
            "resource_usage": evaluation["resource_usage"],
            "portfolio_execution_hash": evaluation["portfolio_execution_hash"]}
        receipt["receipt_hash"] = hash_payload(receipt)
        atomic_write_json(work / "evaluation.json", evaluation)
        atomic_write_json(work / "descriptor.json", grounded)
        atomic_write_json(work / "receipt.json", receipt)
        return receipt

    def evaluate_policy(self, policy, manifest, seeds, *, runtime=None):
        verify_evaluation_manifest(manifest, self.root)
        if not seeds or any(type(s) is not int for s in seeds) or len(set(seeds)) != len(seeds):
            raise ValueError("unique integer evaluation seeds required")
        snapshot = deepcopy(policy.to_dict())
        results = []
        for row in manifest["rows"]:
            for seed in seeds:
                if runtime and runtime.active_policy().policy_hash != policy.policy_hash:
                    raise ValueError("policy changed during final evaluation")
                results.append(self.evaluate_case_with_policy(policy, row, seed))
        verify_evaluation_manifest(manifest, self.root)
        if policy.to_dict() != snapshot or (runtime and runtime.active_policy().policy_hash != policy.policy_hash):
            raise ValueError("policy changed during final evaluation")
        payload = {"schema_version": "r3e-aic-arena-evaluation-v1",
            "dataset": manifest["metadata"]["dataset"], "manifest_hash": manifest["manifest_hash"],
            "policy_hash": policy.policy_hash, "seeds": list(seeds), "cases": results,
            "repair_rate": sum(r["oracle_ok"] for r in results) / len(results)}
        payload["result_hash"] = hash_payload(payload)
        return payload
