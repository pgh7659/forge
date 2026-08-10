# Portable Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore Forge's provider-independent public boundary and deliver an installable Python CLI that validates `forge.dev/v1alpha1` environment documents.

**Architecture:** Keep deployment-neutral policy, schemas, and CLI code at the repository root. Preserve the current OCI/Hermes/Discord/Codex material as a named public reference deployment rather than deleting it or treating it as Forge's identity. Implement `forge validate` as an offline operation over a packaged JSON Schema; target observation, planning, applying, the controller, and runtime adapters remain separate delivery slices.

**Tech Stack:** Python 3.12+, `argparse`, PyYAML 6.x, jsonschema 4.x, pytest 8/9, JSON Schema Draft 2020-12, setuptools, Bash, Make, GitHub Actions.

## Global Constraints

- This plan implements delivery slice 1 only: portable boundaries, `forge.dev/v1alpha1`, and `forge validate`.
- Do not create `pgh7659/forge-ops` in this slice.
- Do not connect to, inspect, or mutate OCI in this slice.
- Do not implement `forge plan`, `forge apply`, `forge doctor`, `forge-controller`, SQLite, Hermes hooks, or Codex execution in this slice.
- Root policy must not require OCI, Hermes, Discord, Tailscale, Codex, systemd, GitHub, or 1Password.
- Deployment-specific material must remain reviewable under `docs/reference-deployments/hermes-discord-codex/`.
- The public configuration API version is exactly `forge.dev/v1alpha1` and the document kind is exactly `Environment`.
- `forge validate` must perform no network or target access.
- The Python package requires Python 3.12 or newer and exposes the console command `forge`.
- The distribution name is `forge-control`; the import package is `forge`.
- CLI exit codes are `0` for valid input, `2` for command-line usage, `3` for file or YAML/JSON read errors, and `4` for schema-validation errors.
- Use TDD for executable behavior: observe each focused test fail before implementing the behavior that makes it pass.
- Keep current Draft PR work and unrelated user changes intact; use explicit file paths when staging.

---

## File Map

### Portable core

- `README.md`: public product identity, quick start, current implemented status, and links to reference deployments.
- `AGENTS.md`: runtime-neutral contribution rules and the boundary between core and reference deployments.
- `docs/architecture.md`: portable CLI/controller/adapter architecture; only the CLI and schema are marked implemented in this slice.
- `docs/roadmap.md`: ordered delivery slices from the approved design.
- `docs/adr/0009-separate-portable-core-from-deployment-profiles.md`: durable decision for public core versus private deployment configuration.
- `docs/adr/README.md`: index core ADRs and link to reference-deployment decisions.
- `docs/operations/README.md`: explains that root runbooks must be runtime-neutral.

### Preserved reference deployment

- `docs/reference-deployments/hermes-discord-codex/README.md`: scope, current evidence level, component selection, and navigation.
- `docs/reference-deployments/hermes-discord-codex/AGENTS.md`: OCI/Hermes/Discord/Codex-specific operating rules moved out of root policy.
- `docs/reference-deployments/hermes-discord-codex/decisions/`: existing ADR-0001 through ADR-0006 and the existing Hermes/Codex ADR-0008.
- `docs/reference-deployments/hermes-discord-codex/operations/`: existing Hermes, Discord, Codex, and OCI runbooks.
- `docs/reference-deployments/hermes-discord-codex/prompts/hermes-assistant-soul.md`: existing Hermes prompt.
- `docs/reference-deployments/hermes-discord-codex/assets/caddy/`: existing Tailnet Caddy assets.
- `docs/reference-deployments/hermes-discord-codex/assets/systemd/`: existing Hermes systemd assets.
- `docs/reference-deployments/hermes-discord-codex/scripts/audit-oci-host.sh`: existing read-only OCI audit script.
- `docs/reference-deployments/hermes-discord-codex/contracts/`: existing Codex task/result examples.
- `prompts/README.md`: point concrete prompts at the named reference deployment.
- `scripts/README.md`: distinguish portable scripts from reference-deployment scripts.
- `templates/README.md`: distinguish portable templates from executor-specific contracts.

### Executable portable foundation

- `pyproject.toml`: package metadata, dependencies, console entry point, package data, and pytest configuration.
- `src/forge/__init__.py`: package version.
- `src/forge/cli.py`: parser, `--version`, `validate` dispatch, output, and exit-code contract.
- `src/forge/config.py`: YAML/JSON loading, JSON Schema validation, JSON Pointer rendering, and canonical digest.
- `src/forge/resources/schemas/environment-v1alpha1.schema.json`: packaged public schema source of truth.
- `examples/environments/minimal.yaml`: generic, secret-free valid environment.
- `tests/unit/test_config.py`: loader, schema, issue ordering, and digest tests.
- `tests/cli/test_validate.py`: CLI success, read error, parse error, and validation error tests.
- `tests/fixtures/environments/invalid-extra-key.yaml`: deterministic schema failure fixture.
- `tests/fixtures/environments/invalid-syntax.yaml`: deterministic YAML parse failure fixture.
- `tests/validate-contracts.sh`: public-tree safety, reference-boundary, JSON, and credential-pattern checks.
- `Makefile`: setup, test, contract, validate, and package entry points.
- `.github/workflows/validate.yml`: Python 3.12/3.14 validation and wheel smoke installation.

---

### Task 1: Move deployment choices behind the reference-deployment boundary

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/adr/README.md`
- Create: `docs/adr/0009-separate-portable-core-from-deployment-profiles.md`
- Create: `docs/operations/README.md`
- Create: `docs/reference-deployments/hermes-discord-codex/README.md`
- Create: `docs/reference-deployments/hermes-discord-codex/AGENTS.md`
- Modify: `prompts/README.md`
- Modify: `scripts/README.md`
- Modify: `templates/README.md`
- Move: deployment-specific ADRs, runbooks, prompt, scripts, service assets, and Codex examples listed in the File Map
- Modify: `tests/validate-contracts.sh`
- Modify: `docs/superpowers/specs/2026-08-10-portable-forge-mvp-design.md`

**Interfaces:**
- Consumes: the approved portable MVP design and all existing deployment-specific documents on the branch.
- Produces: a root documentation boundary in which core rules are portable and `docs/reference-deployments/hermes-discord-codex/` owns the concrete first deployment.

- [ ] **Step 1: Add failing structural checks for the new boundary**

Add these required-path and root-document assertions to `tests/validate-contracts.sh`, replacing the current list that requires deployment files at root paths:

```bash
bash -n \
  docs/reference-deployments/hermes-discord-codex/scripts/audit-oci-host.sh
python3 -m json.tool \
  docs/reference-deployments/hermes-discord-codex/contracts/codex-task-envelope.example.json \
  >/dev/null
python3 -m json.tool \
  docs/reference-deployments/hermes-discord-codex/contracts/codex-result.example.json \
  >/dev/null

required_files=(
  docs/adr/0009-separate-portable-core-from-deployment-profiles.md
  docs/operations/README.md
  docs/reference-deployments/hermes-discord-codex/README.md
  docs/reference-deployments/hermes-discord-codex/AGENTS.md
  docs/reference-deployments/hermes-discord-codex/operations/discord-forum-codex-routing.md
  docs/reference-deployments/hermes-discord-codex/prompts/hermes-assistant-soul.md
  docs/reference-deployments/hermes-discord-codex/contracts/codex-task-envelope.example.json
  docs/reference-deployments/hermes-discord-codex/contracts/codex-result.example.json
)

for required_file in "${required_files[@]}"; do
  test -s "$required_file"
done

grep -q 'portable engineering-control framework' README.md
grep -q 'Reference deployments' docs/architecture.md
grep -q 'Deployment-specific rules' AGENTS.md
```

- [ ] **Step 2: Run the structural contract and confirm failure**

Run: `./tests/validate-contracts.sh`

Expected: non-zero exit because the new ADR and reference-deployment paths do not exist.

- [ ] **Step 3: Move concrete deployment material without deleting history**

Create the target directories, then use `git mv` for these exact mappings:

```text
docs/adr/0001-use-hermes-as-initial-orchestrator.md
  -> docs/reference-deployments/hermes-discord-codex/decisions/0001-use-hermes-as-initial-orchestrator.md
docs/adr/0002-use-host-install-on-oci-for-first-deployment.md
  -> docs/reference-deployments/hermes-discord-codex/decisions/0002-use-host-install-on-oci-for-first-deployment.md
docs/adr/0003-use-discord-as-primary-operator-interface.md
  -> docs/reference-deployments/hermes-discord-codex/decisions/0003-use-discord-as-primary-operator-interface.md
docs/adr/0004-use-tailscale-for-private-dashboard-access.md
  -> docs/reference-deployments/hermes-discord-codex/decisions/0004-use-tailscale-for-private-dashboard-access.md
docs/adr/0005-use-protected-checkouts-and-hermes-worktrees.md
  -> docs/reference-deployments/hermes-discord-codex/decisions/0005-use-protected-checkouts-and-hermes-worktrees.md
docs/adr/0006-use-hermes-profiles-kanban-and-provider-fallback.md
  -> docs/reference-deployments/hermes-discord-codex/decisions/0006-use-hermes-profiles-kanban-and-provider-fallback.md
docs/adr/0008-separate-assistant-control-plane-from-engineering-execution.md
  -> docs/reference-deployments/hermes-discord-codex/decisions/0008-separate-assistant-control-plane-from-engineering-execution.md
docs/operations/assistant-codex-handoff.md
  -> docs/reference-deployments/hermes-discord-codex/operations/assistant-codex-handoff.md
docs/operations/discord-forum-codex-routing.md
  -> docs/reference-deployments/hermes-discord-codex/operations/discord-forum-codex-routing.md
docs/operations/hermes-incident-runbook.md
  -> docs/reference-deployments/hermes-discord-codex/operations/hermes-incident-runbook.md
docs/operations/oci-assistant-control-plane-migration.md
  -> docs/reference-deployments/hermes-discord-codex/operations/oci-assistant-control-plane-migration.md
docs/operations/oci-environment-audit.md
  -> docs/reference-deployments/hermes-discord-codex/operations/oci-environment-audit.md
prompts/hermes-assistant-soul.md
  -> docs/reference-deployments/hermes-discord-codex/prompts/hermes-assistant-soul.md
caddy/Caddyfile.tailnet
  -> docs/reference-deployments/hermes-discord-codex/assets/caddy/Caddyfile.tailnet
caddy/README.md
  -> docs/reference-deployments/hermes-discord-codex/assets/caddy/README.md
systemd/hermes-dashboard.service
  -> docs/reference-deployments/hermes-discord-codex/assets/systemd/hermes-dashboard.service
systemd/README.md
  -> docs/reference-deployments/hermes-discord-codex/assets/systemd/README.md
scripts/audit-oci-host.sh
  -> docs/reference-deployments/hermes-discord-codex/scripts/audit-oci-host.sh
templates/codex-task-envelope.example.json
  -> docs/reference-deployments/hermes-discord-codex/contracts/codex-task-envelope.example.json
templates/codex-result.example.json
  -> docs/reference-deployments/hermes-discord-codex/contracts/codex-result.example.json
```

Update relative paths inside moved documents to their new reference root. Do not rewrite the historical decisions; add a `Scope` paragraph stating that they govern only the named reference deployment.

- [ ] **Step 4: Write the portable root documents and boundary ADR**

Write root documents with these exact responsibilities:

```text
README.md
  Product: portable engineering-control framework
  Implemented now: constitution, security contracts, design, repository scaffold
  First executable milestone: forge.dev/v1alpha1 + forge validate
  Concrete stack: linked reference deployment, never a platform requirement

AGENTS.md
  Core changes remain provider-neutral
  Adapter-specific rules live beside the adapter/reference deployment
  Root docs may name implementations only as examples or evidence
  Deployment-specific rules: follow the nested reference AGENTS.md
  Infrastructure mutation remains approval-gated

docs/architecture.md
  Configuration -> Forge CLI -> provisioner -> controller -> adapters
  Clearly label CLI/schema as this slice and controller/adapters as proposed
  Link the approved portable MVP design

docs/roadmap.md
  Copy the eight ordered delivery slices from the approved design
  Keep forge-ops creation after the configuration contract
  Keep OCI reconciliation last and separately approved
```

Create ADR-0009 with decision: public Forge owns executable contracts and adapter interfaces; private deployment repositories own selected versions and real inventory; named public reference deployments provide conformance evidence without becoming core defaults.

Create the nested reference `AGENTS.md` by moving the OCI/Hermes, Discord, Codex, `/srv/forge`, systemd, and single-executor rules out of the root agent policy. Create the reference `README.md` with sections `Purpose`, `Selected Components`, `Evidence Level`, `Operations`, `Decisions`, `Contracts`, and `Not Core Requirements`.

- [ ] **Step 5: Run the structural contract and inspect references**

Run: `./tests/validate-contracts.sh`

Expected: exit 0 and `contract validation passed`.

Run: `rg -n 'docs/operations/(assistant-codex|discord-forum|hermes-incident|oci-)' README.md AGENTS.md docs/architecture.md docs/roadmap.md docs/adr docs/operations`

Expected: no stale root operation links.

- [ ] **Step 6: Commit the boundary change**

```bash
git add README.md AGENTS.md docs prompts scripts templates tests
git commit -m "docs: separate portable core from reference deployment"
```

---

### Task 2: Establish an installable Forge CLI package

**Files:**
- Create: `pyproject.toml`
- Create: `src/forge/__init__.py`
- Create: `src/forge/cli.py`
- Create: `tests/cli/test_version.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Python 3.12+.
- Produces: `forge.cli.build_parser() -> argparse.ArgumentParser`, `forge.cli.main(argv: Sequence[str] | None = None) -> int`, `forge.__version__ == "0.1.0.dev0"`, and the console command `forge`.

- [ ] **Step 1: Bootstrap an isolated test runner**

Run: `python3 -m venv .venv`

Run: `.venv/bin/python -m pip install 'pytest>=8.3,<10'`

Expected: pytest installs into `.venv`; no project package is installed yet.

- [ ] **Step 2: Write the failing version and parser tests**

Create `tests/cli/test_version.py`:

```python
from forge import __version__
from forge.cli import build_parser, main


def test_version_is_initial_development_release() -> None:
    assert __version__ == "0.1.0.dev0"


def test_parser_uses_forge_program_name() -> None:
    assert build_parser().prog == "forge"


def test_version_flag_prints_version(capsys) -> None:
    exit_code = main(["--version"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "forge 0.1.0.dev0\n"
    assert captured.err == ""
```

- [ ] **Step 3: Run the test and confirm import failure**

Run: `.venv/bin/python -m pytest tests/cli/test_version.py -q`

Expected: failure because the `forge` package does not exist.

- [ ] **Step 4: Add package metadata and minimal CLI implementation**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=75,<82"]
build-backend = "setuptools.build_meta"

[project]
name = "forge-control"
version = "0.1.0.dev0"
description = "Portable control framework for reproducible AI-assisted engineering"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "jsonschema>=4.23,<5",
  "PyYAML>=6.0.2,<7",
]

[project.optional-dependencies]
dev = [
  "build>=1.2,<2",
  "pytest>=8.3,<10",
]

[project.scripts]
forge = "forge.cli:main"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
forge = ["resources/schemas/*.json"]

[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["tests"]
```

Create `src/forge/__init__.py`:

```python
__version__ = "0.1.0.dev0"
```

Create `src/forge/cli.py`:

```python
from __future__ import annotations

import argparse
from collections.abc import Sequence

from forge import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forge",
        description="Validate and reconcile portable Forge environments.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"forge {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Add `.eggs/`, `*.egg-info/`, and `wheel-smoke/` to `.gitignore`.

- [ ] **Step 5: Install the package and complete development dependencies**

Run: `.venv/bin/python -m pip install -e '.[dev]'`

Expected: editable installation succeeds and installs PyYAML, jsonschema, pytest, and build.

- [ ] **Step 6: Run the focused test**

Run: `.venv/bin/python -m pytest tests/cli/test_version.py -q`

Expected: 3 tests pass.

- [ ] **Step 7: Build the wheel and smoke-test the console entry point**

Run: `.venv/bin/python -m build`

Expected: one source distribution and one wheel are created under `dist/`.

Run: `.venv/bin/forge --version`

Expected: `forge 0.1.0.dev0`.

- [ ] **Step 8: Commit the package scaffold**

```bash
git add .gitignore pyproject.toml src/forge tests/cli/test_version.py
git commit -m "feat: add installable Forge CLI"
```

---

### Task 3: Define and validate `forge.dev/v1alpha1`

**Files:**
- Create: `src/forge/resources/schemas/environment-v1alpha1.schema.json`
- Create: `src/forge/config.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/fixtures/environments/invalid-extra-key.yaml`
- Create: `tests/fixtures/environments/invalid-syntax.yaml`
- Create: `tests/fixtures/environments/invalid-duplicate-key.yaml`
- Create: `examples/environments/minimal.yaml`

**Interfaces:**
- Consumes: packaged JSON Schema resources, PyYAML, and jsonschema Draft 2020-12.
- Produces: `ConfigReadError`, `ConfigValidationError`, `ValidationIssue`, `ValidatedEnvironment`, `load_raw_document(path: Path) -> object`, `validate_document(document: object) -> ValidatedEnvironment`, and `load_and_validate(path: Path) -> ValidatedEnvironment`.

- [ ] **Step 1: Write failing loader, schema, and digest tests**

Create `tests/unit/test_config.py`:

```python
from pathlib import Path

import pytest

from forge.config import (
    ConfigReadError,
    ConfigValidationError,
    load_and_validate,
)


ROOT = Path(__file__).resolve().parents[2]


def test_minimal_environment_is_valid() -> None:
    result = load_and_validate(ROOT / "examples/environments/minimal.yaml")

    assert result.name == "example-primary"
    assert result.api_version == "forge.dev/v1alpha1"
    assert len(result.digest) == 64


def test_unknown_property_reports_json_pointer() -> None:
    with pytest.raises(ConfigValidationError) as raised:
        load_and_validate(
            ROOT / "tests/fixtures/environments/invalid-extra-key.yaml"
        )

    assert raised.value.issues[0].pointer == "/spec/unexpected"
    assert "Additional properties are not allowed" in raised.value.issues[0].message


def test_invalid_yaml_is_a_read_error() -> None:
    with pytest.raises(ConfigReadError) as raised:
        load_and_validate(ROOT / "tests/fixtures/environments/invalid-syntax.yaml")

    assert "cannot parse YAML or JSON" in str(raised.value)


def test_duplicate_key_is_a_read_error() -> None:
    with pytest.raises(ConfigReadError) as raised:
        load_and_validate(
            ROOT / "tests/fixtures/environments/invalid-duplicate-key.yaml"
        )

    assert "duplicate mapping key" in str(raised.value)


def test_non_utf8_document_is_a_read_error(tmp_path: Path) -> None:
    path = tmp_path / "non-utf8.yaml"
    path.write_bytes(b"\xff")

    with pytest.raises(ConfigReadError) as raised:
        load_and_validate(path)

    assert "cannot decode UTF-8" in str(raised.value)


def test_digest_is_independent_of_mapping_order(tmp_path: Path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text(
        "apiVersion: forge.dev/v1alpha1\nkind: Environment\n"
        "metadata: {name: same}\nspec:\n  target:\n"
        "    connectionAdapter: ssh\n    runtimeAdapter: systemd\n",
        encoding="utf-8",
    )
    second.write_text(
        "kind: Environment\nspec:\n  target:\n"
        "    runtimeAdapter: systemd\n    connectionAdapter: ssh\n"
        "metadata: {name: same}\napiVersion: forge.dev/v1alpha1\n",
        encoding="utf-8",
    )

    assert load_and_validate(first).digest == load_and_validate(second).digest
```

- [ ] **Step 2: Run the tests and confirm missing configuration API**

Run: `.venv/bin/python -m pytest tests/unit/test_config.py -q`

Expected: collection fails because `forge.config` does not exist.

- [ ] **Step 3: Add the versioned environment schema**

Create `src/forge/resources/schemas/environment-v1alpha1.schema.json` with this complete contract:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://forge.dev/schemas/v1alpha1/environment.json",
  "title": "Forge Environment v1alpha1",
  "type": "object",
  "additionalProperties": false,
  "required": ["apiVersion", "kind", "metadata", "spec"],
  "properties": {
    "apiVersion": {"const": "forge.dev/v1alpha1"},
    "kind": {"const": "Environment"},
    "metadata": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name"],
      "properties": {
        "name": {
          "type": "string",
          "minLength": 1,
          "maxLength": 63,
          "pattern": "^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$"
        }
      }
    },
    "spec": {
      "type": "object",
      "additionalProperties": false,
      "required": ["target"],
      "properties": {
        "target": {"$ref": "#/$defs/target"},
        "gateway": {"$ref": "#/$defs/adapterSelection"},
        "assistant": {"$ref": "#/$defs/adapterSelection"},
        "executor": {"$ref": "#/$defs/executorSelection"},
        "state": {"$ref": "#/$defs/adapterSelection"},
        "workspace": {"$ref": "#/$defs/adapterSelection"},
        "sourceControl": {"$ref": "#/$defs/adapterSelection"},
        "secrets": {"$ref": "#/$defs/adapterSelection"}
      }
    }
  },
  "$defs": {
    "adapterId": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
    },
    "adapterSelection": {
      "type": "object",
      "additionalProperties": false,
      "required": ["adapter"],
      "properties": {
        "adapter": {"$ref": "#/$defs/adapterId"},
        "config": {"type": "object"}
      }
    },
    "executorSelection": {
      "type": "object",
      "additionalProperties": false,
      "required": ["adapter"],
      "properties": {
        "adapter": {"$ref": "#/$defs/adapterId"},
        "config": {"type": "object"},
        "maxConcurrency": {"type": "integer", "minimum": 1}
      }
    },
    "target": {
      "type": "object",
      "additionalProperties": false,
      "required": ["connectionAdapter", "runtimeAdapter"],
      "properties": {
        "connectionAdapter": {"$ref": "#/$defs/adapterId"},
        "runtimeAdapter": {"$ref": "#/$defs/adapterId"},
        "config": {"type": "object"}
      }
    }
  }
}
```

Before implementation, run `.venv/bin/python -c "import json; from importlib.resources import files; from jsonschema import Draft202012Validator; schema=json.loads(files('forge').joinpath('resources/schemas/environment-v1alpha1.schema.json').read_text()); Draft202012Validator.check_schema(schema)"` after the resource loader exists. A non-zero exit means the checked-in schema must be corrected before continuing.

- [ ] **Step 4: Add generic valid and invalid fixtures**

Create `examples/environments/minimal.yaml`:

```yaml
apiVersion: forge.dev/v1alpha1
kind: Environment
metadata:
  name: example-primary
spec:
  target:
    connectionAdapter: ssh
    runtimeAdapter: systemd
  gateway:
    adapter: example-messaging
  executor:
    adapter: example-executor
    maxConcurrency: 1
  state:
    adapter: sqlite
```

Create `tests/fixtures/environments/invalid-extra-key.yaml`:

```yaml
apiVersion: forge.dev/v1alpha1
kind: Environment
metadata:
  name: invalid-extra-key
spec:
  target:
    connectionAdapter: ssh
    runtimeAdapter: systemd
  unexpected: true
```

Create `tests/fixtures/environments/invalid-syntax.yaml`:

```yaml
apiVersion: forge.dev/v1alpha1
kind: Environment
metadata: [name: broken
```

Create `tests/fixtures/environments/invalid-duplicate-key.yaml`:

```yaml
apiVersion: forge.dev/v1alpha1
kind: Environment
metadata:
  name: first
  name: second
spec:
  target:
    connectionAdapter: ssh
    runtimeAdapter: systemd
```

- [ ] **Step 5: Implement the configuration API**

Create `src/forge/config.py` with these types and behaviors:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


class ConfigReadError(Exception):
    """The document could not be read or parsed."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects ambiguous duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate mapping key: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    pointer: str
    message: str


class ConfigValidationError(Exception):
    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__(f"environment has {len(issues)} validation issue(s)")


@dataclass(frozen=True, slots=True)
class ValidatedEnvironment:
    name: str
    api_version: str
    digest: str
    document: dict[str, Any]


def _json_pointer(parts: list[object]) -> str:
    if not parts:
        return "/"
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(encoded)


def _issue_pointer(error: Any) -> str:
    parts = list(error.absolute_path)
    if error.validator == "additionalProperties" and isinstance(
        error.instance, dict
    ):
        known = set(error.schema.get("properties", {}))
        unexpected = sorted(set(error.instance) - known)
        if len(unexpected) == 1:
            parts.append(unexpected[0])
    return _json_pointer(parts)


def _schema() -> dict[str, Any]:
    resource = files("forge").joinpath(
        "resources/schemas/environment-v1alpha1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def load_raw_document(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigReadError(f"cannot read {path}: {exc.strerror}") from exc
    except UnicodeError as exc:
        raise ConfigReadError(f"cannot decode UTF-8 from {path}: {exc}") from exc

    try:
        return yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ConfigReadError(f"cannot parse YAML or JSON from {path}: {exc}") from exc


def validate_document(document: object) -> ValidatedEnvironment:
    validator = Draft202012Validator(_schema())
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    if errors:
        issues = tuple(
            ValidationIssue(
                pointer=_issue_pointer(error),
                message=error.message,
            )
            for error in errors
        )
        raise ConfigValidationError(issues)

    assert isinstance(document, dict)
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return ValidatedEnvironment(
        name=document["metadata"]["name"],
        api_version=document["apiVersion"],
        digest=hashlib.sha256(canonical).hexdigest(),
        document=document,
    )


def load_and_validate(path: Path) -> ValidatedEnvironment:
    return validate_document(load_raw_document(path))
```

The `_issue_pointer` helper derives an unexpected key from the validated
instance and schema instead of parsing jsonschema's human-readable error text.
For the fixture above the pointer is `/spec/unexpected`; when multiple unknown
keys are present it deliberately retains the containing-object pointer.

- [ ] **Step 6: Run the focused tests and schema self-check**

Run: `.venv/bin/python -m pytest tests/unit/test_config.py -q`

Expected: 6 tests pass.

Run: `.venv/bin/python -c "from forge.config import _schema; print(_schema()['$id'])"`

Expected: `https://forge.dev/schemas/v1alpha1/environment.json`.

- [ ] **Step 7: Commit the schema and loader**

```bash
git add src/forge/config.py src/forge/resources examples/environments tests/unit tests/fixtures
git commit -m "feat: validate portable environment contracts"
```

---

### Task 4: Expose the stable `forge validate` command contract

**Files:**
- Modify: `src/forge/cli.py`
- Create: `tests/cli/test_validate.py`

**Interfaces:**
- Consumes: `forge.config.load_and_validate`, `ConfigReadError`, and `ConfigValidationError`.
- Produces: `forge validate --config PATH`, success output `VALID <name> <apiVersion> sha256:<digest>`, deterministic issue lines, and exit codes 0/3/4.

- [ ] **Step 1: Write failing CLI behavior tests**

Create `tests/cli/test_validate.py`:

```python
from pathlib import Path

from forge.cli import main


ROOT = Path(__file__).resolve().parents[2]


def test_validate_prints_identity_and_digest(capsys) -> None:
    exit_code = main(
        ["validate", "--config", str(ROOT / "examples/environments/minimal.yaml")]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.startswith(
        "VALID example-primary forge.dev/v1alpha1 sha256:"
    )
    assert len(captured.out.strip().rsplit(":", 1)[1]) == 64
    assert captured.err == ""


def test_validate_reports_missing_file(capsys) -> None:
    exit_code = main(["validate", "--config", "does-not-exist.yaml"])
    captured = capsys.readouterr()

    assert exit_code == 3
    assert captured.out == ""
    assert captured.err.startswith("READ_ERROR does-not-exist.yaml:")


def test_validate_reports_parse_error(capsys) -> None:
    path = ROOT / "tests/fixtures/environments/invalid-syntax.yaml"
    exit_code = main(["validate", "--config", str(path)])
    captured = capsys.readouterr()

    assert exit_code == 3
    assert captured.out == ""
    assert "cannot parse YAML or JSON" in captured.err


def test_validate_reports_schema_issues(capsys) -> None:
    path = ROOT / "tests/fixtures/environments/invalid-extra-key.yaml"
    exit_code = main(["validate", "--config", str(path)])
    captured = capsys.readouterr()

    assert exit_code == 4
    assert captured.out == ""
    assert captured.err.startswith("INVALID 1 issue(s)\n")
    assert "/spec/unexpected:" in captured.err
```

- [ ] **Step 2: Run the tests and confirm the missing subcommand failure**

Run: `.venv/bin/python -m pytest tests/cli/test_validate.py -q`

Expected: failures because `build_parser()` does not define `validate`.

- [ ] **Step 3: Implement validate dispatch and deterministic output**

Extend `src/forge/cli.py` with:

```python
import sys
from pathlib import Path
from typing import TextIO

from forge.config import ConfigReadError, ConfigValidationError, load_and_validate


def _run_validate(path: Path, stdout: TextIO, stderr: TextIO) -> int:
    try:
        environment = load_and_validate(path)
    except ConfigReadError as exc:
        print(f"READ_ERROR {path}: {exc}", file=stderr)
        return 3
    except ConfigValidationError as exc:
        print(f"INVALID {len(exc.issues)} issue(s)", file=stderr)
        for issue in exc.issues:
            print(f"{issue.pointer}: {issue.message}", file=stderr)
        return 4

    print(
        f"VALID {environment.name} {environment.api_version} "
        f"sha256:{environment.digest}",
        file=stdout,
    )
    return 0
```

In `build_parser()`, add required subcommands without breaking root `--version`:

```python
subcommands = parser.add_subparsers(dest="command")
validate_parser = subcommands.add_parser(
    "validate",
    help="Validate a Forge environment without target access.",
)
validate_parser.add_argument(
    "-f",
    "--config",
    type=Path,
    required=True,
    help="Path to a forge.dev/v1alpha1 Environment YAML or JSON document.",
)
```

Replace `main()` with this exact dispatch while retaining the module entry
point at the bottom of the file:

```python
def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    if args.command == "validate":
        return _run_validate(args.config, sys.stdout, sys.stderr)

    parser.print_help()
    return 2
```

- [ ] **Step 4: Run all CLI tests**

Run: `.venv/bin/python -m pytest tests/cli -q`

Expected: 7 tests pass.

- [ ] **Step 5: Exercise the installed command**

Run: `.venv/bin/forge validate --config examples/environments/minimal.yaml`

Expected: one line beginning `VALID example-primary forge.dev/v1alpha1 sha256:` and exit 0.

Run: `.venv/bin/forge validate --config tests/fixtures/environments/invalid-extra-key.yaml`

Expected: `INVALID 1 issue(s)` followed by `/spec/unexpected:` and exit 4.

- [ ] **Step 6: Commit the command contract**

```bash
git add src/forge/cli.py tests/cli/test_validate.py
git commit -m "feat: expose offline environment validation"
```

---

### Task 5: Integrate validation, packaging, and public quick start

**Files:**
- Modify: `Makefile`
- Modify: `.github/workflows/validate.yml`
- Modify: `tests/validate-contracts.sh`
- Modify: `tests/README.md`
- Modify: `config/README.md`
- Modify: `examples/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: installable `forge-control`, the valid example, pytest, and the structural contract script.
- Produces: `make setup`, `make test`, `make contracts`, `make validate`, `make package`, a Python 3.12/3.14 CI matrix, and a wheel-install smoke test.

- [ ] **Step 1: Add a failing package-resource contract check**

Extend `tests/validate-contracts.sh` with:

```bash
python3 -m json.tool \
  src/forge/resources/schemas/environment-v1alpha1.schema.json >/dev/null

test -s pyproject.toml
test -s examples/environments/minimal.yaml
```

Update the credential-pattern scan to exclude `.venv`, `build`, `dist`, and
`wheel-smoke` in addition to `.git`; those generated dependency and package
trees are not public source inputs. Run the script before adding the schema
checks and confirm it fails because the schema and package metadata do not
exist.

- [ ] **Step 2: Define local Make targets**

Replace `Makefile` with:

```make
.DEFAULT_GOAL := help

PYTHON ?= .venv/bin/python

.PHONY: help setup test contracts validate package
help:
	@printf '%s\n' 'Forge portable control framework'
	@printf '%s\n' 'make setup      Create .venv and install development dependencies.'
	@printf '%s\n' 'make test       Run Python tests.'
	@printf '%s\n' 'make contracts  Validate public files and secret patterns.'
	@printf '%s\n' 'make validate   Run contracts, tests, and the valid example.'
	@printf '%s\n' 'make package    Build source and wheel distributions.'

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e '.[dev]'

test:
	$(PYTHON) -m pytest

contracts:
	./tests/validate-contracts.sh

validate: contracts test
	$(PYTHON) -m forge.cli validate --config examples/environments/minimal.yaml

package:
	$(PYTHON) -m build
```

- [ ] **Step 3: Update CI for supported Python versions and wheel smoke testing**

Change `.github/workflows/validate.yml` to:

```yaml
name: Validate Forge contracts and CLI

on:
  pull_request:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  validate:
    strategy:
      matrix:
        python-version: ["3.12", "3.14"]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - name: Install development dependencies
        run: python -m pip install -e '.[dev]'
      - name: Validate contracts and CLI
        run: make validate PYTHON=python
      - name: Build distributions
        if: matrix.python-version == '3.12'
        run: python -m build
      - name: Smoke-test wheel installation
        if: matrix.python-version == '3.12'
        run: |
          python -m venv wheel-smoke
          wheel-smoke/bin/pip install dist/forge_control-0.1.0.dev0-py3-none-any.whl
          wheel-smoke/bin/forge --version
          wheel-smoke/bin/forge validate --config examples/environments/minimal.yaml
```

- [ ] **Step 4: Document only implemented commands and boundaries**

Add this quick-start flow to `README.md`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/forge validate --config examples/environments/minimal.yaml
```

State directly beside it:

```text
Implemented: installable development package and offline v1alpha1 validation.
Designed but not implemented: plan, apply, doctor, controller, runtime state,
and all concrete runtime adapters.
```

Document in `config/README.md` that real environment configuration and secret
references belong in a private deployment repository after schema
compatibility is established. Document in `examples/README.md` that examples
are synthetic inputs and are not evidence of deployed infrastructure. Update
`tests/README.md` with the exact `make setup` and `make validate` workflow.

- [ ] **Step 5: Run the full validation and package smoke sequence**

Run: `make validate`

Expected: all pytest tests pass, the structural script prints `contract validation passed`, and the CLI prints a `VALID` line.

Run: `make package`

Expected: source distribution and wheel build successfully.

Run: `python3 -m venv wheel-smoke`

Run: `wheel-smoke/bin/pip install dist/forge_control-0.1.0.dev0-py3-none-any.whl`

Run: `wheel-smoke/bin/forge validate --config examples/environments/minimal.yaml`

Expected: the installed wheel prints the same `VALID` contract and returns 0.

- [ ] **Step 6: Commit integration and documentation**

```bash
git add .github/workflows/validate.yml Makefile README.md config/README.md examples/README.md tests
git commit -m "ci: verify portable Forge distributions"
```

---

### Task 6: Perform slice acceptance and prepare the Draft PR for review

**Files:**
- Verify only; modify documentation or tests only if acceptance reveals a specific defect.

**Interfaces:**
- Consumes: Tasks 1-5 and the approved portable MVP design.
- Produces: evidence that delivery slice 1 is portable, installable, offline, and contains no OCI mutation.

- [ ] **Step 1: Run fresh repository acceptance**

Run: `make validate`

Expected: exit 0 with all tests passing, `contract validation passed`, and one valid-environment line.

Run: `git diff --check origin/main...HEAD`

Expected: no output and exit 0.

- [ ] **Step 2: Inspect root coupling and reference preservation**

Run: `rg -n 'OCI|Hermes|Discord|Tailscale|Codex|/srv/forge' README.md AGENTS.md docs/architecture.md docs/roadmap.md`

Expected: any matches describe optional examples or link to a reference deployment; no sentence makes one of these a core requirement.

Run: `find docs/reference-deployments/hermes-discord-codex -type f | sort`

Expected: decisions, operations, prompt, Caddy, systemd, audit script, and Codex contracts are all present.

- [ ] **Step 3: Verify CLI is offline**

Run: `.venv/bin/forge validate --config examples/environments/minimal.yaml`

Expected: success without SSH, network, OCI, Discord, GitHub, Hermes, or Codex access.

- [ ] **Step 4: Inspect commit scope and history**

Run: `git status --short --branch`

Expected: no unstaged implementation files and the feature branch is ahead of its remote only by intentional commits.

Run: `git log --oneline origin/main..HEAD`

Expected: focused design, boundary, CLI, schema, command, and CI commits.

- [ ] **Step 5: Publish only after final review**

Use the `github:yeet` workflow to re-check authentication and scope, push the
existing `feat/assistant-control-plane` branch, update Draft PR #3 so its title
and body describe the portable foundation rather than an OCI/Codex platform,
and report CI status. Do not mark the PR ready for review and do not merge it.
