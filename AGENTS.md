# AGENTS.md — ARTEMIS (Nemesis) Repository Instructions & Rules

Welcome to the **ARTEMIS** repository (`artemis` + `artemis-client` + `mcp_server` + `apps/admin_console` + `apps/showcase_ui`). These instructions apply to all OpenCode agents and subagents working in this workspace.

---

## 1. Repository Architecture Overview

ARTEMIS is an autonomous multimodal AI assistant and testing framework for Android automation. It operates across five primary layers:

1. **Core Agent & Runtime (`artemis/`)**:
   - **Dual Execution Engine**:
     - **Flash Profile (`artemis/agents/flash/`)**: Fast, reactive single-LLM loop (`FlashRunner`, ~3–5s/step) with unbounded turns by default and background visual step summarization (`step_summarizer`). Uses `click_sequence` for transient UI.
     - **Pro Profile (`artemis/graph/`, `artemis/agents/`)**: LangGraph multi-node state machine (`PlannerNode`, `perception_node`, `OperatorNode`, `execution_check_node`, `ValidatorNode`, `Checker`, `SummarizerNode`, `Outputter`). Features a pre-execution Safety Net (XML-first, pixel fallback), fast-action bursts, self-healing execution incidents, and optimistic async checkpoint verification.
   - **Shared Memory & Transcript Ledger (`artemis/memory/`)**: Organizes session context into 4 regions — **S** (Stable prefix), **F** (Frozen history / L2-L3 chunk capsules), **A** (Active window with shallow text scrub edge and occupancy-gated screenshot scrub edge), and **T** (Current tail). Uses session-relative `T+mm:ss` timestamps.
   - **Canonical Action Manifest (`artemis/mcp/action_specs.py`)**: Single source of truth defining all device actions across three dialects: `operator` (LangChain shell + Flash JSON declaration accepting element index `int` or `[x, y]` coordinates), `declaration` (JSON-only for Flash-exclusive tools like `click_sequence`), and `wire` (low-level MCP actuator signature).
   - **LLM Routing & Reliability (`artemis/llm/`)**: Multi-provider router (Google Gemini, Vertex AI, OpenAI, Anthropic) configured via `config/artemis.jsonc`. Note: `object_detector` requires an Embodied Reasoning model (`gemini-robotics-er-2-preview`) for sub-pixel coordinate grounding.
   - **Device Drivers & Controllers (`artemis/drivers/`, `artemis/controllers/`, `artemis/clients/`)**: Android ADB, UIAutomator2, and the on-device `artemis-accessibility-helper` service with automatic fallback.

2. **Universal MCP Server (`mcp_server/`)**:
   - FastMCP server exposing 5 tools to AI IDEs: `mobile_run_task`, `mobile_manage_task`, `mobile_get_device_state`, `mobile_inspect_trace`, and `mobile_diagnose`.
   - Includes multi-channel background task completion notifiers (`mcp_server/notifiers/`: AgentAPI, Desktop toast, Webhook, Script hook, File audit) and shares `artemis/runtime/trace_store.py`.

3. **Web Console & Frontend (`apps/`)**:
   - `apps/admin_console/`: FastAPI server (`artemis-admin` / `uv run artemis ui`) providing REST APIs (`/api/*`), SSE/WebSocket live agent thought streaming (`/stream/events`), replay manager, SQLite session/trace repositories, and `SameOriginBoundaryMiddleware`.
   - `apps/showcase_ui/`: Angular 19 + SCSS dual-pane glassmorphic workspace frontend, bundled into `artemis/resources/showcase_ui` for wheel distribution.

4. **Workspace Packages (`packages/`)**:
   - `packages/artemis-client/`: Zero-runtime-dependency Python SDK (`import artemis_client`) using only the Python standard library to communicate with a remote Artemis daemon over HTTP.
   - `packages/artemis-accessibility-helper/`: On-device Android APK source for reading accessibility hierarchies without seizing the `UiAutomation` connection.

5. **Third-Party Boundary (`third_party/mobile_use/`)**:
   - Upstream Apache-2.0 code derived from Minitap's `mobile-use`. Cross-package imports between `artemis` and `third_party.mobile_use` are strictly policed by `tests/unit/test_third_party_boundary.py`, and legacy import paths are aliased via `artemis/_legacy_imports.py`.

---

## 2. Non-Negotiable Architectural & Coding Rules

### 2.1 Python Style & Imports (Enforced by Ruff)
- **Python Version**: Target **Python 3.12+** (`requires-python = ">=3.12"`).
- **Absolute Imports Only**: Relative imports are **strictly banned** (`[tool.ruff.lint.flake8-tidy-imports] ban-relative-imports = "all"`). Always use full absolute imports from `artemis.*`, `mcp_server.*`, `apps.admin_console.*`, `third_party.mobile_use.*`, or `artemis_client.*`.
- **Formatting**: Line length `100`, 4-space indentation, double quotes (`"`). Run `uv run ruff format --check .` and `uv run ruff check .`.
- **License Header**: New first-party Python files must include the standard `# Copyright 2026 Google LLC` Apache 2.0 header and **must never** include third-party attribution markers (`derived from`, `originally from`, `minitap`) outside `third_party/`.

### 2.2 Quality Ratchet (Enforced by `scripts/quality_ratchet.py`)
- The CI ratchet scans `artemis/`, `mcp_server/`, `apps/admin_console/`, and `third_party/` against `.quality-baseline.json`:
  - **Zero silent broad exception handlers**: Never write `except Exception: pass`, `except BaseException: pass`, or bare `except: pass` (`silent_broad_exception_handlers` must remain `0`).
  - **No net increase in broad exception handlers**: Avoid adding `except Exception:` / `except BaseException:` / bare `except:`. Catch specific exception types instead.
  - **No net increase in `# type: ignore` comments**: Fix types properly rather than suppressing Pyright/Mypy.
  - When refactoring removes existing broad exceptions or `# type: ignore` comments, update `.quality-baseline.json` downward to lock in the improvement.

### 2.3 Protected Type-Checked Modules (`pyright-core.json`)
- Run `uv run pyright --project pyright-core.json` whenever touching any of the core type-protected paths:
  - `artemis/graph/state.py`
  - `artemis/graph/visibility.py`
  - `artemis/runtime/adb_endpoint.py`
  - `artemis/runtime/process_probe.py`
  - `artemis/mcp/action_types.py`
  - `artemis/data_engine/models.py`
  - `artemis/agents/explorer/native_runner.py`
  - `artemis/agents/explorer/perception_tools.py`
  - `mcp_server/utils/device_utils.py`
  - `packages/artemis-client/src/artemis_client`

### 2.4 LangGraph State & Visibility Invariants
- `State` (`artemis/graph/state.py`) uses `ConfigDict(extra="forbid")`. Every state channel must be explicitly declared on `State`.
- Every graph node wraps `state = strict_state(state, "<node_name>")` (`artemis/graph/visibility.py`). Whenever a node or one of its `InjectedState` tools reads or writes a `State` field, that field **must** be declared in `NODE_VISIBILITY["<node_name>"]`. Tests run with `ARTEMIS_STRICT_STATE=1` and will raise `VisibilityError` on undeclared reads or writes.

### 2.5 Canonical Action Specs (`artemis/mcp/action_specs.py`)
- Never hand-roll separate tool schemas for the Pro Operator, FlashRunner, and Action MCP Server. Define or update device actions in `ACTION_SPECS` inside `artemis/mcp/action_specs.py` so `operator`, `declaration`, and `wire` dialects stay in lockstep, and verify with `uv run pytest tests/unit/mcp/test_action_specs.py`.
- Any coordinate target `[x, y]` in the agent dialect requires `target_description` (or `target_descriptions` for `click_sequence`).

### 2.6 Package Boundary Rules
- **`artemis` ↔ `third_party/mobile_use`**: Never import private (`_`-prefixed) symbols across the `artemis` and `third_party.mobile_use` boundary. If moving a module between them, register the alias in `artemis/_legacy_imports.py` and run `uv run pytest tests/unit/test_third_party_boundary.py`.
- **`packages/artemis-client`**: Must maintain **zero runtime dependencies** (stdlib only: `urllib`, `json`, `asyncio`, `dataclasses`, `typing`). Never import `artemis`, `pydantic`, `httpx`, `requests`, or `adbutils` inside `packages/artemis-client/src/artemis_client/`.
- **Public Dependency Registries**: `uv.lock` and `apps/showcase_ui/package-lock.json` must only reference public `pypi.org` / `files.pythonhosted.org` and `registry.npmjs.org` URLs (enforced by `python scripts/check_dependency_sources.py`).

---

## 3. Essential Commands

- **Run hermetic unit & tool test suite (CI default)**: `uv run pytest` (or `make test`)
- **Run linter & formatter check**: `uv run ruff format --check . && uv run ruff check .`
- **Run quality ratchet**: `uv run python scripts/quality_ratchet.py`
- **Run core typecheck**: `uv run pyright --project pyright-core.json`
- **Run dependency source check**: `python scripts/check_dependency_sources.py`
- **Run integration tests**: `make test-integration`
- **Run Android device / E2E tests**: `make test-device`
- **Run frontend tests & build**: `cd apps/showcase_ui && npm test -- --watch=false --browsers=ChromeHeadless && npm run build`
