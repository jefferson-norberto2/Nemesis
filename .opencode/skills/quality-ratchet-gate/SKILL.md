---
name: quality-ratchet-gate
description: Run and maintain ARTEMIS code quality gates including Ruff formatting/linting, the exception and type-ignore quality ratchet (scripts/quality_ratchet.py and .quality-baseline.json), Pyright core typechecking (pyright-core.json), and dependency lockfile verification. Use before completing any code change or when reducing technical debt.
compatibility: opencode
license: Apache-2.0
---

# ARTEMIS Quality Ratchet & CI Gate Workflow

Every pull request in ARTEMIS is gated by five deterministic static and runtime checks in `.github/workflows/ci.yml`. Use this workflow to verify compliance and ratchet down technical debt.

## 1. Run the Complete Gate Sequence

Execute these commands from the repository root:

```bash
# 1. Verify lockfiles point exclusively to public PyPI & npm registries
python scripts/check_dependency_sources.py

# 2. Check formatting and lint rules (including TID252 no-relative-imports)
uv run ruff format --check .
uv run ruff check .

# 3. Check exception-handler and type-ignore debt ratchet
uv run python scripts/quality_ratchet.py

# 4. Type-check protected core modules
uv run pyright --project pyright-core.json

# 5. Run deterministic test suite with 60% minimum coverage gate
uv run pytest tests/unit tests/tools packages/artemis-client/tests -q \
  --cov=artemis --cov=mcp_server --cov=apps/admin_console --cov=third_party \
  --cov-fail-under=60
```

## 2. How the Quality Ratchet Works (`scripts/quality_ratchet.py`)

`scripts/quality_ratchet.py` parses the AST and source text of all `.py` files under `artemis/`, `mcp_server/`, `apps/admin_console/`, and `third_party/` and compares three metrics against `.quality-baseline.json`:

- `broad_exception_handlers`: Count of `except Exception:`, `except BaseException:`, or bare `except:` blocks.
- `silent_broad_exception_handlers`: Count of broad exception handlers whose body is only `pass` (must strictly remain `0`).
- `type_ignore_comments`: Count of `# type: ignore` comments.

### Rules when writing or refactoring code:
1. **Never increase any metric above `.quality-baseline.json`**.
2. **Never write `except Exception: pass`** — always catch narrow exceptions (`(ValueError, KeyError, OSError)`) and log or handle the failure explicitly.
3. **Ratcheting Down Debt**:
   - Inspect current counts anytime with:
     ```bash
     uv run python scripts/quality_ratchet.py --print-current
     ```
   - When your refactoring lowers `broad_exception_handlers` or `type_ignore_comments` below the committed baseline, update `.quality-baseline.json` with the new lower numbers to permanently lock in the improvement.
