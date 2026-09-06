# Roadmap / 排期评估

These are proposed milestones and engineering estimates, not calendar commitments or background jobs. No webhook or MCP code ships in the initial release.

| Order | Proposal | Estimated focused engineering effort | Dependencies |
|---|---|---|---|
| 1 | Reliable HTTP/HTTPS event webhooks | 3–5 person-days | Stable event IDs, persistent delivery queue and site tests |
| 2 | Local MCP adapter: read-only first, optional controls | 3–5 person-days | Stable JSON API, scoped adapter policy and client compatibility tests |
| 3 | Remote MCP over Streamable HTTP | Additional 2–4 person-days | HTTPS deployment, authentication design and selected client support |

Allow additional calendar time for unattended soak tests, site access and maintainer review. Client-specific integration differences may change estimates. Webhooks are the first priority because they support notifications and general home automation with fewer dependencies; a local MCP adapter can follow without waiting for public HTTPS.

## Webhook proposal

On incoming calls and selected lifecycle events, enqueue a versioned JSON event for configured HTTP/HTTPS endpoints. Delivery must happen outside the intercom control thread. Initial scope: endpoint create/edit/disable, event selection, explicit test delivery, stable event ID, timestamp, local panel alias, and call correlation ID. Residence information is opt-in; no audio/video is attached by default.

Use a SQLite outbox, bounded queue, timeout, exponential backoff with jitter, delivery history, and dead-letter/manual retry. Delivery is at least once, not exactly once; receivers deduplicate by event ID. Consider only 2xx successful, honor bounded Retry-After for 429/503, retry network failures/5xx and mark permanent 4xx failures. A failing endpoint must not delay answering or door opening.

Support optional HMAC-SHA256 signatures over the timestamp and exact body, plus configurable authentication headers stored privately and never copied to logs. Validate HTTPS certificates. Endpoints must be explicitly configured by an authenticated administrator; restrict schemes to HTTP/HTTPS, validate ports/hosts, do not follow redirects by default, and keep LAN endpoints possible without enabling arbitrary event-supplied URLs.

Acceptance: call events reach local HTTP and trusted HTTPS receivers; retry/restart/offline/duplicate behavior is deterministic; secrets are absent from history; a blocked endpoint cannot block the intercom loop; configuration and test-send are available in the web UI. Unit tests should use local servers and synthetic events; real external delivery is opt-in.

Suggested breakdown: event contract/outbox 1 day, worker/security rules 1–2 days, settings/history UI 0.5–1 day, tests/docs/soak setup 0.5–1 day.

## MCP proposal

Build a separate adapter around the gateway API instead of adding AI-client code to SIP/ENet processing. Start with local stdio, using a private configuration file or environment variable for the gateway URL and API token. Add remote Streamable HTTP only after the deployment and authentication prerequisites are ready. Protocol-version and SDK selection must be revisited when implementation starts. See the official [transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).

Initial tools: get_status, list_recent_events and get_auto_open_policy. Optional control tools: preview, hangup, set_auto_open_policy and open_door. Mutating tools should be disabled by default, explicitly enabled per adapter configuration and constrained to configured panels/active calls. Actual authorization must be enforced in code, not inferred from tool annotations or supplied event text. Keep credentials, password reset, shell execution and arbitrary floor/address control outside the tool surface.

Opening should expose the current call context and use idempotent request IDs; distinguish queued, confirmed and unknown results. Rate-limit mutations, audit tool invocations without secrets and provide bounded event pagination. The adapter must never treat doorbell names, log text or webhook payloads as instructions to operate the lock.

Acceptance: read-only stdio operation with at least one selected client, then explicit compatibility checks for Hermes Agent, OpenClaw and Codex where supported; mutation-disabled and wrong-call tests; token revocation; disconnected gateway handling; JSON schemas and clear tool descriptions. The proposal does not claim these clients are already compatible.

Suggested breakdown: read-only adapter 1 day, opt-in controls and context guards 1–2 days, client checks/tests/docs 1–2 days. Remote transport is separately estimated above and includes its own authentication and deployment tests.
