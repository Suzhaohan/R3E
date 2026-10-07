"""Audited recovery overlay for the unchanged frozen experiment.

Cache identity includes stage and invocation ordinal: deliberately repeated
samples are not collapsed. Retry happens outside the experiment's timers.
"""
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
import time
from urllib.error import URLError
import ssl

from competition.arena.budget import BudgetedClient
from competition.arena.evidence import read, signed, freeze, verify_signed
from competition.services.arena_evaluation_service import ArenaEvaluationService
from r3e.arena.real_grounded_adapter import RealGroundedArenaAdapter
from r3e.blue.portfolio.audit import verify_blue_evaluation
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.protocol.hashing import hash_file, hash_payload, utc_now


def connection_failure(exc):
    """Retry connect-phase failures only, never read timeouts or HTTP errors."""
    seen = set()
    chain = []
    while isinstance(exc, BaseException) and id(exc) not in seen:
        seen.add(id(exc))
        chain.append(exc)
        exc = exc.__cause__ or exc.__context__ or getattr(exc, "reason", None)
    if any(getattr(e, "status_code", None) is not None or
           type(e).__name__ in {"HTTPError", "ReadTimeout", "ReadError", "WriteError", "WriteTimeout"}
           for e in chain):
        return False
    return (any(type(e).__name__ in {"ConnectError", "ConnectTimeout", "ConnectionRefusedError", "gaierror"}
                for e in chain)
            or any(isinstance(e, URLError) and isinstance(e.reason, ssl.SSLEOFError)
                   for e in chain))


class Recovery:
    def __init__(self, state, config, *, endpoint="", report=print):
        self.state = Path(state).resolve()
        self.config = config
        self.endpoint_hash = hash_payload(endpoint)
        self.root = self.state / "recovery"
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.report = report
        self.counters = defaultdict(int)
        self.case_context = None
        self.depth = 0
        self.last_request = None
        self.stats = defaultdict(int)
        self.prepared = set()
        self.replay_only = False

    def reset(self):
        self.counters.clear()
        self.case_context = None
        self.last_request = None

    def event(self, kind, **fields):
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps({"time": utc_now(), "event": kind, **fields}, ensure_ascii=False) + "\n")

    def operation(self, client):
        paths = []
        while isinstance(client, BudgetedClient):
            paths.append(client.path.resolve())
            client = client.client
        if not paths or any(p.parent != self.state / "budgets" for p in paths):
            raise ValueError("recovery client is outside this arm's budget directory")
        names = [p.stem for p in paths if p.stem != "total"]
        if len(names) != 1:
            raise ValueError("recovery requires one operation budget")
        return names[0]

    def scope(self, client):
        operation = self.operation(client)
        path = self.state / "rounds" / operation / "round_state.json"
        if path.exists():
            checkpoint = read(path)["checkpoints"][-1]
            stage = checkpoint["stage"]
            cutoff = datetime.fromisoformat(checkpoint["completed_at"]).timestamp()
        else:
            stage, cutoff = ("INITIAL_EVALUATION" if operation.startswith("T0-") else "FINAL_EVALUATION"), 0
        return operation, stage, cutoff

    def directory(self, scope):
        operation, stage = scope[:2]
        # Operation names originate in the frozen CLI, not model output.
        if not all(part.replace("-", "").replace("_", "").isalnum() for part in (operation, stage)):
            raise ValueError("unsafe recovery scope")
        return self.root / operation / stage

    def next_index(self, scope, lane):
        key = (*scope[:2], lane)
        index = self.counters[key]
        self.counters[key] += 1
        return index

    @staticmethod
    def case_binding(receipt):
        return {k: receipt[k] for k in (
            "policy_hash", "seed", "case_id", "case_asset_hash", "provider_fingerprint", "verifier_hash")}

    def prepare(self, service, scope):
        """Import complete receipts only from the currently interrupted stage."""
        directory = self.directory(scope)
        if directory in self.prepared:
            return
        marker = directory / "import.json"
        if marker.exists():
            verify_signed(read(marker))
            self.prepared.add(directory)
            return
        output = service.output.resolve()
        arm = "static" if self.state.name == "arm-a" else "adversarial"
        allowed = {self.state / "replays", self.state / "eval" / scope[0],
                   self.state.parent / "baseline-evaluations" / arm / scope[0].removeprefix("T0-")}
        if output not in allowed:
            raise ValueError("recovery evaluation output differs from operation")
        # Final evaluations already have per-case completion indexes. Do not
        # shift ordinals by importing the completed pairs that core skips.
        # Current Core already validates completed T0/T1 pairs and per-round
        # replay caches. Importing ordinal receipts would shift slots when
        # Core skips those completed pairs on restart.
        paths = []
        imported = []
        for index, path in enumerate(paths):
            receipt = verify_signed(read(path), "receipt_hash")
            if receipt["provider_fingerprint"] != service.provider.toolchain_fingerprint:
                raise ValueError("imported provider fingerprint differs")
            freeze(directory / "cases" / f"{index:06d}.json", signed({
                "binding": self.case_binding(receipt), "receipt": receipt,
                "origin": "preexisting_completed_case", "source_hash": hash_file(path),
            }))
            imported.append({"artifact_id": receipt["artifact_id"], "receipt_hash": receipt["receipt_hash"]})
        freeze(marker, signed({"operation": scope[0], "last_completed_stage": scope[1],
                              "cutoff": scope[2], "imported": imported}))
        self.prepared.add(directory)
        if imported:
            self.report(f"恢复缓存：{scope[0]} 导入 {len(imported)} 组已完成回放；复用前逐项核验。", flush=True)

    def validate_case(self, service, policy, row, seed, provider, verifier, record):
        verify_signed(record)
        receipt = verify_signed(record["receipt"], "receipt_hash")
        case = service._case(row)
        expected = {"policy_hash": policy.policy_hash, "seed": seed, "case_id": case["case_id"],
                    "case_asset_hash": hash_payload({"assets": case["manifest_file_hashes"], "buggy": case["buggy_rtl_hash"]}),
                    "provider_fingerprint": provider.toolchain_fingerprint,
                    "verifier_hash": verifier.verifier_hash if verifier else PublicManifestOracleVerifier.verifier_hash}
        if record["binding"] != expected or self.case_binding(receipt) != expected:
            raise ValueError("recovery case sequence/binding changed; refusing to resample")
        work = (service.output / receipt["artifact_id"]).resolve()
        if work.parent != service.output or read(work / "receipt.json") != receipt:
            raise ValueError("recovery raw case receipt changed")
        if receipt["status"] == "evaluated":
            raw = read(work / "evaluation.json")
            verify_blue_evaluation(raw, policy=policy, registry=service.repair.registry,
                portfolio=service.repair.portfolio, provider=provider,
                expected_verifier_hash=receipt["verifier_hash"], router=service.repair.router,
                descriptor=read(work / "descriptor.json"))
            if raw["portfolio_execution_hash"] != receipt["portfolio_execution_hash"] or raw["oracle_ok"] != receipt["oracle_ok"]:
                raise ValueError("recovery evaluation differs from receipt")
        elif receipt["oracle_ok"] or receipt["resource_usage"]["provider_calls"] != 0:
            raise ValueError("invalid unavailable recovery case")
        return receipt

    def evaluate(self, original, service, policy, row, seed, *, provider=None, verifier=None):
        provider = provider or service.provider
        scope = self.scope(provider.client)
        self.prepare(service, scope)
        # Match current Core's one result per policy/case/repetition contract.
        # Include the complete row: different poison versions stay distinct.
        index = hash_payload({"policy": policy.policy_hash, "case": row, "seed": seed}).split(":")[-1]
        target = self.directory(scope) / "cases" / f"{index}.json"
        if target.exists():
            result = self.validate_case(service, policy, row, seed, provider, verifier, read(target))
            self.stats["reused_cases"] += 1
            self.event("case_reused", operation=scope[0], stage=scope[1], index=index, receipt_hash=result["receipt_hash"])
            return result
        previous = self.case_context
        self.case_context = (index, 0)
        try:
            result = original(service, policy, row, seed, provider=provider, verifier=verifier)
            freeze(target, signed({"binding": self.case_binding(result), "receipt": result,
                                  "origin": "recovery_completed_case"}))
            self.stats["new_completed_cases"] += 1
            self.event("case_saved", operation=scope[0], stage=scope[1], index=index,
                       receipt_hash=result["receipt_hash"])
            return result
        finally:
            self.case_context = previous

    def complete(self, original, client, **kwargs):
        if self.depth:
            return original(client, **kwargs)
        scope = self.scope(client)
        if self.case_context is None:
            lane, index = "requests", self.next_index(scope, "requests")
        else:
            case_index, index = self.case_context
            self.case_context = (case_index, index + 1)
            lane = f"case-{case_index}-requests"
        target = self.directory(scope) / lane / f"{index:06d}.json"
        binding = hash_payload({"client_config_hash": client.config.config_hash,
                                "endpoint_hash": self.endpoint_hash, "request": kwargs})
        self.last_request = str(target.relative_to(self.root))
        # Budget changes must fail even on a cache hit.
        budget = client
        while isinstance(budget, BudgetedClient):
            if budget.path.exists():
                saved = read(budget.path)
                if (saved["max_calls"], saved["max_tokens"]) != (budget.max_calls, budget.max_tokens):
                    raise ValueError("resume budget differs from frozen reservation")
            budget = budget.client
        if target.exists():
            cached = verify_signed(read(target))
            if cached["binding"] != binding:
                raise ValueError("recovery request sequence/binding changed; refusing to resample")
            self.stats["reused_responses"] += 1
            self.event("response_reused", request=self.last_request)
            return cached["response"]
        if self.replay_only:
            raise ValueError("saved Red generation requires its original cached responses")
        self.depth += 1
        try:
            response = original(client, **kwargs)
        finally:
            self.depth -= 1
        # Persist before any downstream parser, EDA, or portfolio processing.
        record = freeze(target, signed({"binding": binding, "response": response}))
        self.stats["new_responses"] += 1
        self.event("response_saved", request=self.last_request, record_hash=record["result_hash"])
        return response

    @staticmethod
    def validate_red_record(record):
        """Validate a complete generation before its artifact can be rewritten."""
        row = deepcopy(record)
        digest = row.pop("generated_poison_sha256")
        verify_signed(row)
        choice = verify_signed(row["grounded_choice_receipt"], "choice_hash")
        elapsed = choice["wall_time_ms"]
        if (type(elapsed) is not int or elapsed < 0
                or row["grounded_generation_usage"]["wall_time_ms"] != elapsed):
            raise ValueError("saved Red generation has inconsistent timing")
        if hash_file(row["buggy_rtl"]) != digest:
            raise ValueError("saved Red poison artifact changed")
        return row

    def generate_red(self, original, adapter, parent, config, context):
        """Replay exact responses, then retain the original generation receipt.

        Replay must still consume its request slots and run Core's proposal
        validation. Only the replay timer and its two derived hashes may differ;
        all other fields must match the saved generation byte for byte.
        """
        scope = self.scope(adapter.client)
        poison_id = f"{adapter._round_id}:{adapter._cases[0]['case_id']}:grd"
        key = hash_payload(poison_id).split(":")[-1]
        target = self.directory(scope) / "red" / f"{key}.json"
        binding = hash_payload({"policy": parent.policy_hash, "config": config,
                                "context": context, "poison_id": poison_id})
        saved = None
        if target.exists():
            cached = verify_signed(read(target))
            if cached["binding"] != binding:
                raise ValueError("recovery Red generation binding changed")
            saved = cached["row"]
        index = self.state / "generated_cases.json"
        if index.exists():
            indexed = verify_signed(read(index))["cases"].get(poison_id)
            if indexed is not None:
                if saved is not None and saved != indexed:
                    raise ValueError("recovery Red generation differs from index")
                saved = indexed
        prior = self.validate_red_record(saved) if saved is not None else None
        previous = self.replay_only
        self.replay_only = previous or prior is not None
        try:
            rows = list(original(adapter, parent, config, context))
        finally:
            self.replay_only = previous
        if len(rows) != 1 or rows[0]["poison_id"] != poison_id:
            raise ValueError("unexpected single-target Red generation identity")
        row = rows[0]
        verify_signed(row)
        verify_signed(row["grounded_choice_receipt"], "choice_hash")
        if prior is not None:
            # Restore only observed generation time, never identity/content.
            restored = deepcopy(row)
            elapsed = prior["grounded_choice_receipt"]["wall_time_ms"]
            choice = restored["grounded_choice_receipt"]
            choice["wall_time_ms"] = elapsed
            choice["choice_hash"] = hash_payload({k: v for k, v in choice.items() if k != "choice_hash"})
            restored["grounded_generation_usage"]["wall_time_ms"] = elapsed
            restored["result_hash"] = hash_payload({k: v for k, v in restored.items() if k != "result_hash"})
            if restored != prior or hash_file(row["buggy_rtl"]) != saved["generated_poison_sha256"]:
                raise ValueError("recovery Red generation content/identity changed")
            row = prior
            self.stats["reused_red_generations"] += 1
            self.event("red_generation_reused", operation=scope[0], poison_id=poison_id,
                       result_hash=row["result_hash"])
        record = {**row, "generated_poison_sha256": hash_file(row["buggy_rtl"])}
        self.validate_red_record(record)
        freeze(target, signed({"binding": binding, "row": record}))
        return [row]

    @contextmanager
    def installed(self):
        old_complete = BudgetedClient.complete_json
        old_evaluate = ArenaEvaluationService.evaluate_case_with_policy
        old_generate = RealGroundedArenaAdapter.generate_red
        recovery = self
        def complete(client, **kwargs):
            return recovery.complete(old_complete, client, **kwargs)
        def evaluate(service, policy, row, seed, **kwargs):
            return recovery.evaluate(old_evaluate, service, policy, row, seed, **kwargs)
        def generate(adapter, parent, config, context):
            return recovery.generate_red(old_generate, adapter, parent, config, context)
        BudgetedClient.complete_json = complete
        ArenaEvaluationService.evaluate_case_with_policy = evaluate
        RealGroundedArenaAdapter.generate_red = generate
        try:
            yield
        finally:
            BudgetedClient.complete_json = old_complete
            ArenaEvaluationService.evaluate_case_with_policy = old_evaluate
            RealGroundedArenaAdapter.generate_red = old_generate

    def run(self, operation, *, sleep=time.sleep, delays=(2, 4, 8, 16)):
        failures = defaultdict(int)
        while True:
            self.reset()
            try:
                with self.installed():
                    return operation()
            except Exception as exc:
                if not connection_failure(exc):
                    raise
                key = self.last_request or "before-request"
                attempt = failures[key]
                failures[key] += 1
                self.event("connection_failure", request=key, attempt=attempt + 1,
                           error_type=type(exc).__name__)
                if attempt >= len(delays):
                    raise RuntimeError("连接连续失败，已保留请求缓存；网络恢复后运行同一恢复命令续跑。") from exc
                delay = delays[attempt]
                self.report(f"连接中断：已保存成功响应，{delay} 秒后从检查点恢复（重试 {attempt + 1}/{len(delays)}）。", flush=True)
                sleep(delay)
