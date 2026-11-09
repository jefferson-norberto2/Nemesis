# Architecture & Boundary Rules (ARTEMIS)

## 1. Dual Execution Architecture (Flash vs. Pro)
- **Flash Profile (`artemis/agents/flash/`)**:
  - Reactive single-LLM loop (`FlashRunner`) without LangGraph node orchestration.
  - Uses `StepMemoryService` and `TranscriptLedger` for asynchronous visual summarization and history compression (`agent.flash.step_summarizer`).
  - Supports `click_sequence` for multi-tap bursts on transient UI.
  - Does **not** have a Planner, pre-execution Safety Net, Checker, or ADB shell tool.
- **Pro Profile (`artemis/graph/graph.py` & `artemis/agents/`)**:
  - Multi-agent LangGraph state machine (`PlannerNode` → `perception_node` → `OperatorNode` → `execution_check_node` → `ValidatorNode` → `Checker` / `exit_settlement_node` → `SummarizerNode` / `Outputter`).
  - Single actions pass through the Validator's pre-execution **Safety Net** (XML-first, pixel fallback). Multi-action turns execute as **fast-action bursts** without the safety net to beat turn latency.
  - Blocked or failed actions open an **execution incident** (`open_incident`, `last_closed_incident` on `State`) that remains in the Operator's context until a subsequent action succeeds.

## 2. LangGraph `State` & `NODE_VISIBILITY` Discipline
- `State` in `artemis/graph/state.py` enforces `extra="forbid"`. Never attach ad-hoc attributes to `state`.
- `NODE_VISIBILITY` in `artemis/graph/visibility.py` defines the exact `reads` and `writes` frozensets for each graph node (`perception`, `planner`, `operator`, `execution_check`, `validator`, `exit_settlement`, `summarizer`).
- Any change to what a node (or an `InjectedState` tool invoked inside that node) reads or writes **must** update `NODE_VISIBILITY` and pass `ARTEMIS_STRICT_STATE=1 uv run pytest tests/unit/graph/`.

## 3. Canonical Action Specification (`artemis/mcp/action_specs.py`)
- All mobile device actions are defined once in `ACTION_SPECS` in `artemis/mcp/action_specs.py`.
- Keep the three dialects (`operator`, `declaration`, `wire`) synchronized.
- Any deliberate semantic difference between the agent dialect and the wire dialect must be documented in the `ActionSpec.differences` field.
- Always run `uv run pytest tests/unit/mcp/test_action_specs.py` after modifying action schemas or descriptions.

## 4. Session Transcript Ledger (`artemis/memory/transcript.py`)
- Prompt history is structured into four immutable/append-only regions:
  - **S (Stable prefix)**: Byte-identical static system prompt across the entire session (preserves prompt cache hits).
  - **F (Frozen history)**: Restored history and L2/L3 compressed chunk capsules (`artemis/memory/chunking.py`).
  - **A (Active window)**: Append-only committed turns. Scrubbing happens at two edges: shallow text scrub edge (`xml_scrub_depth: 1`, stripping stale `[n]` UI element lists, plan recitations, and `ephemeral_blocks`) and screenshot scrub edge (`image_scrub_depth`, replacing old screenshots in-place with visual summaries). Never reorder or delete messages in `A` so tool-call/response pairs stay valid.
  - **T (Current tail)**: Fresh per-turn observation built by the operator.
- All transcript timestamps must use session-relative `T+mm:ss` (`format_session_offset`).

## 5. Strict Package Boundaries
- **`artemis` ↔ `third_party/mobile_use`**:
  - Every symbol imported across `artemis` (including `apps/admin_console` and `mcp_server`) and `third_party/mobile_use` must be public (no leading `_`).
  - Moving a module from `artemis` to `third_party/mobile_use` requires registering the old path in `LEGACY_MODULES` inside `artemis/_legacy_imports.py`.
  - First-party files outside `third_party/` must never contain upstream attribution comments (`derived from`, `originally from`, `minitap`).
- **`packages/artemis-client`**:
  - Must have **zero third-party runtime dependencies** (`dependencies = []` in `packages/artemis-client/pyproject.toml`).
  - Must never import from `artemis`, `mcp_server`, or external libraries like `httpx`, `requests`, or `pydantic`.
  - Must preserve backward compatibility with `/api/*` and capability negotiation with `/api/v1/capabilities`.
- **`apps/admin_console` Security Boundary**:
  - `SameOriginBoundaryMiddleware` protects local administration endpoints from cross-origin browser requests and DNS rebinding. Never add permissive wildcard CORS middleware to `apps/admin_console/server.py`.
