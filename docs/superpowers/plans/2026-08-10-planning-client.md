# Planning Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-neutral, non-mutating `forge plan` vertical slice with RFC 8785 identities, a strict Plan contract, exact adapter resolution, a built-in `noop+noop` adapter, and fail-closed stale-plan detection.

**Architecture:** Environment and Plan identities share one RFC 8785/JCS canonicalization module. Planning core owns immutable canonical bytes, strict schema and ID verification, and pure stale comparison; an injected exact-tuple registry owns adapter selection, with only `("noop", "noop")` registered by the CLI. The command validates configuration before adapter resolution and emits one canonical JSON Plan plus a framing newline without target access.

**Tech Stack:** Python 3.12+, `rfc8785>=0.1.4,<0.2`, PyYAML, jsonschema Draft 2020-12, argparse, pytest, Make, GitHub Actions.

## Global Constraints

- The governing design is `docs/superpowers/specs/2026-08-10-planning-client-design.md`.
- Public API version is exactly `forge.dev/v1alpha1`; artifact kind is exactly `Plan`.
- Planning contract version is exactly `forge.dev/planning/v1alpha1`.
- Canonicalization is RFC 8785/JCS UTF-8 bytes through `rfc8785>=0.1.4,<0.2`.
- Plan ID is `sha256:` plus lowercase SHA-256 over the full Plan with only `/metadata/id` omitted.
- The default registry contains exactly `("noop", "noop") -> NoopPlanningAdapter`; selection is an exact structured tuple with no aliases, normalization, fallback, entry points, or dynamic imports.
- `noop+noop` returns observation `{}` and `operations: []` entirely in memory, without network, subprocess, environment, clock, host identity, credential, or target filesystem access.
- CLI exit codes are `0` success, `2` usage, `3` read/parse, `4` configuration validation, and `5` planning unavailable or invalid adapter result.
- Success writes one RFC 8785 Plan JSON document plus one ASCII newline to stdout and nothing to stderr. Errors write no partial Plan.
- Plan instances are private review/audit data by default and must not copy full Environment documents, opaque target config, resolved secrets, local paths, or raw adapter exceptions.
- `verify_plan` must reject schema errors, unsupported planning versions, observation-digest mismatch, duplicate operation IDs, and Plan-ID mismatch before stale comparison.
- `is_stale` is pure and compares a verified Plan ID with the ID materialized from the complete current planning basis.
- No SSH, systemd, OCI, Hermes, Discord, Codex, apply, doctor, controller, SQLite, secrets, capability probing, plugin discovery, provisioning, deployment, or `forge-ops` work belongs in this plan.
- No OCI or live-service access is authorized.

## File map

- `src/forge/canonical.py`: RFC 8785 byte encoding and SHA-256 helpers.
- `src/forge/config.py`: JCS/I-JSON compatibility validation and shared Environment digest.
- `src/forge/planning.py`: immutable planning basis/artifact, strict schema validation, ID verification, and stale predicate.
- `src/forge/adapters.py`: exact adapter tuple, protocol, immutable registry, no-op implementation, and orchestration into a Plan.
- `src/forge/cli.py`: `forge plan` parsing, streams, and exit-code mapping.
- `src/forge/resources/schemas/plan-v1alpha1.schema.json`: strict public Plan artifact contract.
- `examples/environments/noop.yaml`: synthetic supported planning input.
- `tests/unit/test_canonical.py`, `tests/unit/test_planning.py`, `tests/unit/test_adapters.py`, `tests/cli/test_plan.py`: focused behavioral contracts.
- `README.md`, `docs/architecture.md`, `docs/roadmap.md`, `config/README.md`, `examples/README.md`, `tests/README.md`: implemented status, limits, and commands.
- `Makefile`, `tests/validate-contracts.sh`, `.github/workflows/validate.yml`: repository, package, and wheel evidence.

---

### Task 1: Canonical identity and strict Plan contract

**Files:**
- Create: `src/forge/canonical.py`
- Create: `src/forge/planning.py`
- Create: `src/forge/resources/schemas/plan-v1alpha1.schema.json`
- Create: `tests/unit/test_canonical.py`
- Create: `tests/unit/test_planning.py`
- Modify: `src/forge/config.py`
- Modify: `pyproject.toml`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `canonical_json_bytes(value: object) -> bytes`, `sha256_hex(value: object) -> str`, and `sha256_identifier(value: object) -> str` in `forge.canonical`.
- Produces: `AdapterKey`, `PlanningBasis`, `PlanArtifact`, `VerifiedPlan`, `PlanContractError`, `create_plan`, `verify_plan`, and `is_stale` in `forge.planning`.
- `PlanningBasis.create` accepts JSON-compatible observation and ordered operation documents, canonicalizes them immediately, and stores only immutable bytes plus scalar identity fields.
- Consumers receive fresh parsed copies through accessors; no frozen dataclass exposes a mutable dict/list owned by the artifact.

- [ ] **Step 1: Add failing RFC 8785 and Environment-compatibility tests**

Create `tests/unit/test_canonical.py` with assertions equivalent to:

```python
from forge.canonical import canonical_json_bytes, sha256_hex


def test_rfc8785_normalizes_numbers_and_orders_unicode_members() -> None:
    assert canonical_json_bytes({"z": 1.0, "é": 2, "a": 1}) == (
        b'{"a":1,"z":1,"\xc3\xa9":2}'
    )
    assert canonical_json_bytes(1) == canonical_json_bytes(1.0) == b"1"
    assert canonical_json_bytes(-0.0) == b"0"
    assert canonical_json_bytes(1e-6) == b"0.000001"
    assert canonical_json_bytes(1e-7) == b"1e-7"
    assert canonical_json_bytes(1e30) == b"1e+30"


def test_nested_mapping_order_has_one_digest() -> None:
    assert sha256_hex({"b": {"y": 2, "x": 1}, "a": [3]}) == sha256_hex(
        {"a": [3], "b": {"x": 1, "y": 2}}
    )
```

Extend `tests/unit/test_config.py` with a YAML Environment whose opaque target config contains integer `9007199254740992`. Assert `load_and_validate` raises `ConfigValidationError`, pointer `/spec/target/config/value`, and message `integers must be within the I-JSON interoperable range`. Add an equivalent lower-bound case for `-9007199254740992`.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_canonical.py tests/unit/test_config.py -q
```

Expected: collection fails because `forge.canonical` does not exist, and the new large-integer validation assertions are not implemented.

- [ ] **Step 3: Add the pinned JCS dependency and minimal canonical module**

Add `"rfc8785>=0.1.4,<0.2"` to `[project].dependencies` in `pyproject.toml`. Create `src/forge/canonical.py` with this public surface:

```python
from __future__ import annotations

import hashlib

import rfc8785


class CanonicalizationError(ValueError):
    """A value cannot be represented by the Forge RFC 8785 profile."""


def canonical_json_bytes(value: object) -> bytes:
    try:
        return rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise CanonicalizationError("value is not RFC 8785 canonicalizable") from exc


def sha256_hex(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_identifier(value: object) -> str:
    return f"sha256:{sha256_hex(value)}"
```

Update `_json_compatibility_issues` in `src/forge/config.py` so an `int` other than `bool` is accepted only when `-9007199254740991 <= value <= 9007199254740991`. Keep pointer ordering deterministic. Replace the inline `json.dumps`/`hashlib.sha256` Environment digest with `sha256_hex(document)`. Do not catch canonicalization at the CLI boundary; compatibility validation must make valid Environment documents canonicalizable.

- [ ] **Step 4: Install the changed development package and make canonical/config tests GREEN**

Run:

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest tests/unit/test_canonical.py tests/unit/test_config.py -q
```

Expected: all focused tests pass, including previous mapping-order, recursive-alias, non-finite, and non-string-key cases.

- [ ] **Step 5: Write failing Plan schema, identity, verification, immutability, and stale tests**

Create `tests/unit/test_planning.py`. Use a `PlanningBasis.create` fixture with environment `example-noop`, config digest `sha256:` plus 64 `a` characters, adapter `AdapterKey("noop", "noop")`, observation `{}`, and operations `()`. Require these behaviors:

```python
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
```

Also assert:

- modifying the dict returned by `document()` does not change `canonical_bytes` or later `document()` results;
- the packaged schema rejects an unknown root/spec/metadata field, malformed digest, malformed operation, and unsupported action;
- `verify_plan` rejects a changed observation document with its old digest, a duplicate operation ID, unsupported `contractVersion`, and a changed `metadata.id`;
- changing only `metadata.id` does not change the recomputed preimage ID;
- `is_stale(verify_plan(plan.document()), identical_basis)` is false;
- changing environment name/digest, connection adapter, runtime adapter, contract version, observation, operation value, or operation order is true;
- an out-of-range integer in observation or operation details raises `PlanContractError` without exposing the raw value.

- [ ] **Step 6: Run Plan tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_planning.py -q
```

Expected: collection fails because `forge.planning` and the Plan schema do not exist.

- [ ] **Step 7: Implement the strict schema and immutable planning core**

Create `src/forge/resources/schemas/plan-v1alpha1.schema.json` as Draft 2020-12 with `$id` `https://forge.dev/schemas/v1alpha1/plan.json`, exact API/kind constants, and `additionalProperties: false` at root, metadata, spec, environment, planningAdapter, observation, operation, and resource objects. Require:

```text
metadata.id                  ^sha256:[0-9a-f]{64}$
spec.environment.name        same v1alpha1 Environment name pattern
spec.environment.configDigest ^sha256:[0-9a-f]{64}$
spec.planningAdapter.contractVersion const forge.dev/planning/v1alpha1
spec.planningAdapter.connectionAdapter/runtimeAdapter same adapter ID pattern
spec.observation.document    object
spec.observation.digest      ^sha256:[0-9a-f]{64}$
spec.operations              ordered array of strict operations
operation.id                 ^op-[1-9][0-9]*$
operation.action             create|update|replace|delete
operation.resource.kind/id   non-empty strings
operation.details            object
```

Create `src/forge/planning.py` with frozen `AdapterKey`, a frozen `PlanningBasis` that stores `observation_bytes` and `operations_bytes`, and artifact types that store canonical bytes. Use `json.loads` only to return fresh copies. Implement the exact ID projection by copying the materialized preimage, inserting `metadata.id` only after `sha256_identifier(preimage)`, and canonicalizing the final document. Load and self-check the packaged schema with `Draft202012Validator.check_schema`.

`verify_plan` must validate schema first, then operation-ID uniqueness, observation digest, and the Plan ID produced after omitting only `metadata.id`. Return `VerifiedPlan(canonical_bytes, plan_id)` or raise `PlanContractError` with an owned non-sensitive reason. `is_stale` accepts only `VerifiedPlan` and `PlanningBasis`, materializes the candidate ID, and compares IDs without I/O.

- [ ] **Step 8: Run Task 1 tests and the full foundation suite**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_canonical.py tests/unit/test_config.py tests/unit/test_planning.py -q
make validate
git diff --check
```

Expected: all tests and contracts pass; the valid Environment digest may change because the pre-release identity contract now uses RFC 8785.

- [ ] **Step 9: Commit Task 1 explicitly**

```bash
git add pyproject.toml src/forge/canonical.py src/forge/config.py src/forge/planning.py src/forge/resources/schemas/plan-v1alpha1.schema.json tests/unit/test_canonical.py tests/unit/test_config.py tests/unit/test_planning.py
git commit -m "feat: define canonical Forge plan artifacts"
```

---

### Task 2: Exact planning registry and no-op adapter

**Files:**
- Create: `src/forge/adapters.py`
- Create: `tests/unit/test_adapters.py`

**Interfaces:**
- Consumes: `AdapterKey`, `PlanningBasis`, `PlanArtifact`, and `create_plan` from Task 1.
- Produces: `PlanningAdapter` protocol, `PlanningUnavailable`, `PlanningRegistry`, `NoopPlanningAdapter`, `default_planning_registry`, and `plan_environment`.
- `PlanningUnavailable` exposes only `adapter_key` and one owned reason: `adapter not registered`, `observation unavailable`, or `invalid adapter result`.

- [ ] **Step 1: Write failing registry and no-op tests**

Create `tests/unit/test_adapters.py`. Build validated Environments from temporary YAML. Assert:

- `default_planning_registry().resolve(AdapterKey("noop", "noop"))` returns `NoopPlanningAdapter`;
- `ssh+systemd`, `noop+systemd`, and `ssh+noop` each raise `PlanningUnavailable` with `adapter not registered` and never resolve the no-op adapter;
- duplicate tuple registrations are rejected during registry construction;
- the registry owns an immutable copy of the injected mapping;
- `plan_environment(noop_environment, default_registry)` returns a Plan whose observation is `{}` and operations are `[]`;
- mapping-order-equivalent noop Environments produce identical Plan bytes and IDs;
- an injected adapter may return a deterministic observation and ordered operations without becoming a default;
- an adapter that signals observation unavailable produces only the owned redacted reason;
- observation/details with integer `9007199254740992` produces `invalid adapter result` and does not place that integer, opaque target config, or an absolute-path fixture in the exception;
- monkeypatched `socket.socket`, `subprocess.run`, `subprocess.Popen`, `Path.open`, `Path.stat`, and `Path.iterdir` raise if invoked while `NoopPlanningAdapter.observe` and `.plan` execute against an already validated Environment.

- [ ] **Step 2: Run adapter tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_adapters.py -q
```

Expected: collection fails because `forge.adapters` does not exist.

- [ ] **Step 3: Implement the exact immutable registry and no-op adapter**

Create `src/forge/adapters.py` with this protocol shape:

```python
class PlanningAdapter(Protocol):
    def observe(self, environment: ValidatedEnvironment) -> object: ...
    def plan(
        self, environment: ValidatedEnvironment, observation: object
    ) -> tuple[dict[str, object], ...]: ...
```

Construct `PlanningRegistry` from an iterable of `(AdapterKey, PlanningAdapter)` pairs, reject duplicate keys, and store a `MappingProxyType` over a private copied dict. `resolve` performs one exact lookup only. `default_planning_registry()` constructs exactly one registration for `AdapterKey("noop", "noop")`.

`NoopPlanningAdapter.observe` returns a new `{}` and `.plan` returns `()`. `plan_environment` derives the tuple from `environment.document["spec"]["target"]`, resolves the adapter, calls it once for observation and once for operations, creates `PlanningBasis`, and returns `create_plan`. Translate only owned observation-unavailable and canonical/contract failures into `PlanningUnavailable`; do not catch unexpected programming exceptions or use another adapter.

- [ ] **Step 4: Run Task 2 and cross-task tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_adapters.py tests/unit/test_planning.py tests/unit/test_config.py -q
make validate
git diff --check
```

Expected: all focused and full checks pass, with no network or target access.

- [ ] **Step 5: Commit Task 2 explicitly**

```bash
git add src/forge/adapters.py tests/unit/test_adapters.py
git commit -m "feat: add exact no-op planning adapter"
```

---

### Task 3: `forge plan` command and exit contract

**Files:**
- Modify: `src/forge/cli.py`
- Create: `tests/cli/test_plan.py`

**Interfaces:**
- Consumes: `load_and_validate`, `PlanningRegistry`, `PlanningUnavailable`, `default_planning_registry`, and `plan_environment`.
- Produces: `_run_plan(path: Path, stdout: TextIO, stderr: TextIO, registry: PlanningRegistry) -> int` and public `forge plan -f/--config PATH`.
- `main` constructs the default registry only for `plan`; `validate` behavior remains unchanged.

- [ ] **Step 1: Write failing CLI usage and success tests**

Create `tests/cli/test_plan.py` with a temporary valid `noop+noop` Environment. Assert:

- `main(["plan"])` returns 2, has empty stdout, and argparse reports required `-f/--config` on stderr;
- `main(["plan", "-f", path])` returns 0, empty stderr, exactly one JSON document plus one newline, and a document for which `verify_plan` succeeds;
- a second equivalent YAML with reordered mappings emits byte-identical stdout;
- success output contains neither a secret-like fixture value nor an absolute-path fixture placed in `spec.target.config`;
- existing `minimal.yaml` (`ssh+systemd`) returns 5, empty stdout, and exactly `PLAN_UNAVAILABLE ssh+systemd: adapter not registered\n`;
- `noop+systemd` and `ssh+noop` also return 5 without fallback.

- [ ] **Step 2: Write failing validation-precedence and adapter-failure tests**

Assert existing unreadable, invalid YAML, and schema-invalid fixtures return 3/3/4 through `plan` with the same owned prefixes as `validate`. Call `_run_plan` with a registry spy whose `resolve` raises if reached and prove invalid configuration never resolves or invokes an adapter. Inject an adapter that reports unavailable and one that returns an out-of-range integer; assert exit 5, no stdout, non-sensitive owned stderr, and no traceback.

- [ ] **Step 3: Run CLI tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest tests/cli/test_plan.py -q
```

Expected: tests fail because the parser has no `plan` command and `_run_plan` does not exist.

- [ ] **Step 4: Implement the minimal CLI path**

Add the `plan` subparser beside `validate`, with identical required `-f/--config` arguments. Keep the existing owned configuration error formatting by extracting a small shared helper only if it removes duplication without changing output.

Implement `_run_plan` in this exact order: load and validate; map read errors to 3; map configuration errors to 4; call `plan_environment`; map `PlanningUnavailable` to `PLAN_UNAVAILABLE {connection}+{runtime}: {owned_reason}` and 5; on success decode `artifact.canonical_bytes` as UTF-8 and write it plus `"\n"` to stdout. Do not print a status prefix or catch unexpected exceptions.

- [ ] **Step 5: Run CLI, unit, and full validation**

Run:

```bash
.venv/bin/python -m pytest tests/cli/test_plan.py tests/cli/test_validate.py -q
.venv/bin/python -m pytest -q
make validate
git diff --check
```

Expected: all tests pass and existing `forge validate` output/exit behavior remains intact.

- [ ] **Step 6: Commit Task 3 explicitly**

```bash
git add src/forge/cli.py tests/cli/test_plan.py
git commit -m "feat: expose deterministic forge plan"
```

---

### Task 4: Public evidence, package smoke, and cross-PC handoff

**Files:**
- Create: `examples/environments/noop.yaml`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `config/README.md`
- Modify: `examples/README.md`
- Modify: `tests/README.md`
- Modify: `Makefile`
- Modify: `tests/validate-contracts.sh`
- Modify: `.github/workflows/validate.yml`

**Interfaces:**
- Consumes: the final Task 3 CLI output and exit contract.
- Produces: one synthetic runnable planning example, durable contributor commands, repository contract checks, and installed-wheel planning evidence.

- [ ] **Step 1: Add the synthetic no-op Environment and contract assertions**

Create `examples/environments/noop.yaml`:

```yaml
apiVersion: forge.dev/v1alpha1
kind: Environment
metadata:
  name: example-noop
spec:
  target:
    connectionAdapter: noop
    runtimeAdapter: noop
```

Extend `tests/validate-contracts.sh` to parse `plan-v1alpha1.schema.json` with `python3 -m json.tool`, require the new example and planning design/plan files, and retain credential-safe quiet scanning. Do not duplicate Python semantic validation in shell.

- [ ] **Step 2: Add repository and installed-wheel planning smoke**

Extend `Makefile` help with `forge plan` evidence and add this final command to `validate` after the existing Environment smoke:

```make
	$(PYTHON) -m forge.cli plan --config examples/environments/noop.yaml
```

Extend `.github/workflows/validate.yml` wheel smoke with:

```yaml
- name: Smoke-test wheel planning command
  if: matrix.python-version == '3.12'
  run: wheel-smoke/bin/forge plan --config examples/environments/noop.yaml
```

Keep workflow permissions `contents: read`; do not add credentials or deployment jobs.

- [ ] **Step 3: Update public documentation without overclaiming**

Update the listed documents to state:

- implemented now: offline Environment validation and deterministic planning only for exact built-in `noop+noop`;
- `ssh+systemd` remains schema-valid but planning-unavailable until a later reviewed adapter slice;
- Plan instances are private review/audit data by default and do not prove deployability, safety, secret absence, or real target observation;
- `forge plan -f examples/environments/noop.yaml` performs no target access or mutation;
- apply, doctor, controller/state, real adapters, `forge-ops`, OCI reconciliation, merge, and deployment remain unimplemented or separately approval-gated;
- roadmap Slice 1 and Slice 2 are implemented on the feature branch, while Slice 3 is next.

Document the Python `>=3.12` setup, `make validate`, and both CLI examples so a new PC can reproduce the branch without local state.

- [ ] **Step 4: Run full source and distribution verification**

Run:

```bash
.venv/bin/python -m pip install -e '.[dev]'
make validate
make package
git diff --check origin/main...HEAD
```

Create a new temporary directory outside the repository, save the path printed
by `mktemp` as the task-specific `FORGE_PLANNING_SMOKE_DIR`, create its `venv`,
and install `dist/forge_control-0.1.0.dev0-py3-none-any.whl`:

```bash
FORGE_PLANNING_SMOKE_DIR="$(mktemp -d /tmp/forge-planning-wheel-smoke.XXXXXX)"
python3 -m venv "$FORGE_PLANNING_SMOKE_DIR/venv"
"$FORGE_PLANNING_SMOKE_DIR/venv/bin/pip" install dist/forge_control-0.1.0.dev0-py3-none-any.whl
"$FORGE_PLANNING_SMOKE_DIR/venv/bin/forge" --version
"$FORGE_PLANNING_SMOKE_DIR/venv/bin/forge" validate --config examples/environments/minimal.yaml
"$FORGE_PLANNING_SMOKE_DIR/venv/bin/forge" plan --config examples/environments/noop.yaml
```

Expected: version succeeds, validation prints one `VALID` line, and planning prints one schema-valid canonical Plan JSON document plus newline.

- [ ] **Step 5: Inspect portability and scope**

Run:

```bash
rg -n 'OCI|Hermes|Discord|Tailscale|Codex|/srv/forge' README.md AGENTS.md docs/architecture.md docs/roadmap.md
git status --short --branch
git log --oneline origin/main..HEAD
```

Expected: root matches only prohibit concrete defaults or link optional/future reference material; no OCI mutation or private configuration was added; tracked changes are only the intended Task 4 evidence files.

- [ ] **Step 6: Commit Task 4 explicitly**

```bash
git add .github/workflows/validate.yml Makefile README.md config/README.md docs/architecture.md docs/roadmap.md examples/README.md examples/environments/noop.yaml tests/README.md tests/validate-contracts.sh
git commit -m "ci: verify portable planning artifacts"
```

- [ ] **Step 7: Run final whole-branch review and publish the checkpoint**

Use `superpowers:requesting-code-review` over the Slice 2 design commit through Task 4 HEAD. Fix every Critical/Important finding through the SDD final fix wave and scoped re-review. Then run fresh `make validate`, package/wheel smoke, and `git diff --check`; push the existing branch; verify Draft PR #3 head and GitHub Actions for Python 3.12/3.14; and update the existing cross-PC handoff comment with the exact final SHA, validation evidence, remaining deferrals, and next resume prompt.

Do not mark the PR ready, merge it, close it without merge, deploy, access OCI, change the live Hermes/Discord connection, or create `forge-ops` in this plan.
