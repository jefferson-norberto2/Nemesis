# Code Quality, Typing & Ratchet Rules (ARTEMIS)

## 1. Ruff Linting & Formatting Standards
- **Target**: Python 3.12+ (`target-version = "py312"`), line length `100`, double quotes.
- **Enabled Rules**: `E` (pycodestyle), `F` (Pyflakes), `TID` (flake8-tidy-imports), `UP` (pyupgrade).
- **No Relative Imports (`TID252`)**: `ban-relative-imports = "all"` is enforced across the entire repository. Always write explicit absolute imports.
- **Verification**:
  ```bash
  uv run ruff format --check .
  uv run ruff check .
  ```

## 2. Quality Debt Ratchet (`scripts/quality_ratchet.py`)
CI enforces a strict non-regression ratchet over `artemis/`, `mcp_server/`, `apps/admin_console/`, and `third_party/` compared against `.quality-baseline.json`:
1. **`silent_broad_exception_handlers` (Baseline: `0`)**:
   - Never write `except Exception: pass`, `except BaseException: pass`, or `except: pass`.
   - Every exception handler must either catch a narrow exception, log diagnostic context, or re-raise/handle the error meaningfully.
2. **`broad_exception_handlers`**:
   - Do not introduce new `except Exception:`, `except BaseException:`, or bare `except:` blocks. Catch concrete exception classes (e.g., ` (OSError, ValueError, RuntimeError)` or domain-specific exceptions).
3. **`type_ignore_comments`**:
   - Do not add new `# type: ignore` comments. Use proper type annotations, `typing.cast`, protocol definitions, or type guards.
4. **Ratcheting Down**:
   - When a refactoring reduces `broad_exception_handlers` or `type_ignore_comments`, run `uv run python scripts/quality_ratchet.py --print-current` and lower the counts in `.quality-baseline.json`.

## 3. Core Static Type Checking (`pyright-core.json`)
- Pyright is enforced in CI via `uv run pyright --project pyright-core.json`.
- Any modification to files listed in `pyright-core.json` (or imported signatures they depend on) must pass Pyright with zero errors.
- Prefer modern Python 3.12+ typing syntax (`list[str]`, `dict[str, Any]`, `X | None`, `type Alias = ...`).

## 4. Dependency Lockfile Hygiene (`scripts/check_dependency_sources.py`)
- All Python packages in `uv.lock` (except workspace editable members `artemis` and `artemis-client`) must resolve from `https://pypi.org/simple` with wheel/sdist artifacts on `files.pythonhosted.org`.
- All frontend packages in `apps/showcase_ui/package-lock.json` must resolve from `https://registry.npmjs.org`.
- Always verify lockfile changes with `python scripts/check_dependency_sources.py`.
