---
name: langgraph-node-state
description: Add or modify LangGraph nodes, State channels (artemis/graph/state.py), and per-node visibility manifests (artemis/graph/visibility.py) in ARTEMIS Pro. Use when touching graph orchestration, node inputs/outputs, InjectedState tools, or TranscriptLedger integration.
compatibility: opencode
license: Apache-2.0
---

# LangGraph State & Node Visibility Workflow

ARTEMIS Pro uses a strict, visibility-policed LangGraph state machine (`artemis/graph/`) to prevent ghost reads and ghost writes across multi-agent turns.

## 1. Dual Protection Mechanism

1. **No Ghost Writes (`artemis/graph/state.py`)**:
   - `State` inherits from `pydantic.BaseModel` with `model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")`.
   - Constructing `State` or returning a state update dict with an undeclared key immediately fails validation.
   - Cross-turn fields use explicit reducers such as `take_last` or `sticky_or` (for latched flags like `user_stop_requested`).
2. **No Ghost Reads (`artemis/graph/visibility.py`)**:
   - Every graph node wraps its incoming state via `state = strict_state(state, "<node_name>")`.
   - `NODE_VISIBILITY` maps each node name (`perception`, `planner`, `operator`, `execution_check`, `validator`, `exit_settlement`, `summarizer`) to `NodeVisibility(reads=frozenset(...), writes=frozenset(...))`.
   - When `ARTEMIS_STRICT_STATE=1` is active (in tests), reading or writing any attribute outside `NODE_VISIBILITY[node_name].visible` raises `VisibilityError`.
   - **Important**: Tools invoked inside a node's turn via `InjectedState` count toward that node's `reads` set!

## 2. Step-by-Step Workflow for Modifying Graph State or Nodes

1. **Declare Field on `State` (`artemis/graph/state.py`)**:
   - Add the typed field with `Annotated[Type, "Description", reducer]` and a sensible default.
   - Group the field under the appropriate section (`Control plane`, `Perception`, `Turn products`, etc.).
2. **Update `NODE_VISIBILITY` (`artemis/graph/visibility.py`)**:
   - Add the field name to `reads` for every node (or `InjectedState` tool) that reads it, and to `writes` for every node that returns it in its state update dictionary.
3. **Wrap New Nodes with `strict_state` (`artemis/graph/graph.py`)**:
   - At the entry of any new graph node function, call:
     ```python
     state = strict_state(state, "your_node_name")
     ```
   - Register `"your_node_name"` in `NODE_VISIBILITY`.
4. **Preserve Transcript Ledger Invariants (`artemis/memory/transcript.py`)**:
   - If the state change injects feedback into the Operator prompt (like `operator_feedback` or `open_incident`), append it to the per-turn observation tail (**T**) or mark transient blocks with `mark_ephemeral(message, indices)` (`EPHEMERAL_BLOCKS_KEY`) so the stable prefix (**S**) and committed active window (**A**) remain byte-identical for prompt caching.
5. **Verify with Strict State & Pyright**:
   ```bash
   uv run pyright --project pyright-core.json
   ARTEMIS_STRICT_STATE=1 uv run pytest tests/unit/graph/
   ```
