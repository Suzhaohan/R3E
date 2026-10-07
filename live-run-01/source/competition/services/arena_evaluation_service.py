"""Fixed-denominator evaluation using Core portfolio and runner-owned EDA."""
from pathlib import Path
from types import SimpleNamespace
import uuid
from r3e.blue.portfolio.candidate_executor import CandidatePortfolioExecutor
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier, public_case_from_manifest
from r3e.blue.portfolio.audit import verify_blue_evaluation
from r3e.protocol.hashing import hash_payload, hash_file, atomic_write_json
from r3e.semantic_repair_bench.oracle_gate import judge
from competition.arena.isolation import verify_evaluation_manifest
from competition.arena.evidence import signed, read, freeze, verify_signed
from .repair_service import RepairService
from .policy_runtime_service import validate_repair_policy

class ArenaEvaluationService:
    def __init__(self, repo_root, output_root, *, provider=None, artifact_roots=()):
        self.root = Path(repo_root).resolve()
        self.output = Path(output_root).resolve()
        self.repair = RepairService(self.root, self.output)
        self.provider = provider
        self.artifact_roots = tuple(Path(p).resolve() for p in artifact_roots)

    def _case(self, row):
        if not row.get("generated_poison_sha256"):
            case = public_case_from_manifest(row, project_root=self.root)
            if row.get("manifest_file_hashes") and case["manifest_file_hashes"] != row["manifest_file_hashes"]:
                raise ValueError("case asset hash mismatch")
            return case
        buggy = Path(row["buggy_rtl"]).resolve()
        if not any(root in buggy.parents for root in self.artifact_roots):
            raise ValueError("generated poison escapes private artifact roots")
        if hash_file(buggy) != row["generated_poison_sha256"]:
            raise ValueError("generated poison changed")
        # Freeze public oracle/TB independently of the explicitly allowed generated RTL.
        case = public_case_from_manifest({**row, "buggy_rtl": row["golden_rtl"]}, project_root=self.root)
        case.update(buggy_rtl_path=str(buggy), buggy_rtl_source=buggy.read_text(), buggy_rtl_hash=hash_payload(buggy.read_text()))
        return case

    def evaluate_case_with_policy(self, policy, row, seed, *, provider=None, verifier=None):
        policy = validate_repair_policy(policy, self.repair.portfolio)
        if type(seed) is not int:
            raise ValueError("seed must be integer")
        case = self._case(row)
        work = self.output / ("case-" + uuid.uuid4().hex)
        work.mkdir(parents=True, exist_ok=False)
        provider = provider or self.provider
        if provider is None:
            provider, _ = self.repair._live_provider()
        verifier = verifier or PublicManifestOracleVerifier(project_root=self.root,
            workspace=work / "verifier", allowed_case_artifact_roots=self.artifact_roots,
            run_context_hash=hash_payload({"policy": policy.policy_hash, "case": case["case_id"], "seed": seed}),
            timeout_seconds=self.repair.config.timeout_seconds)
        outcome = judge(case, case["buggy_rtl_path"], work / "diagnosis", evidence_k=policy.configuration["evidence_k"])
        # Invalid/timed-out cases remain in the denominator. They are never success.
        base = {"policy_hash": policy.policy_hash, "seed": seed, "case_id": case["case_id"],
            "model_id": provider.toolchain_fingerprint["model_id"], "budget_hash": hash_payload(policy.budgets),
            "verifier_hash": verifier.verifier_hash, "provider_fingerprint": provider.toolchain_fingerprint,
            "source_kind": "live_model" if getattr(provider, "client", None) and getattr(provider.client, "_transport", None) is None else "injected_test",
            "case_asset_hash": hash_payload({"assets": case["manifest_file_hashes"], "buggy": case["buggy_rtl_hash"]}),
            "artifact_id": work.name}
        if outcome.ok or outcome.stage != "compare":
            receipt = signed({**base, "oracle_ok": False, "cost": 0.0,
                "status": "baseline_not_functional_mismatch", "baseline_stage": outcome.stage,
                "resource_usage": {"provider_calls": 0, "input_tokens": 0, "output_tokens": 0},
                "portfolio_execution_hash": ""}, "receipt_hash")
            atomic_write_json(work / "receipt.json", receipt)
            return receipt
        view = SimpleNamespace(case_id=case["case_id"], source=lambda kind: case["buggy_rtl_source"],
            evidence=lambda: {"case_hash": hash_payload(case["manifest_file_hashes"])})
        descriptor, _ = self.repair.diagnosis._runtime_descriptor(view, {
            "core_oracle": {"mismatch": outcome.mismatch, "structured": outcome.structured},
            "authority": "runtime_differential_oracle"})
        grounded = descriptor.grounded_descriptor
        executor = CandidatePortfolioExecutor(registry=self.repair.registry, portfolio=self.repair.portfolio,
            provider=provider, verifier=verifier, project_root=self.root, router=self.repair.router)
        evaluation = executor.execute(policy=policy, case=case, descriptor=grounded, run_seed=seed)
        verify_blue_evaluation(evaluation, policy=policy, registry=self.repair.registry,
            portfolio=self.repair.portfolio, provider=provider, expected_verifier_hash=verifier.verifier_hash,
            router=self.repair.router, descriptor=grounded)
        receipt = signed({**base, "oracle_ok": evaluation["oracle_ok"], "status": "evaluated",
            "cost": float(evaluation["resource_usage"]["input_tokens"] + evaluation["resource_usage"]["output_tokens"]),
            "resource_usage": evaluation["resource_usage"],
            "portfolio_execution_hash": evaluation["portfolio_execution_hash"]}, "receipt_hash")
        atomic_write_json(work / "evaluation.json", evaluation)
        atomic_write_json(work / "descriptor.json", grounded)
        atomic_write_json(work / "receipt.json", receipt)
        return receipt

    def evaluate_policy(self, policy, manifest, seeds, *, runtime=None):
        verify_evaluation_manifest(manifest, self.root)
        if not seeds or any(type(s) is not int for s in seeds) or len(set(seeds)) != len(seeds):
            raise ValueError("unique integer evaluation seeds required")
        snapshot = hash_payload(policy.to_dict())
        registry_hash = hash_file(runtime.registry_path) if runtime else None
        provider = self.provider
        if provider is None:
            provider, _ = self.repair._live_provider()
        # Bind resumable receipts to the complete evaluation, not just case names.
        binding = hash_payload({"manifest": manifest["manifest_hash"], "policy": snapshot,
                                "seeds": list(seeds), "provider": provider.toolchain_fingerprint})
        freeze(self.output / "evaluation_binding.json", {"binding": binding})
        results = []
        def unchanged():
            if hash_payload(policy.to_dict()) != snapshot or (runtime and
                (hash_file(runtime.registry_path) != registry_hash or runtime.active_policy().policy_hash != policy.policy_hash)):
                raise ValueError("policy/registry changed during final evaluation")
        for row in manifest["rows"]:
            for seed in seeds:
                unchanged()
                index = self.output / "completed" / (hash_payload({"binding": binding,
                    "case": row["case_id"], "seed": seed}).split(":")[-1] + ".json")
                if index.exists():
                    receipt = verify_signed(read(index), "receipt_hash")
                    work = (self.output / receipt["artifact_id"]).resolve()
                    if work.parent != self.output or read(work / "receipt.json") != receipt:
                        raise ValueError("cached receipt artifact mismatch")
                    case = self._case(row)
                    if receipt["case_id"] != row["case_id"] or receipt["seed"] != seed or receipt["policy_hash"] != policy.policy_hash or receipt["provider_fingerprint"] != provider.toolchain_fingerprint or receipt["case_asset_hash"] != hash_payload({"assets": case["manifest_file_hashes"], "buggy": case["buggy_rtl_hash"]}):
                        raise ValueError("cached evaluation binding mismatch")
                    if receipt["status"] == "evaluated":
                        raw = read(work / "evaluation.json")
                        verify_blue_evaluation(raw, policy=policy, registry=self.repair.registry,
                            portfolio=self.repair.portfolio, provider=provider,
                            expected_verifier_hash=receipt["verifier_hash"], router=self.repair.router,
                            descriptor=read(work / "descriptor.json"))
                        if raw["portfolio_execution_hash"] != receipt["portfolio_execution_hash"] or raw["oracle_ok"] != receipt["oracle_ok"]:
                            raise ValueError("cached execution differs from receipt")
                    elif receipt["oracle_ok"] or receipt["resource_usage"]["provider_calls"] != 0:
                        raise ValueError("invalid cached unavailable case")
                else:
                    receipt = self.evaluate_case_with_policy(policy, row, seed, provider=provider)
                    freeze(index, receipt)
                results.append(receipt)
        verify_evaluation_manifest(manifest, self.root)
        unchanged()
        return signed({"schema_version": "r3e-aic-arena-evaluation-v1", "dataset": manifest["metadata"]["dataset"],
            "manifest_hash": manifest["manifest_hash"], "policy_hash": policy.policy_hash,
            "case_ids": [r["case_id"] for r in manifest["rows"]], "seeds": list(seeds), "cases": results,
            "denominator": len(results), "repaired": sum(r["oracle_ok"] for r in results),
            "repair_rate": sum(r["oracle_ok"] for r in results) / len(results)})
