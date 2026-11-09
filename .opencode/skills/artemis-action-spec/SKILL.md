---
name: artemis-action-spec
description: Add or modify mobile device actions in ARTEMIS across the canonical action manifest (artemis/mcp/action_specs.py, action_manifest.py, action_names.py, action_executor.py) while keeping operator, declaration, and wire dialects synchronized. Use when creating or changing device tools like click, swipe, input_text, or click_sequence.
compatibility: opencode
license: Apache-2.0
---

# Canonical Device Action Specification Workflow

In ARTEMIS, every mobile device action is defined in a single canonical manifest (`artemis/mcp/action_specs.py`) so that the Pro `OperatorNode` LangChain shells, the `FlashRunner` JSON `ToolDeclaration`s, and the MCP wire actuator tools never drift apart.

## 1. Understand the Three Dialects (`artemis/mcp/action_specs.py`)

Each entry in `ACTION_SPECS` is an `ActionSpec(name, operator, declaration, wire, differences)`:

1. **`operator` (`OperatorDialect`)**:
   - The agent-facing dialect shared by both **Pro Operator** (bound as a declaration-only LangChain shell via `operator_shell_tool`) and **FlashRunner** (projected onto a JSON `ToolDeclaration` via `tool_declaration`).
   - Targets accept `IndexOrCoords` (`int | list[int]`): either an integer element index `[n]` from `Visible UI Elements` or normalized `[x, y]` coordinates (`0..1000`).
   - Whenever a target accepts coordinates, include `ParamSpec("target_description", str, _TARGET_DESCRIPTION, required=False)` so bare coordinates are always accompanied by the model's statement of what it is aiming at.
2. **`declaration` (`DeclarationDialect`)**:
   - JSON-only agent dialect used **only** for actions that have no Pro Operator shell (e.g., `click_sequence`, which is exposed exclusively to `FlashRunner`).
3. **`wire` (`WireDialect`)**:
   - The low-level MCP actuator tool served by `artemis/mcp/action_server.py`.
   - Uses normalized coordinates (`int`), millisecond durations, and no element-index addressing sugar.
   - `McpActionExecutor` (`artemis/mcp/action_executor.py`) resolves element indices against `indexed_elements` and lowers the agent call onto the `wire` dialect.

## 2. Step-by-Step Modification Checklist

1. **Register Action Name (`artemis/mcp/action_names.py` & `artemis/mcp/action_manifest.py`)**:
   - Add the canonical action constant in `artemis/mcp/action_names.py`.
   - Classify the action in `artemis/mcp/action_manifest.py` (required vs. optional vs. internal).
2. **Define the `ActionSpec` (`artemis/mcp/action_specs.py`)**:
   - Add or update the `ActionSpec` in `ACTION_SPECS`.
   - If the action is exposed to the Pro Operator, include it in `OPERATOR_SHELL_ORDER`.
   - Document any intentional semantic divergence between agent and wire dialects in `differences="..."`.
3. **Wire Actuator & Executor (`artemis/mcp/actuators/` & `artemis/mcp/action_executor.py`)**:
   - Implement the underlying device actuator method if adding a new hardware primitive.
   - Update `McpActionExecutor` in `artemis/mcp/action_executor.py` if custom index-to-coordinate lowering or pre-execution safety net handling is required.
4. **Verify Dialect Parity & Type Safety**:
   - Run the action surface contract tests (including snapshot/schema parity checks):
     ```bash
     uv run pytest tests/unit/mcp/test_action_specs.py tests/unit/mcp/
     ```
   - Run Pyright on core action types:
     ```bash
     uv run pyright --project pyright-core.json
     ```
