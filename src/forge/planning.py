from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator

from forge.canonical import CanonicalizationError, canonical_json_bytes, sha256_identifier


API_VERSION = "forge.dev/v1alpha1"
PLAN_KIND = "Plan"
PLANNING_CONTRACT_VERSION = "forge.dev/planning/v1alpha1"


class PlanContractError(ValueError):
    """A Plan input or artifact violates the Forge Plan contract."""


@dataclass(frozen=True, slots=True)
class AdapterKey:
    connection_adapter: str
    runtime_adapter: str


@dataclass(frozen=True, slots=True)
class PlanningBasis:
    environment_name: str
    config_digest: str
    adapter_key: AdapterKey
    contract_version: str
    observation_bytes: bytes
    operations_bytes: bytes

    @classmethod
    def create(
        cls,
        *,
        environment_name: str,
        config_digest: str,
        adapter_key: AdapterKey,
        observation: object,
        operations: tuple[dict[str, object], ...],
        contract_version: str = PLANNING_CONTRACT_VERSION,
    ) -> PlanningBasis:
        observation_bytes = _canonical_input(observation)
        operations_bytes = _canonical_input(list(operations))
        if not isinstance(json.loads(observation_bytes), dict):
            raise PlanContractError("observation document must be an object")
        if not isinstance(json.loads(operations_bytes), list):
            raise PlanContractError("operations must be an ordered array")
        return cls(
            environment_name=environment_name,
            config_digest=config_digest,
            adapter_key=adapter_key,
            contract_version=contract_version,
            observation_bytes=observation_bytes,
            operations_bytes=operations_bytes,
        )

    def observation(self) -> dict[str, Any]:
        value = json.loads(self.observation_bytes)
        assert isinstance(value, dict)
        return value

    def operations(self) -> list[dict[str, Any]]:
        value = json.loads(self.operations_bytes)
        assert isinstance(value, list)
        return value


@dataclass(frozen=True, slots=True)
class PlanArtifact:
    canonical_bytes: bytes
    plan_id: str

    def document(self) -> dict[str, Any]:
        value = json.loads(self.canonical_bytes)
        assert isinstance(value, dict)
        return value


@dataclass(frozen=True, slots=True)
class VerifiedPlan:
    canonical_bytes: bytes
    plan_id: str

    def document(self) -> dict[str, Any]:
        value = json.loads(self.canonical_bytes)
        assert isinstance(value, dict)
        return value


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = files("forge").joinpath("resources/schemas/plan-v1alpha1.schema.json")
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _canonical_input(value: object) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CanonicalizationError as exc:
        raise PlanContractError("planning input is not RFC 8785 canonicalizable") from exc


def _plan_preimage(basis: PlanningBasis) -> dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": PLAN_KIND,
        "metadata": {},
        "spec": {
            "environment": {
                "name": basis.environment_name,
                "configDigest": basis.config_digest,
            },
            "planningAdapter": {
                "contractVersion": basis.contract_version,
                "connectionAdapter": basis.adapter_key.connection_adapter,
                "runtimeAdapter": basis.adapter_key.runtime_adapter,
            },
            "observation": {
                "document": basis.observation(),
                "digest": sha256_identifier(basis.observation()),
            },
            "operations": basis.operations(),
        },
    }


def _plan_id(preimage: dict[str, Any]) -> str:
    try:
        return sha256_identifier(preimage)
    except CanonicalizationError as exc:
        raise PlanContractError("plan identity is not RFC 8785 canonicalizable") from exc


def _validate_schema(document: object) -> None:
    if any(_validator().iter_errors(document)):
        raise PlanContractError("plan does not satisfy the v1alpha1 contract")


def create_plan(basis: PlanningBasis) -> PlanArtifact:
    if not isinstance(basis, PlanningBasis):
        raise TypeError("basis must be a PlanningBasis")
    preimage = _plan_preimage(basis)
    plan_id = _plan_id(preimage)
    document = copy.deepcopy(preimage)
    document["metadata"]["id"] = plan_id
    _validate_schema(document)
    try:
        canonical_bytes = canonical_json_bytes(document)
    except CanonicalizationError as exc:
        raise PlanContractError("plan is not RFC 8785 canonicalizable") from exc
    return PlanArtifact(canonical_bytes=canonical_bytes, plan_id=plan_id)


def verify_plan(document: object) -> VerifiedPlan:
    _validate_schema(document)
    assert isinstance(document, dict)
    spec = document["spec"]
    assert isinstance(spec, dict)
    operations = spec["operations"]
    assert isinstance(operations, list)
    operation_ids = [operation["id"] for operation in operations]
    if len(operation_ids) != len(set(operation_ids)):
        raise PlanContractError("plan contains duplicate operation IDs")

    observation = spec["observation"]
    assert isinstance(observation, dict)
    expected_observation_digest = _plan_id(observation["document"])
    if observation["digest"] != expected_observation_digest:
        raise PlanContractError("plan observation digest does not match its document")

    preimage = copy.deepcopy(document)
    metadata = preimage["metadata"]
    assert isinstance(metadata, dict)
    del metadata["id"]
    expected_plan_id = _plan_id(preimage)
    metadata_id = document["metadata"]["id"]
    if metadata_id != expected_plan_id:
        raise PlanContractError("plan ID does not match its preimage")

    try:
        canonical_bytes = canonical_json_bytes(document)
    except CanonicalizationError as exc:
        raise PlanContractError("plan is not RFC 8785 canonicalizable") from exc
    return VerifiedPlan(canonical_bytes=canonical_bytes, plan_id=expected_plan_id)


def is_stale(verified_plan: VerifiedPlan, basis: PlanningBasis) -> bool:
    if not isinstance(verified_plan, VerifiedPlan):
        raise TypeError("verified_plan must be a VerifiedPlan")
    if not isinstance(basis, PlanningBasis):
        raise TypeError("basis must be a PlanningBasis")
    return verified_plan.plan_id != _plan_id(_plan_preimage(basis))
