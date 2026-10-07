"""Runner-owned, readable differential evidence shared by every repair stage.

Only observed outputs cross the model boundary. Reference RTL and Red edits
remain verifier-owned. The sealed context permits offline prompt reconstruction.
"""
from copy import deepcopy
from pathlib import Path
import re
import tempfile

from r3e.memory.schema import FailureDescriptor
from r3e.protocol.hashing import hash_file, hash_payload
from r3e.semantic_repair_bench.oracle_gate import judge, _compare


def _bucket(cycle):
    return ("cycle_0" if cycle == 0 else "cycle_1" if cycle == 1 else
            "cycle_2_3" if cycle <= 3 else "cycle_4_7" if cycle <= 7 else "cycle_8_plus")


def observable_descriptor(source, structured, raw, binding):
    """A first failing vector is not a temporal offset; procedural is not sequential."""
    match = re.search(r"首个发散\s*@cycle(\d+).*?信号\s*`([^`]+)`", structured)
    cycle, signal = (int(match[1]), match[2]) if match else (0, "unknown")
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.DOTALL)
    clocked = bool(re.search(r"\balways\s*@\s*\([^)]*\b(?:posedge|negedge)\b", code))
    nonblocking = bool(re.search(rf"\b{re.escape(signal)}\b\s*<=", code))
    sequential = clocked or nonblocking
    # Only the observed trajectory may establish a lag; its index cannot.
    lag = sequential and "实得滞后 golden 一个周期" in structured
    features = {
        "oracle_stage": "runtime_differential_oracle",
        "sequential_context": sequential,
        "temporal_relation": "candidate_lags_golden" if lag else "same_cycle",
        "cycle_offset_bucket": 1 if lag else 0,
        "affected_roles": ["observable_output"],
        "assignment_type": "sequential" if clocked else "nonblocking" if nonblocking else "combinational",
        "cone_depth_bucket": "depth_1" if signal != "unknown" else "depth_4_plus",
        "mismatch_pattern": "one_cycle_lag" if lag else "value_mismatch",
        "first_divergence_bucket": _bucket(cycle),
        "first_divergence_signal": signal,
        "observable_artifact_hashes": {"runtime_observations": binding},
    }
    return FailureDescriptor.create(features).to_dict()


def build_runtime_evidence(case, *, project_root, source_descriptor):
    root = Path(project_root).resolve()
    resolved = deepcopy(case)
    for key in ("golden_rtl", "buggy_rtl_path"):
        path = Path(resolved[key])
        resolved[key] = str(path if path.is_absolute() else root / path)
    for key in ("tb_sources", "deps"):
        resolved[key] = [str(Path(p) if Path(p).is_absolute() else root / p) for p in resolved.get(key, [])]
    source = Path(resolved["buggy_rtl_path"]).read_text()
    if source != case["buggy_rtl_source"] or hash_payload(source) != case["buggy_rtl_hash"]:
        raise ValueError("runtime evidence current RTL binding mismatch")
    with tempfile.TemporaryDirectory(prefix="r3e-readable-evidence-") as directory:
        outcome = judge(resolved, resolved["buggy_rtl_path"], directory, evidence_k=6)
        if outcome.ok or outcome.stage != "compare":
            raise ValueError("readable evidence requires a verified functional mismatch")
        gold = (Path(directory) / "golden" / resolved["tb_output"]).read_text()
        actual = (Path(directory) / "cand" / resolved["tb_output"]).read_text()
        observations = {
            "raw_by_k": {str(k): _compare(gold, actual, max_evidence=k)[1] for k in (1, 3, 6)},
            "structured": outcome.structured,
            "golden_trace_hash": hash_payload(gold), "actual_trace_hash": hash_payload(actual),
        }
    context = {"schema_version": "r3e-runtime-repair-evidence-v1", "case_id": case["case_id"],
               "buggy_rtl_hash": case["buggy_rtl_hash"],
               "buggy_rtl_source": source,
               "source_descriptor_hash": source_descriptor["descriptor_hash"],
               "oracle_asset_hashes": {"golden": hash_file(resolved["golden_rtl"]),
                   "testbenches": hash_payload([hash_file(p) for p in resolved["tb_sources"]]),
                   "dependencies": hash_payload([hash_file(p) for p in resolved["deps"]])},
               "observations": observations}
    context["descriptor"] = observable_descriptor(source, outcome.structured, outcome.mismatch,
                                                   hash_payload(observations))
    context["context_hash"] = hash_payload(context)
    return context


def verify_runtime_evidence(context, *, source_descriptor=None):
    value = deepcopy(context)
    digest = value.pop("context_hash", None)
    if digest != hash_payload(value) or value.get("schema_version") != "r3e-runtime-repair-evidence-v1":
        raise ValueError("runtime evidence hash/schema mismatch")
    if source_descriptor is not None and value["source_descriptor_hash"] != source_descriptor["descriptor_hash"]:
        raise ValueError("runtime evidence source descriptor mismatch")
    descriptor = FailureDescriptor.from_dict(value["descriptor"])
    if hash_payload(value["buggy_rtl_source"]) != value["buggy_rtl_hash"]:
        raise ValueError("runtime evidence source hash mismatch")
    if value["descriptor"] != observable_descriptor(value["buggy_rtl_source"],
            value["observations"]["structured"], value["observations"]["raw_by_k"]["6"],
            hash_payload(value["observations"])):
        raise ValueError("runtime descriptor cannot be reconstructed")
    if descriptor.features["observable_artifact_hashes"] != {"runtime_observations": hash_payload(value["observations"])}:
        raise ValueError("runtime evidence observations binding mismatch")
    if set(value["observations"]) != {"raw_by_k", "structured", "golden_trace_hash", "actual_trace_hash"}:
        raise ValueError("undeclared runtime observations")
    if set(value["observations"]["raw_by_k"]) != {"1", "3", "6"}:
        raise ValueError("incomplete runtime evidence levels")
    return context


def visible_observations(context, policy):
    observations = context["observations"]
    result = {"raw_mismatches": observations["raw_by_k"][str(policy.configuration["evidence_k"])],
              "meaning": "actual is the buggy output; expected is the oracle output; cycle is the test observation index"}
    if policy.configuration["evidence_mode"] == "hybrid":
        result["structured_diagnosis"] = observations["structured"]
    return result
