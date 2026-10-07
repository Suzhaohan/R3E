"""Real-model Grounded Red target chooser with proposal-only authority."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import time
from typing import Any, Iterable, Mapping

from r3e.arena.conformance import make_toolchain_fingerprint
from r3e.policy.schema import PolicyState
from r3e.protocol.hashing import atomic_write_json, canonical_json, hash_payload
from r3e.providers.openai_compatible import OpenAICompatibleJSONClient

from .operator_ast import OperatorAstNode


CHOICE_SCHEMA = "r3e-grounded-model-target-choice-v1"


class RealGroundedPlannerViolation(RuntimeError):
    """Raised when a model attempts to widen frozen Grounded authority."""


class OpenAICompatibleGroundedChoiceProvider:
    """Choose one parser-backed node under a frozen GRD intent/assignment."""

    def __init__(
        self,
        client: OpenAICompatibleJSONClient,
        *,
        adapter_version: str = "1",
    ):
        self.client = client
        config = client.config
        self.toolchain_fingerprint = make_toolchain_fingerprint(
            adapter_id=(
                f"r3e-grd-openai-compatible-{config.provider_id}"
            ),
            adapter_version=adapter_version,
            model_id=config.model_id,
            model_version=config.model_version,
            verifier_id="runner-owned-grounded-execution",
            verifier_version="1",
            runtime_id="openai-compatible-json-client",
            runtime_version=config.config_hash,
        )
        self.toolchain_fingerprint_hash = hash_payload(
            self.toolchain_fingerprint
        )

    def choose_target(
        self,
        *,
        policy: PolicyState,
        intent: Mapping[str, Any],
        assignment: Mapping[str, Any],
        clean_source: str,
        target_module: str,
        nodes: Iterable[OperatorAstNode],
        seed: int,
        response_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        options = list(nodes)
        if not options:
            raise RealGroundedPlannerViolation(
                "Grounded planner has no parser-backed target options"
            )
        if (
            intent.get("challenged_policy_hash") != policy.policy_hash
            or intent.get("challenged_effective_policy_hash")
            != policy.effective_policy_hash
            or assignment.get("intent_id") != intent.get("intent_id")
            or assignment.get("intent_hash") != intent.get("intent_hash")
            or assignment.get("challenged_policy_hash")
            != policy.policy_hash
            or assignment.get("model_id")
            != self.client.config.model_id
            or assignment.get("toolchain_fingerprint_hash")
            != self.toolchain_fingerprint_hash
        ):
            raise RealGroundedPlannerViolation(
                "Grounded provider assignment authority mismatch"
            )
        option_rows = [
            {
                "node_ordinal": node.ordinal,
                "node_hash": node.node_hash,
                "node_kind": node.node_kind,
                "old_text": node.old_text,
                "metadata": deepcopy(node.metadata),
            }
            for node in options
        ]
        system = (
            "You are a proposal-only Grounded Red planner. Select exactly "
            "one supplied parser-backed node. You cannot change the family, "
            "operator, expected effect, policy, validator, or budget. Return "
            "one strict JSON object only, with exactly these three top-level "
            "keys: target_module (string), node_ordinal (integer), rationale "
            "(nonempty string). Do not wrap the object or include node_hash, "
            "assignment_id, intent_id, or any other keys."
        )
        user = canonical_json({
            "assignment_id": assignment["assignment_id"],
            "intent_id": intent["intent_id"],
            "frozen_authority": {
                "family_id": intent["family_id"],
                "operator_id": intent["operator_id"],
                "expected_runtime_effect_id": intent[
                    "expected_runtime_effect_id"
                ],
                "difficulty_target": intent["difficulty_target"],
                "target_role": intent["target_role"],
            },
            "target_module": target_module,
            # The runner uses clean_source to derive parser-backed nodes, but
            # the provider must not receive golden RTL.  A hash preserves
            # request binding without leaking the oracle/reference artifact.
            "clean_rtl_hash": hash_payload(clean_source),
            "allowed_nodes": option_rows,
            "required_output_schema": {
                "target_module": target_module,
                "node_ordinal": "integer from allowed_nodes",
                "rationale": "brief target-selection rationale",
            },
        })
        started = time.monotonic()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        required_fields = {"target_module", "node_ordinal", "rationale"}
        attempts = []
        input_tokens = output_tokens = 0
        # One format-correction retry; every call still passes through the
        # client's persistent budget reservations. No guessed/default node.
        for attempt in range(2):
            response = self.client.complete_json(messages=messages, seed=int(seed))
            wall_time_ms = int((time.monotonic() - started) * 1000)
            input_tokens += response["input_tokens"]
            output_tokens += response["output_tokens"]
            record = {
                "assignment_hash": assignment["assignment_hash"],
                "intent_hash": intent["intent_hash"],
                "attempt": attempt + 1,
                "response": response,
            }
            record_hash = hash_payload(record)
            if response_dir is not None:
                atomic_write_json(Path(response_dir) / f"response-{record_hash.split(':')[-1]}.json",
                                  {**record, "record_hash": record_hash})
            attempts.append({
                "record_hash": record_hash,
                **{key: response[key] for key in (
                    "request_hash", "raw_response_hash", "input_tokens", "output_tokens")},
            })
            budget_violations = [
                field for field, used, maximum in (
                    ("input_tokens", input_tokens, assignment["input_token_budget"]),
                    ("output_tokens", output_tokens, assignment["output_token_budget"]),
                    ("wall_time_ms", wall_time_ms, assignment["wall_time_budget_ms"]),
                ) if used > maximum
            ]
            if budget_violations:
                raise RealGroundedPlannerViolation(
                    "Grounded target choice exceeded scheduled budget: "
                    + ",".join(budget_violations)
                )
            choice = response["result"]
            missing = sorted(required_fields - set(choice))
            extra = sorted(set(choice) - required_fields)
            if not missing and not extra:
                break
            detail = canonical_json({"missing": missing, "extra": extra})
            if (attempt == 1 or input_tokens >= assignment["input_token_budget"]
                    or output_tokens >= assignment["output_token_budget"]
                    or wall_time_ms >= assignment["wall_time_budget_ms"]):
                location = f"; responses saved in {response_dir}" if response_dir else ""
                raise RealGroundedPlannerViolation(
                    f"Grounded target choice fields mismatch after {attempt + 1} attempt(s): "
                    + detail + location
                )
            messages.append({"role": "user", "content": (
                "Your previous JSON object had the wrong top-level fields. "
                "Return a corrected object with exactly target_module, node_ordinal, "
                "rationale, using the original allowed_nodes and target_module. "
                "Do not include a wrapper or any other fields."
            )})
        ordinal = choice["node_ordinal"]
        if (
            not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or choice["target_module"] != target_module
            or not isinstance(choice["rationale"], str)
            or not choice["rationale"]
        ):
            raise RealGroundedPlannerViolation(
                "Grounded target choice is invalid"
            )
        selected = next(
            (node for node in options if node.ordinal == ordinal),
            None,
        )
        if selected is None:
            raise RealGroundedPlannerViolation(
                "Grounded target choice is outside parser authority"
            )
        body = {
            "schema_version": CHOICE_SCHEMA,
            "assignment_id": assignment["assignment_id"],
            "assignment_hash": assignment["assignment_hash"],
            "intent_id": intent["intent_id"],
            "intent_hash": intent["intent_hash"],
            "challenged_policy_hash": policy.policy_hash,
            "target_module": target_module,
            "selected_node_ordinal": ordinal,
            "selected_node_hash": selected.node_hash,
            "allowed_node_set_hash": hash_payload(option_rows),
            "model_id": self.client.config.model_id,
            "toolchain_fingerprint_hash": (
                self.toolchain_fingerprint_hash
            ),
            "budget_hash": assignment["budget_hash"],
            "request_hash": response["request_hash"],
            "raw_response_hash": response["raw_response_hash"],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "wall_time_ms": wall_time_ms,
            "provider_attempts": attempts,
            "rationale_hash": hash_payload(choice["rationale"]),
        }
        body["choice_hash"] = hash_payload(body)
        return body
