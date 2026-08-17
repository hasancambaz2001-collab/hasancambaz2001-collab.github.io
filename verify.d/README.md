# verify.d

Project-specific checks for `scripts/verify.sh`.

## Default

If `verify.d/commands.sh` is **absent**, `make verify` runs whatever generic checks fit the repo:

- `pytest -q` when `tests/` exists
- `npm test` when `package.json` has a `test` script
- `cargo test` when `Cargo.toml` exists
- `go test ./...` when `go.mod` exists

## Add project checks

Create `verify.d/commands.sh` (executable optional; verify runs it with `bash`):

```bash
#!/usr/bin/env bash
set -euo pipefail
# Exit non-zero on failure.
# Examples:
#   pytest -q
#   python3 scripts/check_invariants.py
#   npm test
```

When this file exists, **only** this file runs (the generic language fallbacks do not). Put every required check here, including pytest/npm/cargo/go if you still want them.

Do not put secrets in this directory.
