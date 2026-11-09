---
name: mobile-mcp-testing
description: Explore Android apps via ARTEMIS MCP tools (mobile_diagnose, mobile_run_task, mobile_get_device_state, mobile_inspect_trace) and author resilient Python/pytest mobile automation tests using the Dynamic-First, Coordinate-Fallback pattern. Use when testing on Android devices/emulators or writing integration/E2E tests.
compatibility: opencode
license: Apache-2.0
---

# ARTEMIS Mobile MCP Exploration & Test Authoring Workflow

Never guess Android UI hierarchies, resource IDs, or screen transitions. Always verify device behavior interactively through the ARTEMIS MCP server before authoring test code.

## 1. Environment & Device Diagnosis (`mobile_diagnose`)

1. **Diagnose First on Any Error**:
   - If no device is found or a task fails to start, call `mobile_diagnose(attempt_fix=true)` first.
   - Follow `next_steps` in dependency order: run `Run:` shell lines locally, and relay `Guidance:` lines (e.g., unlocking the screen or accepting the USB debugging prompt) verbatim to the user.
   - Use `probe_device=true` (~20s) if a device appears connected in ADB but screenshot/UIAutomator capture fails, or `verify_credentials=true` (~12s) if LLM API auth fails.
2. **Multi-Device Selection**:
   - Check connected devices via `mobile_get_device_state` or `adb devices -l`.
   - When multiple devices or emulators are connected, **always ask the user** to confirm which `device_serial` to target before launching tasks.

## 2. Interactive Exploration (`Flash` vs. `Pro`)

Use `mobile_run_task` and `mobile_get_device_state` to discover the exact UI flow:

- **Choose `Flash` (`profile="flash"`)**:
  - Best for straightforward, deterministic navigation and UI discovery (~3–5s per step, unbounded turns with compressed history).
- **Choose `Pro` (`profile="pro"`)**:
  - Best for complex multi-branch flows, tasks requiring verified checkpoints (`verification_level="checkpoints"` or `"strict"`), `[Loop:continuous]` monitoring, or ADB/log/video root-cause analysis (~15–40s per step).
- **Compensate for Exploration Latency**:
  - When a task requires waiting (e.g., 30s for a media ad or timer), subtract natural model step latency during exploration (~5s/step for Flash → ask to wait ~25s; ~30s/step for Pro → natural pipeline delay often suffices).
- **Inspect the Trace**:
  - Call `mobile_inspect_trace(trace_id=...)` to extract the exact observed `resource-id`, `text`, `content-desc`, bounds, and fallback coordinates recorded on each step.

## 3. Authoring Resilient Test Code (Dynamic-First, Coordinate-Fallback)

When translating an explored trace into a runnable test under `tests/integration/` or `tests/e2e/`:

1. **Pytest Markers & Safe Collection**:
   - Decorate device tests with `@pytest.mark.android` (and `@pytest.mark.integration` or `@pytest.mark.e2e`).
   - Ensure the test module can be imported and collected by `uv run pytest --collect-only` even when no Android device is attached.
2. **Dynamic-First, Coordinate-Fallback Pattern**:
   - Attempt interaction using dynamic locators (`resource-id`, exact text, accessibility description) first so the test survives layout and resolution shifts.
   - Catch locator failures and fall back to the verified coordinates from your ARTEMIS exploration trace:
     ```python
     try:
         device(resourceId="com.android.settings:id/battery_summary").click(timeout=5.0)
     except Exception:
         # Fallback to verified coordinates from ARTEMIS trace
         device.click(540, 820)
     ```
3. **Deterministic Waits**:
   - Replace AI exploration turn latency with explicit wait conditions (e.g., `wait_for_exists`, polling with timeout) in the authored test script.
