from __future__ import annotations

from copy import deepcopy

import pytest

from forge.canonical import canonical_json_bytes, sha256_identifier
from forge.planning import (
    AdapterKey,
    PlanContractError,
    PlanningBasis,
    create_plan,
    is_stale,
    verify_plan,
)


def basis(
    *,
    environment_name: str = "example-noop",
    config_digest: str = "sha256:" + "a" * 64,
    adapter_key: AdapterKey = AdapterKey("noop", "noop"),
    contract_version: str = "forge.dev/planning/v1alpha1",
    observation: object = {},
    operations: tuple[dict[str, object], ...] = (),
) -> PlanningBasis:
    return PlanningBasis.create(
        environment_name=environment_name,
        config_digest=config_digest,
        adapter_key=adapter_key,
        contract_version=contract_version,
        observation=observation,
        operations=operations,
    )


def operation(
    operation_id: str = "op-1", *, details: object = {"image": "v1"}
) -> dict[str, object]:
    assert isinstance(details, dict)
    return {
        "id": operation_id,
        "action": "update",
        "resource": {"kind": "workload", "id": "example"},
        "details": details,
    }


def test_plan_is_strict_deterministic_and_verifiable() -> None:
    first = create_plan(basis())
    second = create_plan(basis())

    assert first.canonical_bytes == second.canonical_bytes
    assert first.plan_id.startswith("sha256:")
    document = first.document()
    assert document["apiVersion"] == "forge.dev/v1alpha1"
    assert document["kind"] == "Plan"
    assert document["spec"]["planningAdapter"] == {
        "contractVersion": "forge.dev/planning/v1alpha1",
        "connectionAdapter": "noop",
        "runtimeAdapter": "noop",
    }
    assert document["spec"]["observation"]["document"] == {}
    assert document["spec"]["operations"] == []
    assert verify_plan(document).plan_id == first.plan_id


def test_plan_document_and_basis_accessors_are_independent_copies() -> None:
    planning_basis = basis(
        observation={"nested": {"value": 1}}, operations=(operation(),)
    )
    artifact = create_plan(planning_basis)
    original_bytes = artifact.canonical_bytes
    document = artifact.document()
    document["spec"]["observation"]["document"]["nested"]["value"] = 2
    document["spec"]["operations"][0]["details"]["image"] = "v2"

    observation = planning_basis.observation()
    observation["nested"]["value"] = 3
    operations = planning_basis.operations()
    operations[0]["details"]["image"] = "v3"

    assert artifact.canonical_bytes == original_bytes
    assert artifact.document()["spec"]["observation"]["document"] == {
        "nested": {"value": 1}
    }
    assert artifact.document()["spec"]["operations"][0]["details"] == {"image": "v1"}
    assert planning_basis.observation() == {"nested": {"value": 1}}
    assert planning_basis.operations()[0]["details"] == {"image": "v1"}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.__setitem__("unexpected", True),
        lambda document: document["metadata"].__setitem__("unexpected", True),
        lambda document: document["spec"].__setitem__("unexpected", True),
        lambda document: document["spec"]["environment"].__setitem__(
            "configDigest", "sha256:not-a-digest"
        ),
        lambda document: document["spec"]["operations"].append({"id": "op-1"}),
        lambda document: document["spec"]["operations"].append(
            {
                "id": "op-1",
                "action": "unsupported",
                "resource": {"kind": "workload", "id": "example"},
                "details": {},
            }
        ),
    ],
)
def test_plan_schema_rejects_strict_contract_violations(mutation: object) -> None:
    document = create_plan(basis()).document()
    assert callable(mutation)
    mutation(document)

    with pytest.raises(PlanContractError):
        verify_plan(document)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document["spec"]["observation"]["document"].__setitem__(
            "changed", True
        ),
        lambda document: document["spec"]["operations"].extend(
            [operation("op-1"), operation("op-1")]
        ),
        lambda document: document["spec"]["planningAdapter"].__setitem__(
            "contractVersion", "forge.dev/planning/v0"
        ),
        lambda document: document["metadata"].__setitem__("id", "sha256:" + "b" * 64),
    ],
)
def test_verify_plan_rejects_tampered_identity_inputs(mutation: object) -> None:
    document = create_plan(basis()).document()
    assert callable(mutation)
    mutation(document)

    with pytest.raises(PlanContractError):
        verify_plan(document)


def test_metadata_identifier_is_not_part_of_its_preimage() -> None:
    document = create_plan(basis()).document()
    first_preimage = deepcopy(document)
    del first_preimage["metadata"]["id"]
    document["metadata"]["id"] = "sha256:" + "b" * 64
    second_preimage = deepcopy(document)
    del second_preimage["metadata"]["id"]

    assert sha256_identifier(first_preimage) == sha256_identifier(second_preimage)
    assert canonical_json_bytes(first_preimage) == canonical_json_bytes(second_preimage)


def test_staleness_compares_every_planning_basis_input() -> None:
    original = basis(operations=(operation(),))
    verified = verify_plan(create_plan(original).document())

    assert not is_stale(verified, original)
    assert is_stale(verified, basis(environment_name="other", operations=(operation(),)))
    assert is_stale(
        verified,
        basis(config_digest="sha256:" + "b" * 64, operations=(operation(),)),
    )
    assert is_stale(
        verified,
        basis(adapter_key=AdapterKey("other", "noop"), operations=(operation(),)),
    )
    assert is_stale(
        verified,
        basis(adapter_key=AdapterKey("noop", "other"), operations=(operation(),)),
    )
    assert is_stale(
        verified,
        basis(contract_version="forge.dev/planning/v2", operations=(operation(),)),
    )
    assert is_stale(
        verified,
        basis(observation={"changed": True}, operations=(operation(),)),
    )
    assert is_stale(
        verified,
        basis(operations=(operation(details={"image": "v2"}),)),
    )
    assert is_stale(
        verified,
        basis(operations=(operation("op-2"), operation("op-1"))),
    )


@pytest.mark.parametrize(
    "planning_basis",
    [
        lambda: basis(observation={"value": 9007199254740992}),
        lambda: basis(operations=(operation(details={"value": 9007199254740992}),)),
    ],
)
def test_planning_basis_rejects_out_of_range_values_without_leaking_them(
    planning_basis: object,
) -> None:
    assert callable(planning_basis)

    with pytest.raises(PlanContractError) as raised:
        planning_basis()

    assert "9007199254740992" not in str(raised.value)


def test_planning_basis_rejects_recursive_observation_with_owned_error() -> None:
    loop: list[object] = []
    loop.append(loop)

    with pytest.raises(PlanContractError) as raised:
        basis(observation={"loop": loop})

    assert "RecursionError" not in str(raised.value)


def test_planning_basis_rejects_recursive_operation_details_with_owned_error() -> None:
    loop: dict[str, object] = {}
    loop["loop"] = loop

    with pytest.raises(PlanContractError) as raised:
        basis(operations=(operation(details={"loop": loop}),))

    assert "RecursionError" not in str(raised.value)


def test_verify_plan_rejects_recursive_observation_with_owned_error() -> None:
    document = create_plan(basis()).document()
    loop: list[object] = []
    loop.append(loop)
    document["spec"]["observation"]["document"]["loop"] = loop

    with pytest.raises(PlanContractError) as raised:
        verify_plan(document)

    assert "RecursionError" not in str(raised.value)
