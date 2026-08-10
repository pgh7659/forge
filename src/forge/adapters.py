from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType
from typing import Protocol

from forge.canonical import CanonicalizationError, canonical_json_bytes
from forge.config import ValidatedEnvironment
from forge.planning import AdapterKey, PlanArtifact, PlanContractError, PlanningBasis, create_plan


_UNAVAILABLE_REASONS = frozenset(
    {
        "adapter not registered",
        "observation unavailable",
        "invalid adapter result",
    }
)


class PlanningAdapter(Protocol):
    def observe(self, environment: ValidatedEnvironment) -> object: ...

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]: ...


class PlanningUnavailable(Exception):
    __slots__ = ("adapter_key", "reason")

    def __init__(self, adapter_key: AdapterKey, reason: str) -> None:
        if reason not in _UNAVAILABLE_REASONS:
            raise ValueError("invalid planning-unavailable reason")
        self.adapter_key = adapter_key
        self.reason = reason
        super().__init__(reason)


class PlanningRegistry:
    def __init__(
        self, registrations: Iterable[tuple[AdapterKey, PlanningAdapter]]
    ) -> None:
        adapters: dict[AdapterKey, PlanningAdapter] = {}
        for adapter_key, adapter in registrations:
            if adapter_key in adapters:
                raise ValueError("duplicate planning adapter registration")
            adapters[adapter_key] = adapter
        self._adapters = MappingProxyType(adapters)

    def resolve(self, adapter_key: AdapterKey) -> PlanningAdapter:
        try:
            return self._adapters[adapter_key]
        except KeyError:
            raise PlanningUnavailable(adapter_key, "adapter not registered") from None


class NoopPlanningAdapter:
    def observe(self, environment: ValidatedEnvironment) -> object:
        return {}

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        return ()


def default_planning_registry() -> PlanningRegistry:
    return PlanningRegistry(((AdapterKey("noop", "noop"), NoopPlanningAdapter()),))


def plan_environment(
    environment: ValidatedEnvironment, registry: PlanningRegistry
) -> PlanArtifact:
    target = environment.document["spec"]["target"]
    adapter_key = AdapterKey(
        target["connectionAdapter"], target["runtimeAdapter"]
    )
    adapter = registry.resolve(adapter_key)
    try:
        observation = adapter.observe(environment)
    except PlanningUnavailable as exc:
        if exc.reason == "observation unavailable":
            raise PlanningUnavailable(adapter_key, "observation unavailable") from None
        raise

    if type(observation) is not dict:
        raise PlanningUnavailable(adapter_key, "invalid adapter result")
    try:
        canonical_json_bytes(observation)
    except CanonicalizationError:
        raise PlanningUnavailable(adapter_key, "invalid adapter result") from None

    operations = adapter.plan(environment, observation)
    if type(operations) is not tuple or any(
        type(operation) is not dict for operation in operations
    ):
        raise PlanningUnavailable(adapter_key, "invalid adapter result")

    try:
        basis = PlanningBasis.create(
            environment_name=environment.name,
            config_digest=f"sha256:{environment.digest}",
            adapter_key=adapter_key,
            observation=observation,
            operations=operations,
        )
        return create_plan(basis)
    except PlanContractError:
        raise PlanningUnavailable(adapter_key, "invalid adapter result") from None
