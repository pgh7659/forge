# Tests

Validation and regression checks live here.

Tests should focus first on contracts, safety rules, and repeatable workflows.

Set up the local development environment and run the complete validation flow:

```bash
make setup
make validate
```

`make validate` syntax-checks public scripts, validates JSON contracts and the
synthetic `forge.dev/v1alpha1` environment, runs the Python test suite, asserts
required public artifacts, scans source inputs for common credential patterns,
and runs a controlled regression proving scanner failures do not echo matched
values.
