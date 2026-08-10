# Forge

Forge is a portable engineering-control framework for safe, repeatable,
reviewable AI-assisted engineering. It defines contracts and boundaries rather
than requiring one host, assistant, executor, or provider.

## Implemented now

The repository currently provides the constitution, runtime-neutral security
contracts, approved portable MVP design, an installable development package,
and offline validation of the `forge.dev/v1alpha1` environment contract.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/forge validate --config examples/environments/minimal.yaml
```

Implemented: installable development package and offline v1alpha1 validation.
Designed but not implemented: plan, apply, doctor, controller, runtime state,
and all concrete runtime adapters.

## Reference deployments

Concrete stacks are conformance evidence, not platform requirements. The first
example is the [Hermes, Discord, and Codex reference deployment](docs/reference-deployments/hermes-discord-codex/), which retains its decisions,
operations material, assets, prompts, scripts, and example contracts beside the
selected deployment. Its selected components must not be inferred as Forge
defaults.

## Read first

1. [FORGE_BOOTSTRAP.md](FORGE_BOOTSTRAP.md)
2. [AGENTS.md](AGENTS.md)
3. [Architecture](docs/architecture.md)
4. [Roadmap](docs/roadmap.md)
5. [Security policy](SECURITY.md) and [security contracts](docs/security/)
6. Relevant [ADRs](docs/adr/)

## Repository layout

- `docs/` contains portable architecture, security contracts, ADRs, and
  reference deployments.
- `prompts/`, `scripts/`, and `templates/` contain portable material only.
- `tests/` validates published contracts and structural boundaries.

Private deployment repositories may select versions and retain real inventory.
They must not place secrets, personal identifiers, or host-specific values in
this public repository.
