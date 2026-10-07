"""Offline eligibility only: reference answers never enter a live experiment."""
from pathlib import Path
import json
import sys
import time
ROOT = Path(__file__).resolve().parent / "source"
sys.path.insert(0, str(ROOT))
from competition.arena.evidence import read
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.adapters.policy_provider import PolicyCandidateProvider
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.providers.openai_compatible import OpenAICompatibleClientConfig, OpenAICompatibleJSONClient
from competition.arena.baseline import source_identity

out = ROOT.parent / "validation-demo32-reference"
current, calls, records = [], [], []
def transport(**request):
    calls.append(1)
    return {"content": json.dumps({"replacement_rtl": current[0], "edit": "Offline reference eligibility check only"}),
            "input_tokens": 1, "output_tokens": 1, "provider_request_id": f"eligibility-{len(calls)}"}
config = OpenAICompatibleClientConfig(provider_id="offline-eligibility", provider_version="1", endpoint_id="test",
    model_id="reference-eligibility-only", model_version="1", api_key_env="UNUSED", base_url_env="UNUSED",
    timeout_seconds=30, maximum_output_tokens=4096, temperature=0, require_seed=True)
client = OpenAICompatibleJSONClient(config, transport=transport, environ={})
provider = PolicyCandidateProvider(client, verifier_id=PublicManifestOracleVerifier.verifier_id,
    verifier_version=PublicManifestOracleVerifier.verifier_version)
service = ArenaEvaluationService(ROOT, out, provider=provider)
policy = service.repair._policy()
identity = source_identity(ROOT)
for name in ["demo32_supplied_assets", "demo32_regression", "demo32_heldout", "demo32_strider"]:
    for row in read(ROOT / "competition/manifests" / (name + ".json"))["rows"]:
        current[:] = [(ROOT / row["golden_rtl"]).read_text()]
        start = time.monotonic()
        receipt = service.evaluate_case_with_policy(policy, row, 1)
        record = {"case_id": row["case_id"], "oracle_ok": receipt["oracle_ok"], "status": receipt["status"],
            "artifact_id": receipt["artifact_id"], "seconds": round(time.monotonic()-start, 3)}
        records.append(record)
        print(json.dumps(record), flush=True)
        (out / "summary.json").write_text(json.dumps({"network_calls": 0, "source_hash": identity["source_hash"],
            "purpose": "Offline reference eligibility only; not model efficacy", "rows": records}, indent=2))
assert len(records) == 32 and all(r["oracle_ok"] for r in records)
