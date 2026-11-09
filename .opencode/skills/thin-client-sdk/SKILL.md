---
name: thin-client-sdk
description: Develop and maintain the zero-dependency artemis-client remote Python SDK (packages/artemis-client) and its compatibility with apps/admin_console server endpoints. Use when modifying packages/artemis-client or remote task/session APIs.
compatibility: opencode
license: Apache-2.0
---

# Artemis Thin Client SDK (`artemis-client`) Workflow

`packages/artemis-client` (`import artemis_client`) is the lightweight remote Python SDK installed on developer or CI machines to communicate with a remote Artemis daemon over HTTP.

## 1. Strict Architectural Constraints (`packages/artemis-client/DESIGN.md`)

1. **Zero Runtime Dependencies**:
   - `packages/artemis-client/pyproject.toml` must keep `dependencies = []`.
   - Use **only** the Python 3.12+ standard library (`urllib.request`, `urllib.error`, `urllib.parse`, `json`, `asyncio`, `dataclasses`, `uuid`, `typing`).
   - Never import `artemis`, `mcp_server`, `pydantic`, `httpx`, `requests`, `adbutils`, or `uiautomator2` inside `packages/artemis-client/src/artemis_client/`.
2. **No Local Daemon Spawning**:
   - The thin client owns HTTP request modeling, status polling, capability negotiation, error normalization, and result dataclasses. It must never attempt to launch a local Artemis server or invoke `adb`.
3. **Idempotent Task Submission**:
   - `submit()` generates a client-side UUID (`task_id`) and sends it as `session_id` to the server so network retries never spawn duplicate tasks.
   - While a task is queued in memory before appearing in the session database, state is reconstructed from `queue` and `active_tasks` in `/api/status`.
4. **Forward & Backward Compatibility**:
   - Preserve compatibility with Phase 1 administration endpoints (`/api/run`, `/api/sessions/{session_id}`, `/api/status`, `/api/stop`, `/api/devices`, `/api/system/readiness`) and Phase 2 versioned endpoints (`/api/v1/*`).
   - Ignore unknown response fields in typed dataclasses while preserving the raw payload in each model's `.raw` attribute.
   - Never persist bearer tokens to disk; accept tokens only via constructor arguments or environment variables (`ARTEMIS_TOKEN`).

## 2. Verification Steps

Whenever modifying `packages/artemis-client` or `apps/admin_console/routers/`:

```bash
# 1. Type-check the thin client (included in pyright-core.json)
uv run pyright --project pyright-core.json

# 2. Run thin client unit & contract tests
uv run pytest packages/artemis-client/tests tests/unit/test_sdk.py

# 3. Verify wheel build isolation
uv build --package artemis-client --wheel --out-dir dist
```
