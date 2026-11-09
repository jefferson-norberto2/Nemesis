# Testing & ARTEMIS Mobile Mindset Rules

## 1. Test Pyramid & Pytest Markers
The repository separates deterministic CI tests from tests requiring external credentials, cloud services, or physical Android hardware:

- **Default Hermetic Suite (`uv run pytest` / `make test`)**:
  - Runs `tests/unit`, `tests/tools`, and `packages/artemis-client/tests` with `-m "not integration and not e2e and not cloud and not manual and not android"`.
  - Must **never** make real LLM API calls, network requests, or ADB device calls. Use `artemis.llm.fake_model` (`FakeListChatModel`), mock drivers (`artemis/drivers/mock`), and temporary SQLite/filesystem fixtures.
  - Must maintain at least **60% branch/line coverage** across `artemis`, `mcp_server`, `apps/admin_console`, and `third_party`.
- **Marker Discipline (`pyproject.toml`)**:
  - `@pytest.mark.android`: Requires an attached, authorized Android device or emulator.
  - `@pytest.mark.integration`: Spans multiple Artemis components or requires configured LLM credentials.
  - `@pytest.mark.e2e`: End-to-end tests requiring a running Artemis environment.
  - `@pytest.mark.cloud`: Requires the optional `cloud_service` package.
  - `@pytest.mark.manual`: Tests that must only be launched explicitly by a human operator.
  - *Rule*: Every test file in `tests/` must remain safely importable/collectable even when external hardware or optional dependencies are absent.

## 2. Mobile Testing Mindset (ARTEMIS MCP Integration)
When authoring or debugging mobile automation tests (`tests/integration/`, `tests/e2e/`, or user app tests):

1. **Explore Before Authoring Code**:
   - Never guess or hallucinate Android UI hierarchies, resource IDs, or screen transitions.
   - Use the ARTEMIS MCP tools (`mobile_get_device_state`, `mobile_run_task`, `mobile_inspect_trace`) to interactively explore the live application and confirm exact UI states first.
2. **Diagnose First (`mobile_diagnose`)**:
   - If any ARTEMIS MCP tool errors, no device is found, or a task fails to start, call `mobile_diagnose(attempt_fix=true)` first before running manual `adb` commands or retrying `mobile_run_task`.
   - When multiple devices/emulators are connected, ask the user to confirm the target `device_serial`.
3. **Flash vs. Pro Profile Selection**:
   - Choose **`flash`** for straightforward, deterministic UI flows (3–5s/step, unbounded turns with compressed history).
   - Choose **`pro`** when the task needs a persistent Markdown task plan, verified checkpoints (`verification_level`), `[Loop:continuous]` monitoring, or deep ADB/log/video diagnostics.
4. **Latency Compensation (Exploration vs. Authored Test Code)**:
   - During exploration, compensate for LLM step latency (~5s/step for Flash, ~30s/step for Pro) when instructing the agent to wait.
   - In final authored Python/pytest scripts, replace AI latency with explicit, deterministic wait conditions and timeouts.
5. **Dynamic-First, Coordinate-Fallback Locator Pattern**:
   - Prioritize dynamic element locators (resource-id, text, content-desc, accessibility hierarchy) for resilience against layout shifts.
   - Provide verified coordinates from ARTEMIS exploration as a fallback in a `try / except` block when the target framework supports both.
