from __future__ import annotations

from pathlib import Path
import socket
import subprocess

import pytest

from forge.adapters import (
    NoopPlanningAdapter,
    PlanningRegistry,
    PlanningUnavailable,
    default_planning_registry,
    plan_environment,
)
from forge.config import ValidatedEnvironment, load_and_validate
from forge.planning import AdapterKey


def environment(
    tmp_path: Path,
    *,
    connection_adapter: str = "noop",
    runtime_adapter: str = "noop",
    name: str = "example-noop",
    config: str = "{}",
    order: str = "normal",
) -> ValidatedEnvironment:
    path = tmp_path / f"{name}-{connection_adapter}-{runtime_adapter}.yaml"
    if order == "reversed":
        path.write_text(
            "kind: Environment\n"
            "spec:\n"
            "  target:\n"
            f"    runtimeAdapter: {runtime_adapter}\n"
            f"    connectionAdapter: {connection_adapter}\n"
            f"    config: {config}\n"
            f"metadata: {{name: {name}}}\n"
            "apiVersion: forge.dev/v1alpha1\n",
            encoding="utf-8",
        )
    else:
        path.write_text(
            "apiVersion: forge.dev/v1alpha1\n"
            "kind: Environment\n"
            f"metadata: {{name: {name}}}\n"
            "spec:\n"
            "  target:\n"
            f"    connectionAdapter: {connection_adapter}\n"
            f"    runtimeAdapter: {runtime_adapter}\n"
            f"    config: {config}\n",
            encoding="utf-8",
        )
    return load_and_validate(path)


def test_default_registry_resolves_only_the_noop_tuple() -> None:
    registry = default_planning_registry()

    assert isinstance(registry.resolve(AdapterKey("noop", "noop")), NoopPlanningAdapter)

    for adapter_key in (
        AdapterKey("ssh", "systemd"),
        AdapterKey("noop", "systemd"),
        AdapterKey("ssh", "noop"),
    ):
        with pytest.raises(PlanningUnavailable) as raised:
            registry.resolve(adapter_key)

        assert raised.value.adapter_key == adapter_key
        assert raised.value.reason == "adapter not registered"


def test_registry_rejects_duplicate_exact_tuples() -> None:
    key = AdapterKey("noop", "noop")

    with pytest.raises(ValueError, match="duplicate planning adapter registration"):
        PlanningRegistry(((key, NoopPlanningAdapter()), (key, NoopPlanningAdapter())))


def test_registry_copies_and_immutably_owns_injected_registrations() -> None:
    key = AdapterKey("custom", "runtime")
    first = NoopPlanningAdapter()
    registrations = {key: first}
    registry = PlanningRegistry(registrations.items())
    registrations[key] = NoopPlanningAdapter()

    assert registry.resolve(key) is first
    with pytest.raises(TypeError):
        registry._adapters[key] = NoopPlanningAdapter()  # type: ignore[index]


def test_plan_environment_creates_the_empty_noop_plan(tmp_path: Path) -> None:
    result = plan_environment(environment(tmp_path), default_planning_registry())

    assert result.document()["spec"]["observation"]["document"] == {}
    assert result.document()["spec"]["operations"] == []


def test_equivalent_noop_environments_produce_identical_plans(tmp_path: Path) -> None:
    first = environment(tmp_path, name="same", config="{alpha: 1, beta: 2}")
    second = environment(
        tmp_path,
        name="same",
        config="{beta: 2, alpha: 1}",
        order="reversed",
    )

    first_plan = plan_environment(first, default_planning_registry())
    second_plan = plan_environment(second, default_planning_registry())

    assert first_plan.canonical_bytes == second_plan.canonical_bytes
    assert first_plan.plan_id == second_plan.plan_id


class _CountingAdapter:
    def __init__(self) -> None:
        self.observations = 0
        self.plans = 0

    def observe(self, environment: ValidatedEnvironment) -> object:
        self.observations += 1
        return {"state": "ready"}

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        self.plans += 1
        assert observation == {"state": "ready"}
        return (
            {
                "id": "op-1",
                "action": "update",
                "resource": {"kind": "workload", "id": "example"},
                "details": {"image": "v2"},
            },
        )


def test_injected_adapter_can_produce_a_deterministic_ordered_plan(
    tmp_path: Path,
) -> None:
    adapter = _CountingAdapter()
    registry = PlanningRegistry(((AdapterKey("custom", "runtime"), adapter),))

    plan = plan_environment(
        environment(
            tmp_path, connection_adapter="custom", runtime_adapter="runtime"
        ),
        registry,
    )

    assert adapter.observations == 1
    assert adapter.plans == 1
    assert plan.document()["spec"]["observation"]["document"] == {"state": "ready"}
    assert plan.document()["spec"]["operations"] == [
        {
            "id": "op-1",
            "action": "update",
            "resource": {"kind": "workload", "id": "example"},
            "details": {"image": "v2"},
        }
    ]
    with pytest.raises(PlanningUnavailable) as raised:
        default_planning_registry().resolve(AdapterKey("custom", "runtime"))
    assert raised.value.reason == "adapter not registered"


class _UnavailableAdapter:
    def observe(self, environment: ValidatedEnvironment) -> object:
        raise PlanningUnavailable(AdapterKey("custom", "runtime"), "observation unavailable")

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        raise AssertionError("unavailable observations must not be planned")


def test_explicit_observation_unavailable_signal_is_preserved(tmp_path: Path) -> None:
    key = AdapterKey("custom", "runtime")
    registry = PlanningRegistry(((key, _UnavailableAdapter()),))

    with pytest.raises(PlanningUnavailable) as raised:
        plan_environment(
            environment(
                tmp_path, connection_adapter="custom", runtime_adapter="runtime"
            ),
            registry,
        )

    assert raised.value.adapter_key == key
    assert raised.value.reason == "observation unavailable"
    assert str(raised.value) == "observation unavailable"


class _SpoofedAvailabilityAdapter:
    def __init__(self, phase: str, reason: str) -> None:
        self.phase = phase
        self.reason = reason

    def _signal(self) -> None:
        raise PlanningUnavailable(
            AdapterKey("secret-like-connection", "secret-like-runtime"), self.reason
        )

    def observe(self, environment: ValidatedEnvironment) -> object:
        if self.phase == "observe":
            self._signal()
        return {}

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        if self.phase == "plan":
            self._signal()
        return ()


@pytest.mark.parametrize("phase", ["observe", "plan"])
def test_adapter_observation_unavailable_is_normalized_to_selected_key(
    tmp_path: Path, phase: str
) -> None:
    selected_key = AdapterKey("custom", "runtime")
    registry = PlanningRegistry(
        ((selected_key, _SpoofedAvailabilityAdapter(phase, "observation unavailable")),)
    )

    with pytest.raises(PlanningUnavailable) as raised:
        plan_environment(
            environment(
                tmp_path, connection_adapter="custom", runtime_adapter="runtime"
            ),
            registry,
        )

    assert raised.value.adapter_key == selected_key
    assert raised.value.reason == "observation unavailable"
    assert "secret-like" not in str(raised.value)


@pytest.mark.parametrize("phase", ["observe", "plan"])
@pytest.mark.parametrize("reason", ["adapter not registered", "invalid adapter result"])
def test_adapter_cannot_spoof_core_availability_failures(
    tmp_path: Path, phase: str, reason: str
) -> None:
    selected_key = AdapterKey("custom", "runtime")
    registry = PlanningRegistry(
        ((selected_key, _SpoofedAvailabilityAdapter(phase, reason)),)
    )

    with pytest.raises(RuntimeError) as raised:
        plan_environment(
            environment(
                tmp_path, connection_adapter="custom", runtime_adapter="runtime"
            ),
            registry,
        )

    assert str(raised.value) == "adapter emitted an invalid availability signal"
    assert "secret-like" not in str(raised.value)
    assert reason not in str(raised.value)


class _OutOfRangeObservationAdapter:
    def observe(self, environment: ValidatedEnvironment) -> object:
        return {"value": 9007199254740992}

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        raise AssertionError("invalid observations must not be planned")


class _OutOfRangeDetailsAdapter:
    def observe(self, environment: ValidatedEnvironment) -> object:
        return {}

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        return (
            {
                "id": "op-1",
                "action": "update",
                "resource": {"kind": "workload", "id": "example"},
                "details": {"value": 9007199254740992},
            },
        )


@pytest.mark.parametrize(
    "adapter",
    [_OutOfRangeObservationAdapter(), _OutOfRangeDetailsAdapter()],
)
def test_invalid_adapter_results_are_redacted(tmp_path: Path, adapter: object) -> None:
    assert hasattr(adapter, "observe")
    key = AdapterKey("custom", "runtime")
    registry = PlanningRegistry(((key, adapter),))  # type: ignore[arg-type]
    opaque_config = "{token: opaque-target-value, path: /private/target-fixture}"

    with pytest.raises(PlanningUnavailable) as raised:
        plan_environment(
            environment(
                tmp_path,
                connection_adapter="custom",
                runtime_adapter="runtime",
                config=opaque_config,
            ),
            registry,
        )

    assert raised.value.adapter_key == key
    assert raised.value.reason == "invalid adapter result"
    message = str(raised.value)
    assert "9007199254740992" not in message
    assert "opaque-target-value" not in message
    assert "/private/target-fixture" not in message


def _forbid_io(*args: object, **kwargs: object) -> object:
    raise AssertionError("NoopPlanningAdapter must not perform I/O")


def test_noop_adapter_does_not_access_network_process_or_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validated = environment(tmp_path)
    adapter = NoopPlanningAdapter()
    monkeypatch.setattr(socket, "socket", _forbid_io)
    monkeypatch.setattr(subprocess, "run", _forbid_io)
    monkeypatch.setattr(subprocess, "Popen", _forbid_io)
    monkeypatch.setattr(Path, "open", _forbid_io)
    monkeypatch.setattr(Path, "stat", _forbid_io)
    monkeypatch.setattr(Path, "iterdir", _forbid_io)

    observation = adapter.observe(validated)
    operations = adapter.plan(validated, observation)

    assert observation == {}
    assert observation is not adapter.observe(validated)
    assert operations == ()


class _EnvironmentMutatingAdapter:
    def observe(self, environment: ValidatedEnvironment) -> object:
        document = environment.document
        document["metadata"]["name"] = "adapter-mutated"
        document["spec"]["target"]["connectionAdapter"] = "adapter-mutated"
        document["spec"]["target"]["config"]["value"] = "adapter-mutated"
        return {}

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        document = environment.document
        document["spec"]["target"]["runtimeAdapter"] = "adapter-mutated"
        return ()


def test_adapter_environment_mutation_cannot_change_snapshot_or_plan_binding(
    tmp_path: Path,
) -> None:
    validated = environment(
        tmp_path,
        connection_adapter="custom",
        runtime_adapter="runtime",
        config="{value: original}",
    )
    original_digest = validated.digest
    key = AdapterKey("custom", "runtime")
    plan = plan_environment(
        validated, PlanningRegistry(((key, _EnvironmentMutatingAdapter()),))
    )

    assert validated.name == "example-noop"
    assert validated.digest == original_digest
    assert validated.document["spec"]["target"] == {
        "connectionAdapter": "custom",
        "runtimeAdapter": "runtime",
        "config": {"value": "original"},
    }
    assert plan.document()["spec"]["environment"] == {
        "name": "example-noop",
        "configDigest": f"sha256:{original_digest}",
    }
    assert plan.document()["spec"]["planningAdapter"] == {
        "contractVersion": "forge.dev/planning/v1alpha1",
        "connectionAdapter": "custom",
        "runtimeAdapter": "runtime",
    }


class _NestedTupleObservationAdapter:
    def observe(self, environment: ValidatedEnvironment) -> object:
        return {"nested": ("tuple-observation",)}

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        raise AssertionError("invalid observations must not be planned")


class _NestedTupleDetailsAdapter:
    def observe(self, environment: ValidatedEnvironment) -> object:
        return {}

    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]:
        return (
            {
                "id": "op-1",
                "action": "update",
                "resource": {"kind": "workload", "id": "example"},
                "details": {"nested": ("tuple-details",)},
            },
        )


@pytest.mark.parametrize(
    "adapter", [_NestedTupleObservationAdapter(), _NestedTupleDetailsAdapter()]
)
def test_nested_tuple_adapter_results_are_redacted(
    tmp_path: Path, adapter: object
) -> None:
    key = AdapterKey("custom", "runtime")
    registry = PlanningRegistry(((key, adapter),))  # type: ignore[arg-type]

    with pytest.raises(PlanningUnavailable) as raised:
        plan_environment(
            environment(
                tmp_path,
                connection_adapter="custom",
                runtime_adapter="runtime",
                config="{token: opaque-target-value}",
            ),
            registry,
        )

    assert raised.value.adapter_key == key
    assert raised.value.reason == "invalid adapter result"
    assert str(raised.value) == "invalid adapter result"
    assert "tuple-" not in str(raised.value)
    assert "opaque-target-value" not in str(raised.value)
