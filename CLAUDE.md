# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is the **Baytrac** Gundi v2 integration — a FastAPI service that receives and processes webhooks or pull-based actions from Baytrac and forwards transformed data to the [Gundi](https://gundiservice.org) platform.

This repo was forked from the Gundi integration template. The core framework lives in `app/services/`, `app/webhooks/core.py`, and `app/actions/core.py`. **Integration-specific logic goes in the files listed under "Implementation files" below.**

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run a single test
pytest app/services/tests/test_webhooks.py::test_name -v

# Run with coverage
pytest --tb=short -v

# Local server
uvicorn app.main:app --reload --port 8080

# Recompile dependencies after editing requirements.in
pip-compile --output-file=requirements.txt requirements-base.in requirements-dev.in requirements.in

# Docker local dev (API docs at http://localhost:8080/docs)
cd local && docker compose up --build
```

## Implementation files

These are the files to edit when implementing Baytrac-specific behavior. All are currently empty stubs:

| File | Purpose |
|------|---------|
| `app/webhooks/handlers.py` | `webhook_handler()` function — receives parsed payload, sends to Gundi |
| `app/webhooks/configurations.py` | Pydantic models for webhook payload and config |
| `app/actions/handlers.py` | Pull/push action handlers |
| `app/actions/configurations.py` | Pydantic config models for actions |
| `app/settings/integration.py` | Baytrac-specific env var settings |
| `requirements.in` | Baytrac-specific Python dependencies |

## Architecture

### Request flow (webhooks)

1. `POST /webhooks` → `app/routers/webhooks.py` → `app/services/webhooks.py::process_webhook()`
2. Integration resolved from `x-consumer-username` (Kong) or `x-gundi-integration-id` header, or `integration_id` query param
3. `app/webhooks/core.py::get_webhook_handler()` inspects type annotations on `webhook_handler` to determine payload/config models
4. If `GenericJsonPayload` + `DynamicSchemaConfig`: Pydantic model built at runtime from JSON schema stored in Gundi portal
5. If `GenericJsonTransformConfig`: applies `jq_filter` and routes to `obv` or `ev` output type
6. Transformed data sent via `app/services/gundi.py`

### Request flow (actions via PubSub)

`POST /` → base64 decode GCP PubSub message → `app/services/action_runner.py::execute_action()` → `app/actions/handlers.py`

Use `@crontab_schedule("0 */4 * * *")` decorator on action handlers to schedule them, or register in `app/register.py`.

### Key framework modules (do not edit)

| Path | Purpose |
|------|---------|
| `app/webhooks/core.py` | Base classes: `WebhookPayload`, `WebhookConfiguration`, `GenericJsonTransformConfig`, `DynamicSchemaConfig`, `HexStringConfig` |
| `app/services/webhooks.py` | Orchestrates webhook processing and error publishing |
| `app/services/gundi.py` | `send_observations_to_gundi()` / `send_events_to_gundi()` |
| `app/services/activity_logger.py` | `@activity_logger()` / `@webhook_activity_logger()` decorators; `log_activity()` |
| `app/services/config_manager.py` | Fetches/caches integration config from Gundi (Redis-backed, 60s TTL) |
| `app/services/utils.py` | `FieldWithUIOptions`, `UIOptions`, `GlobalUISchemaOptions` for portal UI customization |
| `app/conftest.py` | Shared pytest fixtures (mock integrations, handlers, headers, payloads) |

### Webhook configuration modes

- **Fixed schema**: annotate `payload` with a `WebhookPayload` subclass → strict Pydantic validation
- **Dynamic schema**: annotate `payload` with `GenericJsonPayload` + config with `DynamicSchemaConfig` → model built at runtime from Gundi portal JSON schema
- **JQ transform**: annotate config with `GenericJsonTransformConfig` → applies `jq_filter`, routes via `output_type` (`obv`/`ev`)
- **Hex string**: use `HexStringPayload` + `HexStringConfig` for binary data encoded as hex; parsed via Python `struct` format strings

## Testing

Tests use `pytest-asyncio` and `pytest-mock`. All external services (Gundi API, PubSub, Redis) are mocked. Test files live in `app/services/tests/`. When adding webhook handler tests, model them on existing test files in that directory and use fixtures from `app/conftest.py`.

## Key env vars

| Variable | Purpose |
|----------|---------|
| `GUNDI_API_BASE_URL` | Gundi platform API endpoint |
| `KEYCLOAK_CLIENT_SECRET` | Auth secret (required for local dev against stage) |
| `INTEGRATION_TYPE_SLUG` | Unique identifier for this integration type |
| `INTEGRATION_SERVICE_URL` | Public URL of this service |
| `REGISTER_ON_START` | Set `true` to auto-register with Gundi on startup |
| `REDIS_HOST` / `REDIS_PORT` | Config cache and state store |
| `INTEGRATION_EVENTS_TOPIC` | GCP PubSub topic for activity/error events |
| `PROCESS_WEBHOOKS_IN_BACKGROUND` | Default `true`; processes webhooks async |
